import json

import pytest

from ml_pipeline import compare, runtime
from ml_pipeline.compare import error_rate, score_asr_pairs, score_tasks


def test_error_rate_aggregates_edits():
    assert error_rate([("один два", "один три")], unit="word") == 0.5
    assert error_rate([("аб", "ав")], unit="char") == 0.5


def test_task_errors_are_counted_separately():
    reference = [
        {
            "action": "Подготовить отчёт",
            "responsible": "Ерлан",
            "due_date": "2026-10-01",
        },
        {"action": "Проверить договор", "responsible": "Айжан", "due_date": None},
    ]
    predicted = [
        {
            "action": "Подготовить отчёт",
            "responsible": "Айжан",
            "due_date": "2026-10-02",
        },
    ]
    assert score_tasks(reference, predicted) == {
        "reference_tasks": 2,
        "missed_tasks": 1,
        "false_positive_tasks": 0,
        "responsible_errors": 1,
        "deadline_errors": 1,
    }


def test_unmatched_predictions_are_false_positive_tasks():
    reference = [{"action": "Подготовить отчёт", "responsible": None, "due_date": None}]
    predicted = [
        {"action": "Подготовить отчёт", "responsible": None, "due_date": None},
        {"action": "Отменённое поручение", "responsible": None, "due_date": None},
    ]
    assert score_tasks(reference, predicted)["false_positive_tasks"] == 1
    assert score_tasks([], predicted)["false_positive_tasks"] == 2


def test_relative_deadline_errors_are_scored_when_dates_are_unknown():
    reference = [
        {
            "action": "Найти альтернативного поставщика",
            "responsible": "Батагоз",
            "due_date": None,
            "due_text": "неделя максимум десять дней",
        }
    ]
    predicted = [
        {
            "action": "Найти альтернативного поставщика",
            "responsible": "Батагоз",
            "due_date": None,
            "due_text": "за две недели",
        }
    ]
    assert score_tasks(reference, predicted)["deadline_errors"] == 1
    predicted[0]["due_text"] = "Неделя, максимум десять дней!"
    assert score_tasks(reference, predicted)["deadline_errors"] == 0


def test_due_text_label_is_optional_and_does_not_override_matching_dates():
    reference = [
        {
            "action": "Подготовить отчёт",
            "responsible": None,
            "due_date": "2026-10-01",
            "due_text": "к первому октября",
        }
    ]
    predicted = [
        {
            "action": "Подготовить отчёт",
            "responsible": None,
            "due_date": "2026-10-01",
            "due_text": "до 1 октября",
        }
    ]
    assert score_tasks(reference, predicted)["deadline_errors"] == 0
    reference[0]["due_date"] = None
    reference[0].pop("due_text")
    predicted[0]["due_date"] = None
    assert score_tasks(reference, predicted)["deadline_errors"] == 0
    reference[0]["due_text"] = None
    assert score_tasks(reference, predicted)["deadline_errors"] == 1


def test_asr_scores_are_separate_by_language():
    scores = score_asr_pairs(
        {
            "ru": [("один два", "один три")],
            "kk": [("бір екі", "бір екі")],
            "mixed": [("есеп готов", "есеп готов")],
        }
    )
    assert scores["ru"]["wer"] == 0.5
    assert scores["kk"]["wer"] == 0.0
    assert scores["mixed"]["wer"] == 0.0


