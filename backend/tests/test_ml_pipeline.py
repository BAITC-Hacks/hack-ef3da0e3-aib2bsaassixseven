from datetime import UTC, date, datetime

import pytest

from ml_pipeline.abstraction import (
    chunk_utterances,
    extract_abstraction,
    normalize_deadline,
    render_summary,
    validate_evidence,
)
from ml_pipeline.audio import SpeechInterval, split_for_asr
from ml_pipeline.models import Abstraction, EvidenceItem, Task, Utterance


def test_split_for_asr_keeps_absolute_times_and_speaker_boundaries():
    speech = [SpeechInterval(1000, 11000)]
    speakers = [
        SpeechInterval(0, 5000, "SPEAKER_00"),
        SpeechInterval(5000, 12000, "SPEAKER_01"),
    ]
    assert split_for_asr(speech, speakers, max_ms=3000) == [
        SpeechInterval(1000, 4000, "SPEAKER_00"),
        SpeechInterval(4000, 5000, "SPEAKER_00"),
        SpeechInterval(5000, 8000, "SPEAKER_01"),
        SpeechInterval(8000, 11000, "SPEAKER_01"),
    ]


def test_relative_deadline_requires_meeting_date():
    assert normalize_deadline("через две недели", None) == (None, True)
    meeting = datetime(2026, 9, 23, 10, tzinfo=UTC)
    assert normalize_deadline("через две недели", meeting) == (date(2026, 10, 7), False)
    assert normalize_deadline("до пятницы", meeting) == (date(2026, 9, 25), False)
    assert normalize_deadline("екі аптадан кейін", meeting) == (
        date(2026, 10, 7),
        False,
    )
    assert normalize_deadline("на следующей неделе", meeting) == (None, True)


def test_explicit_year_and_negated_relative_day_are_respected():
    meeting = datetime(2026, 9, 23, 10, tzinfo=UTC)
    assert normalize_deadline("до 2 октября 2027 года", meeting) == (
        date(2027, 10, 2), False,
    )
    assert normalize_deadline("не завтра, а через три дня", meeting) == (
        date(2026, 9, 26), False,
    )


def test_unsupported_evidence_and_speaker_as_owner_rejected():
    utterances = [
        Utterance(
            id="u0001",
            start_ms=0,
            end_ms=1000,
            speaker_id="SPEAKER_00",
            text="Ерлан подготовит отчёт к среде.",
        )
    ]
    abstraction = Abstraction(
        tasks=[
            Task(
                action="Подготовить отчёт",
                responsible="SPEAKER_00",
                due_text="к среде",
                source_utterance_ids=["u0001"],
                evidence_quote="Ерлан подготовит отчёт к среде.",
                needs_review=False,
            )
        ]
    )
    with pytest.raises(ValueError, match="speaker label"):
        validate_evidence(abstraction, utterances)
    abstraction.tasks[0].responsible = "Ерлан"
    abstraction.tasks[0].evidence_quote = "Несуществующая цитата"
    with pytest.raises(ValueError, match="quote"):
        validate_evidence(abstraction, utterances)


def test_uncited_owner_is_marked_for_review():
    utterance = Utterance(
        id="u1",
        start_ms=0,
        end_ms=1000,
        speaker_id="SPEAKER_00",
        text="Подготовьте отчёт.",
    )
    task = Task(
        action="Подготовить отчёт",
        responsible="Ерлан",
        source_utterance_ids=["u1"],
        evidence_quote="Подготовьте отчёт.",
    )
    validate_evidence(Abstraction(tasks=[task]), [utterance])
    assert task.needs_review
    assert task.responsible is None


def test_uncited_deadline_is_not_converted():
    utterance = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id=None, text="Подготовьте отчёт."
    )
    task = Task(
        action="Подготовить отчёт",
        due_text="завтра",
        source_utterance_ids=["u1"],
        evidence_quote="Подготовьте отчёт.",
    )
    validate_evidence(Abstraction(tasks=[task]), [utterance])
    assert task.due_text is None
    assert task.needs_review


def test_summary_contains_only_validated_abstraction_items():
    abstraction = Abstraction(
        key_facts=[
            EvidenceItem(
                text="Загрузка — 71%",
                source_utterance_ids=["u0001"],
                evidence_quote="загрузка 71%",
            )
        ],
        tasks=[
            Task(
                action="Подготовить отчёт",
                responsible=None,
                due_text=None,
                source_utterance_ids=["u0002"],
                evidence_quote="подготовить отчёт",
                needs_review=True,
            )
        ],
    )
    summary = render_summary(abstraction)
    assert "загрузка 71%" in summary
    assert "Загрузка — 71%" not in summary
    assert "Подготовить отчёт" in summary
    assert "u0001" in summary and "u0002" in summary
    assert "требует проверки" in summary


