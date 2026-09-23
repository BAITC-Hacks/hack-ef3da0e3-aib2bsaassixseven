import io
import sys
import types
import wave
from pathlib import Path

import numpy as np
import pytest

from ml_pipeline.audio import (
    SAMPLE_RATE,
    SpeechInterval,
    read_wav,
    split_for_asr,
    vad_intervals,
    write_clip,
)
from ml_pipeline.diarization import diarize


def test_read_wav_rejects_non_16_bit_pcm(monkeypatch):
    wav = io.BytesIO()
    with wave.open(wav, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(1)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(bytes([128] * 160))
    original_open = wave.open
    monkeypatch.setattr(
        wave,
        "open",
        lambda path, mode: original_open(io.BytesIO(wav.getvalue()), mode),
    )

    with pytest.raises(ValueError, match="16-bit"):
        read_wav(Path("8-bit.wav"))


def test_vad_sample_offsets_remain_absolute_milliseconds(monkeypatch):
    def fake_vad(samples, vad_options):
        assert len(samples) == SAMPLE_RATE * 12
        assert vad_options.max_speech_duration_s == 25
        return [{"start": SAMPLE_RATE * 5 + 16, "end": SAMPLE_RATE * 7 + 32}]

    class VadOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    vad_module = types.ModuleType("faster_whisper.vad")
    vad_module.VadOptions = VadOptions
    vad_module.get_speech_timestamps = fake_vad
    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.ModuleType("faster_whisper")
    )
    monkeypatch.setitem(sys.modules, "faster_whisper.vad", vad_module)

    speech = vad_intervals(np.zeros(SAMPLE_RATE * 12, dtype=np.float32))
    speakers = [SpeechInterval(4500, 6500, "SPEAKER_00")]
    assert split_for_asr(speech, speakers) == [
        SpeechInterval(5001, 6500, "SPEAKER_00"),
        SpeechInterval(6500, 7002, None),
    ]


def test_close_same_speaker_vad_slices_form_one_asr_clip():
    # Meeting 2 near 02:25: one speaker's phrase was split into three ASR calls.
    speech = [
        SpeechInterval(143789, 145584),
        SpeechInterval(145584, 147535),
        SpeechInterval(147755, 148447),
        SpeechInterval(148700, 154522),
    ]
    speakers = [
        SpeechInterval(143500, 148500, "SPEAKER_02"),
        SpeechInterval(148500, 155000, "SPEAKER_04"),
    ]

    assert split_for_asr(speech, speakers) == [
        SpeechInterval(143789, 148447, "SPEAKER_02"),
        SpeechInterval(148700, 154522, "SPEAKER_04"),
    ]


def test_short_unlabeled_diarization_gap_between_same_speaker_is_recovered():
    # Community-1 leaves a 220 ms unlabeled gap in meeting 2 around 02:27.
    speech = [SpeechInterval(143789, 148447)]
    speakers = [
        SpeechInterval(143789, 147535, "SPEAKER_02"),
        SpeechInterval(147755, 148447, "SPEAKER_02"),
    ]

    assert split_for_asr(speech, speakers) == [
        SpeechInterval(143789, 148447, "SPEAKER_02")
    ]


def test_short_opposing_turn_is_not_absorbed_between_same_speaker_flanks():
    speech = [SpeechInterval(0, 2000)]
    speakers = [
        SpeechInterval(0, 1000, "SPEAKER_00"),
        SpeechInterval(1000, 1020, "SPEAKER_01"),
        SpeechInterval(1020, 2000, "SPEAKER_00"),
    ]

    assert split_for_asr(speech, speakers) == [
        SpeechInterval(0, 1000, "SPEAKER_00"),
        SpeechInterval(1000, 1020, "SPEAKER_01"),
        SpeechInterval(1020, 2000, "SPEAKER_00"),
    ]


def test_long_unlabeled_gap_remains_unattributed():
    speech = [SpeechInterval(0, 2000)]
    speakers = [
        SpeechInterval(0, 900, "SPEAKER_00"),
        SpeechInterval(1300, 2000, "SPEAKER_00"),
    ]

    assert split_for_asr(speech, speakers) == [
        SpeechInterval(0, 900, "SPEAKER_00"),
        SpeechInterval(900, 1300, None),
        SpeechInterval(1300, 2000, "SPEAKER_00"),
    ]


