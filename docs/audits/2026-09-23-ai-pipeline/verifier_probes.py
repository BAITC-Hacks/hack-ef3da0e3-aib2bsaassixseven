"""Independent audit probes: no models, downloads, or production mutations.

Run from repo root with backend/.venv/Scripts/python.exe.
Outputs observations rather than treating known bugs as passing tests.
"""
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from ml_pipeline.abstraction import (  # noqa: E402
    _parse_with_evidence,
    normalize_deadline,
    validate_evidence,
)
from ml_pipeline.compare import score_tasks  # noqa: E402
from ml_pipeline.models import Abstraction, Task, Transcript, Utterance  # noqa: E402


def turn(uid, text):
    return Utterance(id=uid, start_ms=0, end_ms=1000, speaker_id=None, text=text)


results = {"dates": {}}
for phrase in ["до 2 октября 2027 года", "не завтра, а через три дня"]:
    normalized, uncertain = normalize_deadline(phrase, datetime(2026, 9, 23))
    results["dates"][phrase] = {"date": str(normalized), "uncertain": uncertain}

task = Task(action="Подготовить договор поставки оборудования",
            evidence_quote="Подготовьте договор поставки оборудования.",
            source_utterance_ids=["u1"])
abstraction = Abstraction(tasks=[task])
validate_evidence(abstraction, [turn("u1", task.evidence_quote),
                                turn("u2", "Договор аренды офиса отменяем.")])
results["unrelated_cancellation_remaining_tasks"] = len(abstraction.tasks)

ownership_turns = [turn("u1", "Айнур Каировна, подготовьте отчёт."),
                   turn("u2", "Теперь обсудим обслуживание станков."),
                   turn("u3", "Проверьте станок номер три.")]
ownership_task = Task(action="Проверить станок номер три",
                      evidence_quote=ownership_turns[-1].text,
                      source_utterance_ids=["u3"])
validate_evidence(Abstraction(tasks=[ownership_task]), ownership_turns)
results["owner_after_topic_change"] = ownership_task.responsible

payload = {
    "key_facts": [{"text": "absent", "evidence_quote": "absent",
                   "source_utterance_ids": ["u1"], "needs_review": False}],
    "decisions": [],
    "tasks": [{"action": "Проверить договор", "responsible": None,
               "due_date": None, "due_text": None,
               "evidence_quote": "Проверьте договор.",
               "source_utterance_ids": ["u1"], "needs_review": False}],
}


class FixedGenerator:
    def generate(self, prompt):
        return json.dumps(payload, ensure_ascii=False)


salvaged = _parse_with_evidence(
    FixedGenerator(), "audit", [turn("u1", "Проверьте договор."),
                               turn("u2", "Проверку договора отменяем.")], [])
results["salvage_cancelled_remaining_tasks"] = len(salvaged.tasks)
results["scorer_negation_and_relative_deadline"] = score_tasks(
    [{"action": "Утвердить договор", "responsible": None,
      "due_date": None, "due_text": "за две недели"}],
    [{"action": "Не утверждать договор", "responsible": None,
      "due_date": None, "due_text": "за десять дней"}])

archive = Path.home() / "Downloads" / "meeting-2-results.zip"
with zipfile.ZipFile(archive) as source:
    transcript = Transcript.model_validate_json(source.read("meeting-2/transcript.json"))
    raw = json.loads(source.read("meeting-2/abstraction.json"))
    current = Abstraction.model_validate({k: raw[k] for k in ["key_facts", "decisions", "tasks"]})
    validate_evidence(current, transcript.utterances)
    results["archive_revalidated_current_code"] = [
        {"action": item.action, "responsible": item.responsible,
         "due_text": item.due_text} for item in current.tasks
    ]

print(json.dumps(results, ensure_ascii=True, indent=2))
