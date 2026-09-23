# Независимая проверка AI pipeline

Дата: 2026-09-23. Третий агент engineering loop. Проверены фактический dirty working tree, существующие ML-тесты, архивы результатов и отчеты `error-findings.md` и `researched-solutions.md`. Production-код не изменялся; дорогой inference, загрузки моделей и Brev этим агентом не выполнялись. Выводы о сервере принадлежат проверке основного агента.

## Что проверено исполнением

- **62 passed in 0.68s:** `tests/test_ml_compare.py`, `test_ml_pipeline.py`, `test_ml_real_regressions.py`, `test_ml_runtime.py` через `backend/.venv/Scripts/python.exe -m pytest ... -q -p no:cacheprovider`. Sandbox ACL первоначально блокировал pytest temporary directories; повтор вне sandbox с отдельной временной директорией прошел. Это ограничение тестовой среды, не ошибка pipeline.
- **9 passed in 0.40s:** `test_ml_audio_contract.py`. В проектном venv нет NumPy; использована уже установленная локальная NumPy 1.26.4 из Python312 через добавление ее site-packages в конец `sys.path`. Ничего не устанавливалось. Поэтому это не доказательство воспроизводимости чистого `uv sync` ML environment.
- Независимые adversarial probes: [verifier_probes.py](verifier_probes.py), сохраненный результат [verifier-probe-results.json](verifier-probe-results.json). Запуск из корня: `backend/.venv/Scripts/python.exe docs/audits/2026-09-23-ai-pipeline/verifier_probes.py`. Скрипт читает исходный ZIP в Downloads, не изменяет его.

Все 71 существующий тест прошли, при этом ниже воспроизведены реальные детерминированные ошибки. Число проходящих тестов нельзя переводить в accuracy pipeline.

## Проверка первого агента

| Claim | Verdict | Независимое наблюдение |
|---|---|---|
| E1: теряется год и игнорируется отрицание срока | **CONFIRMED** | При anchor 2026-09-23 «до 2 октября 2027 года» дает 2026-10-02; «не завтра, а через три дня» дает 2026-09-24. Обе даты возвращены с `uncertain=False`. |
| E2: отмена другого договора удаляет поручение | **CONFIRMED** | «Подготовьте договор поставки оборудования» + «Договор аренды офиса отменяем» оставляют ноль задач. Общий stem не является идентификатором предмета договора. |
| E3: salvage возвращает отмененное поручение | **CONFIRMED** | При неверной цитате соседнего факта после третьей попытки остается одна уже отмененная task. Валидатор очищает `single.tasks`, salvage добавляет исходный item. |
| E4: владелец переносится через смену темы | **CONFIRMED** | После обращения к Айнур про отчет, «Теперь обсудим обслуживание станков», затем проверки станка, owner становится Айнур Каировна. Реальное намерение не установлено: подтверждено необоснованное заполнение поля, не личность фактического исполнителя. `needs_review` смягчает, но не устраняет проблему. |
| E5: неверные относительные сроки не учитываются | **CONFIRMED** | Разные `due_text` при одинаковых null `due_date` дают ноль deadline errors. Это особенно существенно для двух недатированных встреч. |
| Весь ASR/diarization/LLM работает качественно, поскольку тесты прошли | **REJECTED** | Проверки используют заглушки, сценарные генераторы и готовый текст; качество реального inference ими не измерено. |

Дополнительный независимый finding: `score_tasks` оценивает «Не утверждать договор» как правильную task для gold «Утвердить договор»: ноль missed/false-positive/owner/deadline errors. Лексический matcher не различает отрицание. Обратный случай тоже возможен: перефразирование финансового отчета как сводки о денежных средствах дало missed=1 и false_positive=1. Метрика полезна как предварительная диагностика совпадений, но непригодна как единственный критерий выбора модели.

## Архив и текущая версия — разные доказательства

В исходном M2 ZIP независимо найдены: supplier task со старым «за две недели» вопреки позднему u00046 «неделя максимум десять дней»; одинаковый срок «не больше недели» у уведомлений и правил выставления счетов, хотя u00049 относит его к новому шаблону; назначение короткой справки Ерболату из слитной реплики u00026; отсутствующая смета из u00036–u00037.

