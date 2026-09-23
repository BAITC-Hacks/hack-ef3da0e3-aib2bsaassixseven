import json
import re
from datetime import UTC, date
from hashlib import sha256

from ml_pipeline import abstraction, asr, audio, diarization, runtime
from ml_pipeline.audio import SpeechInterval
from ml_pipeline.catalog import MODELS
from ml_pipeline.models import AbstractionOutput, Transcript


def test_one_command_pipeline_writes_three_outputs_with_absolute_times(
    tmp_path, monkeypatch
):
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"synthetic audio")
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    selected = ("diarization", "gigaam-ctc", "qwen3.5-9b")
    manifest = {}
    for name in selected:
        (models_dir / name).mkdir()
        manifest[name] = {"repo": MODELS[name].repo, "sha": "synthetic-sha"}
    (models_dir / "models.lock.json").write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(runtime, "ZoneInfo", lambda name: UTC)
    monkeypatch.setattr(
        audio, "convert_to_wav", lambda src, dst: dst.write_bytes(b"wav")
    )
    monkeypatch.setattr(audio, "read_wav", lambda path: [0.0] * 16000)
    monkeypatch.setattr(
        audio, "vad_intervals", lambda samples: [SpeechInterval(1000, 4000)]
    )
    monkeypatch.setattr(
        audio, "write_clip", lambda samples, interval, path: path.write_bytes(b"clip")
    )
    monkeypatch.setattr(
        diarization,
        "diarize",
        lambda path, model: [
            SpeechInterval(0, 2000, "SPEAKER_00"),
            SpeechInterval(2000, 5000, "SPEAKER_01"),
        ],
    )

    class FakeASR:
        def transcribe(self, path):
            return "Ерлан подготовит отчёт до 2 октября."

    monkeypatch.setattr(asr, "load_asr", lambda name, path: FakeASR())

    class FakeQwen:
        def __init__(self, path, name):
            pass

        def generate(self, prompt):
            return json.dumps(
                {
                    "key_facts": [],
                    "decisions": [],
                    "tasks": [
                        {
                            "action": "Подготовить отчёт",
                            "responsible": "Ерлан",
                            "due_date": None,
                            "due_text": "2 октября",
                            "source_utterance_ids": ["u00001"],
                            "evidence_quote": "Ерлан подготовит отчёт до 2 октября.",
                            "needs_review": False,
                        },
                    ],
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(abstraction, "LocalQwen", FakeQwen)
    output_dir = tmp_path / "out"
    runtime.run_pipeline(
        runtime.RunConfig(
            audio=source,
            output_dir=output_dir,
            meeting_at="2026-09-23T10:00:00",
            timezone="UTC",
            participants=["Ерлан"],
            asr_model="gigaam-ctc",
            llm_model="qwen3.5-9b",
            models_dir=models_dir,
        )
    )
    transcript = Transcript.model_validate_json(
        (output_dir / "transcript.json").read_text(encoding="utf-8")
    )
    result = AbstractionOutput.model_validate_json(
        (output_dir / "abstraction.json").read_text(encoding="utf-8")
    )
    summary = (output_dir / "summary.md").read_text(encoding="utf-8")
    provenance = json.loads(
        (output_dir / "provenance.json").read_text(encoding="utf-8")
    )
    pipeline_code_sha = provenance.pop("pipeline_code_sha256")
    assert re.fullmatch(r"[0-9a-f]{64}", pipeline_code_sha)
    assert provenance == {
        "audio_sha256": sha256(source.read_bytes()).hexdigest(),
        "models": {
            name: {"repo": MODELS[name].repo, "sha": "synthetic-sha"}
            for name in selected
        },
    }
    assert [(u.start_ms, u.end_ms, u.speaker_id) for u in transcript.utterances] == [
        (1000, 2000, "SPEAKER_00"),
        (2000, 4000, "SPEAKER_01"),
    ]
    assert result.tasks[0].due_date == date(2026, 10, 2)
    assert "Ерлан подготовит отчёт до 2 октября." in summary
    assert "- Подготовить отчёт" not in summary
