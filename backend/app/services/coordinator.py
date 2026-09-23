"""One durable coordination step; scheduling is owned by the caller."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError

from app.models.gpu import GPUContextV1
from app.models.insights import ResultBundleV1
from app.models.meeting import CleanupStatus, Failure, Meeting, MeetingRecord
from app.services.artifact_store import (
    ArtifactIntegrityError,
    ArtifactNotReady,
    LocalArtifactStore,
    UnsafePath,
)
from app.services.gpu_client import (
    GPUClient,
    GPUClientError,
    GPUDomainError,
    GPUInputError,
    GPUProtocolError,
    GPUUnavailable,
)

_FAILURES = {
    "invalid_audio": Failure(
        code="invalid_audio", message="Не удалось прочитать аудиозапись"
    ),
    "processing_failed": Failure(
        code="processing_failed", message="Не удалось обработать запись"
    ),
    "storage_failed": Failure(
        code="storage_failed", message="Не удалось сохранить результат"
    ),
    "source_expired": Failure(
        code="source_expired", message="Срок хранения исходной записи истёк"
    ),
    "invalid_result": Failure(
        code="invalid_result", message="Получен некорректный результат обработки"
    ),
}


class CoordinatorStorageError(Exception):
    """A durable state could not be read; safe for a scheduler to report."""

    def __init__(self) -> None:
        super().__init__("Meeting storage unavailable")


class MeetingCoordinator:
    def __init__(self, store: LocalArtifactStore, gpu: GPUClient) -> None:
        self.store = store
        self.gpu = gpu

    async def process_once(self, owner_id: UUID, meeting_id: UUID) -> Meeting:
        """Advance one meeting; caller must serialize calls for this meeting.

        Network and recoverable write failures retain the durable operation for
        the next call. No scheduling, attempt increment, or GPU restart occurs.
        """
        try:
            return await self._process(owner_id, meeting_id)
        except (OSError, UnsafePath, ArtifactIntegrityError):
            raise CoordinatorStorageError() from None

    async def _process(self, owner_id: UUID, meeting_id: UUID) -> Meeting:
        record = self.store.read_record(owner_id, meeting_id)
        await self._reconcile_pending_jobs(record)
        try:
            try:
                return await self._advance(record)
            except (GPUProtocolError, ValidationError, ArtifactIntegrityError):
                return self._fail(record, "invalid_result")
            except GPUInputError:
                return self._fail(record, "source_expired")
            except GPUDomainError as error:
                if error.code in {"source_expired", "payload_deleted"}:
                    return self._fail(record, "source_expired")
                if error.code in {"job_not_found", "result_not_ready"}:
                    return self.store.read_meeting(owner_id, meeting_id)
                code = (
                    "invalid_audio"
                    if error.status_code in {413, 415}
                    else "processing_failed"
                )
                return self._fail(record, code)
        except (GPUUnavailable, OSError):
            return self.store.read_meeting(owner_id, meeting_id)

    async def _reconcile_pending_jobs(self, record: MeetingRecord) -> None:
        """Confirm old/failed GPU cleanup without retrieving results or sending ACK."""
        changed = False
        for job in record.jobs:
            if job.job_id is None or job.cleanup_status != "pending":
                continue
            current = job.attempt == record.meeting.attempt
            if current and record.meeting.status in {"queued", "processing"}:
                continue
            if (
                current
                and record.meeting.status in {"review_required", "approved"}
                and job.ack_pending
            ):
                continue
            try:
                remote = await self.gpu.get_job(job.job_id)
            except GPUClientError:
                continue
            if remote.job_id != job.job_id or remote.cleanup_status == "pending":
                continue
            job.cleanup_status = remote.cleanup_status
            job.receipt_expires_at = remote.receipt_expires_at
            job.ack_pending = False
            changed = True
        if changed:
            record.meeting.cleanup_status = self._cleanup_status(record)
            self._save(record)

    async def _advance(self, record: MeetingRecord) -> Meeting:
        owner_id, meeting = record.owner_id, record.meeting
        meeting_id = meeting.id
        if meeting.status == "failed":
            return self.store.read_meeting(owner_id, meeting_id)
        job = next(job for job in record.jobs if job.attempt == meeting.attempt)
        try:
            manifest = self.store.read_manifest(owner_id, meeting_id)
        except ArtifactNotReady:
            pass
        else:
            transcript, insights = self.store.read_results(owner_id, meeting_id)
            bundle = ResultBundleV1(
                schema_version=1,
                job_id=manifest.job_id,
                transcript=transcript,
                insights=insights,
                model_versions=manifest.model_versions,
                result_hash=manifest.result_hash,
            )
            # Reading a visible manifest does not prove its prior fsync succeeded.
            self.store.publish_results(owner_id, meeting_id, bundle)
            return await self._cleanup(self.store.read_record(owner_id, meeting_id))
        if job.job_id is None:
            meeting.status = "processing"
            meeting.stage = "uploading_to_gpu"
            self._save(record)
            remote = None
            if job.submit_started is not False:
                try:
                    remote = await self.gpu.get_job_by_key(meeting_id, meeting.attempt)
                except GPUDomainError as error:
                    if error.code == "submission_pending":
                        return self.store.read_meeting(owner_id, meeting_id)
                    if error.code != "job_not_found":
                        raise
            if remote is None:
                if record.audio_sha256 is None:
                    return self._fail(record, "source_expired")
                try:
                    audio_path = self.store.upload_path(owner_id, meeting_id)
                except FileNotFoundError:
                    return self._fail(record, "source_expired")
                context = GPUContextV1(
                    schema_version=1,
                    meeting_id=meeting_id,
                    attempt=meeting.attempt,
                    meeting_date=meeting.meeting_date,
                    timezone=meeting.timezone,
                    participants=meeting.participants,
                    language_hint=meeting.language_hint,
                    audio_sha256=record.audio_sha256,
                )
                job.submit_started = True
                self._save(record)
                remote = await self.gpu.submit(
                    audio_path, context, audio_extension=record.audio_extension
                )
        else:
            remote = await self.gpu.get_job(job.job_id)
        if job.job_id is not None and job.job_id != remote.job_id:
            raise GPUProtocolError()
        job.job_id = remote.job_id
        job.cleanup_status = remote.cleanup_status
        job.expires_at = remote.expires_at
        job.receipt_expires_at = remote.receipt_expires_at
        if remote.status == "expired":
            return self._fail(record, "source_expired")
        if remote.status == "failed":
            return self._fail(
                record, remote.failure.code if remote.failure else "processing_failed"
            )
        meeting.status = "processing"
        meeting.stage = (
            "saving_results" if remote.status == "completed" else remote.stage
        )
        self._save(record)
        if remote.status == "completed":
            bundle = await self.gpu.get_result(remote.job_id)
            if (
                bundle.job_id != remote.job_id
                or bundle.transcript.meeting_id != meeting_id
                or bundle.result_hash != remote.result_hash
            ):
                raise GPUProtocolError()
            self.store.publish_results(owner_id, meeting_id, bundle)
            return await self._cleanup(self.store.read_record(owner_id, meeting_id))
        return self.store.read_meeting(owner_id, meeting_id)

    async def _cleanup(self, record: MeetingRecord) -> Meeting:
        job = next(job for job in record.jobs if job.attempt == record.meeting.attempt)
        if record.local_cleanup_status == "pending":
            try:
                self.store.delete_upload(record.owner_id, record.meeting.id)
            except OSError:
                pass
            else:
                record.local_cleanup_status = "deleted"
                record.meeting.source_available = False
            self._save(record)
        if job.ack_pending and job.job_id is not None and job.result_hash is not None:
            try:
                receipt = await self.gpu.ack(job.job_id, job.result_hash)
            except GPUClientError:
                pass
            else:
                job.cleanup_status = receipt.cleanup_status
                job.receipt_expires_at = receipt.receipt_expires_at
                job.ack_pending = False
        record.meeting.cleanup_status = self._cleanup_status(record)
        return self._save(record)

    @staticmethod
    def _cleanup_status(record: MeetingRecord) -> CleanupStatus:
        statuses = [
            record.local_cleanup_status,
            *(job.cleanup_status for job in record.jobs),
        ]
        if "pending" in statuses:
            return "pending"
        return "expired" if "expired" in statuses else "deleted"

    def _fail(self, record: MeetingRecord, code: str) -> Meeting:
        record.meeting.stage = None
        record.meeting.status = "failed"
        record.meeting.failure = _FAILURES[code].model_copy()
        return self._save(record)

    def _save(self, record: MeetingRecord) -> Meeting:
        record.meeting.updated_at = datetime.now(UTC)
        return self.store.update_meeting(record.owner_id, record)