def test_summary_marks_earlier_supplier_deadline_as_replaced():
    original = "а вы параллельно за две недели найдите альтернативного поставщика"
    abstraction = Abstraction(
        decisions=[EvidenceItem(
            text=original,
            source_utterance_ids=["u10"],
            evidence_quote=original,
            needs_review=True,
        )],
        tasks=[Task(
            action="Найти альтернативного поставщика сырья",
            responsible="Батагоз Нурлановна",
            due_text="неделя максимум десять дней",
            source_utterance_ids=["u10", "u37"],
            evidence_quote=original,
            needs_review=True,
        )],
    )
    summary = render_summary(abstraction)
    decision = summary.split("## Решения\n\n", 1)[1].split("## Поручения", 1)[0]
    assert "исходный срок «за две недели»" in decision
    assert "уточнён до «неделя максимум десять дней»" in decision
    assert "[u10, u37]" in decision
    assert "исходный срок «за две недели»" in summary.split("## Поручения", 1)[1]


def test_summary_shows_only_dated_second_commitment_in_fused_reply():
    abstraction = Abstraction(tasks=[Task(
        action="Дать смету по дополнительным группам",
        responsible="Ерболат Мухтарович",
        due_text="за неделю",
        source_utterance_ids=["u28", "u27", "u21"],
        evidence_quote="понял найду тренера за неделю дам смету по доб группам",
        needs_review=True,
    )])
    summary = render_summary(abstraction)
    assert "Дать смету по дополнительным группам" in summary
    assert "дам смету по доб группам" in summary
    assert "найду тренера" not in summary


def test_summary_does_not_call_longer_equivalent_due_text_a_correction():
    abstraction = Abstraction(tasks=[Task(
        action="Организовать дополнительные группы или привлечь тренера",
        due_text="закрыть очередь за месяц",
        source_utterance_ids=["u27"],
        evidence_quote=(
            "организуйте дополнительные группы если нужно привлеките внешнего "
            "тренера чтобы закрыть очередь за месяц"
        ),
        needs_review=True,
    )])
    summary = render_summary(abstraction)
    assert "срок: закрыть очередь за месяц" in summary
    assert "исходный срок" not in summary
    assert "уточнён до" not in summary


def test_summary_does_not_assign_template_deadline_to_notifications():
    abstraction = Abstraction(tasks=[Task(
        action="Обновить шаблон договора с новыми условиями",
        responsible="Салтанат Ерболовна",
        due_text="не больше недели",
        source_utterance_ids=["u35", "u40"],
        evidence_quote="подготовлю уведомления и обновлю шаблон договора",
        needs_review=True,
    )])
    summary = render_summary(abstraction)
    assert "Обновить шаблон договора" in summary
    assert "обновлю шаблон договора" in summary
    assert "подготовлю уведомления" not in summary
    assert "срок: не больше недели" in summary


def test_later_chunk_replaces_deadline_and_cancels_task():
    import json

    utterances = [
        Utterance(
            id="u1",
            start_ms=0,
            end_ms=1000,
            speaker_id="SPEAKER_00",
            text="Ерлан подготовит план закупок до 30 сентября.",
        ),
        Utterance(
            id="u2",
            start_ms=1000,
            end_ms=2000,
            speaker_id="SPEAKER_00",
            text="Айнур проверит договор к пятнице.",
        ),
        Utterance(
            id="u3",
            start_ms=2000,
            end_ms=3000,
            speaker_id="SPEAKER_00",
            text="Срок плана закупок переносим на 2 октября.",
        ),
        Utterance(
            id="u4",
            start_ms=3000,
            end_ms=4000,
            speaker_id="SPEAKER_00",
            text="Проверку договора отменяем.",
        ),
    ]
    original = {
        "key_facts": [],
        "decisions": [],
        "tasks": [
            {
                "action": "Подготовить план закупок",
                "responsible": "Ерлан",
                "due_date": None,
                "due_text": "до 30 сентября",
                "source_utterance_ids": ["u1"],
                "evidence_quote": "Ерлан подготовит план закупок до 30 сентября.",
                "needs_review": False,
            },
            {
                "action": "Проверить договор",
                "responsible": "Айнур",
                "due_date": None,
                "due_text": "к пятнице",
                "source_utterance_ids": ["u2"],
                "evidence_quote": "Айнур проверит договор к пятнице.",
                "needs_review": False,
            },
        ],
    }
    later = {"key_facts": [], "decisions": [], "tasks": []}
    merged = {
        "key_facts": [],
        "decisions": [],
        "tasks": [
            {
                "action": "Подготовить план закупок",
                "responsible": "Ерлан",
                "due_date": None,
                "due_text": "2 октября",
                "source_utterance_ids": ["u1", "u3"],
                "evidence_quote": "Срок плана закупок переносим на 2 октября.",
                "needs_review": False,
            },
        ],
    }

    class ScriptedGenerator:
        def __init__(self):
            self.responses = iter([original, later, merged])

        def generate(self, prompt):
            return json.dumps(next(self.responses), ensure_ascii=False)

    result = extract_abstraction(
        utterances,
        ScriptedGenerator(),
        datetime(2026, 9, 23, 10, tzinfo=UTC),
        [],
        max_chars=180,
    )
    assert len(result.tasks) == 1
    assert result.tasks[0].due_date == date(2026, 10, 2)
    assert result.tasks[0].responsible == "Ерлан"


def test_invalid_llm_json_is_rejected_after_repair_attempt():
    utterance = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id=None, text="Нужен отчёт."
    )

    class BrokenGenerator:
        def generate(self, prompt):
            return '{"key_facts": [], "decisions": [], "tasks": [], "extra": 1}'

    with pytest.raises(ValueError, match="invalid abstraction JSON"):
        extract_abstraction([utterance], BrokenGenerator(), None, [])


