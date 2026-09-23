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
from pydantic import BaseModel, ValidationError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.models.meeting import (
    AudioExtension,
    MeetingMetadata,
    MeetingUploadMetadata,
    PublicSourceKind,
    UploadExtension,
    VideoExtension,
)
from app.services.artifact_store import LocalArtifactStore

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_METADATA_BYTES = 16 * 1024
MEDIA_PROBE_TIMEOUT_SECONDS = 5
VIDEO_EXTRACTION_TIMEOUT_SECONDS = 120
AUDIO_EXTENSIONS: frozenset[AudioExtension] = frozenset(
    {".wav", ".mp3", ".m4a", ".ogg", ".webm"}
)
VIDEO_EXTENSIONS: frozenset[VideoExtension] = frozenset({".mp4", ".mov", ".mkv"})
ALLOWED_EXTENSIONS: frozenset[UploadExtension] = frozenset(
    {*AUDIO_EXTENSIONS, *VIDEO_EXTENSIONS}
)


class _ProbeFormat(BaseModel):
    format_name: str


class _ProbeStream(BaseModel):
    codec_name: str | None = None
    codec_type: str


class _ProbeResult(BaseModel):
    format: _ProbeFormat
    streams: list[_ProbeStream]


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
            not in {b"", b"application/json"}
        ):
            raise UploadError(422, "invalid_request")

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.field_name == "audio":
            self.audio_bytes += end - start
            if self.audio_bytes > MAX_UPLOAD_BYTES:
                raise UploadError(413, "file_too_large")
        super().on_part_data(data, start, end)


async def parse_upload(
    request: Request,
) -> tuple[UploadFile, MeetingMetadata, PublicSourceKind]:
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
        validated = MeetingUploadMetadata.model_validate(payload)
    except (ValueError, ValidationError) as error:
        await form.close()
        raise UploadError(422, "invalid_request") from error
    if parser.audio_bytes == 0:
        await form.close()
        raise UploadError(415, "unsupported_media_type")
    meeting_metadata = MeetingMetadata.model_validate(
        validated.model_dump(exclude={"source_kind"})
    )
    return audio, meeting_metadata, validated.source_kind


