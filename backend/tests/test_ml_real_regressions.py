"""Small audio-derived cases from the two archived meeting recordings.

These snippets come from the archived ASR transcript, not the supplied protocols.
They exercise deterministic grounding; no speech or language model is loaded.
"""

import json

from ml_pipeline.abstraction import (
    extract_abstraction,
    render_summary,
    validate_evidence,
)
from ml_pipeline.models import Abstraction, Task, Utterance


def _utterance(
    uid: str,
    start_ms: int,
    end_ms: int,
    text: str,
    speaker_id: str | None = None,
) -> Utterance:
    return Utterance(
        id=uid,
        start_ms=start_ms,
        end_ms=end_ms,
        speaker_id=speaker_id,
        text=text,
    )


def test_meeting_one_atyrau_finance_is_not_replaced_by_pavlodar_safety():
    # m1 ~01:40: finance concerns Atyrau. Pavlodar first appears in the later
    # safety discussion (~02:21). The written protocol mixes these subjects.
    finance = _utterance(
        "u00022",
        100792,
        110343,
        "третья подготовить финансовое решение по проекту модернизации завода "
        "в атырауской области ответственный тимур балатович "
        "срок до тридцатого сентября",
    )
    safety = _utterance(
        "u00027",
        141322,
        146614,
        "нурлан сагатович у нас же на прошлой неделе было происшествие "
        "на павлодарском заводе",
    )
    task = Task(
        action="Подготовить финансовое решение по проекту модернизации "
        "завода в Павлодарской области",
        responsible="Тимур Балатович",
        due_text="до тридцатого сентября",
        source_utterance_ids=[finance.id],
        evidence_quote=finance.text,
    )
    abstraction = Abstraction(tasks=[task])
    validate_evidence(abstraction, [finance, safety])

    summary = render_summary(abstraction)
    assert "атырауской области" in summary.casefold()
    assert "павлодар" not in summary.casefold()
    assert task.needs_review


def test_meeting_one_safety_facts_do_not_claim_unspoken_causation():
    # m1 ~02:29 mentions a leak and overdue detector inspection together.
    # Neither the archived ASR nor the independent audit states one caused the other.
    incident = _utterance(
        "u00029",
        149105,
        154198,
        "да было разгерметизация на линии датчики утечки газа "
        "не проходили поверку с прошлого года",
    )
    from ml_pipeline.models import EvidenceItem

    fact = EvidenceItem(
        text="Разгерметизация произошла из-за просроченной поверки датчиков",
        source_utterance_ids=[incident.id],
        evidence_quote=incident.text,
    )
    abstraction = Abstraction(key_facts=[fact])
    validate_evidence(abstraction, [incident])

    summary = render_summary(abstraction)
    assert "разгерметизация" in summary
    assert "не проходили поверку" in summary
    assert "из-за" not in summary
    assert fact.needs_review


def test_meeting_two_split_estimate_quote_is_retained_with_review():
    # m2 ~02:25: ASR splits "за неделю дам смету по доп. группам" between turns.
    estimate = _utterance("u00036", 145584, 147535, "за неделю дам смету подоп")
    ending = _utterance("u00037", 147755, 148447, "группам")
    task = Task(
        action="Подготовить смету по дополнительным группам",
        responsible=None,
        due_text="за неделю",
        source_utterance_ids=[estimate.id, ending.id],
        evidence_quote="за неделю дам смету подоп группам",
    )

    validate_evidence(Abstraction(tasks=[task]), [estimate, ending])

    assert task.evidence_quote in (estimate.text, ending.text)
    assert "u00036" in task.source_utterance_ids
    assert task.needs_review


def test_meeting_one_adjacent_address_can_ground_legal_owner():
    # m1 ~04:13: a direct address precedes the legal follow-up.
    address = _utterance(
        "u00055",
        252970,
        255873,
        "и последняя по этой теме айнур каировна",
        "SPEAKER_02",
    )
    request = _utterance(
        "u00056",
        256058,
        262673,
        "может быть там и материальная ответственность предусмотрена "
        "запросите данную информацию не надо откладывать",
        "SPEAKER_02",
    )
    acceptance = _utterance(
        "u00057",
        263045,
        266302,
        "хорошо запрошу у юристов заключение к среде будет ответ",
        "SPEAKER_01",
    )
    task = Task(
        action="Запросить у юристов заключение о материальной ответственности",
        responsible="Айнур Каировна",
        due_text="к среде",
        source_utterance_ids=[request.id, acceptance.id],
        evidence_quote=acceptance.text,
    )

    validate_evidence(Abstraction(tasks=[task]), [address, request, acceptance])

    assert task.responsible == "Айнур Каировна"
    assert address.id in task.source_utterance_ids
    assert task.due_text == "к среде"
    assert task.needs_review


