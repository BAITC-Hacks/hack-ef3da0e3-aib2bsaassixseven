from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Utterance(StrictModel):
    id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    speaker_id: str | None
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def check_interval(self) -> Utterance:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must exceed start_ms")
        return self


class Transcript(StrictModel):
    audio_path: str
    meeting_at: datetime | None
    timezone: str
    participants: list[str]
    asr_model: str
    utterances: list[Utterance]


class EvidenceItem(StrictModel):
    text: str = Field(min_length=1)
    source_utterance_ids: list[str] = Field(min_length=1)
    evidence_quote: str = Field(min_length=1)
    needs_review: bool = False


class Task(StrictModel):
    action: str = Field(min_length=1)
    responsible: str | None = None
    due_date: date | None = None
    due_text: str | None = None
    source_utterance_ids: list[str] = Field(min_length=1)
    evidence_quote: str = Field(min_length=1)
    needs_review: bool = False


class Abstraction(StrictModel):
    key_facts: list[EvidenceItem] = Field(default_factory=list)
    decisions: list[EvidenceItem] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)


class AbstractionOutput(Abstraction):
    meeting_at: datetime | None
    timezone: str
    llm_model: str
    validation_warnings: list[str] = Field(default_factory=list)
