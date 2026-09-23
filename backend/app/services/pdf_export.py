"""Render a reviewed meeting as a self-contained, Unicode PDF."""

from functools import partial
from html import escape
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from app.models.insights import InsightsV1, SummaryItem
from app.models.meeting import Meeting
from app.models.transcript import Speaker, TranscriptV1

_FONT_NAME = "MeetingNotoSans"
_FONT_PATH = Path(__file__).with_name("fonts") / "NotoSans.ttf"
_INK = colors.HexColor("#17212F")
_MUTED = colors.HexColor("#526070")
_ACCENT = colors.HexColor("#245C80")


def _font_ready() -> None:
    if _FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(  # pyright: ignore[reportUnknownMemberType]
            TTFont(_FONT_NAME, str(_FONT_PATH))
        )


def _markup(value: str) -> str:
    return escape(value).replace("\n", "<br/>")


def _timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _speaker_label(speaker: Speaker) -> str:
    if speaker.display_name is not None:
        return speaker.display_name
    if speaker.identity_status == "unknown":
        return f"Неизвестный спикер ({speaker.speaker_id})"
    return f"Спикер ({speaker.speaker_id})"


def _draw_page(canvas: Canvas, document: SimpleDocTemplate) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#DCE3E8"))
    canvas.line(46, 47, A4[0] - 46, 47)
    canvas.setFillColor(_MUTED)
    canvas.setFont(_FONT_NAME, 8)
    canvas.drawString(46, 33, "Протокол встречи")
    canvas.drawRightString(A4[0] - 46, 33, str(document.page))
    canvas.restoreState()


def _evidence_paragraphs(
    item: SummaryItem,
    transcript: TranscriptV1,
    style: ParagraphStyle,
) -> list[Paragraph]:
    segments = {segment.id: segment for segment in transcript.segments}
    speakers = {speaker.speaker_id: speaker for speaker in transcript.speakers}
    paragraphs: list[Paragraph] = []
    for evidence in item.evidence:
        segment = segments[evidence.segment_id]
        speaker = speakers[segment.speaker_id]
        name = _speaker_label(speaker)
        interval = f"{_timestamp(evidence.start_ms)} - {_timestamp(evidence.end_ms)}"
        text = (
            f"Основание: {_markup(name)}, {interval}<br/>"
            f"«{_markup(segment.text)}»"
        )
        paragraphs.append(Paragraph(text, style))
    return paragraphs


def render_pdf(
    meeting: Meeting,
    transcript: TranscriptV1,
    insights: InsightsV1,
) -> bytes:
    """Return a reviewed meeting PDF without writing to the artifact store."""
    if meeting.status != "approved":
        raise ValueError("Meeting must be approved before PDF export")
    if (meeting.id, meeting.revision) != (
        transcript.meeting_id,
        transcript.revision,
    ):
        raise ValueError("Meeting and transcript must share meeting ID and revision")
    insights.validate_against(transcript)
    _font_ready()

    title_style = ParagraphStyle(
        "meeting-title",
        fontName=_FONT_NAME,
        fontSize=18,
        leading=24,
        textColor=_INK,
        alignment=TA_LEFT,
        spaceAfter=8,
    )
    metadata_style = ParagraphStyle(
        "meeting-metadata",
        fontName=_FONT_NAME,
        fontSize=9,
        leading=14,
        textColor=_MUTED,
        spaceAfter=3,
    )
    approval_style = ParagraphStyle(
        "meeting-approval",
        fontName=_FONT_NAME,
        fontSize=9.5,
        leading=15,
        textColor=_ACCENT,
        spaceAfter=8,
    )
    heading_style = ParagraphStyle(
        "meeting-section",
        fontName=_FONT_NAME,
        fontSize=12,
        leading=17,
        textColor=_ACCENT,
        spaceBefore=16,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "meeting-body",
        fontName=_FONT_NAME,
        fontSize=10,
        leading=16,
        textColor=_INK,
        spaceAfter=5,
    )
    evidence_style = ParagraphStyle(
        "meeting-evidence",
        fontName=_FONT_NAME,
        fontSize=8.5,
        leading=13,
        textColor=_MUTED,
        leftIndent=12,
        spaceAfter=10,
    )

    story: list[Flowable] = [
        Paragraph(_markup(meeting.title), title_style),
        Paragraph("Проверено и утверждено человеком", approval_style),
        Paragraph(
            f"Дата: {meeting.meeting_date.isoformat()} · "
            f"Часовой пояс: {_markup(meeting.timezone)}",
            metadata_style,
        ),
        Paragraph(
            "Участники: " + _markup(", ".join(meeting.participants)),
            metadata_style,
        ),
    ]
    if meeting.source.kind == "demo_fixture" and meeting.source.label:
        story.append(Paragraph(_markup(meeting.source.label), metadata_style))
    story.extend(
        [
            Spacer(1, 11),
            HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#DCE3E8")),
            Paragraph("Краткое содержание", heading_style),
        ]
    )
    if insights.summary:
        for index, item in enumerate(insights.summary, start=1):
            story.append(Paragraph(f"{index}. {_markup(item.text)}", body_style))
            story.extend(_evidence_paragraphs(item, transcript, evidence_style))
    else:
        story.append(Paragraph("Нет пунктов.", body_style))

    story.append(Paragraph("Поручения", heading_style))
    if insights.action_items:
        speaker_names = {
            speaker.speaker_id: _speaker_label(speaker)
            for speaker in transcript.speakers
        }
        for index, item in enumerate(insights.action_items, start=1):
            story.append(Paragraph(f"{index}. {_markup(item.text)}", body_style))
            assignee = item.assignee_name
            if item.assignee_speaker_id is not None:
                assignee = speaker_names[item.assignee_speaker_id]
            story.append(
                Paragraph(
                    "Ответственный: " + _markup(assignee or "Не указан"),
                    metadata_style,
                )
            )
            due_values = [
                value
                for value in (
                    item.due_date.isoformat() if item.due_date else None,
                    item.due_date_text,
                )
                if value is not None
            ]
            story.append(
                Paragraph(
                    "Срок: " + _markup("; ".join(due_values) or "Не указан"),
                    metadata_style,
                )
            )
            story.extend(_evidence_paragraphs(item, transcript, evidence_style))
    else:
        story.append(Paragraph("Нет поручений.", body_style))

    story.append(Paragraph("Транскрипт", heading_style))
    speaker_names = {
        speaker.speaker_id: _speaker_label(speaker)
        for speaker in transcript.speakers
    }
    if transcript.segments:
        for segment in transcript.segments:
            interval = f"{_timestamp(segment.start_ms)} - {_timestamp(segment.end_ms)}"
            story.append(
                Paragraph(
                    f"{interval} · {_markup(speaker_names[segment.speaker_id])}",
                    metadata_style,
                )
            )
            story.append(Paragraph(_markup(segment.text), body_style))
            story.append(Spacer(1, 6))
    else:
        story.append(Paragraph("Нет сегментов.", body_style))

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=46,
        leftMargin=46,
        topMargin=46,
        bottomMargin=62,
        title=meeting.title,
        author="Hackalem",
    )
    document.build(
        story,
        onFirstPage=_draw_page,
        onLaterPages=_draw_page,
        canvasmaker=partial(Canvas, invariant=1),
    )
    return output.getvalue()