def test_meeting_one_spelled_two_word_day_remains_a_deadline():
    # m1 preliminary u18 says "до двадцать шестого сентября". GigaAM uses
    # an ungrammatical two-word ordinal, but the phrase is still a due text.
    catalyst = _utterance(
        "u00018",
        89671,
        100150,
        "второе провести совещание с проектным институтом и зафиксировать "
        "график поставки катализаторов ответственный айнур каировна "
        "срок до двадцать шестого сентября",
    )
    task = Task(
        action="Провести совещание с проектным институтом",
        responsible="Айнур Каировна",
        due_text="до двадцать шестого сентября",
        source_utterance_ids=[catalyst.id],
        evidence_quote=catalyst.text,
    )

    validate_evidence(Abstraction(tasks=[task]), [catalyst])

    assert task.due_text == "до двадцать шестого сентября"
    assert task.responsible == "Айнур Каировна"


def test_meeting_one_later_audit_report_does_not_change_earlier_group_report():
    # m1 u21 is a report on the chemical assets for Гульмира, due 20 Oct.
    # u34 is a later audit report on production sites for Нурлан, due 15 Oct.
    # Shared generic words "сводный отчет" do not make one a revision of the other.
    group_report = _utterance(
        "u00021",
        119607,
        127446,
        "пятае представить сводный отчет на следующем совещании "
        "ответственный гульмира сериковна срок к двадцатому октября",
    )
    audit_address = _utterance(
        "u00029",
        179716,
        185318,
        "нурлан сагатович а по остальным площадкам ситуация такая же",
    )
    audit_request = _utterance(
        "u00032",
        190685,
        194363,
        "мне нужен полный аудит две недели вам достаточно",
    )
    audit_report = _utterance(
        "u00034",
        197738,
        206058,
        "хорошо три недели но не больше к пятнадцатому октября "
        "жду сводный отчет по каждой площадке отдельно принято",
    )
    earlier = Task(
        action="Представить сводный отчет",
        responsible="Гульмира Сериковна",
        due_text="к двадцатому октября",
        source_utterance_ids=[group_report.id],
        evidence_quote=group_report.text,
    )
    later = Task(
        action="Провести аудит всех площадок и представить сводный отчет по каждой",
        responsible="Нурлан Сагатович",
        due_text="к пятнадцатому октября",
        source_utterance_ids=[audit_request.id, audit_report.id, audit_address.id],
        evidence_quote=audit_report.text,
    )
    abstraction = Abstraction(tasks=[earlier, later])

    validate_evidence(
        abstraction, [group_report, audit_address, audit_request, audit_report]
    )

    assert earlier.due_text == "к двадцатому октября"
    assert audit_report.id not in earlier.source_utterance_ids
    assert later.due_text == "к пятнадцатому октября"


def test_meeting_two_next_topic_address_is_not_owner_of_previous_brief():
    # Independent Whisper audit splits the short "Сделаю" from the subsequent
    # address to Ерболат. Raw diarization did not split that short speaker turn.
    request = _utterance(
        "u00026a", 93080, 95500, "и мне по итогам этого совещания короткую справку"
    )
    acceptance = _utterance("u00026b", 95500, 96500, "сделаю")
    next_topic = _utterance(
        "u00026c", 96500, 98412, "ерболат мухтарович по вашему направлению"
    )
    task = Task(
        action="Подготовить короткую справку по итогам совещания",
        responsible="Ерболат Мухтарович",
        source_utterance_ids=[request.id, acceptance.id, next_topic.id],
        evidence_quote=request.text,
    )

    validate_evidence(Abstraction(tasks=[task]), [request, acceptance, next_topic])

    assert task.responsible is None
    assert task.needs_review