def test_short_same_speaker_sliver_is_kept_but_speaker_boundary_is_hard():
    speech = [
        SpeechInterval(1000, 2000),
        SpeechInterval(2000, 2015),
        SpeechInterval(2015, 3000),
    ]
    speakers = [
        SpeechInterval(1000, 2500, "SPEAKER_00"),
        SpeechInterval(2500, 3000, "SPEAKER_01"),
    ]

    assert split_for_asr(speech, speakers) == [
        SpeechInterval(1000, 2500, "SPEAKER_00"),
        SpeechInterval(2500, 3000, "SPEAKER_01"),
    ]


def test_same_speaker_clips_do_not_exceed_asr_limit():
    speech = [SpeechInterval(0, 24000), SpeechInterval(24100, 27000)]
    speakers = [SpeechInterval(0, 27000, "SPEAKER_00")]

    assert split_for_asr(speech, speakers) == [
        SpeechInterval(0, 24000, "SPEAKER_00"),
        SpeechInterval(24100, 27000, "SPEAKER_00"),
    ]


def test_longer_pause_keeps_separate_utterances():
    # Meeting 2 near 03:09: this 490 ms pause separates two clauses.
    speech = [SpeechInterval(187478, 188423), SpeechInterval(188913, 194802)]
    speakers = [SpeechInterval(187000, 195000, "SPEAKER_04")]

    assert split_for_asr(speech, speakers) == [
        SpeechInterval(187478, 188423, "SPEAKER_04"),
        SpeechInterval(188913, 194802, "SPEAKER_04"),
    ]


def test_vad_missed_opposing_turn_still_blocks_same_speaker_merge():
    speech = [SpeechInterval(0, 1000), SpeechInterval(1200, 2000)]
    speakers = [
        SpeechInterval(0, 1050, "SPEAKER_00"),
        SpeechInterval(1050, 1150, "SPEAKER_01"),
        SpeechInterval(1150, 2000, "SPEAKER_00"),
    ]

    assert split_for_asr(speech, speakers) == [
        SpeechInterval(0, 1000, "SPEAKER_00"),
        SpeechInterval(1200, 2000, "SPEAKER_00"),
    ]


def test_write_clip_uses_absolute_recording_offsets(monkeypatch):
    samples = (np.arange(SAMPLE_RATE * 4, dtype=np.int32) % 30000).astype(
        np.float32
    ) / 32768
    clip = io.BytesIO()
    original_open = wave.open
    monkeypatch.setattr(wave, "open", lambda path, mode: original_open(clip, mode))
    write_clip(samples, SpeechInterval(2000, 2005), Path("clip.wav"))
    monkeypatch.setattr(
        wave,
        "open",
        lambda path, mode: original_open(io.BytesIO(clip.getvalue()), mode),
    )

    decoded = read_wav(Path("clip.wav"))
    np.testing.assert_array_equal(decoded, samples[32000:32080])


def test_diarization_uses_local_waveform_and_absolute_turns(monkeypatch):
    samples = np.zeros(SAMPLE_RATE * 12, dtype=np.float32)
    calls = {}

    class Tensor:
        def unsqueeze(self, dimension):
            assert dimension == 0
            return self

    class Pipeline:
        @staticmethod
        def from_pretrained(model_dir):
            calls["model_dir"] = model_dir
            return Pipeline()

        def __call__(self, audio):
            calls["audio"] = audio
            turns = [
                (types.SimpleNamespace(start=8.25, end=9.0), None, "SPEAKER_01"),
                (types.SimpleNamespace(start=2.0, end=3.5), None, "SPEAKER_00"),
            ]
            diarization = types.SimpleNamespace(itertracks=lambda yield_label: turns)
            return types.SimpleNamespace(exclusive_speaker_diarization=diarization)

    torch_module = types.ModuleType("torch")
    torch_module.cuda = types.SimpleNamespace(is_available=lambda: False)
    torch_module.from_numpy = lambda value: Tensor() if value is samples else None
    pyannote_module = types.ModuleType("pyannote")
    audio_module = types.ModuleType("pyannote.audio")
    audio_module.Pipeline = Pipeline
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "pyannote", pyannote_module)
    monkeypatch.setitem(sys.modules, "pyannote.audio", audio_module)

    assert diarize(samples, Path("local/community-1")) == [
        SpeechInterval(2000, 3500, "SPEAKER_00"),
        SpeechInterval(8250, 9000, "SPEAKER_01"),
    ]
    assert calls["model_dir"] == str(Path("local/community-1"))
    assert isinstance(calls["audio"]["waveform"], Tensor)
    assert calls["audio"]["sample_rate"] == SAMPLE_RATE
