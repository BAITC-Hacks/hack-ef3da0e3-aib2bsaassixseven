"""Owner-scoped public meeting upload and read routes."""

import asyncio
import base64
import binascii
import json
import logging
import re
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from io import BytesIO
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ValidationError
from pypdf import PdfReader
from starlette.types import Receive, Scope, Send

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
from app.services.pdf_export import render_pdf
from app.services.reviews import (
    ApprovalRequest,
    ReviewConflict,
    ReviewRequest,
    ReviewValidationError,
    approve_review,
    read_reviewed_results,
    read_reviewed_results_unlocked,
    update_review,
)
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
        "stale_revision": "Встреча была изменена; обновите страницу",
        "review_required": "Сначала проверьте и утвердите текущую ревизию",
        "export_failed": "Не удалось создать PDF",
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
        return read_reviewed_results(store, owner_id, meeting_id)
    except ReviewConflict as error:
        raise _error(409, error.code) from error
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
    transcript, _ = await asyncio.to_thread(
        _ready_results, store, user.id, _parse_id(meeting_id)
    )
    return transcript


@router.get("/{meeting_id}/insights", response_model=InsightsV1)
async def get_insights(
    meeting_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
) -> InsightsV1:
    _, insights = await asyncio.to_thread(
        _ready_results, store, user.id, _parse_id(meeting_id)
    )
    return insights


async def _review_body(request: Request) -> object:
    """Read bounded JSON without reflecting private meeting text in errors."""
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 2 * 1024 * 1024:
            raise _error(422, "invalid_request")
        chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks))
    except (ValueError, UnicodeDecodeError):
        raise _error(422, "invalid_request") from None


@router.put("/{meeting_id}/review")
async def put_review(
    meeting_id: str,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
) -> dict[str, int | str]:
    identifier = _parse_id(meeting_id)
    try:
        await asyncio.to_thread(store.read_record, user.id, identifier)
        payload = ReviewRequest.model_validate(await _review_body(request))
        meeting = await asyncio.to_thread(
            update_review, store, user.id, identifier, payload
        )
        return {"revision": meeting.revision, "status": meeting.status}
    except ValidationError as error:
        raise _error(422, "invalid_request") from error
    except ReviewValidationError as error:
        raise _error(422, "invalid_request") from error
    except ReviewConflict as error:
        raise _error(409, error.code) from error
    except MeetingNotFound as error:
        raise _error(404, "meeting_not_found") from error
    except (OSError, ArtifactIntegrityError, ArtifactNotReady, UnsafePath) as error:
        raise _error(503, "storage_failed") from error


@router.post("/{meeting_id}/approve", response_model=Meeting)
async def post_approve(
    meeting_id: str,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
) -> Meeting:
    identifier = _parse_id(meeting_id)
    try:
        await asyncio.to_thread(store.read_record, user.id, identifier)
        payload = ApprovalRequest.model_validate(await _review_body(request))
        return await asyncio.to_thread(
            approve_review, store, user.id, identifier, payload
        )
    except ValidationError as error:
        raise _error(422, "invalid_request") from error
    except ReviewConflict as error:
        raise _error(409, error.code) from error
    except MeetingNotFound as error:
        raise _error(404, "meeting_not_found") from error
    except (OSError, ArtifactIntegrityError, ArtifactNotReady, UnsafePath) as error:
        raise _error(503, "storage_failed") from error


def _valid_pdf(data: bytes) -> bool:
    if not data.startswith(b"%PDF-") or not data.rstrip().endswith(b"%%EOF"):
        return False
    try:
        return len(PdfReader(BytesIO(data), strict=True).pages) > 0
    except Exception:
        return False


def _clear_exporting_stage(
    store: LocalArtifactStore, owner_id: UUID, meeting_id: UUID
) -> None:
    record = store.read_record(owner_id, meeting_id)
    if record.meeting.stage == "exporting":
        record.meeting = record.meeting.model_copy(
            update={"stage": None, "updated_at": datetime.now(UTC)}
        )
        store.update_meeting(owner_id, record)


