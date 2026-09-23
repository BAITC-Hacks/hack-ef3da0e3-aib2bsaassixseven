"""Current-code verifier probes, no actual audio/model execution."""
import json
import sys
import tempfile
from contextlib import ExitStack
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from ml_pipeline import abstraction, asr, audio, diarization, runtime
from ml_pipeline.catalog import MODELS
from ml_pipeline.compare import score_tasks
from ml_pipeline.models import Abstraction, Task, Utterance

results = {"dates": {}}
anchor = datetime(2026, 9, 23)
for text, when in [
    ("до 2 октября 2027 года", None),
    ("не 2 октября, а 5 октября", anchor),
    ("не через три дня, а через пять дней", anchor),
    ("не 2026-10-02, а 2026-10-05", anchor),
    ("не 2026-10-02, а 5 октября", anchor),
    ("с 2 октября по 5 октября", anchor),
]:
    value, uncertain = abstraction.normalize_deadline(text, when)
    results["dates"][text] = {"date": str(value), "uncertain": uncertain}

results["negated_action_only"] = score_tasks(
    [{"action": "Утвердить договор", "responsible": None, "due_date": None}],
    [{"action": "Не утверждать договор", "responsible": None, "due_date": None}],
)
results["same_relative_deadline_different_wording"] = score_tasks(
    [{"action": "Подготовить отчет", "responsible": None,
      "due_date": None, "due_text": "через две недели"}],
    [{"action": "Подготовить отчет", "responsible": None,
      "due_date": None, "due_text": "через 14 дней"}],
)

address = Utterance(id="r00001", start_ms=100, end_ms=500, speaker_id=None,
                    text="Тимур Болатович")
new_topic = Utterance(id="u00001", start_ms=600000, end_ms=602000,
                      speaker_id="S2", text="Теперь обсудим станки. Проверьте станок номер три.")
unassigned = Task(action="Проверить станок номер три", responsible=None,
                  source_utterance_ids=[new_topic.id], evidence_quote=new_topic.text)
abstraction.validate_evidence(Abstraction(tasks=[unassigned]), [address, new_topic])
results["distant_reviewed_name_current_turn_topic_change"] = {
    "owner": unassigned.responsible, "sources": unassigned.source_utterance_ids,
    "needs_review": unassigned.needs_review,
}
assignment = Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id=None,
                       text="Подготовьте договор поставки оборудования.")
negative = Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id=None,
                     text="Не снимаем поручение подготовить договор поставки оборудования.")
active = Abstraction(tasks=[Task(action="Подготовить договор поставки оборудования",
                                 source_utterance_ids=[assignment.id], evidence_quote=assignment.text)])
abstraction.validate_evidence(active, [assignment, negative])
results["explicit_non_cancellation_remaining_tasks"] = len(active.tasks)


def runtime_case(base, mode):
    recording = base / "meeting.mp3"
    recording.write_bytes(b"synthetic recording")
    output = base / "output"
    output.mkdir()
    manifest = (output if mode == "same-path" else base) / "reviewed_corrections.json"
    payload = {
        "audio_sha256": sha256(recording.read_bytes()).hexdigest(),
        "insertions": [{"id": "r00001", "start_ms": 100, "end_ms": 300,
                        "text": "Тимур Болатович", "review_note": "Audit fixture."}],
    }
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    original_hash = sha256(manifest.read_bytes()).hexdigest()
    models = base / "models"
    models.mkdir()
    selected = ("diarization", "gigaam-ctc", "qwen3.5-9b")
    for name in selected:
        (models / name).mkdir()
    (models / "models.lock.json").write_text(json.dumps({
        name: {"repo": MODELS[name].repo, "sha": "synthetic"} for name in selected
    }), encoding="utf-8")

    class Generator:
        def __init__(self, *args):
            pass

        def generate(self, prompt):
            if mode == "mutation":
                payload["insertions"][0]["text"] = "Другое исправление"
                manifest.write_text(json.dumps(payload), encoding="utf-8")
            return '{"key_facts":[],"decisions":[],"tasks":[]}'

    with ExitStack() as stack:
        mocks = [
            (runtime, "ZoneInfo", lambda name: UTC),
            (runtime, "_release_device_cache", lambda: None),
            (audio, "convert_to_wav", lambda src, dst: dst.write_bytes(b"wav")),
            (audio, "read_wav", lambda path: [0.0] * 16000),
            (audio, "vad_intervals", lambda samples: []),
            (diarization, "diarize", lambda samples, model: []),
            (asr, "load_asr", lambda name, model: None),
            (abstraction, "LocalQwen", Generator),
        ]
        for module, attr, replacement in mocks:
            stack.enter_context(patch.object(module, attr, replacement))
        outcome = {}
        try:
            runtime.run_pipeline(runtime.RunConfig(
                audio=recording, output_dir=output, timezone="UTC",
                asr_model="gigaam-ctc", models_dir=models,
                reviewed_corrections=manifest,
            ))
            if mode == "stale":
                runtime.run_pipeline(runtime.RunConfig(
                    audio=recording, output_dir=output, timezone="UTC",
                    asr_model="gigaam-ctc", models_dir=models,
                ))
            outcome["exception"] = None
        except Exception as exc:
            outcome["exception"] = type(exc).__name__
        outcome["written_files"] = sorted(p.name for p in output.iterdir())
        provenance_path = output / "provenance.json"
        if provenance_path.is_file():
            provenance = json.loads(provenance_path.read_text())
            if "reviewed_corrections" not in provenance:
                outcome["correction_in_provenance"] = False
                return outcome
            declared = provenance["reviewed_corrections"]["manifest_sha256"]
            copied = sha256((output / "reviewed_corrections.json").read_bytes()).hexdigest()
            outcome.update(original_hash=original_hash, declared_hash=declared,
                           copied_hash=copied, manifest_hash_matches=declared == copied)
        return outcome


with tempfile.TemporaryDirectory(prefix="hackalem-recheck-verifier-") as temporary:
    for mode in ("same-path", "mutation", "stale"):
        base = Path(temporary) / mode
        base.mkdir()
        results[mode] = runtime_case(base, mode)

print(json.dumps(results, ensure_ascii=True, indent=2))
