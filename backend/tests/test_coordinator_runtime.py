"""The scheduler resumes durable meetings without overlapping their steps."""

import asyncio
import json
import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import SecretStr
from test_artifact_store import bundle
from test_coordinator import FakeGPUClient

from app.core.config import Settings
from app.main import create_app
from app.models.meeting import Failure, MeetingMetadata
from app.services.artifact_store import LocalArtifactStore
from app.services.coordinator import CoordinatorStorageError, MeetingCoordinator
from app.services.coordinator_runtime import CoordinatorRuntime

OWNER = UUID("11111111-1111-4111-8111-111111111111")


def create_meeting(store: LocalArtifactStore) -> UUID:
    meeting = store.create_meeting(
        OWNER,
        MeetingMetadata(
            title="План",
            meeting_date=date(2026, 9, 23),
            timezone="Asia/Almaty",
            participants=[],
            recording_notice_confirmed=True,
            language_hint="mixed",
        ),
        b"synthetic audio",
    )
    return meeting.id


class RecordingCoordinator:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID]] = []

    async def process_once(self, owner_id: UUID, meeting_id: UUID) -> None:
        self.calls.append((owner_id, meeting_id))


async def test_runtime_discovers_existing_queued_meeting_after_restart(
    tmp_path: Path,
) -> None:
    meeting_id = create_meeting(LocalArtifactStore(tmp_path))
    coordinator = RecordingCoordinator()
    runtime = CoordinatorRuntime(LocalArtifactStore(tmp_path), coordinator)

    await runtime.tick()

    assert coordinator.calls == [(OWNER, meeting_id)]