def test_meeting_two_fused_asr_turn_does_not_assign_next_name_to_brief():
    # The actual GigaAM clip fused three speaker acts into one diarization turn.
    fused = _utterance(
        "u00026",
        93080,
        98412,
        "и мне по итогам этого совещания короткую справку что р сделаю "
        "ерболат мухтарович по вашему направлению",
        "SPEAKER_04",
    )
    task = Task(
        action="Подготовить короткую справку по итогам совещания",
        responsible="Ерболат Мухтарович",
        source_utterance_ids=[fused.id],
        evidence_quote=fused.text,
    )

    validate_evidence(Abstraction(tasks=[task]), [fused])

    assert task.responsible is None
    assert task.needs_review


def test_meeting_one_adjacent_addresses_ground_gulmira_and_nurlan():
    # Both names are explicit nearby addressees of the chair, unlike a bare
    # diarization speaker ID. The task quotes themselves omit the addressee.
    gulmira_address = _utterance(
        "u00032",
        160938,
        167330,
        "так это недопустимо коллеги гульмира сериковна вы же курируете "
        "подрядчиков по этому направлению",
    )
    contractor = _utterance(
        "u00034",
        169979,
        177556,
        "значит так до пятницы разберитесь с этим подрядчиком если "
        "систематически нарушают расторгаем договор ищем замену",
    )
    nurlan_address = _utterance(
        "u00036",
        179716,
        185318,
        "нурлан сагатович а по остальным площадкам ситуация такая же "
        "или это разовый случай",
    )
    audit = _utterance(
        "u00039", 190685, 194363, "мне нужен полный аудит две недели вам достаточно"
    )
    report = _utterance(
        "u00042",
        200874,
        206058,
        "к пятнадцатому октября жду сводный отчет по каждой площадке отдельно принято",
    )
    gulmira_task = Task(
        action="Разобраться с подрядчиком по поверке датчиков",
        responsible="Гульмира Сериковна",
        due_text="до пятницы",
        source_utterance_ids=[contractor.id],
        evidence_quote=contractor.text,
    )
    nurlan_task = Task(
        action="Провести полный аудит площадок и представить сводный отчет",
        responsible="Нурлан Сагатович",
        due_text="к пятнадцатому октября",
        source_utterance_ids=[audit.id, report.id],
        evidence_quote=audit.text,
    )

    validate_evidence(
        Abstraction(tasks=[gulmira_task, nurlan_task]),
        [gulmira_address, contractor, nurlan_address, audit, report],
    )

    assert gulmira_task.responsible == "Гульмира Сериковна"
    assert gulmira_address.id in gulmira_task.source_utterance_ids
    assert nurlan_task.responsible == "Нурлан Сагатович"
    assert nurlan_address.id in nurlan_task.source_utterance_ids


def test_meeting_one_budget_owner_requires_audible_timur_address():
    # Independent Whisper audit of the original MP3 at 206-222 s preserves the
    # direct "Тимур Болатович" address that GigaAM u00044 omitted.
    budget = _utterance(
        "u00044",
        214799,
        219743,
        "тимур болатович свяжитесь с нурланом сагатовичем на этой неделе "
        "не задваивайте бюджет",
    )
    task = Task(
        action="Согласовать бюджет безопасности с инвестиционным планом",
        responsible="Тимур Болатович",
        due_text="на этой неделе",
        source_utterance_ids=[budget.id],
        evidence_quote=budget.text,
    )

    validate_evidence(Abstraction(tasks=[task]), [budget])

    assert task.responsible == "Тимур Болатович"
    assert task.needs_review


