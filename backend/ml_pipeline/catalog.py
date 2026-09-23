from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelSpec:
    repo: str
    revision: str
    allow_patterns: list[str] | None = None


MODELS = {
    "diarization": ModelSpec("pyannote/speaker-diarization-community-1", "main"),
    "gigaam-ctc": ModelSpec("ai-sage/GigaAM-Multilingual", "ctc"),
    "gigaam-large-ctc": ModelSpec("ai-sage/GigaAM-Multilingual", "large_ctc"),
    "rukk": ModelSpec("alibiserikbay/kazakh-russian-mixed-stt", "main", ["asr/rukk/*"]),
    "whisper-turbo": ModelSpec("mobiuslabsgmbh/faster-whisper-large-v3-turbo", "main"),
    "qwen3.5-9b": ModelSpec("Qwen/Qwen3.5-9B", "main"),
    "qwen3-4b": ModelSpec("Qwen/Qwen3-4B-Instruct-2507", "main"),
    "issai-4b-kazakh": ModelSpec("issai/Qwen3.5-4B-Kazakh", "main"),
}
ASR_MODELS = ("gigaam-ctc", "gigaam-large-ctc", "rukk", "whisper-turbo")
LLM_MODELS = ("qwen3.5-9b", "qwen3-4b", "issai-4b-kazakh")


def model_record(models_dir: Path, name: str) -> dict[str, str]:
    manifest = models_dir / "models.lock.json"
    if not manifest.is_file():
        raise FileNotFoundError(f"prepare local models first: {manifest}")
    locked = json.loads(manifest.read_text(encoding="utf-8"))
    record = locked.get(name) if isinstance(locked, dict) else None
    if (
        name not in MODELS
        or not isinstance(record, dict)
        or record.get("repo") != MODELS[name].repo
        or not isinstance(record.get("sha"), str)
        or not record["sha"]
    ):
        raise ValueError(f"model {name} is not pinned in {manifest}")
    return {"repo": record["repo"], "sha": record["sha"]}


def model_path(models_dir: Path, name: str) -> Path:
    model_record(models_dir, name)
    path = models_dir / name
    if not path.is_dir():
        raise FileNotFoundError(path)
    return path
