"""Coordinator contracts exercised against durable temporary storage."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from test_artifact_store import bundle, metadata

from app.models.gpu import AckV1, GPUContextV1, JobV1
from app.models.insights import ResultBundleV1
from app.models.meeting import Failure, Meeting
from app.services.artifact_store import LocalArtifactStore, MeetingNotFound
from app.services.coordinator import CoordinatorStorageError, MeetingCoordinator
from app.services.gpu_client import (
    GPUClient,
    GPUDomainError,
    GPUProtocolError,
    GPUUnavailable,
)
from app.services.lifecycle import retry_meeting


class FakeGPUClient(GPUClient):
    """Only the external GPU operations are replaced; all artifacts are real."""

    def __init__(self, result: ResultBundleV1) -> None:
        self.result = result
        self.job = JobV1(
            job_id=result.job_id,
            status="queued",
            stage=None,
            failure=None,
            result_hash=None,
            cleanup_status="pending",
            expires_at=datetime.now(UTC) + timedelta(hours=24),
            receipt_expires_at=None,
        )
        self.error: Exception | None = None
        self.lookup: JobV1 | Exception = GPUDomainError(404, "job_not_found")
        self.calls: list[str] = []
        self.contexts: list[GPUContextV1] = []
        self.audio_extensions: list[str | None] = []

    def check(self, operation: str) -> None:
        self.calls.append(operation)
        if self.error is not None:
            raise self.error

    async def submit(
        self,
        audio_path: Path,
        context: GPUContextV1,
        *,
        audio_extension: str | None = None,
    ) -> JobV1:
        assert audio_path.read_bytes() == b"synthetic audio"
        self.audio_extensions.append(audio_extension)
        self.contexts.append(context)
        self.check("submit")
        return self.job

    async def get_job(self, job_id: UUID) -> JobV1:
        assert job_id == self.job.job_id
        self.check("poll")
        return self.job

    async def get_job_by_key(self, meeting_id: UUID, attempt: int) -> JobV1:
        assert meeting_id == self.result.transcript.meeting_id
        assert attempt in {1, 2, 3}
        self.calls.append("lookup")
        if isinstance(self.lookup, Exception):
            raise self.lookup
        return self.lookup

    async def get_result(self, job_id: UUID) -> ResultBundleV1:
        assert job_id == self.job.job_id
        self.check("result")
        return self.result

    async def ack(self, job_id: UUID, result_hash: str) -> AckV1:
        assert job_id == self.job.job_id
        assert result_hash == self.result.result_hash
        self.check("ack")
        return AckV1(
            job_id=job_id,
            result_hash=result_hash,
            cleanup_status="deleted",
            receipt_expires_at=datetime.now(UTC) + timedelta(days=7),
        )


@pytest.fixture
def setup(tmp_path: Path) -> tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient]:
    store = LocalArtifactStore(tmp_path)
    owner = uuid4()
    meeting = store.create_meeting(owner, metadata(), b"synthetic audio")
    return store, owner, meeting, FakeGPUClient(bundle(meeting.id))


async def test_submit_uses_persisted_audio_extension_after_reload(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path)
    owner = uuid4()
    meeting = store.create_meeting(
        owner, metadata(), b"synthetic audio", audio_extension=".webm"
    )
    gpu = FakeGPUClient(bundle(meeting.id))
    coordinator = MeetingCoordinator(LocalArtifactStore(tmp_path), gpu)
    await coordinator.process_once(owner, meeting.id)
    assert gpu.audio_extensions == [".webm"]


async def test_submit_timeout_resumes_same_context_and_attempt(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
) -> None:
    store, owner, meeting, gpu = setup
    gpu.error = GPUUnavailable("timeout")
    coordinator = MeetingCoordinator(store, gpu)
    first = await coordinator.process_once(owner, meeting.id)
    assert (first.status, first.stage, first.attempt) == (
        "processing",
        "uploading_to_gpu",
        1,
    )
    assert first.failure is None
    assert store.read_record(owner, meeting.id).jobs[0].job_id is None
    gpu.error = None
    resumed = MeetingCoordinator(LocalArtifactStore(store.root), gpu)
    second = await resumed.process_once(owner, meeting.id)
    assert second.status == "processing"
    assert second.attempt == 1
    assert store.read_record(owner, meeting.id).jobs[0].job_id == gpu.job.job_id
    assert gpu.contexts[0] == gpu.contexts[1]
    context = gpu.contexts[0]
    assert context.meeting_id == meeting.id
    assert context.attempt == 1
    assert context.timezone == "Asia/Almaty"
    assert context.participants == ["Алия"]
    assert context.audio_sha256 == store.read_record(owner, meeting.id).audio_sha256
    assert gpu.calls == ["submit", "lookup", "submit"]


async def test_timeout_lookup_binds_existing_job_without_resubmitting_audio(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
) -> None:
    store, owner, meeting, gpu = setup
    gpu.error = GPUUnavailable("timeout")
    await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    gpu.error = None
    gpu.lookup = gpu.job

    coordinator = MeetingCoordinator(LocalArtifactStore(store.root), gpu)
    resumed = await coordinator.process_once(owner, meeting.id)

    assert resumed.status == "processing"
    assert store.read_record(owner, meeting.id).jobs[0].job_id == gpu.job.job_id
    assert gpu.calls == ["submit", "lookup"]
    assert len(gpu.contexts) == 1


async def test_legacy_unknown_submit_looks_up_existing_job_before_posting(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
) -> None:
    store, owner, meeting, gpu = setup
    record = store.read_record(owner, meeting.id)
    record.jobs[0].submit_started = None
    record.meeting.status = "processing"
    record.meeting.stage = "uploading_to_gpu"
    store.update_meeting(owner, record)
    gpu.lookup = gpu.job

    resumed = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)

    assert resumed.status == "processing"
    assert store.read_record(owner, meeting.id).jobs[0].job_id == gpu.job.job_id
    assert gpu.calls == ["lookup"]
    assert gpu.contexts == []


async def test_pending_reservation_waits_without_resubmitting_audio(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
) -> None:
    store, owner, meeting, gpu = setup
    gpu.error = GPUUnavailable("timeout")
    await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    gpu.error = None
    gpu.lookup = GPUDomainError(409, "submission_pending")

    for _ in range(2):
        result = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
        assert (result.status, result.stage) == ("processing", "uploading_to_gpu")
    assert store.read_record(owner, meeting.id).jobs[0].job_id is None
    assert gpu.calls == ["submit", "lookup", "lookup"]


async def test_lookup_can_recover_completed_job_after_local_source_deadline(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
) -> None:
    store, owner, meeting, gpu = setup
    gpu.error = GPUUnavailable("timeout")
    await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    gpu.error = None
    complete(gpu)
    gpu.lookup = gpu.job
    record = store.read_record(owner, meeting.id)
    record.meeting.temporary_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    store.update_meeting(owner, record)

    result = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)

    assert result.status == "review_required"
    assert store.read_results(owner, meeting.id)[0] == gpu.result.transcript
    assert gpu.calls == ["submit", "lookup", "result", "ack"]


@pytest.mark.parametrize(
    "stage", ["ingesting", "transcribing", "diarizing", "analyzing"]
)
async def test_poll_persists_actual_gpu_stage(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient], stage: str
) -> None:
    store, owner, meeting, gpu = setup
    coordinator = MeetingCoordinator(store, gpu)
    await coordinator.process_once(owner, meeting.id)
    gpu.job = JobV1.model_validate(
        {**gpu.job.model_dump(), "status": "processing", "stage": stage}
    )
    result = await coordinator.process_once(owner, meeting.id)
    assert (result.status, result.stage) == ("processing", stage)
    assert store.read_meeting(owner, meeting.id).stage == stage
    assert gpu.calls == ["submit", "poll"]


async def test_wrong_owner_never_reaches_gpu(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
) -> None:
    store, _owner, meeting, gpu = setup
    with pytest.raises(MeetingNotFound):
        await MeetingCoordinator(store, gpu).process_once(uuid4(), meeting.id)
    assert gpu.calls == []


def complete(gpu: FakeGPUClient) -> None:
    gpu.job = gpu.job.model_copy(
        update={
            "status": "completed",
            "stage": None,
            "result_hash": gpu.result.result_hash,
        }
    )


async def test_completed_publication_and_local_removal_precede_ack(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, owner, meeting, gpu = setup
    coordinator = MeetingCoordinator(store, gpu)
    await coordinator.process_once(owner, meeting.id)
    source = store.upload_path(owner, meeting.id)
    complete(gpu)
    original_ack = gpu.ack

    async def inspect_ack(job_id: UUID, result_hash: str) -> AckV1:
        assert store.read_results(owner, meeting.id)[0] == gpu.result.transcript
        assert store.read_manifest(owner, meeting.id).result_hash == result_hash
        assert store.read_meeting(owner, meeting.id).status == "review_required"
        assert not source.exists()
        assert store.read_record(owner, meeting.id).local_cleanup_status == "deleted"
        return await original_ack(job_id, result_hash)

    monkeypatch.setattr(gpu, "ack", inspect_ack)
    result = await coordinator.process_once(owner, meeting.id)
    assert (result.status, result.stage, result.cleanup_status) == (
        "review_required",
        None,
        "deleted",
    )
    assert not result.source_available
    record = store.read_record(owner, meeting.id)
    assert not record.jobs[0].ack_pending
    assert record.jobs[0].receipt_expires_at is not None
    assert gpu.calls == ["submit", "poll", "result", "ack"]
    await coordinator.process_once(owner, meeting.id)
    assert gpu.calls == ["submit", "poll", "result", "ack"]


@pytest.mark.parametrize("failure_point", ["insights.json", "manifest_sync"])
async def test_storage_failure_never_acks_and_resume_reestablishes_durability(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    store, owner, meeting, gpu = setup
    coordinator = MeetingCoordinator(store, gpu)
    await coordinator.process_once(owner, meeting.id)
    complete(gpu)
    folder = store.upload_path(owner, meeting.id).parent
    original_write = store._atomic_write  # pyright: ignore[reportPrivateUsage]
    original_sync = store._sync_directory  # pyright: ignore[reportPrivateUsage]

    def write(path: Path, data: bytes, *, immutable: bool = False) -> None:
        if path.name == failure_point:
            raise OSError("private disk detail")
        original_write(path, data, immutable=immutable)

    def sync(path: Path) -> None:
        if failure_point == "manifest_sync" and (folder / "manifest.json").exists():
            raise OSError("private sync detail")
        original_sync(path)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_atomic_write", write)
        patch.setattr(store, "_sync_directory", sync)
        for _ in range(2):
            result = await MeetingCoordinator(store, gpu).process_once(
                owner, meeting.id
            )
            assert result.failure is None
            assert "ack" not in gpu.calls
            assert (folder / "upload.bin").exists()
            if failure_point == "insights.json":
                assert (result.status, result.stage) == ("processing", "saving_results")
            else:
                assert (folder / "manifest.json").exists()
    result = await MeetingCoordinator(LocalArtifactStore(store.root), gpu).process_once(
        owner, meeting.id
    )
    assert (result.status, result.cleanup_status) == ("review_required", "deleted")
    assert gpu.calls.count("ack") == 1


@pytest.mark.parametrize("reason", ["service_unavailable", "timeout", "unauthorized"])
async def test_published_result_resumes_ack_without_poll_or_fetch(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
    reason: str,
) -> None:
    store, owner, meeting, gpu = setup
    await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    store.publish_results(owner, meeting.id, gpu.result)
    gpu.calls.clear()
    gpu.error = GPUUnavailable(reason)
    for _ in range(2):
        ready = await MeetingCoordinator(
            LocalArtifactStore(store.root), gpu
        ).process_once(owner, meeting.id)
        assert ready.status == "review_required"
        assert ready.cleanup_status == "pending"
        assert ready.failure is None
        assert not ready.source_available
        assert store.read_results(owner, meeting.id)[0] == gpu.result.transcript
        assert store.read_record(owner, meeting.id).jobs[0].ack_pending
    gpu.error = None
    ready = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    assert ready.cleanup_status == "deleted"
    assert gpu.calls == ["ack", "ack", "ack"]


async def test_local_unlink_failure_does_not_hide_result_or_gpu_cleanup(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, owner, meeting, gpu = setup
    await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    complete(gpu)
    source = store.upload_path(owner, meeting.id)
    original = Path.unlink

    def unlink(path: Path, missing_ok: bool = False) -> None:
        if path == source:
            raise OSError("private unlink failure")
        original(path, missing_ok=missing_ok)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", unlink)
        ready = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
        assert ready.status == "review_required"
        assert ready.cleanup_status == "pending"
        assert ready.source_available
        record = store.read_record(owner, meeting.id)
        assert record.local_cleanup_status == "pending"
        assert record.jobs[0].cleanup_status == "deleted"
    ready = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    assert ready.cleanup_status == "deleted"
    assert not source.exists()
    assert gpu.calls.count("ack") == 1


@pytest.mark.parametrize("cleanup", ["pending", "expired"])
async def test_expired_gpu_without_local_result_fails_safely(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
    cleanup: str,
) -> None:
    store, owner, meeting, gpu = setup
    coordinator = MeetingCoordinator(store, gpu)
    await coordinator.process_once(owner, meeting.id)
    gpu.job = JobV1.model_validate(
        {
            **gpu.job.model_dump(),
            "status": "expired",
            "cleanup_status": cleanup,
            "receipt_expires_at": (
                datetime.now(UTC) + timedelta(days=7)
                if cleanup == "expired"
                else None
            ),
        }
    )
    result = await coordinator.process_once(owner, meeting.id)
    assert (result.status, result.stage) == ("failed", None)
    assert result.failure is not None and result.failure.code == "source_expired"
    assert result.cleanup_status == "pending"  # Local source has not been removed.
    assert store.read_record(owner, meeting.id).jobs[0].cleanup_status == cleanup
    calls = list(gpu.calls)
    await coordinator.process_once(owner, meeting.id)
    assert gpu.calls == calls + (["poll"] if cleanup == "pending" else [])


async def test_failed_gpu_message_is_never_exposed(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
) -> None:
    store, owner, meeting, gpu = setup
    await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    gpu.job = JobV1.model_validate(
        {
            **gpu.job.model_dump(),
            "status": "failed",
            "failure": {
                "code": "invalid_audio",
                "message": "private transcript path token",
            },
        }
    )
    result = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    assert result.status == "failed"
    assert result.failure is not None and result.failure.code == "invalid_audio"
    assert "private" not in result.model_dump_json()
    assert "private" not in store.read_record(owner, meeting.id).model_dump_json()


@pytest.mark.parametrize(
    "kind", ["meeting", "job", "hash", "reference", "protocol", "poll_hash"]
)
async def test_invalid_result_never_publishes_or_acks(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    from app.services.artifact_store import ArtifactNotReady
    from app.services.gpu_client import GPUProtocolError

    store, owner, meeting, gpu = setup
    await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    complete(gpu)
    if kind == "meeting":
        gpu.result = bundle(uuid4())
    elif kind == "job":
        gpu.result = bundle(meeting.id)
    elif kind == "hash":
        gpu.result = gpu.result.model_copy(update={"result_hash": "0" * 64})
    elif kind == "reference":
        gpu.result.insights.summary[0].evidence[0].segment_id = uuid4()
    elif kind == "poll_hash":
        gpu.job.result_hash = "0" * 64
    else:

        async def invalid(_job_id: UUID) -> ResultBundleV1:
            raise GPUProtocolError()

        monkeypatch.setattr(gpu, "get_result", invalid)
    result = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    assert (result.status, result.stage) == ("failed", None)
    assert result.failure is not None and result.failure.code == "invalid_result"
    assert "ack" not in gpu.calls
    with pytest.raises(ArtifactNotReady):
        store.read_results(owner, meeting.id)
    assert store.upload_path(owner, meeting.id).exists()


@pytest.mark.parametrize("operation", ["submit", "poll", "result"])
@pytest.mark.parametrize(
    "reason", ["timeout", "connection", "service_unavailable", "unauthorized"]
)
async def test_transient_gpu_errors_preserve_attempt_and_progress(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    reason: str,
) -> None:
    store, owner, meeting, gpu = setup
    coordinator = MeetingCoordinator(store, gpu)
    if operation != "submit":
        await coordinator.process_once(owner, meeting.id)
    if operation == "result":
        complete(gpu)

        async def unavailable(_job_id: UUID) -> ResultBundleV1:
            raise GPUUnavailable(reason)

        monkeypatch.setattr(gpu, "get_result", unavailable)
    else:
        gpu.error = GPUUnavailable(reason)
    result = await coordinator.process_once(owner, meeting.id)
    assert result.status == "processing"
    assert result.failure is None
    assert result.attempt == 1
    job = store.read_record(owner, meeting.id).jobs[0]
    assert job.job_id == (None if operation == "submit" else gpu.job.job_id)
    assert "ack" not in gpu.calls


async def test_local_deadline_blocks_resubmit_after_uncertain_timeout(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
) -> None:
    store, owner, meeting, gpu = setup
    gpu.error = GPUUnavailable("timeout")
    await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    record = store.read_record(owner, meeting.id)
    record.meeting.temporary_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    store.update_meeting(owner, record)
    result = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    assert result.status == "failed"
    assert result.failure is not None and result.failure.code == "source_expired"
    assert result.attempt == 1
    assert gpu.calls == ["submit", "lookup"]
    assert store.read_record(owner, meeting.id).jobs[0].cleanup_status == "pending"


async def test_missing_receipt_keeps_ready_result_and_cleanup_pending(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
) -> None:
    from app.services.gpu_client import GPUDomainError

    store, owner, meeting, gpu = setup
    store.publish_results(owner, meeting.id, gpu.result)
    gpu.error = GPUDomainError(404, "job_not_found")
    result = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    assert result.status == "review_required"
    assert result.cleanup_status == "pending"
    assert store.read_record(owner, meeting.id).jobs[0].ack_pending
    assert store.read_results(owner, meeting.id)[0] == gpu.result.transcript


async def test_source_expired_domain_error_fails_without_resubmit(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
) -> None:
    from app.services.gpu_client import GPUDomainError

    store, owner, meeting, gpu = setup
    await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    gpu.error = GPUDomainError(410, "source_expired")
    result = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    assert result.status == "failed"
    assert result.failure is not None and result.failure.code == "source_expired"
    assert gpu.calls == ["submit", "poll"]


async def test_local_cleanup_sync_failure_stays_pending_until_retry(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, owner, meeting, gpu = setup
    store.publish_results(owner, meeting.id, gpu.result)
    source = store.upload_path(owner, meeting.id)
    original = store._sync_directory  # pyright: ignore[reportPrivateUsage]
    failed = False

    def fail_after_unlink(path: Path) -> None:
        nonlocal failed
        if path == source.parent and not source.exists() and not failed:
            failed = True
            raise OSError("private sync detail")
        original(path)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_sync_directory", fail_after_unlink)
        result = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
        assert failed
        assert result.status == "review_required"
        assert result.cleanup_status == "pending"
        assert store.read_record(owner, meeting.id).local_cleanup_status == "pending"
        assert store.read_record(owner, meeting.id).jobs[0].cleanup_status == "deleted"
    result = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    assert result.cleanup_status == "deleted"
    assert gpu.calls == ["ack"]


async def test_storage_read_error_has_no_private_details(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, owner, meeting, gpu = setup
    original = store._read  # pyright: ignore[reportPrivateUsage]

    def fail_read(path: Path) -> bytes:
        if path.name == "meeting.json":
            raise OSError("private recording path")
        return original(path)

    monkeypatch.setattr(store, "_read", fail_read)
    with pytest.raises(CoordinatorStorageError) as caught:
        await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    assert "private" not in str(caught.value)
    assert gpu.calls == []


@pytest.mark.parametrize("approved", [False, True])
async def test_expired_ack_receipt_confirms_cleanup_without_changing_ready_state(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
    monkeypatch: pytest.MonkeyPatch,
    approved: bool,
) -> None:
    store, owner, meeting, gpu = setup
    store.publish_results(owner, meeting.id, gpu.result)
    if approved:
        record = store.read_record(owner, meeting.id)
        record.meeting.status = "approved"
        store.update_meeting(owner, record)
    original = gpu.ack

    async def expired(job_id: UUID, result_hash: str) -> AckV1:
        receipt = await original(job_id, result_hash)
        return receipt.model_copy(update={"cleanup_status": "expired"})

    monkeypatch.setattr(gpu, "ack", expired)
    result = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)
    assert result.status == ("approved" if approved else "review_required")
    assert result.cleanup_status == "expired"
    assert result.failure is None


@pytest.mark.parametrize("cleanup", ["deleted", "expired"])
async def test_failed_job_reconciles_confirmed_remote_cleanup_without_ack(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
    cleanup: str,
) -> None:
    store, owner, meeting, gpu = setup
    record = store.read_record(owner, meeting.id)
    record.meeting.status = "failed"
    record.meeting.failure = Failure(
        code="processing_failed", message="Не удалось обработать запись"
    )
    record.jobs[0].job_id = gpu.job.job_id
    record.jobs[0].result_hash = gpu.result.result_hash
    record.jobs[0].ack_pending = True
    store.delete_upload(owner, meeting.id)
    record.local_cleanup_status = "deleted"
    record.meeting.source_available = False
    store.update_meeting(owner, record)
    gpu.job = JobV1.model_validate(
        {
            **gpu.job.model_dump(),
            "status": "completed" if cleanup == "deleted" else "expired",
            "result_hash": gpu.result.result_hash if cleanup == "deleted" else None,
            "cleanup_status": cleanup,
            "receipt_expires_at": datetime.now(UTC) + timedelta(days=7),
        }
    )

    result = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)

    persisted = LocalArtifactStore(store.root).read_record(owner, meeting.id)
    assert result.status == "failed"
    assert result.failure == record.meeting.failure
    assert result.cleanup_status == cleanup
    assert persisted.jobs[0].cleanup_status == cleanup
    assert persisted.jobs[0].receipt_expires_at == gpu.job.receipt_expires_at
    assert not persisted.jobs[0].ack_pending
    assert gpu.calls == ["poll"]


async def test_retry_reconciles_old_job_without_changing_current_attempt(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, owner, meeting, gpu = setup
    old_job_id = uuid4()
    record = store.read_record(owner, meeting.id)
    record.meeting.status = "failed"
    record.meeting.failure = Failure(
        code="processing_failed", message="Не удалось обработать запись"
    )
    record.jobs[0].job_id = old_job_id
    store.update_meeting(owner, record)
    retry_meeting(store, owner, meeting.id)
    old_remote = gpu.job.model_copy(
        update={
            "job_id": old_job_id,
            "status": "expired",
            "cleanup_status": "expired",
        }
    )

    async def old_receipt(job_id: UUID) -> JobV1:
        assert job_id == old_job_id
        gpu.calls.append("poll")
        return old_remote

    monkeypatch.setattr(gpu, "get_job", old_receipt)
    result = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)

    persisted = LocalArtifactStore(store.root).read_record(owner, meeting.id)
    assert result.attempt == 2 and result.status == "processing"
    assert persisted.jobs[0].cleanup_status == "expired"
    assert persisted.jobs[1].job_id == gpu.job.job_id
    assert persisted.meeting.cleanup_status == "pending"
    assert gpu.calls == ["poll", "submit"]


@pytest.mark.parametrize(
    "error",
    [
        GPUDomainError(404, "job_not_found"),
        GPUUnavailable("timeout"),
        GPUProtocolError(),
    ],
)
async def test_failed_job_without_cleanup_receipt_stays_pending(
    setup: tuple[LocalArtifactStore, UUID, Meeting, FakeGPUClient],
    error: Exception,
) -> None:
    store, owner, meeting, gpu = setup
    record = store.read_record(owner, meeting.id)
    record.meeting.status = "failed"
    record.meeting.failure = Failure(
        code="processing_failed", message="Не удалось обработать запись"
    )
    record.jobs[0].job_id = gpu.job.job_id
    store.delete_upload(owner, meeting.id)
    record.local_cleanup_status = "deleted"
    record.meeting.source_available = False
    store.update_meeting(owner, record)
    gpu.error = error

    result = await MeetingCoordinator(store, gpu).process_once(owner, meeting.id)

    assert result.status == "failed" and result.cleanup_status == "pending"
    assert store.read_record(owner, meeting.id).jobs[0].cleanup_status == "pending"
    assert gpu.calls == ["poll"]