def stage_and_validate(
    audio: UploadFile, store: LocalArtifactStore
) -> tuple[Path, AudioExtension]:
    """Privately stage media and return a validated, audio-only GPU payload."""
    suffix = Path(audio.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise UploadError(415, "unsupported_media_type")
    upload_extension = cast(UploadExtension, suffix)
    source_path = store.temporary_upload_path()
    normalized_path: Path | None = None
    try:
        with os.fdopen(
            os.open(source_path, os.O_WRONLY | os.O_NOFOLLOW), "wb"
        ) as output:
            shutil.copyfileobj(audio.file, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        if upload_extension == ".wav":
            _validate_wav(source_path)
            return source_path, ".wav"

        probe = _probe_media(source_path)
        _validate_container(source_path, upload_extension, probe)
        audio_streams = [
            stream for stream in probe.streams if stream.codec_type == "audio"
        ]
        if not audio_streams:
            raise UploadError(415, "unsupported_media_type")

        needs_extraction = upload_extension in VIDEO_EXTENSIONS or any(
            stream.codec_type == "video" for stream in probe.streams
        )
        if needs_extraction:
            normalized_path = _extract_first_audio(source_path, store)
            source_path.unlink()
            return normalized_path, ".m4a"

        _validate_audio_only(upload_extension, probe)
        return source_path, cast(AudioExtension, upload_extension)
    except BaseException:
        source_path.unlink(missing_ok=True)
        if normalized_path is not None:
            normalized_path.unlink(missing_ok=True)
        raise


def _validate_wav(path: Path) -> None:
    try:
        with wave.open(str(path), "rb") as stream:
            if (
                stream.getnchannels() < 1
                or stream.getframerate() < 1
                or stream.getnframes() < 1
            ):
                raise ValueError("Empty WAV")
            frame_size = stream.getnchannels() * stream.getsampwidth()
            remaining = stream.getnframes()
            frames_per_chunk = max(1, 64 * 1024 // frame_size)
            while remaining:
                frames = min(remaining, frames_per_chunk)
                if len(stream.readframes(frames)) != frames * frame_size:
                    raise ValueError("Truncated WAV")
                remaining -= frames
    except (EOFError, ValueError, wave.Error):
        raise UploadError(415, "unsupported_media_type") from None


def _probe_media(path: Path) -> _ProbeResult:
    """Read only structural media metadata with a strict wall-clock bound."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=format_name:stream=codec_name,codec_type",
                "-of",
                "json",
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=MEDIA_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise UploadError(415, "unsupported_media_type") from None
    if result.returncode != 0:
        raise UploadError(415, "unsupported_media_type")
    try:
        return _ProbeResult.model_validate_json(result.stdout)
    except (ValidationError, ValueError):
        raise UploadError(415, "unsupported_media_type") from None


def _validate_container(
    path: Path, suffix: UploadExtension, probe: _ProbeResult
) -> None:
    formats = set(probe.format.format_name.split(","))
    expected = {
        ".mp3": {"mp3"},
        ".m4a": {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"},
        ".ogg": {"ogg"},
        ".webm": {"matroska", "webm"},
        ".mp4": {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"},
        ".mov": {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"},
        ".mkv": {"matroska", "webm"},
    }[suffix]
    if not formats.intersection(expected) or not probe.streams:
        raise UploadError(415, "unsupported_media_type")
    if suffix == ".webm" and not _has_webm_doctype(path):
        raise UploadError(415, "unsupported_media_type")


def _validate_audio_only(suffix: UploadExtension, probe: _ProbeResult) -> None:
    if not all(stream.codec_type == "audio" for stream in probe.streams):
        raise UploadError(415, "unsupported_media_type")
    if suffix == ".webm" and not all(
        stream.codec_name == "opus" for stream in probe.streams
    ):
        raise UploadError(415, "unsupported_media_type")


def _extract_first_audio(source: Path, store: LocalArtifactStore) -> Path:
    """Convert one local video stream to a bounded audio-only M4A payload."""
    target = store.temporary_upload_path()
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-threads",
                "1",
                "-fs",
                str(MAX_UPLOAD_BYTES + 1),
                "-f",
                "ipod",
                str(target),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=VIDEO_EXTRACTION_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        target.unlink(missing_ok=True)
        raise UploadError(415, "unsupported_media_type") from None
    try:
        if (
            result.returncode != 0
            or not target.is_file()
            or not 0 < target.stat().st_size <= MAX_UPLOAD_BYTES
        ):
            raise UploadError(415, "unsupported_media_type")
        probe = _probe_media(target)
        _validate_container(target, ".m4a", probe)
        _validate_audio_only(".m4a", probe)
        return target
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def _has_webm_doctype(path: Path) -> bool:
    """Distinguish WebM from Matroska, which ffprobe reports under one format name."""
    try:
        with path.open("rb") as source:
            data = source.read(4096)
    except OSError:
        return False
    if not data.startswith(b"\x1a\x45\xdf\xa3"):
        return False

    def vint(offset: int, *, size: bool) -> tuple[int, int]:
        if offset >= len(data):
            raise ValueError
        first = data[offset]
        mask = 0x80
        width = 1
        while width <= 8 and not first & mask:
            mask >>= 1
            width += 1
        if width > 8 or offset + width > len(data):
            raise ValueError
        value = first & (mask - 1) if size else first
        for byte in data[offset + 1 : offset + width]:
            value = (value << 8) | byte
        return value, offset + width

    try:
        header_size, cursor = vint(4, size=True)
        header_end = cursor + header_size
        if header_end > len(data):
            return False
        while cursor < header_end:
            element_id, cursor = vint(cursor, size=False)
            element_size, cursor = vint(cursor, size=True)
            end = cursor + element_size
            if end > header_end:
                return False
            if element_id == 0x4282:
                return data[cursor:end] == b"webm"
            cursor = end
    except ValueError:
        return False
    return False
