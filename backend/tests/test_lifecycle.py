"""Retry and deletion contract tests with durable local meeting state."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.routes.meetings import get_artifact_store
from app.core.auth import AuthenticatedUser, InvalidAccessToken, get_token_verifier
from app.models.meeting import Failure, JobRecord, MeetingMetadata
from app.services.artifact_store import LocalArtifactStore

OWNER = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
HEADERS = {"Authorization": "Bearer owner"}


class Verifier:
    async def verify(self, token: str) -> AuthenticatedUser:
        if token == "owner":
            return AuthenticatedUser(id=OWNER, role="authenticated")
        if token == "other":
            return AuthenticatedUser(id=OTHER, role="authenticated")
        raise InvalidAccessToken


@pytest.fixture
def store(app: FastAPI, tmp_path: Path) -> LocalArtifactStore:
    result = LocalArtifactStore(tmp_path / "artifacts")
    app.dependency_overrides[get_artifact_store] = lambda: result
    app.dependency_overrides[get_token_verifier] = lambda: Verifier()
    return result


def meeting(store: LocalArtifactStore) -> UUID:
    created = store.create_meeting(
        OWNER,
        MeetingMetadata(
            title="План запуска",
            meeting_date=datetime(2026, 9, 23).date(),
            timezone="Asia/Almaty",
            participants=["Алия"],
            recording_notice_confirmed=True,
        ),
        b"audio",
    )
    return created.id


def fail(store: LocalArtifactStore, meeting_id: UUID) -> None:
    record = store.read_record(OWNER, meeting_id)
    record.meeting.status = "failed"
    record.meeting.failure = Failure(
        code="processing_failed", message="Не удалось обработать запись"
    )
    store.update_meeting(OWNER, record)


async def test_retry_increments_attempt_and_keeps_previous_history(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    meeting_id = meeting(store)
    fail(store, meeting_id)

    result = await client.post(f"/api/v1/meetings/{meeting_id}/retry", headers=HEADERS)

    assert result.status_code == 202
    assert result.json()["status"] == "queued"
    assert result.json()["attempt"] == 2
    assert result.json()["failure"] is None
    record = store.read_record(OWNER, meeting_id)
    assert [job.attempt for job in record.jobs] == [1, 2]
    archive = store.root / "users" / str(OWNER) / "meetings" / str(meeting_id)
    assert (archive / "attempts" / "1" / "meeting.json").exists()
    assert store.upload_path(OWNER, meeting_id).read_bytes() == b"audio"


async def test_retry_rejects_non_failed_and_fourth_attempt(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    meeting_id = meeting(store)
    url = f"/api/v1/meetings/{meeting_id}/retry"
    queued = await client.post(url, headers=HEADERS)
    assert queued.status_code == 409
    assert queued.json()["code"] == "invalid_state"

    fail(store, meeting_id)
    for attempt in (2, 3):
        result = await client.post(url, headers=HEADERS)
        assert result.status_code == 202
        assert result.json()["attempt"] == attempt
        fail(store, meeting_id)
    exhausted = await client.post(url, headers=HEADERS)
    assert exhausted.status_code == 409
    assert exhausted.json()["code"] == "attempts_exhausted"
    assert store.read_record(OWNER, meeting_id).meeting.attempt == 3


async def test_retry_requires_unexpired_existing_source(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    meeting_id = meeting(store)
    fail(store, meeting_id)
    record = store.read_record(OWNER, meeting_id)
    record.meeting.temporary_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    store.update_meeting(OWNER, record)

    expired = await client.post(f"/api/v1/meetings/{meeting_id}/retry", headers=HEADERS)
    assert expired.status_code == 409
    assert expired.json()["code"] == "source_expired"
    assert store.read_record(OWNER, meeting_id).meeting.attempt == 1


async def test_lifecycle_routes_hide_foreign_meeting(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    meeting_id = meeting(store)
    fail(store, meeting_id)
    foreign_headers = {"Authorization": "Bearer other"}
    for method, suffix in (("POST", "/retry"), ("DELETE", "")):
        result = await client.request(
            method,
            f"/api/v1/meetings/{meeting_id}{suffix}",
            headers=foreign_headers,
        )
        assert result.status_code == 404
        assert result.json()["code"] == "meeting_not_found"
    assert store.read_record(OWNER, meeting_id).meeting.status == "failed"


async def test_delete_requires_terminal_state_and_cleanup(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    meeting_id = meeting(store)
    url = f"/api/v1/meetings/{meeting_id}"
    queued = await client.delete(url, headers=HEADERS)
    assert queued.status_code == 409
    assert queued.json()["code"] == "invalid_state"

    fail(store, meeting_id)
    pending = await client.delete(url, headers=HEADERS)
    assert pending.status_code == 409
    assert pending.json()["code"] == "cleanup_pending"
    assert (await client.get(url, headers=HEADERS)).status_code == 200


async def test_delete_waits_for_physical_source_removal(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    meeting_id = meeting(store)
    fail(store, meeting_id)
    record = store.read_record(OWNER, meeting_id)
    record.local_cleanup_status = "deleted"
    record.jobs[0].cleanup_status = "deleted"
    record.meeting.cleanup_status = "deleted"
    store.update_meeting(OWNER, record)

    result = await client.delete(f"/api/v1/meetings/{meeting_id}", headers=HEADERS)

    assert result.status_code == 409
    assert result.json()["code"] == "cleanup_pending"
    assert store.upload_path(OWNER, meeting_id).exists()


async def test_delete_removes_terminal_clean_meeting(
    client: AsyncClient, store: LocalArtifactStore
) -> None:
    meeting_id = meeting(store)
    fail(store, meeting_id)
    store.delete_upload(OWNER, meeting_id)
    record = store.read_record(OWNER, meeting_id)
    record.local_cleanup_status = "deleted"
    record.jobs = [JobRecord(attempt=1, cleanup_status="deleted")]
    record.meeting.cleanup_status = "deleted"
    store.update_meeting(OWNER, record)

    result = await client.delete(f"/api/v1/meetings/{meeting_id}", headers=HEADERS)

    assert result.status_code == 204
    assert result.content == b""
    assert store.list_meetings(OWNER) == []
    missing = await client.get(f"/api/v1/meetings/{meeting_id}", headers=HEADERS)
    assert missing.status_code == 404
    folder = store.root / "users" / str(OWNER) / "meetings" / str(meeting_id)
    assert not folder.exists()


async def test_delete_failure_keeps_meeting_accessible(
    client: AsyncClient,
    store: LocalArtifactStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meeting_id = meeting(store)
    fail(store, meeting_id)
    store.delete_upload(OWNER, meeting_id)
    record = store.read_record(OWNER, meeting_id)
    record.local_cleanup_status = "deleted"
    record.jobs[0].cleanup_status = "deleted"
    record.meeting.cleanup_status = "deleted"
    store.update_meeting(OWNER, record)

    def fail_delete(_owner_id: UUID, _meeting_id: UUID) -> None:
        raise OSError("test injection")

    monkeypatch.setattr(store, "delete_meeting", fail_delete, raising=False)
    result = await client.delete(f"/api/v1/meetings/{meeting_id}", headers=HEADERS)
    assert result.status_code == 503
    assert result.json()["code"] == "delete_failed"
    still_present = await client.get(f"/api/v1/meetings/{meeting_id}", headers=HEADERS)
    assert still_present.status_code == 200
