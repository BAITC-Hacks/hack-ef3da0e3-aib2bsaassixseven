"""Convert the offline pipeline result shape into the canonical API bundle.

The adapter is intentionally pure: it does not read files, persist artifacts, or log
pipeline content. Pipeline-local paths and review sidecars are validated when present
but never copied into the returned public result bundle.
"""

import hashlib
from collections.abc import Mapping
from datetime import date, datetime
from typing import Annotated, Self
from uuid import UUID, uuid5

from pydantic import (
    Field,
    StrictBool,
    StringConstraints,
    ValidationError,
    model_validator,
)

from app.models.insights import (
    ActionItem,
    Evidence,
    InsightsV1,
    ModelVersions,
    ResultBundleV1,
    SummaryItem,
    canonical_json,
)
from app.models.transcript import (
    NonEmptyText,
    NonNegativeInt,
    PersonName,
    Segment,
    Speaker,
    StrictModel,
    TranscriptV1,
)

GitSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{40}$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ModelName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class PipelineResultAdapterError(ValueError):
    """A pipeline payload cannot be converted without violating the contract."""


class _PipelineUtterance(StrictModel):
    id: NonEmptyText
    start_ms: NonNegativeInt
    end_ms: NonNegativeInt
    speaker_id: NonEmptyText | None
    text: NonEmptyText

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if self.start_ms >= self.end_ms:
            raise ValueError("Utterance interval must be positive")
        return self


class _PipelineTranscript(StrictModel):
    # Known pipeline-only metadata is accepted so the real result can be passed
    # directly. None of these fields, especially audio_path, reaches the output.
    audio_path: NonEmptyText | None = None
    meeting_at: datetime | None = None
    timezone: NonEmptyText | None = None
    participants: list[PersonName] = Field(default_factory=list)
    asr_model: ModelName | None = None
    utterances: Annotated[list[_PipelineUtterance], Field(min_length=1)]

    @model_validator(mode="after")
    def valid_utterances(self) -> Self:
        ids = [utterance.id for utterance in self.utterances]
        if len(set(ids)) != len(ids):
            raise ValueError("Utterance IDs must be unique")
        starts = [utterance.start_ms for utterance in self.utterances]
        if starts != sorted(starts):
            raise ValueError("Utterances must be ordered by start time")
        return self


class _PipelineInsight(StrictModel):
    text: NonEmptyText
    source_utterance_ids: Annotated[list[NonEmptyText], Field(min_length=1)]
    evidence_quote: NonEmptyText
    needs_review: StrictBool

    @model_validator(mode="after")
    def unique_sources(self) -> Self:
        if len(set(self.source_utterance_ids)) != len(self.source_utterance_ids):
            raise ValueError("Evidence references must be unique")
        return self


class _PipelineTask(StrictModel):
    action: NonEmptyText
    responsible: PersonName | None
    due_date: date | None
    due_text: NonEmptyText | None
    source_utterance_ids: Annotated[list[NonEmptyText], Field(min_length=1)]
    evidence_quote: NonEmptyText
    needs_review: StrictBool

    @model_validator(mode="after")
    def unique_sources(self) -> Self:
        if len(set(self.source_utterance_ids)) != len(self.source_utterance_ids):
            raise ValueError("Evidence references must be unique")
        return self


class _PipelineAbstraction(StrictModel):
    key_facts: list[_PipelineInsight]
    decisions: list[_PipelineInsight]
    tasks: list[_PipelineTask]
    meeting_at: datetime | None = None
    timezone: NonEmptyText | None = None
    llm_model: ModelName | None = None
    validation_warnings: list[NonEmptyText] = Field(default_factory=list)


class _PipelineModel(StrictModel):
    repo: NonEmptyText
    sha: GitSha


class _PipelineCorrections(StrictModel):
    manifest_sha256: Sha256
    inserted_utterance_ids: list[NonEmptyText]
    replaced_utterance_ids: list[NonEmptyText]


class _PipelineProvenance(StrictModel):
    audio_sha256: Sha256 | None = None
    pipeline_code_sha256: Sha256 | None = None
    models: Annotated[dict[ModelName, _PipelineModel], Field(min_length=1)]
    reviewed_corrections: _PipelineCorrections | None = None


def _parse_inputs(
    transcript: Mapping[str, object],
    abstraction: Mapping[str, object],
    provenance: Mapping[str, object],
) -> tuple[_PipelineTranscript, _PipelineAbstraction, _PipelineProvenance]:
    try:
        return (
            _PipelineTranscript.model_validate(transcript),
            _PipelineAbstraction.model_validate(abstraction),
            _PipelineProvenance.model_validate(provenance),
        )
    except ValidationError:
        # Pydantic's default error includes rejected input values. Do not leak
        # transcript or participant content through this public boundary.
        raise PipelineResultAdapterError(
            "Pipeline result does not match the supported schema"
        ) from None


