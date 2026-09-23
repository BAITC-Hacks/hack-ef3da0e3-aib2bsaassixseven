from __future__ import annotations

from pathlib import Path

from ml_pipeline.audio import SAMPLE_RATE, SpeechInterval


def diarize(samples, model_dir: Path) -> list[SpeechInterval]:
    import torch
    from pyannote.audio import Pipeline

    pipeline = Pipeline.from_pretrained(str(model_dir))
    if torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))
    # The recording has already been decoded by FFmpeg. Supplying its waveform
    # avoids pyannote's optional TorchCodec decoder and preserves its time base.
    waveform = torch.from_numpy(samples).unsqueeze(0)
    output = pipeline({"waveform": waveform, "sample_rate": SAMPLE_RATE})
    result = output.exclusive_speaker_diarization
    intervals = [
        SpeechInterval(round(turn.start * 1000), round(turn.end * 1000), speaker)
        for turn, _, speaker in result.itertracks(yield_label=True)
    ]
    return sorted(intervals, key=lambda item: item.start_ms)
