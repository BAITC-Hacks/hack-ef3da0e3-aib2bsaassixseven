"""Bounded multipart upload validation before a meeting becomes visible."""

import json
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path
from typing import cast

from fastapi import Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.models.meeting import MeetingMetadata
from app.services.artifact_store import LocalArtifactStore

MAX_AUDIO_BYTES = 100 * 1024 * 1024
MAX_METADATA_BYTES = 16 * 1024
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".webm"}


class UploadError(Exception):
    def __init__(self, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code


class BoundedMeetingParser(MultiPartParser):
    def __init__(self, request: Request) -> None:
        super().__init__(
            request.headers,
            request.stream(),
            max_files=1,
            max_fields=1,
            max_part_size=MAX_METADATA_BYTES,
        )
        self.audio_bytes = 0
        self.seen: set[str] = set()

    def on_headers_finished(self) -> None:
        super().on_headers_finished()
        part = self._current_part
        name = part.field_name
        if name not in {"audio", "metadata"} or name in self.seen:
            raise UploadError(422, "invalid_request")
        self.seen.add(name)
        headers = dict(part.item_headers)
        if name == "audio":
            if part.file is None:
                raise UploadError(422, "invalid_request")
        elif (
            part.file is not None
            or headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
            != b"application/json"
        ):
            raise UploadError(422, "invalid_request")

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.field_name == "audio":
            self.audio_bytes += end - start
            if self.audio_bytes > MAX_AUDIO_BYTES:
                raise UploadError(413, "file_too_large")
        super().on_part_data(data, start, end)


async def parse_upload(request: Request) -> tuple[UploadFile, MeetingMetadata]:
    if (
        not request.headers.get("content-type", "")
        .lower()
        .startswith("multipart/form-data")
    ):
        raise UploadError(422, "invalid_request")
    parser = BoundedMeetingParser(request)
    try:
        form = await parser.parse()
    except (MultiPartException, KeyError, ValueError) as error:
        raise UploadError(422, "invalid_request") from error
    audio = form.get("audio")
    metadata = form.get("metadata")
    if not isinstance(audio, UploadFile) or not isinstance(metadata, str):
        await form.close()
        raise UploadError(422, "invalid_request")
    try:
        decoded = cast(object, json.loads(metadata))
        if not isinstance(decoded, dict):
            raise ValueError("Metadata must be an object")
        payload = cast(dict[str, object], decoded)
        meeting_date = payload.get("meeting_date")
        if not isinstance(meeting_date, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", meeting_date
        ):
            raise ValueError("Invalid meeting date")
        validated = MeetingMetadata.model_validate(payload)
    except (ValueError, ValidationError) as error:
        await form.close()
        raise UploadError(422, "invalid_request") from error
    if parser.audio_bytes == 0:
        await form.close()
        raise UploadError(415, "unsupported_media_type")
    return audio, validated


def stage_and_validate(audio: UploadFile, store: LocalArtifactStore) -> Path:
    """Copy a parsed, size-bounded file to private staging and validate audio."""
    suffix = Path(audio.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise UploadError(415, "unsupported_media_type")
    path = store.temporary_upload_path()
    try:
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_NOFOLLOW), "wb") as output:
            shutil.copyfileobj(audio.file, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        _validate_audio(path, suffix)
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _validate_audio(path: Path, suffix: str) -> None:
    if suffix == ".wav":
        try:
            with wave.open(str(path), "rb") as stream:
                if (
                    stream.getnchannels() < 1
                    or stream.getframerate() < 1
                    or stream.getnframes() < 1
                ):
                    raise ValueError("Empty WAV")
                if not stream.readframes(1):
                    raise ValueError("Truncated WAV")
            return
        except (EOFError, ValueError, wave.Error):
            raise UploadError(415, "unsupported_media_type") from None
    # Check the actual container and an audio stream. The suffix alone is never
    # sufficient, and ffprobe is strictly time bounded.
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=format_name:stream=codec_type",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise UploadError(415, "unsupported_media_type") from None
    if result.returncode != 0:
        raise UploadError(415, "unsupported_media_type")
    try:
        probe = json.loads(result.stdout)
        formats = set(probe["format"]["format_name"].split(","))
        streams = probe["streams"]
    except (KeyError, TypeError, ValueError):
        raise UploadError(415, "unsupported_media_type") from None
    expected = {
        ".mp3": {"mp3"},
        ".m4a": {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"},
        ".ogg": {"ogg"},
        ".webm": {"matroska", "webm"},
    }[suffix]
    if (
        not formats.intersection(expected)
        or not streams
        or not all(item.get("codec_type") == "audio" for item in streams)
    ):
        raise UploadError(415, "unsupported_media_type")