async def test_runtime_retries_ready_meeting_with_pending_cleanup(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    meeting_id = create_meeting(store)
    store.publish_results(OWNER, meeting_id, bundle(meeting_id))
    coordinator = RecordingCoordinator()

    await CoordinatorRuntime(store, coordinator).tick()

    assert coordinator.calls == [(OWNER, meeting_id)]


async def test_runtime_skips_terminal_meeting_with_completed_cleanup(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    meeting_id = create_meeting(store)
    record = store.read_record(OWNER, meeting_id)
    record.meeting.status = "failed"
    record.meeting.cleanup_status = "deleted"
    store.update_meeting(OWNER, record)
    coordinator = RecordingCoordinator()

    await CoordinatorRuntime(store, coordinator).tick()

    assert coordinator.calls == []


async def test_runtime_revisits_failed_meeting_for_gpu_cleanup_receipt(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    meeting_id = create_meeting(store)
    gpu = FakeGPUClient(bundle(meeting_id))
    record = store.read_record(OWNER, meeting_id)
    record.meeting.status = "failed"
    record.meeting.failure = Failure(
        code="processing_failed", message="Не удалось обработать запись"
    )
    record.jobs[0].job_id = gpu.job.job_id
    store.delete_upload(OWNER, meeting_id)
    record.local_cleanup_status = "deleted"
    store.update_meeting(OWNER, record)
    gpu.job = gpu.job.model_copy(
        update={
            "status": "expired",
            "cleanup_status": "expired",
            "receipt_expires_at": datetime.now(UTC) + timedelta(days=7),
        }
    )

    await CoordinatorRuntime(store, MeetingCoordinator(store, gpu)).tick()

    assert store.read_meeting(OWNER, meeting_id).cleanup_status == "expired"
    assert gpu.calls == ["poll"]


class BlockingCoordinator:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.active = 0
        self.max_active = 0
        self.calls = 0

    async def process_once(self, owner_id: UUID, meeting_id: UUID) -> None:
        self.active += 1
        self.calls += 1
        self.max_active = max(self.max_active, self.active)
        self.entered.set()
        await self.release.wait()
        self.active -= 1


async def test_concurrent_ticks_never_overlap_one_meeting(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    create_meeting(store)
    coordinator = BlockingCoordinator()
    runtime = CoordinatorRuntime(store, coordinator)

    first = asyncio.create_task(runtime.tick())
    await coordinator.entered.wait()
    second = asyncio.create_task(runtime.tick())
    await asyncio.sleep(0)
    assert coordinator.max_active == 1
    coordinator.release.set()
    await asyncio.gather(first, second)

    assert coordinator.max_active == 1
    assert coordinator.calls == 2


async def test_separate_runtime_instances_do_not_overlap_one_meeting(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    create_meeting(store)
    coordinator = BlockingCoordinator()
    first_runtime = CoordinatorRuntime(LocalArtifactStore(tmp_path), coordinator)
    second_runtime = CoordinatorRuntime(LocalArtifactStore(tmp_path), coordinator)

    first = asyncio.create_task(first_runtime.tick())
    await coordinator.entered.wait()
    second = asyncio.create_task(second_runtime.tick())
    await asyncio.sleep(0.01)
    assert coordinator.calls == 1
    coordinator.release.set()
    await asyncio.gather(first, second)
    assert coordinator.calls == 1
    await second_runtime.tick()
    assert coordinator.calls == 2


async def test_inconsistent_job_record_does_not_block_other_meeting(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    broken_id = create_meeting(store)
    valid_id = create_meeting(store)
    record = store.read_record(OWNER, broken_id)
    payload = json.loads(record.model_dump_json())
    payload["jobs"] = []
    path = (
        tmp_path / "users" / str(OWNER) / "meetings" / str(broken_id) / "meeting.json"
    )
    path.write_text(json.dumps(payload))
    gpu = FakeGPUClient(bundle(valid_id))

    await CoordinatorRuntime(store, MeetingCoordinator(store, gpu)).tick()

    assert store.read_record(OWNER, valid_id).jobs[0].job_id == gpu.job.job_id


async def test_runtime_skips_meeting_while_lifecycle_mutation_holds_lock(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    meeting_id = create_meeting(store)
    entered = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with store.lifecycle_lock(OWNER, meeting_id):
            entered.set()
            assert release.wait(timeout=2)

    holder = asyncio.create_task(asyncio.to_thread(hold_lock))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        coordinator = RecordingCoordinator()
        await CoordinatorRuntime(store, coordinator).tick()
        assert coordinator.calls == []
    finally:
        release.set()
        await holder


async def test_corrupt_meeting_does_not_block_other_queued_meeting(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    broken_id = create_meeting(store)
    valid_id = create_meeting(store)
    broken_file = (
        tmp_path / "users" / str(OWNER) / "meetings" / str(broken_id) / "meeting.json"
    )
    broken_file.write_bytes(b"not-json")
    coordinator = RecordingCoordinator()

    await CoordinatorRuntime(store, coordinator).tick()

    assert coordinator.calls == [(OWNER, valid_id)]


class OneMeetingFailsCoordinator(RecordingCoordinator):
    def __init__(self, failing_id: UUID) -> None:
        super().__init__()
        self.failing_id = failing_id

    async def process_once(self, owner_id: UUID, meeting_id: UUID) -> None:
        self.calls.append((owner_id, meeting_id))
        if meeting_id == self.failing_id:
            raise CoordinatorStorageError()


async def test_one_storage_failure_does_not_block_other_meetings(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    failing_id = create_meeting(store)
    other_id = create_meeting(store)
    coordinator = OneMeetingFailsCoordinator(failing_id)

    await CoordinatorRuntime(store, coordinator).tick()

    assert set(coordinator.calls) == {(OWNER, failing_id), (OWNER, other_id)}


async def test_run_forever_repeats_steps_until_cancelled(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    create_meeting(store)
    coordinator = RecordingCoordinator()
    runtime = CoordinatorRuntime(store, coordinator)
    task = asyncio.create_task(runtime.run_forever(0.01))
    try:
        async with asyncio.timeout(1):
            while len(coordinator.calls) < 2:
                await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


class StartupFakeGPU(FakeGPUClient):
    closed = False

    async def aclose(self) -> None:
        self.closed = True


async def test_app_lifespan_resumes_queued_meeting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    meeting_id = create_meeting(LocalArtifactStore(tmp_path))
    gpu = StartupFakeGPU(bundle(meeting_id))
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(
            data_root=tmp_path,
            gpu_api_url="https://gpu.example",
            gpu_api_token=SecretStr("synthetic-token"),
            coordinator_poll_seconds=0.01,
        ),
    )

    def gpu_factory(
        base_url: str, service_token: str, *, timeout: float
    ) -> StartupFakeGPU:
        assert (base_url, service_token, timeout) == (
            "https://gpu.example",
            "synthetic-token",
            30.0,
        )
        return gpu

    monkeypatch.setattr("app.main.GPUClient", gpu_factory)
    app = create_app()

    async with app.router.lifespan_context(app):
        async with asyncio.timeout(1):
            while (
                LocalArtifactStore(tmp_path)
                .read_record(OWNER, meeting_id)
                .jobs[0]
                .job_id
                is None
            ):
                await asyncio.sleep(0.01)

    assert LocalArtifactStore(tmp_path).read_meeting(OWNER, meeting_id).status == (
        "processing"
    )
    assert gpu.closed
