from copy import deepcopy
from uuid import UUID

import pytest

from app.services.pipeline_result_adapter import (
    PipelineResultAdapterError,
    adapt_pipeline_result,
)

MEETING_ID = UUID("00000000-0000-4000-8000-000000000101")
JOB_ID = UUID("00000000-0000-4000-8000-000000000202")


def pipeline_transcript() -> dict[str, object]:
    return {
        "audio_path": "/private/pipeline/input.wav",
        "meeting_at": None,
        "timezone": "Asia/Almaty",
        "participants": [],
        "asr_model": "synthetic-asr",
        "utterances": [
            {
                "id": "utterance-001",
                "start_ms": 100,
                "end_ms": 800,
                "speaker_id": "SOURCE_00",
                "text": "Синтетический первый фрагмент.",
            },
            {
                "id": "utterance-002",
                "start_ms": 900,
                "end_ms": 1600,
                "speaker_id": None,
                "text": "Синтетический фрагмент без спикера.",
            },
            {
                "id": "utterance-003",
                "start_ms": 1700,
                "end_ms": 2500,
                "speaker_id": "SOURCE_01",
                "text": "Синтетический заключительный фрагмент.",
            },
        ],
    }


def pipeline_abstraction() -> dict[str, object]:
    return {
        "key_facts": [
            {
                "text": "Синтетический факт.",
                "source_utterance_ids": ["utterance-001"],
                "evidence_quote": "Синтетическая цитата.",
                "needs_review": True,
            }
        ],
        "decisions": [
            {
                "text": "Синтетическое решение.",
                "source_utterance_ids": ["utterance-002"],
                "evidence_quote": "Синтетическая цитата решения.",
                "needs_review": True,
            }
        ],
        "tasks": [
            {
                "action": "Подготовить синтетический результат.",
                "responsible": "Тестовый исполнитель",
                "due_date": None,
                "due_text": "после проверки",
                "source_utterance_ids": ["utterance-003"],
                "evidence_quote": "Синтетическая цитата задачи.",
                "needs_review": True,
            },
            {
                "action": "Проверить результат.",
                "responsible": None,
                "due_date": None,
                "due_text": None,
                "source_utterance_ids": ["utterance-001", "utterance-003"],
                "evidence_quote": "Синтетическая объединенная цитата.",
                "needs_review": True,
            },
        ],
        "meeting_at": None,
        "timezone": "Asia/Almaty",
        "llm_model": "synthetic-analysis",
        "validation_warnings": [],
    }


def pipeline_provenance() -> dict[str, object]:
    return {
        "audio_sha256": "a" * 64,
        "pipeline_code_sha256": "b" * 64,
        "models": {
            "diarization": {
                "repo": "offline/synthetic-diarization",
                "sha": "1" * 40,
            },
            "synthetic-asr": {
                "repo": "offline/synthetic-asr",
                "sha": "2" * 40,
            },
            "synthetic-analysis": {
                "repo": "offline/synthetic-analysis",
                "sha": "3" * 40,
            },
        },
        "reviewed_corrections": {
            "manifest_sha256": "c" * 64,
            "inserted_utterance_ids": ["utterance-002"],
            "replaced_utterance_ids": [],
        },
    }


def test_adapts_pipeline_result_to_deterministic_canonical_bundle() -> None:
    first = adapt_pipeline_result(
        meeting_id=MEETING_ID,
        job_id=JOB_ID,
        transcript=pipeline_transcript(),
        abstraction=pipeline_abstraction(),
        provenance=pipeline_provenance(),
    )
    second = adapt_pipeline_result(
        meeting_id=MEETING_ID,
        job_id=JOB_ID,
        transcript=pipeline_transcript(),
        abstraction=pipeline_abstraction(),
        provenance=pipeline_provenance(),
    )

    assert first == second
    assert first.transcript.meeting_id == MEETING_ID
    assert first.transcript.revision == 0
    assert [speaker.speaker_id for speaker in first.transcript.speakers] == [
        "speaker_1",
        "speaker_2",
        "speaker_3",
    ]
    assert all(
        speaker.identity_status == "unreviewed"
        and speaker.display_name is None
        for speaker in first.transcript.speakers
    )
    assert all(
        segment.language == "unknown" and not segment.edited
        for segment in first.transcript.segments
    )
    assert len(first.insights.summary) == 2
    assert len(first.insights.action_items) == 2
    assert first.insights.summary[0].evidence[0].start_ms == 100
    assert first.insights.summary[0].evidence[0].end_ms == 800
    assert first.insights.action_items[0].assignee_speaker_id is None
    assert first.insights.action_items[0].assignee_name == "Тестовый исполнитель"
    assert first.insights.action_items[0].due_date is None
    assert first.insights.action_items[0].due_date_text == "после проверки"
    assert first.insights.action_items[1].assignee_name is None
    assert len(first.insights.action_items[1].evidence) == 2
    assert first.model_versions.asr == f"synthetic-asr@{'2' * 40}"
    assert first.model_versions.diarization == f"diarization@{'1' * 40}"
    assert first.model_versions.analysis == f"synthetic-analysis@{'3' * 40}"
    public_bundle = first.model_dump(mode="json")
    assert "audio_path" not in str(public_bundle)
    assert "reviewed_corrections" not in str(public_bundle)


def test_rejects_unknown_evidence_reference_without_echoing_it() -> None:
    abstraction = pipeline_abstraction()
    key_facts = abstraction["key_facts"]
    assert isinstance(key_facts, list)
    first_fact = key_facts[0]
    assert isinstance(first_fact, dict)
    first_fact["source_utterance_ids"] = ["private-missing-id"]

    with pytest.raises(PipelineResultAdapterError) as caught:
        adapt_pipeline_result(
            meeting_id=MEETING_ID,
            job_id=JOB_ID,
            transcript=pipeline_transcript(),
            abstraction=abstraction,
            provenance=pipeline_provenance(),
        )

    assert "private-missing-id" not in str(caught.value)


def test_rejects_invalid_utterance_interval_without_echoing_content() -> None:
    transcript = deepcopy(pipeline_transcript())
    utterances = transcript["utterances"]
    assert isinstance(utterances, list)
    first_utterance = utterances[0]
    assert isinstance(first_utterance, dict)
    first_utterance["end_ms"] = first_utterance["start_ms"]

    with pytest.raises(PipelineResultAdapterError) as caught:
        adapt_pipeline_result(
            meeting_id=MEETING_ID,
            job_id=JOB_ID,
            transcript=transcript,
            abstraction=pipeline_abstraction(),
            provenance=pipeline_provenance(),
        )

    assert "Синтетический первый фрагмент" not in str(caught.value)