def test_missing_json_sections_are_rejected_after_repair_attempt():
    utterance = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id=None, text="Нужен отчёт."
    )

    class IncompleteGenerator:
        def generate(self, prompt):
            return '{"tasks": []}'

    with pytest.raises(ValueError, match="invalid abstraction JSON"):
        extract_abstraction([utterance], IncompleteGenerator(), None, [])


def test_model_supplied_due_date_is_rejected_after_repair_attempt():
    import json

    utterance = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id=None,
        text="Ерлан подготовит отчёт завтра."
    )
    response = {
        "key_facts": [], "decisions": [],
        "tasks": [{
            "action": "Подготовить отчёт", "responsible": "Ерлан",
            "due_date": "2026-09-24", "due_text": "завтра",
            "source_utterance_ids": ["u1"],
            "evidence_quote": "Ерлан подготовит отчёт завтра.",
            "needs_review": False,
        }],
    }

    class PrematureDateGenerator:
        def generate(self, prompt):
            return json.dumps(response, ensure_ascii=False)

    with pytest.raises(ValueError, match="invalid abstraction JSON"):
        extract_abstraction([utterance], PrematureDateGenerator(), None, [])


def test_deadline_cannot_be_spliced_across_utterances():
    utterances = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id=None,
                  text="Ерлан подготовит отчёт завтра"),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id=None,
                  text="или послезавтра"),
    ]
    task = Task(
        action="Подготовить отчёт", responsible="Ерлан",
        due_text="завтра или послезавтра",
        source_utterance_ids=["u1", "u2"],
        evidence_quote="Ерлан подготовит отчёт завтра",
    )
    validate_evidence(Abstraction(tasks=[task]), utterances)
    assert task.due_text is None
    assert task.needs_review


def test_ambiguous_relative_deadline_is_not_normalized():
    meeting = datetime(2026, 9, 23, 10, tzinfo=UTC)
    assert normalize_deadline("завтра или послезавтра", meeting) == (None, True)
    assert normalize_deadline("2026-09-24 или 2026-09-25", meeting) == (
        None, True
    )
    assert normalize_deadline("не 2026-09-24, а 2026-09-25", meeting) == (
        None, True
    )


def test_long_utterance_is_split_without_exceeding_chunk_budget():
    utterance = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id=None,
        text="А" * 220,
    )
    chunks = chunk_utterances([utterance], max_chars=100)
    fragments = [item for chunk in chunks for item in chunk]
    assert len(chunks) > 1
    assert "".join(item.text for item in fragments) == utterance.text
    assert all(len(item.text) + 32 <= 100 for item in fragments)


def test_paraphrased_or_unsupported_claims_require_manual_review():
    utterance = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id=None,
        text="Ерлан обсудил бюджет и отчёт.",
    )
    fact = EvidenceItem(
        text="Бюджет утверждён", source_utterance_ids=["u1"],
        evidence_quote="Ерлан обсудил бюджет и отчёт.",
    )
    task = Task(
        action="Ерлан увеличит бюджет", responsible="Ерлан",
        source_utterance_ids=["u1"],
        evidence_quote="Ерлан обсудил бюджет и отчёт.",
    )
    abstraction = Abstraction(key_facts=[fact], tasks=[task])
    validate_evidence(abstraction, [utterance])
    summary = render_summary(abstraction)
    assert fact.needs_review
    assert task.needs_review
    assert "Бюджет утверждён" not in summary
    assert "Ерлан увеличит бюджет" not in summary
    assert "Ерлан обсудил бюджет и отчёт." in summary
    assert "требует проверки" in summary


def test_duplicate_json_keys_are_rejected_after_repair_attempt():
    utterance = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id=None, text="Нужен отчёт."
    )

    class DuplicateKeyGenerator:
        def generate(self, prompt):
            return '{"key_facts": [], "key_facts": [], "decisions": [], "tasks": []}'

    with pytest.raises(ValueError, match="invalid abstraction JSON"):
        extract_abstraction([utterance], DuplicateKeyGenerator(), None, [])


def test_reconciliation_uses_cited_fragment_of_long_utterance():
    import json

    utterance = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id=None,
        text="Решили начать работу. " + "А" * 220,
    )
    fact = {
        "text": "Решили начать работу.",
        "source_utterance_ids": ["u1"],
        "evidence_quote": "Решили начать работу.",
    }

    class InspectingGenerator:
        def __init__(self):
            self.calls = 0

        def generate(self, prompt):
            self.calls += 1
            if "Реплики-основания:" in prompt:
                evidence_lines = prompt.split("Реплики-основания:\n", 1)[1]
                assert utterance.text not in evidence_lines
            has_prior_context = "Реплики-основания:" in prompt
            response = {
                "key_facts": [fact] if self.calls == 1 or has_prior_context else [],
                "decisions": [], "tasks": [],
            }
            return json.dumps(response, ensure_ascii=False)

    result = extract_abstraction(
        [utterance], InspectingGenerator(), None, [], max_chars=100
    )
    assert len(result.key_facts) == 1


