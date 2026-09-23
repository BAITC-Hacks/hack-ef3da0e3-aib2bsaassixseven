"""The exported PDF stays readable for reviewers using Russian and Kazakh."""

from datetime import UTC, date, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from pypdf import PdfReader

from app.models.insights import InsightsV1
from app.models.meeting import Meeting
from app.models.transcript import TranscriptV1
from app.services.pdf_export import render_pdf


def _reviewed_result() -> tuple[Meeting, TranscriptV1, InsightsV1]:
    meeting_id = uuid4()
    segment_id = uuid4()
    unknown_segment_id = uuid4()
    now = datetime(2026, 9, 23, tzinfo=UTC)
    meeting = Meeting.model_validate(
        {
            "id": meeting_id,
            "title": "Итоги встречи <Алматы>",
            "meeting_date": date(2026, 9, 23),
            "timezone": "Asia/Almaty",
            "participants": ["Әлия", "Бекзат"],
            "recording_notice_confirmed": True,
            "language_hint": "mixed",
            "created_at": now,
            "updated_at": now,
            "attempt": 1,
            "revision": 1,
            "status": "approved",
            "stage": None,
            "source_available": True,
            "cleanup_status": "pending",
            "temporary_expires_at": None,
            "source": {
                "kind": "demo_fixture",
                "label": "Подготовленный пример · обработка выполнена заранее",
                "fixture_id": "synthetic-1",
            },
            "failure": None,
        }
    )
    transcript = TranscriptV1.model_validate(
        {
            "schema_version": 1,
            "meeting_id": meeting_id,
            "revision": 1,
            "speakers": [
                {
                    "speaker_id": "speaker_1",
                    "display_name": "Әлия",
                    "identity_status": "named",
                },
                {
                    "speaker_id": "speaker_2",
                    "display_name": None,
                    "identity_status": "unknown",
                },
            ],
            "segments": [
                {
                    "id": segment_id,
                    "start_ms": 1000,
                    "end_ms": 4000,
                    "speaker_id": "speaker_1",
                    "language": "kk",
                    "text": "Жоба келесі аптада дайын болады.",
                    "edited": True,
                },
                {
                    "id": unknown_segment_id,
                    "start_ms": 5000,
                    "end_ms": 7000,
                    "speaker_id": "speaker_2",
                    "language": "ru",
                    "text": "Неизвестный участник подтвердил сроки.",
                    "edited": True,
                },
                {
                    "id": uuid4(),
                    "start_ms": 8000,
                    "end_ms": 9000,
                    "speaker_id": "speaker_1",
                    "language": "ru",
                    "text": "Финальная ремарка без ссылки.",
                    "edited": True,
                },
            ],
        }
    )
    evidence = {"segment_id": segment_id, "start_ms": 1200, "end_ms": 3400}
    insights = InsightsV1.model_validate(
        {
            "schema_version": 1,
            "meeting_id": meeting_id,
            "revision": 1,
            "summary": [
                {
                    "id": uuid4(),
                    "text": "Қысқаша қорытынды",
                    "evidence": [
                        evidence,
                        {
                            "segment_id": unknown_segment_id,
                            "start_ms": 5200,
                            "end_ms": 6800,
                        },
                    ],
                }
            ],
            "action_items": [
                {
                    "id": uuid4(),
                    "text": "Подготовить отчёт & смету",
                    "evidence": [evidence],
                    "assignee_speaker_id": "speaker_1",
                    "assignee_name": None,
                    "due_date": date(2026, 10, 1),
                    "due_date_text": None,
                },
                {
                    "id": uuid4(),
                    "text": "Келісімді тексеру",
                    "evidence": [evidence],
                    "assignee_speaker_id": None,
                    "assignee_name": "Заң бөлімі",
                    "due_date": None,
                    "due_date_text": "келесі жұмаға дейін",
                },
            ],
        }
    )
    return meeting, transcript, insights


def test_pdf_extracts_unicode_summary_actions_and_evidence() -> None:
    meeting, transcript, insights = _reviewed_result()

    result = render_pdf(meeting, transcript, insights)

    assert result.startswith(b"%PDF-")
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(result)).pages)
    for expected in (
        "Итоги встречи <Алматы>",
        "Проверено и утверждено человеком",
        "Подготовленный пример · обработка выполнена заранее",
        "Қысқаша қорытынды",
        "Подготовить отчёт & смету",
        "Келісімді тексеру",
        "Әлия",
        "Заң бөлімі",
        "2026-10-01",
        "келесі жұмаға дейін",
        "Жоба келесі аптада дайын болады.",
        "00:00:01.200 - 00:00:03.400",
        "Транскрипт",
        "Финальная ремарка без ссылки.",
        "00:00:08.000 - 00:00:09.000",
    ):
        assert expected in text
    assert text.count("Неизвестный спикер (speaker_2)") >= 2


def test_pdf_rejects_mismatched_review_revisions() -> None:
    meeting, transcript, insights = _reviewed_result()
    meeting.revision = 2

    with pytest.raises(ValueError, match="revision"):
        render_pdf(meeting, transcript, insights)


def test_pdf_rejects_unapproved_meeting() -> None:
    meeting, transcript, insights = _reviewed_result()
    meeting.status = "review_required"

    with pytest.raises(ValueError, match="approved"):
        render_pdf(meeting, transcript, insights)
