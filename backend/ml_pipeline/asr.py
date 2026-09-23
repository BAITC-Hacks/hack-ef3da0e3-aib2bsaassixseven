from __future__ import annotations

import re
from pathlib import Path


class GigaAM:
    def __init__(self, model_dir: Path) -> None:
        from transformers import AutoModel

        self.model = AutoModel.from_pretrained(
            model_dir, trust_remote_code=True, local_files_only=True
        ).eval()
        self.model.to("cuda" if self._cuda_available() else "cpu")

    @staticmethod
    def _cuda_available() -> bool:
        import torch

        return torch.cuda.is_available()

    def transcribe(self, wav_path: Path) -> str:
        return str(self.model.transcribe(str(wav_path))).strip()


class Rukk:
    def __init__(self, model_dir: Path) -> None:
        import torch

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        base = model_dir / "asr" / "rukk"
        self.model = torch.jit.load(
            str(base / "model.pt"), map_location=self.device
        ).eval()
        self.tokens: dict[int, str] = {}
        for line in (base / "tokens.lst").read_text(encoding="utf-8").splitlines():
            if line.strip():
                symbol, index = line.split("\t")
                self.tokens[int(index)] = symbol
        self.blank = max(self.tokens) + 1

    def transcribe(self, wav_path: Path) -> str:
        from ml_pipeline.audio import read_wav

        samples = read_wav(wav_path)
        with self.torch.inference_mode():
            logits = self.model(
                self.torch.from_numpy(samples).unsqueeze(0).to(self.device)
            )[0]
        ids = logits[0].argmax(-1).tolist()
        output: list[str] = []
        previous = None
        for index in ids:
            if index != previous and index != self.blank:
                output.append(self.tokens.get(index, ""))
            previous = index
        return re.sub(
            r"\s+", " ", "".join(output).replace("|", " ").replace("_", " ")
        ).strip()


class WhisperTurbo:
    def __init__(self, model_dir: Path) -> None:
        import torch
        from faster_whisper import WhisperModel

        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = WhisperModel(
            str(model_dir),
            device=device,
            compute_type="float16" if device == "cuda" else "int8",
            local_files_only=True,
        )

    def transcribe(self, wav_path: Path) -> str:
        segments, _ = self.model.transcribe(
            str(wav_path), beam_size=5, vad_filter=False, multilingual=True
        )
        return " ".join(segment.text.strip() for segment in segments).strip()


def load_asr(name: str, model_dir: Path):
    if name.startswith("gigaam-"):
        return GigaAM(model_dir)
    if name == "rukk":
        return Rukk(model_dir)
    if name == "whisper-turbo":
        return WhisperTurbo(model_dir)
    raise ValueError(f"unknown ASR model: {name}")