def test_meeting_two_one_week_deadline_belongs_only_to_template():
    # m2 ~03:21: "не больше недели" modifies "новый шаблон договора".
    # It is not a deadline for the notifications or the contract clause itself.
    clause = _utterance(
        "u00042",
        169760,
        177539,
        "тогда прямое решение пропишите в новых договорах жесткий срок выставления "
        "счета например пять рабочих дней после выполнения работ и штрафную "
        "санкцию за нарушение",
    )
    notices = _utterance(
        "u00043",
        178130,
        184103,
        "а по текущим договорам с этими подрядчиками направьте официальное "
        "уведомление что с определенной даты просроченные счета приниматься не будут",
    )
    acceptance = _utterance(
        "u00044",
        184441,
        187192,
        "хорошо подготовлю уведомления и обновлю шаблон договора",
    )
    final = _utterance(
        "u00049",
        201248,
        204134,
        "салтанат ерболовна не больше недели на новый шаблон договора",
    )
    tasks = [
        Task(
            action="Прописать срок выставления счета в договорах",
            responsible="Салтанат Ерболовна",
            due_text="не больше недели",
            source_utterance_ids=[clause.id, final.id],
            evidence_quote=clause.text,
        ),
        Task(
            action="Направить уведомления действующим подрядчикам",
            responsible="Салтанат Ерболовна",
            due_text="не больше недели",
            source_utterance_ids=[notices.id, final.id],
            evidence_quote=notices.text,
        ),
        Task(
            action="Обновить шаблон договора",
            responsible="Салтанат Ерболовна",
            due_text="не больше недели",
            source_utterance_ids=[acceptance.id, final.id],
            evidence_quote=acceptance.text,
        ),
    ]

    validate_evidence(Abstraction(tasks=tasks), [clause, notices, acceptance, final])

    assert tasks[0].due_text is None
    assert tasks[1].due_text is None
    assert tasks[2].due_text == "не больше недели"
    assert tasks[0].needs_review and tasks[1].needs_review


def test_meeting_two_final_supplier_deadline_overrides_earlier_two_weeks():
    # m2 ~00:39 says two weeks; ~03:09 closes the meeting with
    # "неделя максимум десять дней" for the same supplier search.
    initial = _utterance(
        "u00013",
        39000,
        47000,
        "хорошо пусть ерлан до конца недели подготовит претензию "
        "а вы параллельно за две недели найдите альтернативного поставщика "
        "хотя бы для расчета",
    )
    final = _utterance(
        "u00046",
        188913,
        194802,
        "подытожим батагоз нурлановна по вашим вопросам неделя максимум "
        "десять дней на поиск альтернативы как говорил ранее",
    )

    def response(source: Utterance, due_text: str, ids: list[str]) -> str:
        return json.dumps(
            {
                "key_facts": [],
                "decisions": [],
                "tasks": [
                    {
                        "action": "Найти альтернативного поставщика сырья",
                        "responsible": None,
                        "due_date": None,
                        "due_text": due_text,
                        "source_utterance_ids": ids,
                        "evidence_quote": source.text,
                        "needs_review": True,
                    }
                ],
            },
            ensure_ascii=False,
        )

    class ScriptedGenerator:
        def generate(self, prompt: str) -> str:
            if "Сверь накопленное состояние" in prompt:
                # Simulate a model that kept the stale value despite seeing u46.
                return response(initial, "за две недели", [initial.id, final.id])
            if final.id in prompt:
                return response(final, "неделя максимум десять дней", [final.id])
            return response(initial, "за две недели", [initial.id])

    result = extract_abstraction(
        [initial, final], ScriptedGenerator(), None, [], max_chars=175
    )

    assert len(result.tasks) == 1
    task = result.tasks[0]
    assert "десять дней" in (task.due_text or "")
    assert task.due_text != "за две недели"
    assert final.id in task.source_utterance_ids
    assert task.responsible == "Батагоз Нурлановна"
    assert task.needs_review