def test_deadline_word_inside_another_word_is_not_evidence():
    utterance = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id=None,
        text="Ерлан подготовит отчёт послезавтра.",
    )
    task = Task(
        action="Подготовить отчёт", responsible="Ерлан", due_text="завтра",
        source_utterance_ids=["u1"],
        evidence_quote="Ерлан подготовит отчёт послезавтра.",
    )
    validate_evidence(Abstraction(tasks=[task]), [utterance])
    assert task.due_text is None
    assert task.needs_review


def test_owner_inside_another_name_is_not_evidence():
    utterance = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id=None,
        text="Ерланова подготовит отчёт.",
    )
    task = Task(
        action="Подготовить отчёт", responsible="Ерлан",
        source_utterance_ids=["u1"],
        evidence_quote="Ерланова подготовит отчёт.",
    )
    validate_evidence(Abstraction(tasks=[task]), [utterance])
    assert task.responsible is None
    assert task.needs_review


def test_qwen_json_code_fence_is_unwrapped_before_strict_validation():
    utterance = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id=None, text="Начинаем."
    )

    class FencedGenerator:
        def generate(self, prompt):
            return '```json\n{"key_facts": [], "decisions": [], "tasks": []}\n```'

    result = extract_abstraction([utterance], FencedGenerator(), None, [])
    assert result.key_facts == [] and result.decisions == [] and result.tasks == []


def test_invalid_source_id_is_repaired_against_current_chunk():
    import json

    utterance = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id=None, text="Начинаем."
    )

    class RepairingGenerator:
        calls = 0

        def generate(self, prompt):
            self.calls += 1
            if self.calls == 2:
                assert "unknown utterance ids" in prompt
                assert "u1 [0-1000 ms" in prompt
            return json.dumps(
                {
                    "key_facts": [
                        {
                            "text": "Начинаем.",
                            "source_utterance_ids": ["u5" if self.calls == 1 else "u1"],
                            "evidence_quote": "Начинаем.",
                            "needs_review": False,
                        }
                    ],
                    "decisions": [],
                    "tasks": [],
                },
                ensure_ascii=False,
            )

    generator = RepairingGenerator()
    result = extract_abstraction([utterance], generator, None, [])
    assert generator.calls == 2
    assert result.key_facts[0].source_utterance_ids == ["u1"]


def test_source_id_zero_padding_is_canonicalized_only_with_matching_quote():
    utterance = Utterance(
        id="u00005", start_ms=0, end_ms=1000, speaker_id=None,
        text="Начинаем.",
    )
    fact = EvidenceItem(
        text="Начинаем.", source_utterance_ids=["u0005"],
        evidence_quote="Начинаем.",
    )
    validate_evidence(Abstraction(key_facts=[fact]), [utterance])
    assert fact.source_utterance_ids == ["u00005"]


def test_unsupported_llm_quote_is_dropped_and_reported():
    import json

    utterance = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id=None, text="Начинаем."
    )

    class UnsupportedGenerator:
        def generate(self, prompt):
            return json.dumps(
                {
                    "key_facts": [
                        {
                            "text": "Решили увеличить бюджет",
                            "source_utterance_ids": ["u1"],
                            "evidence_quote": "увеличить бюджет",
                            "needs_review": False,
                        }
                    ],
                    "decisions": [],
                    "tasks": [],
                },
                ensure_ascii=False,
            )

    warnings: list[str] = []
    result = extract_abstraction(
        [utterance], UnsupportedGenerator(), None, [],
        validation_warnings=warnings,
    )
    assert result.key_facts == []
    assert len(warnings) == 1 and "Dropped key_facts[0]" in warnings[0]
    assert "увеличить бюджет" not in render_summary(result, warnings)


def test_concatenated_asr_quote_keeps_item_with_one_verbatim_source():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="S1",
                  text="Провести аудит"),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="S1",
                  text="и подготовить отчёт"),
    ]
    decision = EvidenceItem(
        text="Провести аудит",
        source_utterance_ids=["u1", "u2"],
        evidence_quote="Провести аудит и подготовить отчёт",
    )
    validate_evidence(Abstraction(decisions=[decision]), turns)
    assert decision.evidence_quote == "Провести аудит"
    assert decision.needs_review


def test_unsupported_region_and_causation_do_not_remain_in_fact_text():
    turn = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id=None,
        text="На заводе была разгерметизация, датчики не проходили поверку.",
    )
    fact = EvidenceItem(
        text="На заводе в другом регионе была разгерметизация из-за датчиков.",
        source_utterance_ids=["u1"],
        evidence_quote=turn.text,
    )
    validate_evidence(Abstraction(key_facts=[fact]), [turn])
    assert fact.text == turn.text
    assert fact.needs_review


def test_contextual_owner_is_cited_without_speaker_name_mapping():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="S1",
                  text="Ерлан Петрович, вы курируете договоры."),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="S2",
                  text="Да."),
        Utterance(id="u3", start_ms=2000, end_ms=3000, speaker_id="S1",
                  text="Подготовьте претензию к пятнице."),
    ]
    task = Task(
        action="Подготовить претензию", responsible=None, due_text="к пятнице",
        source_utterance_ids=["u3"], evidence_quote=turns[2].text,
    )
    validate_evidence(Abstraction(tasks=[task]), turns)
    assert task.responsible == "Ерлан Петрович"
    assert task.source_utterance_ids == ["u3", "u1"]
    assert task.needs_review


