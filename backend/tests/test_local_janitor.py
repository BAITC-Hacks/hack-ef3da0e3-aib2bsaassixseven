"""Periodic cleanup of private local files and durable cleanup state."""

import asyncio
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from test_artifact_store import bundle, metadata
from test_coordinator_runtime import RecordingCoordinator

from app.models.meeting import CleanupStatus
from app.services.artifact_store import LocalArtifactStore
from app.services.coordinator_runtime import CoordinatorRuntime

OWNER = UUID("11111111-1111-4111-8111-111111111111")


def create_meeting(store: LocalArtifactStore) -> UUID:
    return store.create_meeting(OWNER, metadata(), b"synthetic audio").id


def age(path: Path) -> None:
    old = (datetime.now(UTC) - timedelta(hours=25)).timestamp()
    os.utime(path, (old, old))


async def test_periodic_tick_sweeps_stale_private_staging_without_new_upload(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    stale = store.temporary_upload_path()
    fresh = store.temporary_upload_path()
    unrelated = stale.parent / "customer.upload"
    unrelated.write_bytes(b"keep")
    age(stale)
    age(unrelated)

    await CoordinatorRuntime(store, RecordingCoordinator()).tick()

    assert not stale.exists()
    assert fresh.exists()
    assert unrelated.read_bytes() == b"keep"


async def test_periodic_tick_removes_abandoned_meeting_and_delete_tombstone(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    create_meeting(store)
    parent = tmp_path / "users" / str(OWNER) / "meetings"
    abandoned = parent / str(uuid4())
    abandoned.mkdir()
    (abandoned / "upload.bin").write_bytes(b"orphan")
    age(abandoned / "upload.bin")
    age(abandoned)
    fresh = parent / str(uuid4())
    fresh.mkdir()
    tombstone = parent / f".deleted-{uuid4()}-{uuid4()}"
    tombstone.mkdir()
    (tombstone / "review.json").write_text("private")
    unrelated = parent / ".deleted-untrusted"
    unrelated.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_link = parent / f".deleted-{uuid4()}-{uuid4()}"
    outside_link.symlink_to(outside, target_is_directory=True)

    await CoordinatorRuntime(store, RecordingCoordinator()).tick()

    assert not abandoned.exists()
    assert fresh.exists()
    assert not tombstone.exists()
    assert unrelated.exists()
    assert outside_link.is_symlink()
    assert outside.exists()


@pytest.mark.parametrize(
    "gpu_cleanup,expected", [("pending", "pending"), ("deleted", "expired")]
)
async def test_failed_meeting_upload_expires_without_losing_gpu_cleanup_state(
    tmp_path: Path, gpu_cleanup: CleanupStatus, expected: CleanupStatus
) -> None:
    store = LocalArtifactStore(tmp_path)
    meeting_id = create_meeting(store)
    record = store.read_record(OWNER, meeting_id)
    record.meeting.status = "failed"
    record.meeting.temporary_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    record.jobs[0].job_id = uuid4()
    record.jobs[0].cleanup_status = gpu_cleanup
    store.update_meeting(OWNER, record)

    await CoordinatorRuntime(store, RecordingCoordinator()).tick()

    persisted = store.read_record(OWNER, meeting_id)
    assert not store.upload_present(OWNER, meeting_id)
    assert persisted.local_cleanup_status == "expired"
    assert persisted.meeting.source_available is False
    assert persisted.meeting.cleanup_status == expected
    assert persisted.meeting.status == "failed"


async def test_never_submitted_expired_meeting_has_no_pending_gpu_copy(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    meeting_id = create_meeting(store)
    record = store.read_record(OWNER, meeting_id)
    record.meeting.temporary_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    store.update_meeting(OWNER, record)

    await CoordinatorRuntime(store, RecordingCoordinator()).tick()

    persisted = store.read_record(OWNER, meeting_id)
    assert persisted.jobs[0].job_id is None
    assert persisted.jobs[0].cleanup_status == "expired"
    assert persisted.meeting.cleanup_status == "expired"
    assert not store.upload_present(OWNER, meeting_id)


async def test_ready_results_survive_upload_ttl_cleanup(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    meeting_id = create_meeting(store)
    result = bundle(meeting_id)
    store.publish_results(OWNER, meeting_id, result)
    record = store.read_record(OWNER, meeting_id)
    record.meeting.temporary_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    record.jobs[0].cleanup_status = "deleted"
    record.jobs[0].ack_pending = False
    store.update_meeting(OWNER, record)

    await CoordinatorRuntime(store, RecordingCoordinator()).tick()

    meeting = store.read_meeting(OWNER, meeting_id)
    transcript, insights = store.read_results(OWNER, meeting_id)
    assert meeting.status == "review_required"
    assert meeting.cleanup_status == "expired"
    assert meeting.source_available is False
    assert transcript == result.transcript
    assert insights == result.insights


async def test_unlink_failure_keeps_cleanup_pending_until_next_tick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalArtifactStore(tmp_path)
    meeting_id = create_meeting(store)
    record = store.read_record(OWNER, meeting_id)
    record.meeting.status = "failed"
    record.meeting.temporary_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    record.jobs[0].cleanup_status = "expired"
    store.update_meeting(OWNER, record)
    real_delete = store.delete_upload

    def fail_delete(owner_id: UUID, target_id: UUID) -> None:
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(store, "delete_upload", fail_delete)
    runtime = CoordinatorRuntime(store, RecordingCoordinator())
    await runtime.tick()
    pending = store.read_record(OWNER, meeting_id)
    assert pending.local_cleanup_status == "pending"
    assert pending.meeting.source_available is False
    assert store.read_meeting(OWNER, meeting_id).cleanup_status == "pending"

    monkeypatch.setattr(store, "delete_upload", real_delete)
    await runtime.tick()
    assert store.read_meeting(OWNER, meeting_id).cleanup_status == "expired"


async def test_janitor_waits_for_meeting_mutation_before_expiring_upload(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    meeting_id = create_meeting(store)
    record = store.read_record(OWNER, meeting_id)
    record.meeting.temporary_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    store.update_meeting(OWNER, record)
    entered = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with store.lifecycle_lock(OWNER, meeting_id):
            entered.set()
            assert release.wait(timeout=5)

    holder = asyncio.create_task(asyncio.to_thread(hold_lock))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        await CoordinatorRuntime(store, RecordingCoordinator()).tick()
        assert store.upload_present(OWNER, meeting_id)
    finally:
        release.set()
        await holder

    await CoordinatorRuntime(store, RecordingCoordinator()).tick()
    assert not store.upload_present(OWNER, meeting_id)