def test_meeting_two_split_estimate_keeps_week_deadline_and_addressed_owner():
    # m2 01:33-02:34: the chair addresses Ерболат before the training topic;
    # the reply and estimate are by the same addressed speaker. GigaAM splits
    # the final word across u36/u37. The estimate has a different deadline
    # from the month allowed to close the training queue in u34.
    turns = [
        _utterance(
            "u00026",
            93080,
            98412,
            "ерболат мухтарович по вашему направлению",
            "SPEAKER_04",
        ),
        _utterance(
            "u00027",
            98716,
            102665,
            "по травматизму и промбезопасности показатель в норме",
            "SPEAKER_02",
        ),
        _utterance(
            "u00028",
            102783,
            105432,
            "серьезных инцидентов за месяц не было",
            "SPEAKER_02",
        ),
        _utterance(
            "u00029", 106006, 108115, "но есть проблема по обучению", "SPEAKER_02"
        ),
        _utterance(
            "u00030",
            108436,
            121227,
            "двенадцать процентов персонала с просроченными сертификатами",
            "SPEAKER_02",
        ),
        _utterance(
            "u00031", 121565, 123235, "двенадцать процентов это много", "SPEAKER_04"
        ),
        _utterance(
            "u00032",
            123320,
            127454,
            "люди без сертификата работают незаконно",
            "SPEAKER_04",
        ),
        _utterance(
            "u00033",
            127775,
            134086,
            "проблема в пропускной способности учебного центра",
            "SPEAKER_02",
        ),
        _utterance(
            "u00034",
            134356,
            143502,
            "организуйте дополнительные группы если нужно привлеките "
            "внешнего тренера чтобы закрыть очередь за месяц",
            "SPEAKER_04",
        ),
        _utterance("u00035", 143789, 145584, "понял найду тренера", "SPEAKER_02"),
        _utterance("u00036", 145584, 147535, "за неделю дам смету подоп", "SPEAKER_02"),
        _utterance("u00037", 147755, 148447, "группам", "SPEAKER_02"),
        _utterance(
            "u00038",
            148700,
            154522,
            "хорошо жду смету согласуем бюджет быстро",
            "SPEAKER_04",
        ),
    ]
    estimate = Task(
        action="Подготовить смету по дополнительным группам",
        responsible=None,
        due_text="за месяц",  # model borrowed the queue deadline from u34
        source_utterance_ids=["u00034", "u00036", "u00037"],
        evidence_quote="за неделю дам смету подоп группам",
    )
    abstraction = Abstraction(tasks=[estimate])

    validate_evidence(abstraction, turns)

    assert abstraction.tasks == [estimate]
    assert "смету" in estimate.action.casefold()
    assert "групп" in estimate.action.casefold()
    assert estimate.due_text == "за неделю"
    assert estimate.responsible == "Ерболат Мухтарович"
    assert "u00026" in estimate.source_utterance_ids
    assert {"u00036", "u00037"} <= set(estimate.source_utterance_ids)
    assert any(
        estimate.evidence_quote in turn.text
        for turn in turns
        if turn.id in estimate.source_utterance_ids
    )
    assert estimate.needs_review


def test_meeting_one_finance_and_budget_do_not_duplicate_acknowledgement():
    # Preliminary rerun: m1 u19 names Timur for Atyrau finance. The original
    # u36 ASR clip lost the address at its left boundary; the widened crop of
    # the same audio recovers it. u37 only acknowledges that instruction.
    finance = _utterance(
        "u00019",
        100792,
        110343,
        "третья подготовить финансовое решение по проекту модернизации "
        "завода в атырауской области ответственный тимур балатович "
        "срок до тридцатого сентября",
        "SPEAKER_02",
    )
    budget = _utterance(
        "u00036",
        214799,
        219743,
        "тимур балатович свяжитесь с нурланом сагатовичем на этой неделе "
        "не задваивайте бюджет",
        "SPEAKER_02",
    )
    ack = _utterance(
        "u00037",
        220165,
        221836,
        "понял на этой неделе созвонимся",
        "SPEAKER_01",
    )
    tasks = [
        Task(
            action=(
                "Подготовить финансовое решение по модернизации завода "
                "в Атырауской области"
            ),
            responsible=None,
            due_text="до тридцатого сентября",
            source_utterance_ids=[finance.id],
            evidence_quote=finance.text,
        ),
        Task(
            action="Связаться с Нурланом и согласовать бюджет без задвоения",
            responsible="Тимур Балатович",
            due_text="на этой неделе",
            source_utterance_ids=[budget.id],
            evidence_quote=budget.text,
        ),
        Task(
            action="Созвониться с Нурланом по бюджету",
            responsible="Тимур Балатович",
            due_text="на этой неделе",
            source_utterance_ids=[ack.id],
            evidence_quote=ack.text,
        ),
    ]
    abstraction = Abstraction(tasks=tasks)

    validate_evidence(abstraction, [finance, budget, ack])

    assert len(abstraction.tasks) == 2
    assert abstraction.tasks == tasks[:2]
    assert {task.responsible for task in abstraction.tasks} == {"Тимур Балатович"}
    assert {task.due_text for task in abstraction.tasks} == {
        "до тридцатого сентября",
        "на этой неделе",
    }
    assert all(
        any(
            task.evidence_quote in turn.text
            for turn in (finance, budget, ack)
            if turn.id in task.source_utterance_ids
        )
        for task in abstraction.tasks
    )


