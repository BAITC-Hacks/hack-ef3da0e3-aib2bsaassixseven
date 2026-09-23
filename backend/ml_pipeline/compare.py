from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ml_pipeline.catalog import ASR_MODELS, LLM_MODELS

LANGUAGES = ("ru", "kk", "mixed")


def _normal(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold(), flags=re.UNICODE))


def _distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, token in enumerate(reference, 1):
        current = [row]
        for col, candidate in enumerate(hypothesis, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[col] + 1,
                    previous[col - 1] + (token != candidate),
                )
            )
        previous = current
    return previous[-1]


def error_rate(pairs: list[tuple[str, str]], unit: str) -> float | None:
    if unit not in {"word", "char"}:
        raise ValueError("unit must be word or char")
    edits = total = 0
    for reference, hypothesis in pairs:
        left = _normal(reference)
        right = _normal(hypothesis)
        ref = left.split() if unit == "word" else list(left.replace(" ", ""))
        hyp = right.split() if unit == "word" else list(right.replace(" ", ""))
        edits += _distance(ref, hyp)
        total += len(ref)
    return edits / total if total else None


def score_tasks(reference: list[dict], predicted: list[dict]) -> dict[str, int]:
    """Greedy action matching; reference labels must describe final active tasks."""
    unmatched = set(range(len(predicted)))
    missed = owner_errors = deadline_errors = 0
    for expected in reference:
        ranked = sorted(
            (
                (
                    SequenceMatcher(
                        None,
                        _normal(expected["action"]),
                        _normal(predicted[i]["action"]),
                    ).ratio(),
                    i,
                )
                for i in unmatched
            ),
            reverse=True,
        )
        if not ranked or ranked[0][0] < 0.55:
            missed += 1
            continue
        index = ranked[0][1]
        unmatched.remove(index)
        actual = predicted[index]
        if _normal(expected.get("responsible") or "") != _normal(
            actual.get("responsible") or ""
        ):
            owner_errors += 1
        if expected.get("due_date") != actual.get("due_date") or (
            expected.get("due_date") is None
            and actual.get("due_date") is None
            and "due_text" in expected
            and _normal(expected.get("due_text") or "")
            != _normal(actual.get("due_text") or "")
        ):
            deadline_errors += 1
    return {
        "reference_tasks": len(reference),
        "missed_tasks": missed,
        "false_positive_tasks": len(unmatched),
        "responsible_errors": owner_errors,
        "deadline_errors": deadline_errors,
    }


def _validate_manifest(manifest: object, manifest_path: Path) -> list[dict]:
    if (
        not isinstance(manifest, dict)
        or not isinstance(manifest.get("recordings"), list)
        or not manifest["recordings"]
    ):
        raise ValueError("comparison manifest has no recordings")
    for index, item in enumerate(manifest["recordings"], 1):
        label = f"recordings[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{label} must be an object")
        audio = item.get("audio")
        if not isinstance(audio, str) or not audio.strip() or Path(audio).is_absolute():
            raise ValueError(f"{label}.audio must be a relative file path")
        if not (manifest_path.parent / audio).is_file():
            raise ValueError(f"{label}.audio does not exist: {audio}")
        timezone = item.get("timezone")
        if not isinstance(timezone, str) or not timezone.strip():
            raise ValueError(f"{label}.timezone is required")
        if timezone != "UTC":
            try:
                ZoneInfo(timezone)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(f"{label}.timezone is invalid: {timezone}") from exc
        meeting_at = item.get("meeting_at")
        if meeting_at is not None:
            if not isinstance(meeting_at, str):
                raise ValueError(f"{label}.meeting_at must be an ISO datetime")
            try:
                datetime.fromisoformat(meeting_at)
            except ValueError as exc:
                raise ValueError(f"{label}.meeting_at must be an ISO datetime") from exc
        participants = item.get("participants", [])
        if not isinstance(participants, list) or any(
            not isinstance(name, str) or not name.strip() for name in participants
        ):
            raise ValueError(f"{label}.participants must be a list of names")
        utterances = item.get("reference_utterances")
        if not isinstance(utterances, list):
            raise ValueError(f"{label}.reference_utterances must be a list")
        for utterance_index, utterance in enumerate(utterances, 1):
            prefix = f"{label}.reference_utterances[{utterance_index}]"
            if not isinstance(utterance, dict):
                raise ValueError(f"{prefix} must be an object")
            if utterance.get("language") not in LANGUAGES:
                raise ValueError(f"{prefix}.language must be ru, kk, or mixed")
            if (
                not isinstance(utterance.get("text"), str)
                or not utterance["text"].strip()
            ):
                raise ValueError(f"{prefix}.text is required")
            start, end = utterance.get("start_ms"), utterance.get("end_ms")
            if (
                type(start) is not int
                or type(end) is not int
                or start < 0
                or end <= start
                or end - start > 25_000
            ):
                raise ValueError(f"{prefix}.start_ms/end_ms must span 1-25000 ms")
        tasks = item.get("reference_tasks")
        if not isinstance(tasks, list):
            raise ValueError(f"{label}.reference_tasks must be a list")
        for task_index, task in enumerate(tasks, 1):
            prefix = f"{label}.reference_tasks[{task_index}]"
            if not isinstance(task, dict):
                raise ValueError(f"{prefix} must be an object")
            if not isinstance(task.get("action"), str) or not task["action"].strip():
                raise ValueError(f"{prefix}.action is required")
            if "responsible" not in task:
                raise ValueError(f"{prefix}.responsible must be present (or null)")
            owner = task.get("responsible")
            if owner is not None and (not isinstance(owner, str) or not owner.strip()):
                raise ValueError(f"{prefix}.responsible must be a name or null")
            if "due_date" not in task:
                raise ValueError(f"{prefix}.due_date must be present (or null)")
            due_date = task.get("due_date")
            if due_date is not None:
                try:
                    if (
                        not isinstance(due_date, str)
                        or date.fromisoformat(due_date).isoformat() != due_date
                    ):
                        raise ValueError
                except ValueError as exc:
                    raise ValueError(
                        f"{prefix}.due_date must be YYYY-MM-DD or null"
                    ) from exc
            if "due_text" in task:
                due_text = task["due_text"]
                if due_text is not None and (
                    not isinstance(due_text, str) or not due_text.strip()
                ):
                    raise ValueError(f"{prefix}.due_text must be text or null")
    return manifest["recordings"]


