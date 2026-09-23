"""Strict wire models for the backend-only NVIDIA inference API."""

from datetime import date, datetime, timedelta
from typing import Annotated, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, StrictInt, field_validator, model_validator

from app.models.insights import Sha256
from app.models.meeting import LanguageHint
from app.models.transcript import NonEmptyText, PersonName, StrictModel, VersionedModel

PositiveInt = Annotated[StrictInt, Field(ge=1)]


class GPUContextV1(VersionedModel):
    meeting_id: UUID
    attempt: PositiveInt
    meeting_date: date
    timezone: str
    participants: Annotated[list[PersonName], Field(max_length=30)]
    language_hint: LanguageHint
    audio_sha256: Sha256

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


class GPUFailure(StrictModel):
    code: Literal[
        "invalid_audio", "processing_failed", "storage_failed", "source_expired"
    ]
    message: NonEmptyText


class JobV1(StrictModel):
    job_id: UUID
    status: Literal["queued", "processing", "completed", "failed", "expired"]
    stage: Literal["ingesting", "transcribing", "diarizing", "analyzing"] | None
    failure: GPUFailure | None
    result_hash: Sha256 | None
    cleanup_status: Literal["pending", "deleted", "expired"]
    expires_at: datetime
    receipt_expires_at: datetime | None

    @field_validator("expires_at", "receipt_expires_at")
    @classmethod
    def utc_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("Timestamp must use UTC")
        return value

    @model_validator(mode="after")
    def valid_stage(self) -> Self:
        if self.stage is not None and self.status != "processing":
            raise ValueError("GPU stage requires processing status")
        if self.status == "completed" and self.result_hash is None:
            raise ValueError("Completed GPU job requires result hash")
        if self.status in {"queued", "processing"} and self.result_hash is not None:
            raise ValueError("GPU job has result hash before completion")
        if self.cleanup_status == "pending" and self.receipt_expires_at is not None:
            raise ValueError("Pending GPU cleanup cannot have a receipt")
        if self.cleanup_status != "pending" and (
            self.receipt_expires_at is None
            or self.status in {"queued", "processing"}
        ):
            raise ValueError("Confirmed GPU cleanup requires a terminal receipt")
        return self


class AckV1(StrictModel):
    job_id: UUID
    result_hash: Sha256
    cleanup_status: Literal["deleted", "expired"]
    receipt_expires_at: datetime

    @field_validator("receipt_expires_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("Timestamp must use UTC")
        return value