def _build_export_unlocked(
    store: LocalArtifactStore, owner_id: UUID, meeting_id: UUID
) -> bytes:
    """Build/cache PDF while caller holds the lifecycle lock through HTTP send."""
    record = store.read_record(owner_id, meeting_id)
    meeting = record.meeting
    if meeting.status != "approved":
        raise ReviewConflict("review_required")
    try:
        cached = store.read_pdf_cache(owner_id, meeting_id, meeting.revision)
    except FileNotFoundError:
        cached = None
    except ArtifactIntegrityError:
        store.delete_pdf_cache(owner_id, meeting_id, meeting.revision)
        cached = None
    if cached is not None:
        if _valid_pdf(cached):
            _clear_exporting_stage(store, owner_id, meeting_id)
            return cached
        store.delete_pdf_cache(owner_id, meeting_id, meeting.revision)
    try:
        record.meeting = meeting.model_copy(
            update={"stage": "exporting", "updated_at": datetime.now(UTC)}
        )
        store.update_meeting(owner_id, record)
        transcript, insights = read_reviewed_results_unlocked(
            store, owner_id, meeting_id
        )
        if (
            transcript.revision != meeting.revision
            or insights.revision != meeting.revision
        ):
            raise ArtifactIntegrityError("Review revision mismatch")
        data = render_pdf(meeting, transcript, insights)
        if not _valid_pdf(data):
            raise ValueError("Renderer did not return a PDF")
        store.write_pdf_cache(owner_id, meeting_id, meeting.revision, data)
        return data
    finally:
        _clear_exporting_stage(store, owner_id, meeting_id)


class _LockedPdfResponse(Response):
    """Keep the approved revision locked until its bytes leave the ASGI app."""

    def __init__(
        self, content: bytes, lock: AbstractContextManager[bool], meeting_id: UUID
    ) -> None:
        super().__init__(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="meeting-{meeting_id}.pdf"'
                ),
                "Cache-Control": "no-store",
            },
        )
        self._lock = lock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await asyncio.to_thread(self._lock.__exit__, None, None, None)


def _prepare_export(
    store: LocalArtifactStore, owner_id: UUID, meeting_id: UUID
) -> tuple[bytes, AbstractContextManager[bool]]:
    """Acquire, build, and transfer the lock to the HTTP response."""
    lock = store.lifecycle_lock(owner_id, meeting_id)
    entered = False
    try:
        lock.__enter__()
        entered = True
        return _build_export_unlocked(store, owner_id, meeting_id), lock
    except BaseException:
        if entered:
            lock.__exit__(None, None, None)
        raise


def _release_abandoned_export(
    task: asyncio.Task[tuple[bytes, AbstractContextManager[bool]]],
) -> None:
    """A cancelled HTTP request must let its worker finish before unlock."""
    try:
        _, lock = task.result()
    except BaseException:
        return  # The worker released its own lock on failure.
    asyncio.create_task(asyncio.to_thread(lock.__exit__, None, None, None))


@router.get("/{meeting_id}/export.pdf")
async def get_export_pdf(
    meeting_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
) -> Response:
    identifier = _parse_id(meeting_id)
    preparing = asyncio.create_task(
        asyncio.to_thread(_prepare_export, store, user.id, identifier)
    )
    try:
        pdf, lock = await asyncio.shield(preparing)
    except asyncio.CancelledError:
        preparing.add_done_callback(_release_abandoned_export)
        raise
    except ReviewConflict as error:
        raise _error(409, error.code) from error
    except MeetingNotFound as error:
        raise _error(404, "meeting_not_found") from error
    except Exception as error:
        logger.warning("PDF export failed")
        raise _error(503, "export_failed") from error
    try:
        return _LockedPdfResponse(pdf, lock, identifier)
    except BaseException:
        await asyncio.to_thread(lock.__exit__, None, None, None)
        raise
