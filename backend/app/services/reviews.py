"""Durable, owner-scoped human review of immutable machine results."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self, cast
from uuid import UUID

from pydantic import Field, ValidationError, model_validator

from app.models.insights import ActionItem, InsightsV1, SummaryItem
from app.models.meeting import Meeting
from app.models.transcript import (
    NonEmptyText,
    NonNegativeInt,
    Speaker,
    SpeakerId,
    StrictModel,
    TranscriptV1,
    VersionedModel,
)
from app.services.artifact_store import ArtifactIntegrityError, LocalArtifactStore


class ReviewConflict(Exception):
    """A review operation is incompatible with the committed meeting state."""

    def __init__(
        self, code: Literal["stale_revision", "invalid_state", "review_required"]
    ) -> None:
        self.code = code
        super().__init__(code)


class ReviewValidationError(Exception):
    """The review refers to missing or inconsistent result data."""


class SegmentEdit(StrictModel):
    segment_id: UUID
    text: NonEmptyText | None = None
    speaker_id: SpeakerId | None = None

    @model_validator(mode="after")
    def has_edit(self) -> Self:
        if self.text is None and self.speaker_id is None:
            raise ValueError("A segment edit needs text or a speaker")
        return self


class ReviewRequest(StrictModel):
    base_revision: NonNegativeInt
    speaker_mappings: list[Speaker]
    segment_edits: list[SegmentEdit]
    summary: list[SummaryItem]
    action_items: list[ActionItem]


class ApprovalRequest(StrictModel):
    base_revision: NonNegativeInt


class ReviewSnapshot(VersionedModel):
    meeting_id: UUID
    revision: Annotated[int, Field(ge=1)]
    speaker_mappings: list[Speaker]
    segment_edits: list[SegmentEdit]
    summary: list[SummaryItem]
    action_items: list[ActionItem]


def _overlay(
    original: TranscriptV1, snapshot: ReviewSnapshot
) -> tuple[TranscriptV1, InsightsV1]:
    speaker_ids = {speaker.speaker_id for speaker in original.speakers}
    mappings = {speaker.speaker_id: speaker for speaker in snapshot.speaker_mappings}
    if len(mappings) != len(snapshot.speaker_mappings) or set(mappings) != speaker_ids:
        raise ReviewValidationError("Speaker mappings must cover each voice once")

    original_segments = {segment.id: segment for segment in original.segments}
    edits = {edit.segment_id: edit for edit in snapshot.segment_edits}
    if len(edits) != len(snapshot.segment_edits):
        raise ReviewValidationError("Duplicate segment edit")
    if set(edits) - set(original_segments):
        raise ReviewValidationError("Unknown segment")
    if any(
        edit.speaker_id is not None and edit.speaker_id not in speaker_ids
        for edit in edits.values()
    ):
        raise ReviewValidationError("Unknown segment speaker")

    transcript_data = original.model_dump(mode="python")
    transcript_data["revision"] = snapshot.revision
    transcript_data["speakers"] = snapshot.speaker_mappings
    segments = cast(list[dict[str, object]], transcript_data["segments"])
    for segment in segments:
        edit = edits.get(cast(UUID, segment["id"]))
        if edit is not None:
            if edit.text is not None:
                segment["text"] = edit.text
            if edit.speaker_id is not None:
                segment["speaker_id"] = edit.speaker_id
            segment["edited"] = True
    try:
        transcript = TranscriptV1.model_validate(transcript_data)
        insights = InsightsV1(
            schema_version=1,
            meeting_id=original.meeting_id,
            revision=snapshot.revision,
            summary=snapshot.summary,
            action_items=snapshot.action_items,
        )
        insights.validate_against(transcript)
    except (ValidationError, ValueError) as error:
        raise ReviewValidationError("Invalid review results") from error
    return transcript, insights


def _snapshot_path(
    store: LocalArtifactStore, owner_id: UUID, meeting_id: UUID, revision: int
) -> Path:
    return store._check(  # pyright: ignore[reportPrivateUsage]
        store.review_path(owner_id, meeting_id).with_name(f"review-{revision}.json")
    )


def _read_current_locked(
    store: LocalArtifactStore, owner_id: UUID, meeting_id: UUID, meeting: Meeting
) -> tuple[TranscriptV1, InsightsV1]:
    if meeting.status not in {"review_required", "approved"}:
        raise ReviewConflict("invalid_state")
    original, insights = store.read_results(owner_id, meeting_id)
    if meeting.revision == 0:
        return original, insights
    try:
        snapshot = ReviewSnapshot.model_validate_json(
            store._read(  # pyright: ignore[reportPrivateUsage]
                _snapshot_path(store, owner_id, meeting_id, meeting.revision)
            )
        )
        if snapshot.meeting_id != meeting_id or snapshot.revision != meeting.revision:
            raise ArtifactIntegrityError("Review identity mismatch")
        return _overlay(original, snapshot)
    except FileNotFoundError as error:
        raise ArtifactIntegrityError("Committed review is missing") from error
    except (ValidationError, ReviewValidationError) as error:
        raise ArtifactIntegrityError("Committed review is invalid") from error


def read_reviewed_results(
    store: LocalArtifactStore, owner_id: UUID, meeting_id: UUID
) -> tuple[TranscriptV1, InsightsV1]:
    """Read one committed revision while excluding edit and export transactions."""
    with store.lifecycle_lock(owner_id, meeting_id):
        return read_reviewed_results_unlocked(store, owner_id, meeting_id)


def read_reviewed_results_unlocked(
    store: LocalArtifactStore, owner_id: UUID, meeting_id: UUID
) -> tuple[TranscriptV1, InsightsV1]:
    """Read a revision when the caller already holds the lifecycle lock."""
    meeting = store.read_record(owner_id, meeting_id).meeting
    return _read_current_locked(store, owner_id, meeting_id, meeting)


def update_review(
    store: LocalArtifactStore,
    owner_id: UUID,
    meeting_id: UUID,
    request: ReviewRequest,
) -> Meeting:
    """Replace all edits and publish their revision after durable snapshot writes."""
    with store.lifecycle_lock(owner_id, meeting_id):
        record = store.read_record(owner_id, meeting_id)
        meeting = record.meeting
        if meeting.status not in {"review_required", "approved"}:
            raise ReviewConflict("invalid_state")
        if request.base_revision != meeting.revision:
            raise ReviewConflict("stale_revision")
        original, _ = store.read_results(owner_id, meeting_id)
        next_revision = meeting.revision + 1
        snapshot = ReviewSnapshot(
            schema_version=1,
            meeting_id=meeting_id,
            revision=next_revision,
            speaker_mappings=request.speaker_mappings,
            segment_edits=request.segment_edits,
            summary=request.summary,
            action_items=request.action_items,
        )
        _overlay(original, snapshot)
        payload = snapshot.model_dump_json().encode("utf-8")
        # An interrupted earlier PUT may have left an uncommitted file for
        # this revision. The lock and old marker make replacement safe.
        store._atomic_write(  # pyright: ignore[reportPrivateUsage]
            _snapshot_path(store, owner_id, meeting_id, next_revision), payload
        )
        # This convenience copy may run ahead of the marker after a crash.
        # Readers always select the immutable snapshot by meeting.revision.
        store._atomic_write(  # pyright: ignore[reportPrivateUsage]
            store.review_path(owner_id, meeting_id), payload
        )
        if meeting.status == "approved":
            # Delete and sync before publishing the new marker. If cleanup
            # fails, the old approval remains committed. A missing cache can
            # be regenerated from the old review snapshot.
            store.delete_pdf_cache(owner_id, meeting_id, meeting.revision)
        record.meeting = meeting.model_copy(
            update={
                "revision": next_revision,
                "status": "review_required",
                "stage": None,
                "updated_at": datetime.now(UTC),
            }
        )
        return store.update_meeting(owner_id, record)


def approve_review(
    store: LocalArtifactStore,
    owner_id: UUID,
    meeting_id: UUID,
    request: ApprovalRequest,
) -> Meeting:
    """Approve exactly the revision that the client inspected."""
    with store.lifecycle_lock(owner_id, meeting_id):
        record = store.read_record(owner_id, meeting_id)
        meeting = record.meeting
        if meeting.status != "review_required":
            raise ReviewConflict("invalid_state")
        if request.base_revision != meeting.revision:
            raise ReviewConflict("stale_revision")
        transcript, insights = _read_current_locked(
            store, owner_id, meeting_id, meeting
        )
        if any(
            speaker.identity_status == "unreviewed" for speaker in transcript.speakers
        ):
            raise ReviewConflict("review_required")
        try:
            insights.validate_against(transcript)
        except ValueError as error:
            raise ReviewConflict("review_required") from error
        record.meeting = meeting.model_copy(
            update={"status": "approved", "updated_at": datetime.now(UTC)}
        )
        return store.update_meeting(owner_id, record)
