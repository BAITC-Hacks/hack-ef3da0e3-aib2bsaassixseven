"""Generate small synthetic output files without loading speech or LLM models."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ml_pipeline.abstraction import (
    finalize_deadlines,
    render_summary,
    validate_evidence,
)
from ml_pipeline.models import (
    Abstraction,
    AbstractionOutput,
    EvidenceItem,
    Task,
    Transcript,
    Utterance,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    meeting_at = datetime(2026, 9, 23, 10, tzinfo=timezone(timedelta(hours=5)))
    utterances = [
        Utterance(
            id="u00001",
            start_ms=1000,
            end_ms=4200,
            speaker_id="SPEAKER_00",
            text="Загрузка цеха — 71 процент.",
        ),
        Utterance(
            id="u00002",
            start_ms=4500,
            end_ms=8200,
            speaker_id="SPEAKER_01",
            text="Ерлан, подготовьте отчёт до 30 сентября.",
        ),
        Utterance(
            id="u00003",
            start_ms=8600,
            end_ms=12000,
            speaker_id="SPEAKER_01",
            text="Уточняю: срок отчёта переносим на 2 октября.",
        ),
        Utterance(
            id="u00004",
            start_ms=13000,
            end_ms=16500,
            speaker_id="SPEAKER_00",
            text="Проверьте договор на следующей неделе.",
        ),
    ]
    transcript = Transcript(
        audio_path="synthetic-demo.wav",
        meeting_at=meeting_at,
        timezone="Asia/Qyzylorda",
        participants=["Ерлан"],
        asr_model="synthetic",
        utterances=utterances,
    )
    abstraction = Abstraction(
        key_facts=[
            EvidenceItem(
                text="Загрузка цеха — 71 процент",
                source_utterance_ids=["u00001"],
                evidence_quote="Загрузка цеха — 71 процент.",
            )
        ],
        decisions=[
            EvidenceItem(
                text="Срок отчёта перенесён на 2 октября",
                source_utterance_ids=["u00003"],
                evidence_quote="срок отчёта переносим на 2 октября",
            )
        ],
        tasks=[
            Task(
                action="Подготовить отчёт",
                responsible="Ерлан",
                due_text="2 октября",
                source_utterance_ids=["u00002", "u00003"],
                evidence_quote="подготовьте отчёт",
            ),
            Task(
                action="Проверить договор",
                responsible=None,
                due_text="на следующей неделе",
                source_utterance_ids=["u00004"],
                evidence_quote="Проверьте договор на следующей неделе.",
                needs_review=True,
            ),
        ],
    )
    validate_evidence(abstraction, utterances)
    finalize_deadlines(abstraction, meeting_at)
    output = AbstractionOutput(
        **abstraction.model_dump(),
        meeting_at=meeting_at,
        timezone="Asia/Qyzylorda",
        llm_model="synthetic",
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "transcript.json").write_text(
        transcript.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "abstraction.json").write_text(
        output.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "summary.md").write_text(
        render_summary(abstraction), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