def test_direct_address_then_first_person_reply_can_ground_owner():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
                  text="Айнур Каировна, запросите заключение у юристов."),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="other",
                  text="Хорошо, запрошу заключение к среде."),
    ]
    task = Task(
        action="Запросить заключение", responsible="Айнур Каировна",
        due_text="к среде", source_utterance_ids=["u2"],
        evidence_quote=turns[1].text,
    )
    validate_evidence(Abstraction(tasks=[task]), turns)
    assert task.responsible == "Айнур Каировна"
    assert "u1" in task.source_utterance_ids
    assert task.needs_review


def test_name_after_first_person_commitment_is_not_previous_task_owner():
    turn = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id="S1",
        text=("По итогам совещания короткую справку. Сделаю. "
              "Ерболат Мухтарович, по вашему направлению."),
    )
    task = Task(
        action="Подготовить короткую справку",
        responsible="Ерболат Мухтарович",
        source_utterance_ids=["u1"], evidence_quote=turn.text,
    )
    validate_evidence(Abstraction(tasks=[task]), [turn])
    assert task.responsible is None
    assert task.needs_review


def test_later_subject_linked_recap_names_owner_and_adds_source():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
                  text=("По итогам совещания с подрядчиками короткую справку. "
                        "Сделаю. Ерболат Мухтарович, по вашему направлению.")),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="chair",
                  text="Жандос Талгатович, совещание с подрядчиками, жду справку."),
    ]
    task = Task(
        action="Подготовить справку по совещанию с подрядчиками",
        responsible="Ерболат Мухтарович",
        source_utterance_ids=["u1"], evidence_quote=turns[0].text,
    )
    validate_evidence(Abstraction(tasks=[task]), turns)
    assert task.responsible == "Жандос Талгатович"
    assert "u2" in task.source_utterance_ids
    assert task.needs_review


def test_later_recap_with_only_meeting_context_does_not_name_owner():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
                  text="Подготовить справку по итогам совещания."),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="chair",
                  text="Ерболат Мухтарович, по итогам совещания жду смету."),
    ]
    task = Task(
        action="Подготовить справку по итогам совещания", responsible=None,
        source_utterance_ids=["u1"], evidence_quote=turns[0].text,
    )
    validate_evidence(Abstraction(tasks=[task]), turns)
    assert task.responsible is None
    assert task.source_utterance_ids == ["u1"]


def test_summary_address_and_topic_deadline_ground_supplier_owner():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
                  text="За две недели найдите альтернативного поставщика."),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="chair",
                  text=("Подытожим. Батагоз Нурлановна, по вашим вопросам "
                        "неделя максимум десять дней на поиск альтернативы.")),
    ]
    task = Task(
        action="Найти альтернативного поставщика", responsible=None,
        due_text="за две недели", source_utterance_ids=["u1"],
        evidence_quote=turns[0].text,
    )
    validate_evidence(Abstraction(tasks=[task]), turns)
    assert task.responsible == "Батагоз Нурлановна"
    assert task.due_text == "неделя максимум десять дней"
    assert "u2" in task.source_utterance_ids
    assert task.needs_review


def test_first_person_estimate_uses_prior_address_deadline_and_split_subject():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
                  text="Ерболат Мухтарович, по вашему направлению."),
        Utterance(id="u2", start_ms=1100, end_ms=2100, speaker_id="worker",
                  text="Есть проблема по обучению."),
        Utterance(id="u3", start_ms=2200, end_ms=3200, speaker_id="worker",
                  text="Очередь на переаттестацию персонала."),
        Utterance(id="u4", start_ms=3300, end_ms=4300, speaker_id="chair",
                  text="Организуйте дополнительные группы."),
        Utterance(id="u5", start_ms=4400, end_ms=5400, speaker_id="worker",
                  text="Понял найду тренера за неделю дам смету подоп"),
        Utterance(id="u6", start_ms=5500, end_ms=6000, speaker_id="worker",
                  text="группам"),
    ]
    task = Task(
        action="Подготовить смету на привлечение тренера", responsible=None,
        due_text="дам смету", source_utterance_ids=["u5"],
        evidence_quote="дам смету",
    )
    validate_evidence(Abstraction(tasks=[task]), turns)
    assert task.responsible == "Ерболат Мухтарович"
    assert task.due_text == "за неделю"
    assert task.action == "Дать смету по дополнительным группам"
    assert task.source_utterance_ids == ["u5", "u1", "u4", "u6"]
    assert task.needs_review


def test_fused_first_person_reply_keeps_estimate_deadline_off_trainer_task():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
                  text="Ерболат Мухтарович, по вашему направлению."),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="chair",
                  text=("Организуйте дополнительные группы, если нужно "
                        "привлеките внешнего тренера, закройте очередь за месяц.")),
        Utterance(id="u3", start_ms=2000, end_ms=3000, speaker_id="worker",
                  text="Понял найду тренера за неделю дам смету по доб группам."),
    ]
    training = Task(
        action="Организовать дополнительные группы или привлечь тренера",
        due_text="за месяц", source_utterance_ids=["u2"],
        evidence_quote=turns[1].text,
    )
    merged = Task(
        action="Найти тренера и предоставить смету по дополнительным группам",
        responsible=None, due_text="за неделю",
        source_utterance_ids=["u3"],
        evidence_quote="найду тренера за неделю дам смету по доб группам",
    )
    abstraction = Abstraction(tasks=[training, merged])
    validate_evidence(abstraction, turns)
    assert len(abstraction.tasks) == 2
    assert merged.action == "Дать смету по дополнительным группам"
    assert merged.due_text == "за неделю"
    assert merged.responsible == "Ерболат Мухтарович"
    assert "u1" in merged.source_utterance_ids
    assert training.due_text == "за месяц"