def transcribe_reference_clips(
    audio: Path,
    reference: list[dict],
    asr_name: str,
    models_dir: Path,
) -> dict[str, list[tuple[str, str]]]:
    """Score each labeled speech interval directly, avoiding overlap double counts."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from ml_pipeline.asr import load_asr
    from ml_pipeline.audio import (
        SAMPLE_RATE,
        SpeechInterval,
        convert_to_wav,
        read_wav,
        write_clip,
    )
    from ml_pipeline.catalog import model_path

    result: dict[str, list[tuple[str, str]]] = {language: [] for language in LANGUAGES}
    with tempfile.TemporaryDirectory(prefix="hackalem-asr-eval-") as temporary:
        wav = Path(temporary) / "recording.wav"
        clip = Path(temporary) / "clip.wav"
        convert_to_wav(audio, wav)
        samples = read_wav(wav)
        adapter = load_asr(asr_name, model_path(models_dir, asr_name))
        for item in reference:
            language = item["language"]
            if language not in LANGUAGES:
                raise ValueError(f"unsupported language label: {language}")
            duration_ms = len(samples) * 1000 / SAMPLE_RATE
            if not 0 <= item["start_ms"] < item["end_ms"] <= duration_ms:
                raise ValueError("reference utterance is outside the recording")
            if item["end_ms"] - item["start_ms"] > 25_000:
                raise ValueError(
                    "split reference utterances into intervals of at most 25 s"
                )
            write_clip(samples, SpeechInterval(item["start_ms"], item["end_ms"]), clip)
            result[language].append((item["text"], adapter.transcribe(clip)))
        del adapter
    return result


def score_asr_pairs(
    pairs_by_language: dict[str, list[tuple[str, str]]],
) -> dict[str, dict]:
    return {
        language: {
            "segments": len(pairs),
            "wer": error_rate(pairs, "word"),
            "cer": error_rate(pairs, "char"),
        }
        for language, pairs in pairs_by_language.items()
    }


def compare_manifest(
    manifest_path: Path,
    output_dir: Path,
    models_dir: Path,
    asr_models: list[str],
    llm_models: list[str],
) -> dict:
    from ml_pipeline.runtime import RunConfig, run_pipeline

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recordings = _validate_manifest(manifest, manifest_path)
    if (
        not asr_models
        or not llm_models
        or any(name not in ASR_MODELS for name in asr_models)
        or any(name not in LLM_MODELS for name in llm_models)
    ):
        raise ValueError("comparison needs known ASR and LLM candidates")
    results: dict[str, dict] = {}
    oracle_cache: dict[tuple[str, int], dict[str, list[tuple[str, str]]]] = {}
    for asr_name in asr_models:
        for llm_name in llm_models:
            key = f"{asr_name}__{llm_name}"
            runs = []
            corpus_pairs: dict[str, list[tuple[str, str]]] = {
                language: [] for language in LANGUAGES
            }
            task_totals = {
                "reference_tasks": 0,
                "missed_tasks": 0,
                "false_positive_tasks": 0,
                "responsible_errors": 0,
                "deadline_errors": 0,
            }
            for index, item in enumerate(recordings, 1):
                audio = (manifest_path.parent / item["audio"]).resolve()
                target = output_dir / key / f"recording-{index:03d}"
                run_pipeline(
                    RunConfig(
                        audio=audio,
                        output_dir=target,
                        meeting_at=item.get("meeting_at"),
                        timezone=item["timezone"],
                        participants=item.get("participants", []),
                        asr_model=asr_name,
                        llm_model=llm_name,
                        models_dir=models_dir,
                    )
                )
                abstraction = json.loads(
                    (target / "abstraction.json").read_text(encoding="utf-8")
                )
                cache_key = (asr_name, index)
                if cache_key not in oracle_cache:
                    oracle_cache[cache_key] = transcribe_reference_clips(
                        audio, item["reference_utterances"], asr_name, models_dir
                    )
                labeled_pairs = oracle_cache[cache_key]
                for language in LANGUAGES:
                    corpus_pairs[language].extend(labeled_pairs[language])
                task_scores = score_tasks(item["reference_tasks"], abstraction["tasks"])
                for metric, value in task_scores.items():
                    task_totals[metric] += value
                runs.append(
                    {
                        "recording": item["audio"],
                        "provenance": json.loads(
                            (target / "provenance.json").read_text(encoding="utf-8")
                        ),
                        "asr": score_asr_pairs(labeled_pairs),
                        "tasks": task_scores,
                    }
                )
            corpus = score_asr_pairs(corpus_pairs)
            results[key] = {"asr": corpus, "tasks": task_totals, "runs": runs}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return results
