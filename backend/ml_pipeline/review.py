from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ml_pipeline.models import Utterance


class ReviewedInsertion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^r\d{5}$")
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1)
    review_note: str = Field(min_length=1)


class ReviewedReplacement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    utterance_id: str = Field(pattern=r"^u\d{5}$")
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    old_text: str = Field(min_length=1)
    new_text: str = Field(min_length=1)
    review_note: str = Field(min_length=1)


class ReviewedManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audio_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    insertions: list[ReviewedInsertion] = Field(default_factory=list)
    replacements: list[ReviewedReplacement] = Field(default_factory=list)


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def apply_reviewed_insertions(
    manifest_path: Path,
    audio_path: Path,
    utterances: list[Utterance],
    *,
    duration_ms: int,
) -> tuple[list[Utterance], dict[str, object]]:
    """Apply recording-bound transcript corrections before LLM extraction.

    The manifest is an optional, auditable correction to an ASR/diarization
    boundary failure. It changes the transcript before LLM extraction; it does
    not modify a generated abstraction or a packaged result.
    """
    raw = manifest_path.read_bytes()
    manifest = ReviewedManifest.model_validate(json.loads(raw))
    if manifest.audio_sha256.lower() != _file_sha256(audio_path):
        raise ValueError("reviewed corrections audio SHA-256 does not match")
    corrected = list(utterances)
    replaced_ids: list[str] = []
    for item in manifest.replacements:
        if item.end_ms <= item.start_ms or item.end_ms > duration_ms:
            raise ValueError("reviewed replacement is outside the recording")
        if item.old_text == item.new_text:
            raise ValueError("reviewed replacement must change the text")
        matches = [
            index
            for index, utterance in enumerate(corrected)
            if utterance.id == item.utterance_id
            and utterance.start_ms >= item.start_ms
            and utterance.end_ms <= item.end_ms
            and utterance.text.count(item.old_text) == 1
        ]
        if len(matches) != 1:
            raise ValueError(
                "reviewed replacement must match exactly one utterance "
                "and phrase exactly once"
            )
        index = matches[0]
        utterance = corrected[index]
        corrected[index] = utterance.model_copy(
            update={"text": utterance.text.replace(item.old_text, item.new_text, 1)}
        )
        replaced_ids.append(utterance.id)
    seen = {item.id for item in utterances}
    insertions: list[Utterance] = []
    for item in manifest.insertions:
        if item.id in seen:
            raise ValueError(f"duplicate reviewed utterance id: {item.id}")
        if item.end_ms <= item.start_ms or item.end_ms > duration_ms:
            raise ValueError(f"reviewed utterance {item.id} is outside the recording")
        seen.add(item.id)
        insertions.append(
            Utterance(
                id=item.id,
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                speaker_id=None,
                text=item.text,
            )
        )
    merged = sorted(
        [*corrected, *insertions], key=lambda item: (item.start_ms, item.id)
    )
    audit: dict[str, object] = {
        "manifest_sha256": sha256(raw).hexdigest(),
        "inserted_utterance_ids": [item.id for item in insertions],
    }
    if replaced_ids:
        audit["replaced_utterance_ids"] = replaced_ids
    return merged, audit
