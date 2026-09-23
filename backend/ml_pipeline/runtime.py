from __future__ import annotations

import gc
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from ml_pipeline.audio import SAMPLE_RATE
from ml_pipeline.catalog import ASR_MODELS, LLM_MODELS, model_path, model_record
from ml_pipeline.models import Abstraction, AbstractionOutput, Transcript, Utterance


@dataclass(frozen=True)
class RunConfig:
    audio: Path
    output_dir: Path
    timezone: str
    asr_model: str
    models_dir: Path
    meeting_at: str | None = None
    participants: list[str] = field(default_factory=list)
    llm_model: str = "qwen3.5-9b"
    chunk_chars: int = 10_000
    reviewed_corrections: Path | None = None


def parse_meeting_at(value: str | None, timezone: str) -> datetime | None:
    zone = ZoneInfo(timezone)
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def _release_device_cache() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pipeline_code_sha256() -> str:
    digest = sha256()
    for source in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(source.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(source.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def run_pipeline(config: RunConfig) -> tuple[Transcript, AbstractionOutput]:
    if config.asr_model not in ASR_MODELS or config.llm_model not in LLM_MODELS:
        raise ValueError("unknown ASR or LLM model")
    if not config.audio.is_file():
        raise FileNotFoundError(config.audio)
    if config.chunk_chars < 1:
        raise ValueError("chunk_chars must be positive")
    meeting_at = parse_meeting_at(config.meeting_at, config.timezone)
    # Model files must have been fetched in a separate setup step. These switches
    # block Hub/Transformers downloads and telemetry during processing.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["PYANNOTE_METRICS_ENABLED"] = "0"
    diarization_dir = model_path(config.models_dir, "diarization")
    asr_dir = model_path(config.models_dir, config.asr_model)
    llm_dir = model_path(config.models_dir, config.llm_model)

    from ml_pipeline.abstraction import LocalQwen, extract_abstraction, render_summary
    from ml_pipeline.asr import load_asr
    from ml_pipeline.audio import (
        convert_to_wav,
        read_wav,
        split_for_asr,
        vad_intervals,
        write_clip,
    )
    from ml_pipeline.diarization import diarize

    with tempfile.TemporaryDirectory(prefix="hackalem-ml-") as temporary:
        temp = Path(temporary)
        wav_path = temp / "meeting.wav"
        convert_to_wav(config.audio, wav_path)
        samples = read_wav(wav_path)
        speaker_turns = diarize(samples, diarization_dir)
        _release_device_cache()
        speech = vad_intervals(samples)
        clips = split_for_asr(speech, speaker_turns)
        asr = load_asr(config.asr_model, asr_dir)
        utterances = []
        for interval in clips:
            # Diarization boundaries can leave millisecond slivers. GigaAM's
            # spectrogram needs more samples than those fragments contain.
            if interval.end_ms - interval.start_ms < 100:
                continue
            clip_path = temp / "clip.wav"
            write_clip(samples, interval, clip_path)
            text = asr.transcribe(clip_path).strip()
            if text:
                utterances.append(
                    Utterance(
                        id=f"u{len(utterances) + 1:05d}",
                        start_ms=interval.start_ms,
                        end_ms=interval.end_ms,
                        speaker_id=interval.speaker_id,
                        text=text,
                    )
                )
        del asr
        _release_device_cache()

    reviewed_audit = None
    reviewed_manifest_bytes: bytes | None = None
    if config.reviewed_corrections is not None:
        from ml_pipeline.review import apply_reviewed_insertions

        utterances, reviewed_audit = apply_reviewed_insertions(
            config.reviewed_corrections,
            config.audio,
            utterances,
            duration_ms=round(len(samples) * 1000 / SAMPLE_RATE),
        )
        reviewed_manifest_bytes = config.reviewed_corrections.read_bytes()
        reviewed_digest = sha256(reviewed_manifest_bytes).hexdigest()
        if reviewed_digest != reviewed_audit["manifest_sha256"]:
            raise ValueError("reviewed corrections changed while being applied")

    transcript = Transcript(
        audio_path=str(config.audio.resolve()),
        meeting_at=meeting_at,
        timezone=config.timezone,
        participants=config.participants,
        asr_model=config.asr_model,
        utterances=utterances,
    )
    validation_warnings: list[str] = []
    if utterances:
        generator = LocalQwen(llm_dir, config.llm_model)
        abstraction = extract_abstraction(
            utterances,
            generator,
            meeting_at,
            config.participants,
            max_chars=config.chunk_chars,
            validation_warnings=validation_warnings,
        )
        del generator
        _release_device_cache()
    else:
        abstraction = Abstraction()
    output = AbstractionOutput(
        **abstraction.model_dump(),
        meeting_at=meeting_at,
        timezone=config.timezone,
        llm_model=config.llm_model,
        validation_warnings=validation_warnings,
    )
    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / "transcript.json").write_text(
        transcript.model_dump_json(indent=2, exclude_none=False) + "\n",
        encoding="utf-8",
    )
    (config.output_dir / "abstraction.json").write_text(
        output.model_dump_json(indent=2, exclude_none=False) + "\n", encoding="utf-8"
    )
    (config.output_dir / "summary.md").write_text(
        render_summary(abstraction, validation_warnings), encoding="utf-8"
    )
    provenance = {
        "audio_sha256": _file_sha256(config.audio),
        "pipeline_code_sha256": _pipeline_code_sha256(),
        "models": {
            name: model_record(config.models_dir, name)
            for name in ("diarization", config.asr_model, config.llm_model)
        },
    }
    if reviewed_audit is not None and reviewed_manifest_bytes is not None:
        provenance["reviewed_corrections"] = reviewed_audit
        (config.output_dir / "reviewed_corrections.json").write_bytes(
            reviewed_manifest_bytes
        )
    (config.output_dir / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return transcript, output