def test_meeting_one_clipped_budget_address_requires_review():
    # The preliminary u36 omits the audible name at its left clip boundary.
    # An ASR or diarization repair must provide that text before the owner is
    # asserted in a machine-readable task.
    clipped = _utterance(
        "u00036",
        214799,
        219743,
        "свяжитесьс нурланом сагатовичем на этой неделе не задваивайте бюджет",
        "SPEAKER_02",
    )
    task = Task(
        action="Связаться с Нурланом и избежать задвоения бюджета",
        responsible="Тимур Балатович",
        due_text="на этой неделе",
        source_utterance_ids=[clipped.id],
        evidence_quote=clipped.text,
    )

    validate_evidence(Abstraction(tasks=[task]), [clipped])

    assert task.responsible is None
    assert task.needs_review


def test_meeting_two_preliminary_estimate_candidate_uses_continuation():
    # Exact candidate shape from the preliminary rerun: u33 joins an ACK and
    # a new first-person promise; u34 contains its final word. The model cited
    # only "дам смету", called it a trainer estimate and set that as a deadline.
    turns = [
        _utterance(
            "u00024",
            93080,
            98412,
            "и мне по итогам этого совещания короткую справку что р "
            "сделаю ерболат мухтарович по вашему направлению",
            "SPEAKER_04",
        ),
        _utterance(
            "u00025",
            98716,
            102665,
            "по травматизму и промбезопасности показатель в норме",
            "SPEAKER_02",
        ),
        _utterance(
            "u00026",
            102783,
            105432,
            "серьезных инцидентов за месяц не было",
            "SPEAKER_02",
        ),
        _utterance(
            "u00027", 106006, 108115, "но есть проблема по обучению", "SPEAKER_02"
        ),
        _utterance(
            "u00028",
            108436,
            121227,
            "двенадцать процентов персонала с просроченными сертификатами",
            "SPEAKER_02",
        ),
        _utterance(
            "u00029", 121565, 123235, "двенадцать процентов это много", "SPEAKER_04"
        ),
        _utterance(
            "u00030",
            123320,
            127454,
            "люди без сертификата работают незаконно",
            "SPEAKER_04",
        ),
        _utterance(
            "u00031",
            127775,
            134086,
            "проблема в пропускной способности учебного центра",
            "SPEAKER_02",
        ),
        _utterance(
            "u00032",
            134356,
            143502,
            "организуйте дополнительные группы если нужно привлеките "
            "внешнего тренера чтобы закрыть очередь за месяц",
            "SPEAKER_04",
        ),
        _utterance(
            "u00033",
            143789,
            147535,
            "понял найду тренера за неделю дам смету подоп",
            "SPEAKER_02",
        ),
        _utterance("u00034", 147755, 148447, "группам", "SPEAKER_02"),
        _utterance(
            "u00035",
            148700,
            154522,
            "хорошо жду смету согласуем бюджет быстро",
            "SPEAKER_04",
        ),
    ]
    estimate = Task(
        action="Подготовить смету на привлечение тренера.",
        responsible=None,
        due_text="дам смету",
        source_utterance_ids=["u00033"],
        evidence_quote="дам смету",
        needs_review=True,
    )
    abstraction = Abstraction(tasks=[estimate])

    validate_evidence(abstraction, turns)

    assert estimate in abstraction.tasks
    other = [task for task in abstraction.tasks if task is not estimate]
    assert len(other) == 1
    assert "тренер" in other[0].action.casefold()
    assert other[0].due_text is None
    assert any(
        other[0].evidence_quote in turn.text
        for turn in turns if turn.id in other[0].source_utterance_ids
    )
    assert "смет" in estimate.action.casefold()
    assert "дополнительн" in estimate.action.casefold()
    assert "групп" in estimate.action.casefold()
    assert "тренер" not in estimate.action.casefold()
    assert "подоп" not in estimate.action.casefold()
    assert estimate.due_text == "за неделю"
    assert estimate.responsible == "Ерболат Мухтарович"
    assert {"u00024", "u00032", "u00033", "u00034"} <= set(
        estimate.source_utterance_ids
    )
    assert any(
        estimate.evidence_quote in turn.text
        for turn in turns
        if turn.id in estimate.source_utterance_ids
    )
    assert estimate.needs_review