Полный archived transcript + abstraction повторно пропущены через **текущий** `validate_evidence`, без ASR/LLM. Supplier deadline обновился; сроки правил/уведомлений стали null, срок шаблона сохранился; owner справки изменился на Жандоса Талгатовича. Эти изменения подтверждают работу текущих эвристик на знакомых данных, но не доказывают акустическую истинность новых имен. Отсутствующую смету validator не восстановил: он не генерирует пропущенные кандидаты.

Вердикт: **CONFIRMED** для исторических ошибок архива; **REJECTED** для утверждения, что именно те же сроки неизменно ошибочны в текущем validator; **NEEDS EVIDENCE** для улучшения свежего полного ASR+LLM запуска. Существующие regression tests на split estimate проверяют сохранение уже предложенной task; они не доказывают, что новая модель сама ее извлечет.

Все null `due_date` нельзя считать ошибками: в архиве неизвестна дата встречи. Сохранять относительный `due_text` и воздерживаться от календарной даты правильно. Сравнивать результат с Markdown-протоколом как безусловным gold нельзя: protocol и ASR расходятся, например по области модернизации. В споре между ними нужен независимый разбор оригинальной записи; второй ASR является дополнительным свидетельством, не автоматической истиной.

## Что доказывают модели данных и тесты

`models.py` запрещает лишние поля, проверяет основные типы, непустые строки и интервалы. `_parse_response` дополнительно требует все разделы/поля task, запрещает дубликаты JSON keys и model-supplied `due_date`. Это полезный структурный контракт. Название `StrictModel` не означает полной semantic validation: configuration содержит `extra=forbid`, а не Pydantic `strict=True`; связь задания с владельцем/сроком схемой не доказана. В Transcript нет schema validator уникальности ID, календарной timezone или непересечения интервалов. Runtime обычно формирует эти данные сам, поэтому это boundary limitations, не доказанный сбой текущего запуска.

`test_ml_runtime.py` подменяет FFmpeg/audio/VAD/diarization/ASR/Qwen и проверяет orchestration, время и файловый контракт. `test_ml_audio_contract.py` проверяет настоящее PCM slicing и логику объединения интервалов, но подменяет VAD и pyannote — это не измерение пропущенной речи, overlap или DER. `test_ml_compare.py` проверяет формулы/manifest и mocked candidate runs. `test_ml_real_regressions.py` явно использует archived ASR snippets; в нескольких случаях это скорректированные Whisper snippets и scripted LLM. Эти тесты полезны для предотвращения повторения конкретных ошибок, но не являются independent held-out evaluation.

Circular validation возникает, если ASR-текст считается истиной для проверки того же ASR, найденные на двух встречах ошибки превращаются в regex/tests, а затем те же встречи объявляются доказательством обобщения. Аналогично цитата из ASR доказывает принадлежность тексту, но не точность распознавания и не semantic entailment задачи. Отдельный verifier должен проверять raw evidence и новые контрпримеры, а не голосовать за отчеты двух агентов.

## Проверка второго агента и acceptance gates

