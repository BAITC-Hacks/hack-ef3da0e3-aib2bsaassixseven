"""Owner-scoped public meeting upload and read routes."""

import asyncio
import base64
import binascii
import json
import logging
import re
from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.auth import AuthenticatedUser, get_current_user
from app.models.insights import InsightsV1
from app.models.meeting import Meeting
from app.models.transcript import TranscriptV1
from app.services.artifact_store import (
    ArtifactIntegrityError,
    ArtifactNotReady,
    LocalArtifactStore,
    MeetingNotFound,
    UnsafePath,
)
from app.services.lifecycle import LifecycleConflict
from app.services.lifecycle import delete_meeting as delete_lifecycle
from app.services.lifecycle import retry_meeting as retry_lifecycle
from app.services.uploads import UploadError, parse_upload, stage_and_validate

router = APIRouter(prefix="/meetings", tags=["meetings"])
logger = logging.getLogger(__name__)


class MeetingPage(BaseModel):
    items: list[Meeting]
    next_cursor: str | None


def get_artifact_store() -> LocalArtifactStore:
    try:
        return LocalArtifactStore()
    except (OSError, UnsafePath) as error:
        raise _error(503, "storage_failed") from error


class MeetingApiError(HTTPException):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.code = code


def _error(status_code: int, code: str) -> MeetingApiError:
    details = {
        "invalid_request": "Некорректные данные запроса",
        "meeting_not_found": "Встреча не найдена",
        "invalid_state": "Результат ещё не готов",
        "file_too_large": "Файл слишком большой",
        "unsupported_media_type": "Неподдерживаемый формат аудио",
        "storage_failed": "Не удалось сохранить данные",
        "attempts_exhausted": "Достигнут лимит попыток обработки",
        "source_expired": "Загрузите запись повторно",
        "cleanup_pending": "Очистка временных данных ещё не завершена",
        "delete_failed": "Не удалось удалить встречу",
    }
    return MeetingApiError(status_code, code, details[code])


def _parse_id(raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError:
        raise _error(422, "invalid_request") from None


def _encode_cursor(meeting: Meeting) -> str:
    return _encode_cursor_stub(meeting.created_at, str(meeting.id))


def _decode_cursor(raw: str) -> tuple[datetime, str]:
    if len(raw) > 256:
        raise _error(422, "invalid_request")
    try:
        payload = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        decoded = cast(object, json.loads(payload))
        if not isinstance(decoded, list):
            raise ValueError
        data = cast(list[object], decoded)
        if (
            len(data) != 2
            or not isinstance(data[0], str)
            or not isinstance(data[1], str)
        ):
            raise ValueError
        timestamp = datetime.fromisoformat(data[0])
        offset = timestamp.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError
        identifier = str(UUID(data[1]))
        if _encode_cursor_stub(timestamp, identifier) != raw:
            raise ValueError
        return timestamp, identifier
    except (TypeError, ValueError, UnicodeDecodeError, binascii.Error):
        raise _error(422, "invalid_request") from None


def _encode_cursor_stub(timestamp: datetime, identifier: str) -> str:
    payload = json.dumps(
        [timestamp.isoformat(), identifier], separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


@router.post("", response_model=Meeting, status_code=202)
async def create_meeting(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
) -> Meeting:
    try:
        audio, metadata, source_kind = await parse_upload(request)
        try:
            path, audio_extension = await asyncio.to_thread(
                stage_and_validate, audio, store
            )
        finally:
            await audio.close()
        try:
            meeting = await asyncio.to_thread(
                store.create_meeting,
                user.id,
                metadata,
                path,
                source_kind=source_kind,
                audio_extension=audio_extension,
            )
        except BaseException:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Staging cleanup deferred after failed meeting creation")
            raise
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Staging cleanup deferred after committed meeting creation")
        return meeting
    except UploadError as error:
        raise _error(error.status_code, error.code) from error
    except (OSError, ArtifactIntegrityError, UnsafePath) as error:
        raise _error(503, "storage_failed") from error


@router.get("", response_model=MeetingPage)
async def list_meetings(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
    limit: str = "20",
    cursor: str | None = None,
) -> MeetingPage:
    if (
        len(limit) > 3
        or not re.fullmatch(r"[0-9]+", limit)
        or not 1 <= int(limit) <= 100
    ):
        raise _error(422, "invalid_request")
    boundary = _decode_cursor(cursor) if cursor is not None else None
    try:
        meetings = store.list_meetings(user.id)
    except (OSError, ArtifactIntegrityError, UnsafePath) as error:
        raise _error(503, "storage_failed") from error
    if boundary is not None:
        meetings = [
            item for item in meetings if (item.created_at, str(item.id)) < boundary
        ]
    page = meetings[: int(limit)]
    next_cursor = _encode_cursor(page[-1]) if len(meetings) > len(page) else None
    return MeetingPage(items=page, next_cursor=next_cursor)


@router.get("/{meeting_id}", response_model=Meeting)
async def get_meeting(
    meeting_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
) -> Meeting:
    try:
        return store.read_meeting(user.id, _parse_id(meeting_id))
    except MeetingNotFound as error:
        raise _error(404, "meeting_not_found") from error
    except (OSError, ArtifactIntegrityError, UnsafePath) as error:
        raise _error(503, "storage_failed") from error


@router.post("/{meeting_id}/retry", response_model=Meeting, status_code=202)
async def retry_meeting(
    meeting_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
) -> Meeting:
    try:
        return await asyncio.to_thread(
            retry_lifecycle, store, user.id, _parse_id(meeting_id)
        )
    except MeetingNotFound as error:
        raise _error(404, "meeting_not_found") from error
    except LifecycleConflict as error:
        raise _error(409, error.code) from error
    except (OSError, ArtifactIntegrityError, UnsafePath) as error:
        raise _error(503, "storage_failed") from error


@router.delete("/{meeting_id}", status_code=204)
async def delete_meeting(
    meeting_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
) -> None:
    try:
        await asyncio.to_thread(delete_lifecycle, store, user.id, _parse_id(meeting_id))
    except MeetingNotFound as error:
        raise _error(404, "meeting_not_found") from error
    except LifecycleConflict as error:
        raise _error(409, error.code) from error
    except (OSError, ArtifactIntegrityError, UnsafePath) as error:
        raise _error(503, "delete_failed") from error


def _ready_results(
    store: LocalArtifactStore, owner_id: UUID, meeting_id: UUID
) -> tuple[TranscriptV1, InsightsV1]:
    try:
        meeting = store.read_meeting(owner_id, meeting_id)
        if meeting.status not in {"review_required", "approved"}:
            raise _error(409, "invalid_state")
        return store.read_results(owner_id, meeting_id)
    except MeetingNotFound as error:
        raise _error(404, "meeting_not_found") from error
    except ArtifactNotReady as error:
        raise _error(409, "invalid_state") from error
    except (OSError, ArtifactIntegrityError, UnsafePath) as error:
        raise _error(503, "storage_failed") from error


@router.get("/{meeting_id}/transcript", response_model=TranscriptV1)
async def get_transcript(
    meeting_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
) -> TranscriptV1:
    transcript, _ = _ready_results(store, user.id, _parse_id(meeting_id))
    return transcript


@router.get("/{meeting_id}/insights", response_model=InsightsV1)
async def get_insights(
    meeting_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
) -> InsightsV1:
    _, insights = _ready_results(store, user.id, _parse_id(meeting_id))
    return insights
