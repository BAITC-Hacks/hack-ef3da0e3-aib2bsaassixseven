import json
from datetime import UTC
from hashlib import sha256

import pytest

from ml_pipeline.models import Utterance
from ml_pipeline.review import apply_reviewed_insertions


def test_reviewed_audio_fragment_is_inserted_before_abstraction(tmp_path):
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"recording")
    manifest = tmp_path / "review.json"
    manifest.write_text(
        json.dumps(
            {
                "audio_sha256": sha256(audio.read_bytes()).hexdigest(),
                "insertions": [
                    {
                        "id": "r00001",
                        "start_ms": 214000,
                        "end_ms": 214799,
                        "text": "Тимур Болатович",
                        "review_note": "Name verified in an extended audio window.",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw = [
        Utterance(
            id="u00035",
            start_ms=206058,
            end_ms=214343,
            speaker_id="SPEAKER_03",
            text="про бюджет",
        ),
        Utterance(
            id="u00036",
            start_ms=214799,
            end_ms=219743,
            speaker_id="SPEAKER_02",
            text="свяжитесь с Нурланом",
        ),
    ]

    merged, audit = apply_reviewed_insertions(manifest, audio, raw, duration_ms=230000)

    assert [item.id for item in merged] == ["u00035", "r00001", "u00036"]
    assert merged[1].speaker_id is None
    assert merged[1].text == "Тимур Болатович"
    assert audit == {
        "manifest_sha256": sha256(manifest.read_bytes()).hexdigest(),
        "inserted_utterance_ids": ["r00001"],
    }


def test_reviewed_insertions_require_matching_audio_and_anonymous_speaker(tmp_path):
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"recording")
    manifest = tmp_path / "review.json"
    data = {
        "audio_sha256": "0" * 64,
        "insertions": [
            {
                "id": "r00001",
                "start_ms": 100,
                "end_ms": 300,
                "text": "Тимур Болатович",
                "review_note": "Verified by listening.",
            }
        ],
    }
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="audio SHA-256"):
        apply_reviewed_insertions(manifest, audio, [], duration_ms=1000)

    data["audio_sha256"] = sha256(audio.read_bytes()).hexdigest()
    data["insertions"][0]["speaker_id"] = "SPEAKER_02"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="speaker_id"):
        apply_reviewed_insertions(manifest, audio, [], duration_ms=1000)


def test_reviewed_replacement_normalizes_only_the_audio_verified_span(tmp_path):
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"recording")
    manifest = tmp_path / "review.json"
    manifest.write_text(
        json.dumps(
            {
                "audio_sha256": sha256(audio.read_bytes()).hexdigest(),
                "insertions": [],
                "replacements": [
                    {
                        "utterance_id": "u00018",
                        "start_ms": 100000,
                        "end_ms": 111000,
                        "old_text": "тимур балатович",
                        "new_text": "Тимур Болатович",
                        "review_note": "Canonical spelling verified against the audio.",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw = [
        Utterance(
            id="u00018", start_ms=100792, end_ms=110343,
            speaker_id="SPEAKER_02", text="ответственный тимур балатович",
        ),
        Utterance(
            id="u00019", start_ms=108000, end_ms=109000,
            speaker_id="SPEAKER_03", text="тимур балатович ответил",
        ),
    ]

    merged, audit = apply_reviewed_insertions(
        manifest, audio, raw, duration_ms=130000
    )

    assert merged[0].text == "ответственный Тимур Болатович"
    assert merged[1].text == "тимур балатович ответил"
    assert raw[0].text == "ответственный тимур балатович"
    assert audit["replaced_utterance_ids"] == ["u00018"]


def test_reviewed_replacement_rejects_nonmatching_utterance_id(tmp_path):
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"recording")
    manifest = tmp_path / "review.json"
    manifest.write_text(
        json.dumps(
            {
                "audio_sha256": sha256(audio.read_bytes()).hexdigest(),
                "insertions": [],
                "replacements": [
                    {
                        "utterance_id": "u00099",
                        "start_ms": 0, "end_ms": 1000,
                        "old_text": "тимур балатович",
                        "new_text": "Тимур Болатович",
                        "review_note": "Verified by listening.",
                    }
                ],
            }),
        encoding="utf-8",
    )
    raw = [
        Utterance(
            id=f"u{i:05d}", start_ms=10 * i, end_ms=100 * i,
            speaker_id=None, text="тимур балатович",
        )
        for i in (1, 2)
    ]
    with pytest.raises(ValueError, match="exactly one"):
        apply_reviewed_insertions(manifest, audio, raw, duration_ms=1000)


def test_reviewed_replacement_rejects_duplicate_phrase_in_one_utterance(tmp_path):
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"recording")
    manifest = tmp_path / "review.json"
    manifest.write_text(
        json.dumps(
            {
                "audio_sha256": sha256(audio.read_bytes()).hexdigest(),
                "replacements": [
                    {
                        "utterance_id": "u00018",
                        "start_ms": 100, "end_ms": 300,
                        "old_text": "тимур балатович",
                        "new_text": "Тимур Болатович",
                        "review_note": "Verified by listening.",
                    }
                ],
            }),
        encoding="utf-8",
    )
    raw = [Utterance(
        id="u00018", start_ms=110, end_ms=220, speaker_id=None,
        text="тимур балатович и тимур балатович",
    )]
    with pytest.raises(ValueError, match="exactly once"):
        apply_reviewed_insertions(manifest, audio, raw, duration_ms=1000)


def test_pipeline_uses_reviewed_text_and_records_manifest(tmp_path, monkeypatch):
    from ml_pipeline import abstraction, asr, audio, diarization, runtime
    from ml_pipeline.catalog import MODELS

    recording = tmp_path / "meeting.mp3"
    recording.write_bytes(b"recording")
    reviewed = tmp_path / "review.json"
    reviewed.write_text(
        json.dumps(
            {
                "audio_sha256": sha256(recording.read_bytes()).hexdigest(),
                "insertions": [
                    {
                        "id": "r00001",
                        "start_ms": 100,
                        "end_ms": 300,
                        "text": "Тимур Болатович",
                        "review_note": "Verified in a wider audio window.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    initial_manifest = reviewed.read_bytes()
    models = tmp_path / "models"
    models.mkdir()
    selected = ("diarization", "gigaam-ctc", "qwen3.5-9b")
    for name in selected:
        (models / name).mkdir()
    (models / "models.lock.json").write_text(
        json.dumps(
            {name: {"repo": MODELS[name].repo, "sha": "synthetic"} for name in selected}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        audio, "convert_to_wav", lambda src, dst: dst.write_bytes(b"wav")
    )
    monkeypatch.setattr(runtime, "ZoneInfo", lambda name: UTC)
    monkeypatch.setattr(audio, "read_wav", lambda path: [0.0] * 16000)
    monkeypatch.setattr(audio, "vad_intervals", lambda samples: [])
    monkeypatch.setattr(diarization, "diarize", lambda samples, model: [])
    monkeypatch.setattr(asr, "load_asr", lambda name, model: None)

    class FakeQwen:
        def __init__(self, path, name):
            pass

        def generate(self, prompt):
            reviewed.write_bytes(b"changed during generation")
            return '{"key_facts":[],"decisions":[],"tasks":[]}'

    monkeypatch.setattr(abstraction, "LocalQwen", FakeQwen)
    result_dir = tmp_path / "output"
    runtime.run_pipeline(
        runtime.RunConfig(
            audio=recording,
            output_dir=result_dir,
            timezone="UTC",
            asr_model="gigaam-ctc",
            models_dir=models,
            reviewed_corrections=reviewed,
        )
    )

    transcript = json.loads((result_dir / "transcript.json").read_text())
    provenance = json.loads((result_dir / "provenance.json").read_text())
    assert [x["id"] for x in transcript["utterances"]] == ["r00001"]
    assert transcript["utterances"][0]["speaker_id"] is None
    assert provenance["reviewed_corrections"]["inserted_utterance_ids"] == ["r00001"]
    copied = (result_dir / "reviewed_corrections.json").read_bytes()
    assert copied == initial_manifest
    assert (
        sha256(copied).hexdigest()
        == provenance["reviewed_corrections"]["manifest_sha256"]
    )
