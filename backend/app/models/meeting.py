"""Public meeting fields and private durable coordinator state."""

from datetime import date, datetime, timedelta
from typing import Annotated, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from app.models.insights import ModelVersions, Sha256
from app.models.transcript import (
    NonEmptyText,
    NonNegativeInt,
    PersonName,
    StrictModel,
    VersionedModel,
)

MeetingStatus = Literal["queued", "processing", "review_required", "approved", "failed"]
MeetingStage = Literal[
    "uploading_to_gpu",
    "ingesting",
    "transcribing",
    "diarizing",
    "analyzing",
    "saving_results",
    "exporting",
]
CleanupStatus = Literal["pending", "deleted", "expired"]
LanguageHint = Literal["auto", "ru", "kk", "mixed"]
PublicSourceKind = Literal["uploaded_audio", "browser_recording"]
AudioExtension = Literal[".wav", ".mp3", ".m4a", ".ogg", ".webm"]
VideoExtension = Literal[".mp4", ".mov", ".mkv"]
UploadExtension = AudioExtension | VideoExtension
PositiveInt = Annotated[StrictInt, Field(ge=1)]


class MeetingMetadata(StrictModel):
    title: Annotated[NonEmptyText, Field(max_length=120)]
    meeting_date: date
    timezone: str
    participants: Annotated[list[PersonName], Field(max_length=30)]
    recording_notice_confirmed: StrictBool
    language_hint: LanguageHint = "auto"

    @field_validator("recording_notice_confirmed")
    @classmethod
    def notice_required(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Recording notice confirmation required")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("Invalid IANA timezone") from error
        return value

    @field_validator("participants")
    @classmethod
    def unique_participants(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Participants must be unique")
        return value


class MeetingUploadMetadata(MeetingMetadata):
    source_kind: PublicSourceKind = "uploaded_audio"


class MeetingSource(StrictModel):
    kind: Literal["uploaded_audio", "browser_recording", "demo_fixture"]
    label: Literal["Подготовленный пример · обработка выполнена заранее"] | None = None
    fixture_id: NonEmptyText | None = None

    @model_validator(mode="after")
    def valid_source(self) -> Self:
        if self.kind == "demo_fixture" and (
            self.label is None or self.fixture_id is None
        ):
            raise ValueError("Demo source needs its label and fixture ID")
        if self.kind != "demo_fixture" and (
            self.label is not None or self.fixture_id is not None
        ):
            raise ValueError("Audio source cannot be marked as demo")
        return self


class Failure(StrictModel):
    code: Literal[
        "invalid_audio",
        "processing_failed",
        "storage_failed",
        "source_expired",
        "gpu_unavailable",
        "invalid_result",
    ]
    message: NonEmptyText


class Meeting(MeetingMetadata):
    id: UUID
    created_at: datetime
    updated_at: datetime
    attempt: PositiveInt
    revision: NonNegativeInt
    status: MeetingStatus
    stage: MeetingStage | None
    source_available: StrictBool
    cleanup_status: CleanupStatus
    temporary_expires_at: datetime | None
    source: MeetingSource
    failure: Failure | None

    @field_validator("created_at", "updated_at", "temporary_expires_at")
    @classmethod
    def utc_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("Timestamp must use UTC")
        return value

    @model_validator(mode="after")
    def valid_stage(self) -> Self:
        if self.stage is not None:
            expected = "approved" if self.stage == "exporting" else "processing"
            if self.status != expected:
                raise ValueError("Stage does not match meeting state")
        return self


class JobRecord(StrictModel):
    attempt: PositiveInt
    job_id: UUID | None = None
    # None marks legacy state where a send may have happened before this field existed.
    submit_started: StrictBool | None = None
    result_hash: Sha256 | None = None
    cleanup_status: CleanupStatus = "pending"
    expires_at: datetime | None = None
    receipt_expires_at: datetime | None = None
    ack_pending: bool = False


class MeetingRecord(VersionedModel):
    owner_id: UUID
    meeting: Meeting
    audio_sha256: Sha256 | None
    audio_extension: AudioExtension | None = None
    local_cleanup_status: CleanupStatus
    jobs: list[JobRecord] = Field(default_factory=lambda: list[JobRecord]())

    @model_validator(mode="after")
    def valid_job_history(self) -> Self:
        attempts = {job.attempt for job in self.jobs}
        if (
            not self.jobs
            or len(attempts) != len(self.jobs)
            or any(attempt > self.meeting.attempt for attempt in attempts)
        ):
            raise ValueError("Job history is inconsistent")
        return self


class ArtifactHashes(StrictModel):
    transcript_json: Sha256
    insights_json: Sha256
    transcript_txt: Sha256


class ReadyManifest(VersionedModel):
    owner_id: UUID
    meeting_id: UUID
    attempt: PositiveInt
    job_id: UUID
    result_hash: Sha256
    model_versions: ModelVersions
    artifacts: ArtifactHashes