def _model_version(
    models: Mapping[str, _PipelineModel],
    *,
    requested_name: str | None,
    role: str,
) -> str:
    name = requested_name if requested_name is not None else role
    model = models.get(name)
    if model is None:
        raise PipelineResultAdapterError(f"Missing {role} model provenance")
    # The repository URL is intentionally excluded from public artifacts.
    return f"{name}@{model.sha.lower()}"


def _evidence_for(
    source_ids: list[str],
    segments_by_source_id: Mapping[str, Segment],
) -> list[Evidence]:
    evidence: list[Evidence] = []
    for source_id in source_ids:
        segment = segments_by_source_id.get(source_id)
        if segment is None:
            raise PipelineResultAdapterError(
                "Insight references an unknown transcript segment"
            )
        evidence.append(
            Evidence(
                segment_id=segment.id,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
            )
        )
    return evidence


def adapt_pipeline_result(
    *,
    meeting_id: UUID,
    job_id: UUID,
    transcript: Mapping[str, object],
    abstraction: Mapping[str, object],
    provenance: Mapping[str, object],
) -> ResultBundleV1:
    """Return a validated revision-zero bundle from an offline pipeline result.

    Source utterance, speaker, and insight identifiers are normalized within the
    meeting namespace, making repeated conversion of the same input deterministic.
    Responsibility strings remain external assignee names; the adapter never guesses
    participant identity from diarization labels.
    """

    source_transcript, source_abstraction, source_provenance = _parse_inputs(
        transcript, abstraction, provenance
    )

    speaker_ids: dict[str | None, str] = {}
    speakers: list[Speaker] = []
    segments: list[Segment] = []
    segments_by_source_id: dict[str, Segment] = {}

    for utterance in source_transcript.utterances:
        if utterance.speaker_id not in speaker_ids:
            normalized = f"speaker_{len(speaker_ids) + 1}"
            speaker_ids[utterance.speaker_id] = normalized
            speakers.append(
                Speaker(
                    speaker_id=normalized,
                    display_name=None,
                    identity_status="unreviewed",
                )
            )
        segment = Segment(
            id=uuid5(meeting_id, f"pipeline-segment:{utterance.id}"),
            start_ms=utterance.start_ms,
            end_ms=utterance.end_ms,
            speaker_id=speaker_ids[utterance.speaker_id],
            language="unknown",
            text=utterance.text,
            edited=False,
        )
        segments.append(segment)
        segments_by_source_id[utterance.id] = segment

    canonical_transcript = TranscriptV1(
        schema_version=1,
        meeting_id=meeting_id,
        revision=0,
        speakers=speakers,
        segments=segments,
    )

    summary: list[SummaryItem] = []
    for category, items in (
        ("key-fact", source_abstraction.key_facts),
        ("decision", source_abstraction.decisions),
    ):
        for index, item in enumerate(items):
            summary.append(
                SummaryItem(
                    id=uuid5(
                        meeting_id,
                        f"pipeline-summary:{category}:{index}",
                    ),
                    text=item.text,
                    evidence=_evidence_for(
                        item.source_utterance_ids, segments_by_source_id
                    ),
                )
            )

    action_items: list[ActionItem] = []
    for index, task in enumerate(source_abstraction.tasks):
        action_items.append(
            ActionItem(
                id=uuid5(meeting_id, f"pipeline-task:{index}"),
                text=task.action,
                evidence=_evidence_for(
                    task.source_utterance_ids, segments_by_source_id
                ),
                assignee_speaker_id=None,
                assignee_name=task.responsible,
                due_date=task.due_date,
                due_date_text=task.due_text,
            )
        )

    canonical_insights = InsightsV1(
        schema_version=1,
        meeting_id=meeting_id,
        revision=0,
        summary=summary,
        action_items=action_items,
    )
    model_versions = ModelVersions(
        asr=_model_version(
            source_provenance.models,
            requested_name=source_transcript.asr_model,
            role="asr",
        ),
        diarization=_model_version(
            source_provenance.models,
            requested_name=None,
            role="diarization",
        ),
        analysis=_model_version(
            source_provenance.models,
            requested_name=source_abstraction.llm_model,
            role="analysis",
        ),
    )

    payload: dict[str, object] = {
        "schema_version": 1,
        "job_id": str(job_id),
        "transcript": canonical_transcript.model_dump(mode="json"),
        "insights": canonical_insights.model_dump(mode="json"),
        "model_versions": model_versions.model_dump(mode="json"),
    }
    payload["result_hash"] = hashlib.sha256(canonical_json(payload)).hexdigest()
    try:
        return ResultBundleV1.model_validate(payload)
    except ValidationError:
        raise PipelineResultAdapterError(
            "Pipeline result could not be converted to a canonical bundle"
        ) from None