def test_fused_reply_retains_trainer_when_model_returns_only_merged_task():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
                  text="Ерболат Мухтарович, по вашему направлению."),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="chair",
                  text="Организуйте дополнительные группы, привлеките тренера."),
        Utterance(id="u3", start_ms=2000, end_ms=3000, speaker_id="worker",
                  text="Понял найду тренера за неделю дам смету по доб группам."),
    ]
    merged = Task(
        action="Найти тренера и предоставить смету по дополнительным группам",
        due_text="за неделю", source_utterance_ids=["u3"],
        evidence_quote="найду тренера за неделю дам смету по доб группам",
    )
    abstraction = Abstraction(tasks=[merged])
    validate_evidence(abstraction, turns)
    assert len(abstraction.tasks) == 2
    assert merged.action == "Дать смету по дополнительным группам"
    trainer = next(task for task in abstraction.tasks if task is not merged)
    assert trainer.action == "Найти тренера"
    assert trainer.due_text is None
    assert trainer.evidence_quote == "найду тренера"
    assert trainer.responsible == "Ерболат Мухтарович"


def test_one_word_acknowledgment_is_not_joined_to_previous_action():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="S1",
                  text="Проведите инструктаж с реальной проверкой знаний"),
        Utterance(id="u2", start_ms=1000, end_ms=1400, speaker_id="S1",
                  text="сделаем"),
    ]
    task = Task(
        action="Провести инструктаж с проверкой знаний",
        source_utterance_ids=["u1"], evidence_quote=turns[0].text,
    )
    validate_evidence(Abstraction(tasks=[task]), turns)
    assert task.action == "Провести инструктаж с проверкой знаний"
    assert task.source_utterance_ids == ["u1"]


def test_explicit_owner_in_same_turn_repairs_missing_or_misspelled_name():
    turn = Utterance(
        id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
        text=("Подготовить финансовое решение по модернизации завода. "
              "Ответственный Тимур Балатович."),
    )
    task = Task(
        action="Подготовить финансовое решение по модернизации завода",
        responsible="Тимур Болатович", source_utterance_ids=["u1"],
        evidence_quote="Подготовить финансовое решение по модернизации завода",
    )
    validate_evidence(Abstraction(tasks=[task]), [turn])
    assert task.responsible == "Тимур Балатович"
    assert task.needs_review


def test_immediately_preceding_reviewed_address_grounds_imperative():
    turns = [
        Utterance(id="r00001", start_ms=0, end_ms=400, speaker_id=None,
                  text="Тимур Болатович"),
        Utterance(id="u1", start_ms=400, end_ms=1600, speaker_id="chair",
                  text="Свяжитесь с Нурланом Сагатовичем, не задваивайте бюджет."),
    ]
    task = Task(
        action="Связаться с Нурланом и не задваивать бюджет",
        responsible=None, source_utterance_ids=["u1"],
        evidence_quote=turns[1].text,
    )
    validate_evidence(Abstraction(tasks=[task]), turns)
    assert task.responsible == "Тимур Болатович"
    assert task.source_utterance_ids == ["u1", "r00001"]
    assert task.needs_review


def test_immediate_address_overrides_named_object_claimed_as_owner():
    turns = [
        Utterance(id="r00001", start_ms=0, end_ms=400, speaker_id=None,
                  text="Тимур Болатович"),
        Utterance(id="u1", start_ms=400, end_ms=1600, speaker_id="chair",
                  text="Свяжитесь с Нурланом Сагатовичем, не задваивайте бюджет."),
    ]
    task = Task(
        action="Связаться с Нурланом Сагатовичем по бюджету",
        responsible="Нурлан Сагатович", source_utterance_ids=["u1"],
        evidence_quote=turns[1].text,
    )
    validate_evidence(Abstraction(tasks=[task]), turns)
    assert task.responsible == "Тимур Болатович"
    assert task.source_utterance_ids == ["u1", "r00001"]
    assert task.needs_review


def test_acknowledgment_of_prior_contact_does_not_duplicate_task():
    turns = [
        Utterance(
            id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
            text=("Тимур Балатович, свяжитесь с Нурланом Сагатовичем "
                  "на этой неделе, не задваивайте бюджет."),
        ),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="worker",
                  text="Понял, на этой неделе созвонимся."),
    ]
    directive = Task(
        action="Связаться с Нурланом Сагатовичем, не задваивать бюджет",
        responsible=None, source_utterance_ids=["u1"],
        evidence_quote=turns[0].text,
    )
    acknowledgment = Task(
        action="Созвониться с Нурланом Сагатовичем", responsible=None,
        source_utterance_ids=["u2"], evidence_quote=turns[1].text,
    )
    abstraction = Abstraction(tasks=[directive, acknowledgment])
    validate_evidence(abstraction, turns)
    assert len(abstraction.tasks) == 1
    assert abstraction.tasks[0].responsible == "Тимур Балатович"


