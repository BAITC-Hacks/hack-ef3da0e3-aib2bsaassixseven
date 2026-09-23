"""Synchronous, owner-scoped retry and deletion transitions."""

from datetime import UTC, datetime
from uuid import UUID

from app.models.meeting import JobRecord, Meeting
from app.services.artifact_store import LocalArtifactStore


class LifecycleConflict(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def retry_meeting(
    store: LocalArtifactStore, owner_id: UUID, meeting_id: UUID
) -> Meeting:
    with store.lifecycle_lock(owner_id, meeting_id):
        record = store.read_record(owner_id, meeting_id)
        if record.meeting.status != "failed":
            raise LifecycleConflict("invalid_state")
        if record.meeting.attempt >= 3:
            raise LifecycleConflict("attempts_exhausted")
        if not store.read_meeting(owner_id, meeting_id).source_available:
            raise LifecycleConflict("source_expired")
        next_attempt = record.meeting.attempt + 1
        record.meeting.attempt = next_attempt
        record.meeting.status = "queued"
        record.meeting.stage = None
        record.meeting.failure = None
        record.meeting.revision = 0
        record.meeting.updated_at = datetime.now(UTC)
        record.jobs.append(JobRecord(attempt=next_attempt, submit_started=False))
        record.meeting.cleanup_status = "pending"
        return store.update_meeting(owner_id, record)


def delete_meeting(store: LocalArtifactStore, owner_id: UUID, meeting_id: UUID) -> None:
    with store.lifecycle_lock(owner_id, meeting_id):
        record = store.read_record(owner_id, meeting_id)
        if record.meeting.status in {"queued", "processing"} or record.meeting.stage:
            raise LifecycleConflict("invalid_state")
        if (
            record.meeting.cleanup_status == "pending"
            or record.local_cleanup_status == "pending"
            or store.upload_present(owner_id, meeting_id)
            or any(
                job.cleanup_status == "pending" or job.ack_pending
                for job in record.jobs
            )
        ):
            raise LifecycleConflict("cleanup_pending")
        store.delete_meeting(owner_id, meeting_id)