def test_meeting_two_training_and_estimate_do_not_share_week_deadline():
    # Preliminary tasks #5/#6 both inherited the week mentioned in u33.
    # In the recording the chair allows a month to close the training queue;
    # the reply promises the estimate in a week.
    request = _utterance(
        "u00032",
        134356,
        143502,
        "организуйте дополнительные группы если нужно привлеките внешнего "
        "сертифицированного тренера на подряд чтобы закрыть очередь за месяц",
        "SPEAKER_04",
    )
    reply = _utterance(
        "u00033",
        143789,
        147535,
        "понял найду тренера за неделю дам смету подоп",
        "SPEAKER_02",
    )
    continuation = _utterance(
        "u00034",
        147755,
        148447,
        "группам",
        "SPEAKER_02",
    )
    training = Task(
        action=(
            "Найти внешнего тренера или организовать дополнительные группы "
            "для переатестации"
        ),
        responsible=None,
        due_text="за неделю",
        source_utterance_ids=[reply.id],
        evidence_quote="найду тренера",
    )
    estimate = Task(
        action="Подготовить смету по дополнительным группам",
        responsible=None,
        due_text="дам смету",
        source_utterance_ids=[reply.id],
        evidence_quote="дам смету",
    )
    abstraction = Abstraction(tasks=[training, estimate])

    validate_evidence(abstraction, [request, reply, continuation])

    assert abstraction.tasks == [training, estimate]
    assert training.due_text in (None, "за месяц")
    assert estimate.due_text == "за неделю"
    assert continuation.id in estimate.source_utterance_ids


def test_meeting_two_vad_joined_reply_keeps_estimate_separate_from_trainer():
    # New VAD run keeps u28 intact. The model candidate combines "найду тренера"
    # with "за неделю дам смету по доб группам" and incorrectly makes the week
    # cover both actions. u27 already supplies the separate training task.
    turns = [
        _utterance(
            "u00021",
            93080,
            98412,
            "и мне короткую справку сделаю ерболат мухтарович по вашему направлению",
            "SPEAKER_04",
        ),
        _utterance(
            "u00022",
            98716,
            105432,
            "по травматизму и промбезопасности показатель в норме",
            "SPEAKER_02",
        ),
        _utterance(
            "u00023", 106006, 108115, "но есть проблема по обучению", "SPEAKER_02"
        ),
        _utterance(
            "u00024",
            108436,
            121227,
            "у нас двенадцать процентов персонала с просроченными сертификатами",
            "SPEAKER_02",
        ),
        _utterance(
            "u00025", 121565, 127454, "двенадцать процентов это много", "SPEAKER_04"
        ),
        _utterance(
            "u00026",
            127775,
            134086,
            "проблема в пропускной способности учебного центра",
            "SPEAKER_02",
        ),
        _utterance(
            "u00027",
            134356,
            143502,
            "организуйте дополнительные группы если нужно привлеките "
            "внешнего тренера чтобы закрыть очередь за месяц",
            "SPEAKER_04",
        ),
        _utterance(
            "u00028",
            143789,
            148700,
            "понял найду тренера за неделю дам смету по доб группам",
            "SPEAKER_02",
        ),
    ]
    training = Task(
        action="Организовать дополнительные группы или привлечь внешнего тренера",
        responsible=None,
        due_text="за месяц",
        source_utterance_ids=["u00027"],
        evidence_quote=turns[-2].text,
    )
    estimate = Task(
        action="Найти тренера и предоставить смету по дополнительным группам.",
        responsible=None,
        due_text="за неделю",
        source_utterance_ids=["u00028"],
        evidence_quote=turns[-1].text,
    )
    abstraction = Abstraction(tasks=[training, estimate])

    validate_evidence(abstraction, turns)

    assert abstraction.tasks == [training, estimate]
    assert "смет" in estimate.action.casefold()
    assert "дополнительн" in estimate.action.casefold()
    assert "групп" in estimate.action.casefold()
    assert "тренер" not in estimate.action.casefold()
    assert estimate.due_text == "за неделю"
    assert estimate.responsible == "Ерболат Мухтарович"
    assert {"u00021", "u00028"} <= set(estimate.source_utterance_ids)
    assert estimate.evidence_quote in turns[-1].text
    assert estimate.needs_review