def test_distant_address_is_used_for_same_audit_topic_not_contact_object():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
                  text="Нурлан Сагатович, а по остальным площадкам ситуация такая же?"),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="chair",
                  text="Нужно проверить одиннадцать площадок."),
        Utterance(id="u3", start_ms=2000, end_ms=3000, speaker_id="chair",
                  text="Так проверьте."),
        Utterance(id="u4", start_ms=3000, end_ms=4000, speaker_id="chair",
                  text="Мне нужен полный аудит, две недели достаточно?"),
        Utterance(id="u5", start_ms=4000, end_ms=5000, speaker_id="worker",
                  text="Две недели маловато."),
        Utterance(id="u6", start_ms=5000, end_ms=6000, speaker_id="chair",
                  text="Жду сводный отчет по каждой площадке."),
    ]
    audit = Task(
        action="Провести полный аудит всех площадок", responsible=None,
        source_utterance_ids=["u6"], evidence_quote=turns[-1].text,
    )
    contact = Task(
        action="Связаться с Нурланом Сагатовичем по бюджету", responsible=None,
        source_utterance_ids=["u6"], evidence_quote=turns[-1].text,
    )
    validate_evidence(Abstraction(tasks=[audit, contact]), turns)
    assert audit.responsible == "Нурлан Сагатович"
    assert "u1" in audit.source_utterance_ids
    assert contact.responsible is None


def test_estimate_week_does_not_replace_month_for_training_queue():
    turns = [
        Utterance(
            id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
            text=("Организуйте дополнительные группы, привлеките тренера "
                  "чтобы закрыть очередь за месяц."),
        ),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="worker",
                  text="Понял найду тренера за неделю дам смету подоп"),
        Utterance(id="u3", start_ms=2100, end_ms=2500, speaker_id="worker",
                  text="группам"),
    ]
    training = Task(
        action="Организовать группы и найти тренера для закрытия очереди",
        responsible=None, due_text="за месяц", source_utterance_ids=["u1"],
        evidence_quote=turns[0].text,
    )
    estimate = Task(
        action="Подготовить смету на привлечение тренера", responsible=None,
        due_text="за месяц", source_utterance_ids=["u1", "u2"],
        evidence_quote="дам смету",
    )
    validate_evidence(Abstraction(tasks=[training, estimate]), turns)
    assert training.due_text == "за месяц"
    assert estimate.due_text == "за неделю"


def test_later_report_for_other_subject_does_not_replace_prior_report_deadline():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
                  text=("Представить сводный отчет. Ответственная Гульмира "
                        "Сериковна, к двадцатому октября.")),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="chair",
                  text="Нурлан Сагатович, по остальным площадкам нужен аудит."),
        Utterance(id="u3", start_ms=2000, end_ms=3000, speaker_id="chair",
                  text=("К пятнадцатому октября жду сводный отчет "
                        "по каждой площадке.")),
    ]
    task = Task(
        action="Представить сводный отчет",
        responsible="Гульмира Сериковна", due_text="к двадцатому октября",
        source_utterance_ids=["u1"], evidence_quote=turns[0].text,
    )
    validate_evidence(Abstraction(tasks=[task]), turns)
    assert task.due_text == "к двадцатому октября"
    assert "u3" not in task.source_utterance_ids


def test_deadline_from_other_subject_is_not_transferred():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="S1",
                  text="Подготовьте уведомление подрядчикам."),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="S1",
                  text="Не больше недели на новый шаблон договора."),
    ]
    task = Task(
        action="Подготовить уведомление подрядчикам", responsible=None,
        due_text="не больше недели", source_utterance_ids=["u1", "u2"],
        evidence_quote=turns[0].text,
    )
    validate_evidence(Abstraction(tasks=[task]), turns)
    assert task.due_text is None
    assert task.needs_review


def test_later_subject_linked_deadline_replaces_earlier_one():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="S1",
                  text="Найдите альтернативного поставщика за две недели."),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="S1",
                  text="Неделя максимум десять дней на поиск альтернативы."),
    ]
    task = Task(
        action="Найти альтернативного поставщика", responsible=None,
        due_text="за две недели", source_utterance_ids=["u1", "u2"],
        evidence_quote=turns[0].text,
    )
    warnings: list[str] = []
    validate_evidence(
        Abstraction(tasks=[task]), turns, validation_warnings=warnings
    )
    assert task.due_text == "Неделя максимум десять дней"
    assert task.needs_review
    assert any("за две недели" in warning and "Неделя максимум десять дней" in warning
               for warning in warnings)


def test_explicit_later_cancellation_removes_only_matching_task():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="S1",
                  text="Проверить договор до пятницы."),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="S1",
                  text="Проверку договора отменяем."),
        Utterance(id="u3", start_ms=2000, end_ms=3000, speaker_id="S1",
                  text="Аудит датчиков не отменяем."),
    ]
    cancelled = Task(
        action="Проверить договор", due_text="до пятницы",
        source_utterance_ids=["u1"], evidence_quote=turns[0].text,
    )
    unrelated = Task(
        action="Аудит датчиков", source_utterance_ids=["u3"],
        evidence_quote=turns[2].text,
    )
    abstraction = Abstraction(tasks=[cancelled, unrelated])
    validate_evidence(abstraction, turns)
    assert abstraction.tasks == [unrelated]


