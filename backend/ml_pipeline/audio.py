from __future__ import annotations

import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

SAMPLE_RATE = 16_000
# Join brief VAD pauses or unlabeled diarization gaps (220 ms in meeting 2)
# while keeping longer gaps (490 ms there) and speaker changes separate.
MAX_SAME_SPEAKER_GAP_MS = 300


@dataclass(frozen=True)
class SpeechInterval:
    start_ms: int
    end_ms: int
    speaker_id: str | None = None


def convert_to_wav(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        check=True,
    )


def read_wav(path: Path):
    import numpy as np

    with wave.open(str(path), "rb") as handle:
        if (
            handle.getnchannels() != 1
            or handle.getframerate() != SAMPLE_RATE
            or handle.getsampwidth() != 2
        ):
            raise ValueError("expected 16 kHz mono 16-bit WAV")
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0


def vad_intervals(samples) -> list[SpeechInterval]:
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    options = VadOptions(
        min_silence_duration_ms=400, speech_pad_ms=150, max_speech_duration_s=25
    )
    timestamps = get_speech_timestamps(samples, vad_options=options)
    return [
        SpeechInterval(
            round(x["start"] * 1000 / SAMPLE_RATE), round(x["end"] * 1000 / SAMPLE_RATE)
        )
        for x in timestamps
    ]


def split_for_asr(
    speech: list[SpeechInterval],
    speakers: list[SpeechInterval],
    max_ms: int = 25_000,
) -> list[SpeechInterval]:
    """Intersect VAD and exclusive diarization without changing recording offsets."""
    if max_ms <= 0:
        raise ValueError("max_ms must be positive")
    result: list[SpeechInterval] = []
    speakers = sorted(speakers, key=lambda item: item.start_ms)
    for voiced in speech:
        cursor = voiced.start_ms
        for speaker in speakers:
            if speaker.end_ms <= cursor or speaker.start_ms >= voiced.end_ms:
                continue
            if speaker.start_ms > cursor:
                _append_splits(
                    result, cursor, min(speaker.start_ms, voiced.end_ms), None, max_ms
                )
            start = max(cursor, speaker.start_ms)
            end = min(voiced.end_ms, speaker.end_ms)
            _append_splits(result, start, end, speaker.speaker_id, max_ms)
            cursor = max(cursor, end)
            if cursor >= voiced.end_ms:
                break
        if cursor < voiced.end_ms:
            _append_splits(result, cursor, voiced.end_ms, None, max_ms)
    merged: list[SpeechInterval] = []
    for interval in result:
        if merged:
            bridge_unknown = (
                len(merged) > 1
                and merged[-1].speaker_id is None
                and merged[-1].start_ms == merged[-2].end_ms
                and merged[-1].end_ms == interval.start_ms
            )
            previous = merged[-2] if bridge_unknown else merged[-1]
            if (
                interval.speaker_id is not None
                and interval.speaker_id == previous.speaker_id
                and 0 <= interval.start_ms - previous.end_ms <= MAX_SAME_SPEAKER_GAP_MS
                and interval.end_ms - previous.start_ms <= max_ms
                and not any(
                    turn.speaker_id != interval.speaker_id
                    and turn.start_ms < interval.start_ms
                    and turn.end_ms > previous.end_ms
                    for turn in speakers
                )
            ):
                if bridge_unknown:
                    merged.pop()
                merged[-1] = SpeechInterval(
                    previous.start_ms, interval.end_ms, interval.speaker_id
                )
                continue
        merged.append(interval)
    return merged


def _append_splits(
    result: list[SpeechInterval],
    start: int,
    end: int,
    speaker_id: str | None,
    max_ms: int,
) -> None:
    while start < end:
        stop = min(end, start + max_ms)
        result.append(SpeechInterval(start, stop, speaker_id))
        start = stop


def write_clip(samples, interval: SpeechInterval, destination: Path) -> None:
    import numpy as np

    start = round(interval.start_ms * SAMPLE_RATE / 1000)
    end = round(interval.end_ms * SAMPLE_RATE / 1000)
    data = np.clip(samples[start:end] * 32768.0, -32768, 32767).astype("<i2")
    with wave.open(str(destination), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(data.tobytes())
