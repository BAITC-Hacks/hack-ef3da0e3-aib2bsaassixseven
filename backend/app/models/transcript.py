"""Public transcript schema; speaker labels remain stable across human reviews."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("Text must not be blank")
    return value


NonEmptyText = Annotated[
    str, StringConstraints(min_length=1), AfterValidator(_non_blank)
]
PersonName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
SpeakerId = Annotated[str, StringConstraints(pattern=r"^speaker_[1-9][0-9]*$")]
NonNegativeInt = Annotated[StrictInt, Field(ge=0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class VersionedModel(StrictModel):
    schema_version: Literal[1]

    @field_validator("schema_version", mode="before")
    @classmethod
    def version_is_integer_one(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("Unsupported schema version")
        return value


class Speaker(StrictModel):
    speaker_id: SpeakerId
    display_name: PersonName | None
    identity_status: Literal["unreviewed", "named", "unknown"]

    @model_validator(mode="after")
    def valid_identity(self) -> Self:
        if (self.identity_status == "named") != (self.display_name is not None):
            raise ValueError("Only named speakers have a display name")
        return self


class Segment(StrictModel):
    id: UUID
    start_ms: NonNegativeInt
    end_ms: NonNegativeInt
    speaker_id: SpeakerId
    language: Literal["ru", "kk", "unknown"]
    text: NonEmptyText
    edited: StrictBool

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if self.start_ms >= self.end_ms:
            raise ValueError("Segment interval must be positive")
        return self


class TranscriptV1(VersionedModel):
    meeting_id: UUID
    revision: NonNegativeInt
    speakers: list[Speaker]
    segments: list[Segment]

    @model_validator(mode="after")
    def valid_references(self) -> Self:
        speakers = {speaker.speaker_id for speaker in self.speakers}
        if len(speakers) != len(self.speakers):
            raise ValueError("Duplicate speaker ID")
        if len({segment.id for segment in self.segments}) != len(self.segments):
            raise ValueError("Duplicate segment ID")
        if any(segment.speaker_id not in speakers for segment in self.segments):
            raise ValueError("Unknown segment speaker")
        starts = [segment.start_ms for segment in self.segments]
        if starts != sorted(starts):
            raise ValueError("Segments must be ordered by start time")
        return self