def test_cancellation_of_other_contract_keeps_equipment_contract_task():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
                  text="Подготовить договор поставки оборудования."),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="chair",
                  text="Договор аренды офиса отменяем."),
    ]
    task = Task(
        action="Подготовить договор поставки оборудования",
        source_utterance_ids=["u1"], evidence_quote=turns[0].text,
    )
    abstraction = Abstraction(tasks=[task])
    validate_evidence(abstraction, turns)
    assert abstraction.tasks == [task]


def test_topic_change_stops_owner_inheritance():
    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
                  text="Айнур Каировна, подготовьте отчёт."),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="chair",
                  text="Теперь обсудим обслуживание станков."),
        Utterance(id="u3", start_ms=2000, end_ms=3000, speaker_id="chair",
                  text="Проверьте станок номер три."),
    ]
    task = Task(
        action="Проверить станок номер три", responsible=None,
        source_utterance_ids=["u3"], evidence_quote=turns[2].text,
    )
    validate_evidence(Abstraction(tasks=[task]), turns)
    assert task.responsible is None
    assert "u1" not in task.source_utterance_ids


def test_invalid_reconciliation_does_not_restore_cancelled_task():
    import json

    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id=None,
                  text="Проверьте договор."),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id=None,
                  text="Проверку договора отменяем."),
    ]
    task = {
        "action": "Проверить договор", "responsible": None,
        "due_date": None, "due_text": None,
        "source_utterance_ids": ["u1"], "evidence_quote": turns[0].text,
        "needs_review": False,
    }

    class InvalidMergeGenerator:
        def generate(self, prompt):
            facts = []
            tasks = []
            if "Реплики-основания:" in prompt or "Ошибка проверки:" in prompt:
                facts = [{
                    "text": "Несуществующий факт", "source_utterance_ids": ["u1"],
                    "evidence_quote": "Несуществующий факт", "needs_review": False,
                }]
                tasks = [task]
            elif "u1 [" in prompt:
                tasks = [task]
            return json.dumps({"key_facts": facts, "decisions": [], "tasks": tasks},
                              ensure_ascii=False)

    result = extract_abstraction(
        turns, InvalidMergeGenerator(), None, [], max_chars=50,
    )
    assert result.tasks == []
    assert "Проверьте договор" not in render_summary(result)


def test_final_pass_grounds_owner_when_task_first_appears_in_last_chunk():
    import json

    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id="chair",
                  text="Ерболат Мухтарович, по вашему направлению."),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id="worker",
                  text="Есть проблема с переаттестацией персонала и учебной очередью."),
        Utterance(id="u3", start_ms=2000, end_ms=3000, speaker_id="worker",
                  text="Понял, за неделю дам смету по дополнительным группам."),
    ]
    task = {
        "action": "Дать смету по дополнительным группам",
        "responsible": None, "due_date": None, "due_text": "за неделю",
        "source_utterance_ids": ["u3"],
        "evidence_quote": "дам смету по дополнительным группам",
        "needs_review": True,
    }

    class LastChunkGenerator:
        def generate(self, prompt):
            tasks = [task] if "u3 [" in prompt else []
            return json.dumps({"key_facts": [], "decisions": [], "tasks": tasks},
                              ensure_ascii=False)

    result = extract_abstraction(
        turns, LastChunkGenerator(), None, [], max_chars=120,
    )
    assert len(result.tasks) == 1
    assert result.tasks[0].responsible == "Ерболат Мухтарович"
    assert result.tasks[0].source_utterance_ids == ["u3", "u1"]


def test_invalid_merged_item_does_not_discard_other_new_task():
    import json

    turns = [
        Utterance(id="u1", start_ms=0, end_ms=1000, speaker_id=None,
                  text="Ерлан подготовит отчёт."),
        Utterance(id="u2", start_ms=1000, end_ms=2000, speaker_id=None,
                  text="Айнур проверит договор."),
    ]

    def task(action, owner, turn):
        return {
            "action": action, "responsible": owner, "due_date": None,
            "due_text": None, "source_utterance_ids": [turn.id],
            "evidence_quote": turn.text, "needs_review": False,
        }

    first = task("Подготовить отчёт", "Ерлан", turns[0])
    second = task("Проверить договор", "Айнур", turns[1])

    class MixedGenerator:
        def generate(self, prompt):
            if "Реплики-основания:" in prompt or "Ошибка проверки:" in prompt:
                facts = [{
                    "text": "Нет такого факта", "source_utterance_ids": ["u1"],
                    "evidence_quote": "Нет такого факта", "needs_review": False,
                }]
                response = {"key_facts": facts, "decisions": [],
                            "tasks": [first, second]}
            else:
                response = {"key_facts": [], "decisions": [],
                            "tasks": [first if "u1 [" in prompt else second]}
            return json.dumps(response, ensure_ascii=False)

    warnings: list[str] = []
    result = extract_abstraction(
        turns, MixedGenerator(), None, [], max_chars=50,
        validation_warnings=warnings,
    )
    assert {task.responsible for task in result.tasks} == {"Ерлан", "Айнур"}
    assert any("Dropped key_facts" in warning for warning in warnings)