| Решение | Verdict | Условия приемки |
|---|---|---|
| Исправить salvage, explicit years/negation и разрушительную привязку до смены моделей | **ACCEPT** | Пять подтвержденных probes исправлены; соседние валидные задачи сохраняются; same-subject cancel по-прежнему работает. Дата либо корректна, либо явно unresolved — неверная уверенная дата недопустима. |
| Append-only task events + stable IDs + deterministic reducer | **ACCEPT, после уточнения** | Исследователь включил мою просьбу о поэтапном внедрении после локальных исправлений. IDs назначает приложение; ambiguous target не меняет active state; нет исчезновения без confirmed cancel; reinstatement имеет явную семантику; повтор event идемпотентен. Event log сам не решает entity resolution. |
| Field-level evidence и отдельная проверка semantic support | **ACCEPT** | Action/owner/deadline/cancel имеют свои spans; сохранены контекст и исходные offsets. Сходство строки или второй LLM judge не считается независимым gold. |
| Полный token budget, уникальные fragments, stage checkpoints | **ACCEPT как engineering safeguards** | Длинная запись, длинная utterance, ранняя цитата, поздний перенос, timeout/truncation и resume с несовпадающим hash. Context overflow и аварийная потеря transcript пока не воспроизводились этим verifier на моделях; это отдельно от подтвержденных E1–E5. |
| Переход на vLLM/schema decoding, quantization или иную ASR | **REVISE до условного эксперимента** | Только после measured bottleneck и pinned adapter smoke; valid JSON не заменяет semantic correctness. В итоговом исследовательском отчете уже оформлено условно, поэтому план приемлем; утверждение улучшения остается NEEDS EVIDENCE. |
| Две встречи как regression/development, новый held-out набор для качества | **ACCEPT** | Gold размечается по audio, disagreement adjudicated; split целыми встречами/говорящими, без утечки из разработки. Нужны ru/kk/mixed, шум, overlap, имена/числа, отмены, отрицания и переносы. |
| Oracle WER плюс end-to-end transcript/extraction metrics | **ACCEPT** | Отдельно gold-transcript extraction и ASR-transcript extraction; DER policy объявлена; due_text semantic errors считаются при null date; task links проверены людьми или gold IDs. |

Проверены отдельно upstream cards: alias `qwen3-4b` в catalog действительно указывает на Instruct-2507, для которого non-thinking является единственным режимом. Поэтому отсутствие `enable_thinking=False` в этой ветке **REJECTED как баг**. [Qwen model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507). Community-1 предоставляет regular и exclusive diarization; сохранение обоих outputs для оценки является обоснованным предложением, а не доказательством плохого качества текущей модели. [Community-1 model card](https://huggingface.co/pyannote/speaker-diarization-community-1).

До model ranking нужны свежие воспроизводимые запуски с code snapshot (включая dirty files), config/prompt/schema, audio/model/lock hashes, version/runtime/hardware, stage timing и raw outputs. Необходимо объявить число встреч и задач, denominators precision/recall, ошибки критических полей и coverage review. Численный production threshold до разметки baseline нельзя выдавать за уже достигнутый результат. Две известные встречи остаются регрессионным материалом даже после исправления всех обнаруженных на них ошибок.

## Заключительный review итоговых документов

Прочитаны `audit.md`, `brev-verification.md` и `docs/superpowers/plans/2026-09-23-ai-pipeline-improvements.md`. Сообщенное основным агентом наблюдение Brev: обычная команда упала при collection, потому что web `conftest.py` импортирует отсутствующий `app`; те же пять ML modules с `--noconftest` дали **71 passed in 1.12s**. Я не запускал этот remote command независимо. Документы корректно трактуют это как passing isolated tests плюс отдельный deployment reproducibility gap, а не как полностью рабочую стандартную поставку.

Финальный review отправлен основному агенту с verdict **REVISE** ровно по двум пунктам: явно выбирать модели/prompts/config на development/validation и использовать frozen holdout только для финальной приемки зафиксированного решения; не утверждать хронологическую новизну текущего кода относительно ZIP без code provenance архивного запуска. Различие validator replay доказывает различие поведения, но само по себе не датирует исходный код. Остальные существенные контракты плана приняты. Root-файлы этим reviewer не редактировались.

**Повторная проверка после исправлений: ACCEPT.** Прочитаны исправленный абзац `audit.md:52` и Task 8 плана (`:189`, `:201–205`). Аудит теперь прямо оставляет версию кода архивного запуска неизвестной. План отделяет development/validation selection от заранее определенной финальной приемки frozen candidate на holdout и требует новой нетронутой test-партии после настройки по предыдущему holdout. Оба замечания закрыты; существенных оставшихся REVISE в этом review-round нет. ACCEPT относится к аудиту и предложенному плану, а не к еще не реализованным исправлениям или недоказанному качеству моделей.