def test_compare_manifest_uses_same_recordings_for_candidates(tmp_path, monkeypatch):
    manifest = {
        "recordings": [
            {
                "audio": "meeting.wav",
                "timezone": "UTC",
                "reference_utterances": [
                    {
                        "language": "ru",
                        "start_ms": 0,
                        "end_ms": 1000,
                        "text": "один два",
                    },
                ],
                "reference_tasks": [
                    {
                        "action": "Подготовить отчёт",
                        "responsible": "Ерлан",
                        "due_date": None,
                    },
                ],
            }
        ]
    }
    manifest_path = tmp_path / "reference.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "meeting.wav").write_bytes(b"synthetic audio")
    seen = []

    def fake_run(config):
        seen.append((config.audio.name, config.asr_model, config.llm_model))
        config.output_dir.mkdir(parents=True)
        (config.output_dir / "abstraction.json").write_text(
            json.dumps(
                {
                    "tasks": [
                        {
                            "action": "Подготовить отчёт",
                            "responsible": "Ерлан",
                            "due_date": None,
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        (config.output_dir / "provenance.json").write_text(
            json.dumps(
                {
                    "audio_sha256": "audio-hash",
                    "models": {"diarization": {"sha": "diarization-hash"}},
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(runtime, "run_pipeline", fake_run)
    monkeypatch.setattr(
        compare,
        "transcribe_reference_clips",
        lambda audio, refs, asr, models: {
            "ru": [("один два", "один два")],
            "kk": [],
            "mixed": [],
        },
    )
    result = compare.compare_manifest(
        manifest_path,
        tmp_path / "out",
        tmp_path / "models",
        ["gigaam-ctc", "rukk"],
        ["qwen3.5-9b"],
    )
    assert len(seen) == 2
    assert {item[1] for item in seen} == {"gigaam-ctc", "rukk"}
    assert result["gigaam-ctc__qwen3.5-9b"]["asr"]["ru"]["wer"] == 0.0
    assert result["rukk__qwen3.5-9b"]["tasks"]["missed_tasks"] == 0
    assert (
        result["rukk__qwen3.5-9b"]["runs"][0]["provenance"]["audio_sha256"]
        == "audio-hash"
    )
    assert (tmp_path / "out" / "comparison.json").is_file()


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("timezone", "Invalid/Zone", "timezone"),
        ("meeting_at", "not a date", "meeting_at"),
        ("participants", "Ерлан", "participants"),
        ("reference_utterances", None, "reference_utterances"),
        (
            "reference_utterances",
            [{"language": "ru", "start_ms": 0, "end_ms": 0, "text": "x"}],
            "end_ms",
        ),
        (
            "reference_utterances",
            [{"language": "ru", "start_ms": False, "end_ms": 1000, "text": "x"}],
            "start_ms",
        ),
        (
            "reference_utterances",
            [{"language": "en", "start_ms": 0, "end_ms": 1000, "text": "x"}],
            "language",
        ),
        (
            "reference_tasks",
            [{"action": "", "responsible": None, "due_date": None}],
            "action",
        ),
        ("reference_tasks", None, "reference_tasks"),
        ("reference_tasks", [{"action": "x", "due_date": None}], "responsible"),
        ("reference_tasks", [{"action": "x", "responsible": None}], "due_date"),
        (
            "reference_tasks",
            [{"action": "x", "responsible": None, "due_date": "tomorrow"}],
            "due_date",
        ),
        (
            "reference_tasks",
            [{"action": "x", "responsible": None, "due_date": None, "due_text": 7}],
            "due_text",
        ),
    ],
)
def test_compare_rejects_invalid_manifest_before_running_models(
    tmp_path, monkeypatch, field, value, error
):
    (tmp_path / "meeting.wav").write_bytes(b"synthetic audio")
    recording = {
        "audio": "meeting.wav",
        "timezone": "UTC",
        "reference_utterances": [],
        "reference_tasks": [],
    }
    recording[field] = value
    manifest_path = tmp_path / "reference.json"
    manifest_path.write_text(json.dumps({"recordings": [recording]}), encoding="utf-8")
    monkeypatch.setattr(
        runtime, "run_pipeline", lambda config: pytest.fail("inference started")
    )
    with pytest.raises(ValueError, match=error):
        compare.compare_manifest(
            manifest_path,
            tmp_path / "out",
            tmp_path / "models",
            ["gigaam-ctc"],
            ["qwen3.5-9b"],
        )


def test_compare_rejects_missing_audio_before_running_models(tmp_path, monkeypatch):
    manifest_path = tmp_path / "reference.json"
    manifest_path.write_text(
        json.dumps(
            {
                "recordings": [
                    {
                        "audio": "missing.wav",
                        "timezone": "UTC",
                        "reference_utterances": [],
                        "reference_tasks": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime, "run_pipeline", lambda config: pytest.fail("inference started")
    )
    with pytest.raises(ValueError, match="audio"):
        compare.compare_manifest(
            manifest_path,
            tmp_path / "out",
            tmp_path / "models",
            ["gigaam-ctc"],
            ["qwen3.5-9b"],
        )
