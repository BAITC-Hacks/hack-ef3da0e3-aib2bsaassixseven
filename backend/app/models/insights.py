"""Evidence-backed insights and validated immutable GPU result bundles."""

import hashlib
import json
from datetime import date
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from app.models.transcript import (
    NonEmptyText,
    NonNegativeInt,
    PersonName,
    SpeakerId,
    StrictModel,
    TranscriptV1,
    VersionedModel,
)

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


class Evidence(StrictModel):
    segment_id: UUID
    start_ms: NonNegativeInt
    end_ms: NonNegativeInt

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if self.start_ms >= self.end_ms:
            raise ValueError("Evidence interval must be positive")
        return self


class SummaryItem(StrictModel):
    id: UUID
    text: NonEmptyText
    evidence: Annotated[list[Evidence], Field(min_length=1)]


class ActionItem(SummaryItem):
    assignee_speaker_id: SpeakerId | None
    assignee_name: PersonName | None
    due_date: date | None
    due_date_text: NonEmptyText | None

    @model_validator(mode="after")
    def valid_assignee(self) -> Self:
        if self.assignee_speaker_id is not None and self.assignee_name is not None:
            raise ValueError("Choose a speaker or an external assignee")
        return self


class InsightsV1(VersionedModel):
    meeting_id: UUID
    revision: NonNegativeInt
    summary: list[SummaryItem]
    action_items: list[ActionItem]

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        for items in (self.summary, self.action_items):
            if len({item.id for item in items}) != len(items):
                raise ValueError("Duplicate insight ID")
        return self

    def validate_against(self, transcript: TranscriptV1) -> None:
        if (self.meeting_id, self.revision) != (
            transcript.meeting_id,
            transcript.revision,
        ):
            raise ValueError("Insights and transcript must share meeting and revision")
        segments = {segment.id: segment for segment in transcript.segments}
        speakers = {speaker.speaker_id for speaker in transcript.speakers}
        for item in [*self.summary, *self.action_items]:
            for evidence in item.evidence:
                segment = segments.get(evidence.segment_id)
                if segment is None or not (
                    segment.start_ms
                    <= evidence.start_ms
                    < evidence.end_ms
                    <= segment.end_ms
                ):
                    raise ValueError("Evidence must reference and fit its segment")
        for item in self.action_items:
            if (
                item.assignee_speaker_id is not None
                and item.assignee_speaker_id not in speakers
            ):
                raise ValueError("Unknown assignee speaker")


class ModelVersions(StrictModel):
    asr: NonEmptyText
    diarization: NonEmptyText
    analysis: NonEmptyText


class ResultBundleV1(VersionedModel):
    job_id: UUID
    transcript: TranscriptV1
    insights: InsightsV1
    model_versions: ModelVersions
    result_hash: Sha256

    @model_validator(mode="after")
    def valid_machine_bundle(self) -> Self:
        self.insights.validate_against(self.transcript)
        if self.transcript.revision != 0 or self.insights.revision != 0:
            raise ValueError("Machine output must have revision zero")
        if any(segment.edited for segment in self.transcript.segments):
            raise ValueError("Machine segments cannot be edited")
        if any(
            speaker.identity_status != "unreviewed"
            for speaker in self.transcript.speakers
        ):
            raise ValueError("Machine speaker identities must be unreviewed")
        payload = self.model_dump(mode="json", exclude={"result_hash"})
        if hashlib.sha256(canonical_json(payload)).hexdigest() != self.result_hash:
            raise ValueError("Result hash mismatch")
        return self
