# Повторная независимая проверка pipeline

23 сентября 2026. Проверена текущая рабочая версия после независимых изменений пользователя/другой задачи. Это повторная оценка фактического кода, не отчет о выполнении предложенного ранее плана. Production не изменялся; модели не загружались и не запускались. Brev и новые серверные результаты проверяет основной агент.

## Вывод

Изменения существенные: прежние точные примеры E1–E4 теперь дают ожидаемый результат, E5 начинает учитывать относительный срок при наличии `due_text` в gold. Но класс ошибок дат/отмен/назначений исправлен частично: соседние контрпримеры все еще воспроизводятся. V1 — неверное совпадение противоположных действий в оценщике — остается. Новый механизм ручных вставок полезен и аудируем на обычном пути, но имеет воспроизведенные ошибки повторного запуска и сохранения manifest.

**Первый снимок: 103 passed за 8.61 s. Промежуточный: 104 passed, 2 failed за 7.93 s. Последний согласованный однократный прогон: 105 passed, 3 failed за 10.86 s.** Во время проверки другая задача продолжала менять тесты и код. Последний запуск собрал уже 108 тестов; manifest replacements реализованы, но tests ожидают еще и `utterance_id`, которого в протестированной схеме нет. Старые два failures не выдаются за текущую причину. Результаты относятся к регрессионному покрытию и wiring, а не качеству ASR/LLM на независимом аудио. Заявление «старые конкретные repro исправлены» принимается; «весь класс semantic bugs закрыт» — **REJECTED**.

## Сравнение с исходным снимком

Снимок [recheck-code-fingerprints.json](recheck-code-fingerprints.json) обновлен основным агентом до последней наблюденной версии. Из 13 ранее хешированных файлов изменились пять: `__main__.py`, `abstraction.py`, `audio.py`, `compare.py`, `runtime.py`. Добавлен `review.py`. Не изменились ASR adapters, model catalog, diarization adapter, data models, prepare, `__init__.py`, `pyproject.toml`, `uv.lock`. Это проверка исходников, не доказательство неизменности файлов весов или фактически выбранной модели каждого запуска.

Между первым и промежуточным запуском `abstraction.py` изменился с `a54202a504c456492e07a7477b382fb2f157af7c7eb77eae9f83e73c8b82dc03` на `be6177ba3722493a8e25103f32beb12dde474c757f1a828ecc260d9d207dcbea`; aggregate hash промежуточного запуска был `d36a308a7a5f429b85123ffdc9c96be38ee071f8d6373980691b25d0b95366c2`. Последний однократный запуск имел одинаковый hash **до и после pytest**: `60509a297efe0865f148993787bb2b94a9496ea8bc0b251e67d0f61593af305a`. Во время него наблюдены `abstraction.py=11562a3e2ad29dd4b2b74c95ddf6988c558922d2460b74697dc8e48e9e48177b`, `review.py=f2f3748a7af6f061bc4b64aadaebddc7f80b8096516867ffa1eaddb4f66bd367`; runtime остался `691348aa808733e4cefafce34172abf674705a147ecfbcb84d8a92a5e2ed8b27`. Tests добавлялись параллельно и не входят в package hash. Это последняя граница отчета; дальнейшие изменения не преследовались.

Основная дельта: новые эвристики принадлежности срока и адресата, разбора слитных обещаний и продолжений, более осторожная отмена, правильное сохранение прошедших salvage элементов, восстановление коротких unlabeled gaps между одинаковыми speakers, CLI `--reviewed-corrections`, вставки до extraction, code hash и копия correction manifest в provenance.

Прежний [verifier-probe-results.json](verifier-probe-results.json) сохранен без изменения; SHA-256 `e7370f877193914a57d6b7268053fbde2ddcab1c179aef0b3dbea9f77236f3ae`. Старый probe script выполнен заново, вывод записан отдельно в [recheck-verifier-probe-results.json](recheck-verifier-probe-results.json). Новые независимые контрпримеры: [recheck-extra-probes.py](recheck-extra-probes.py), [результаты](recheck-extra-probe-results.json).

## Статус прежних findings

| Finding | Точный прежний repro сейчас | Статус семейства |
|---|---|---|
| E1: explicit year / «не завтра, а через три дня» | При anchor 2026-09-23 дает 2027-10-02 и 2026-09-26 соответственно | **FIXED narrowly / PARTIAL**: другие отрицания и диапазоны все еще выбирают неверную дату без uncertainty. |
| E2: отмена аренды удаляет поставку оборудования | Остается 1 корректная задача | **FIXED narrowly / PARTIAL**: «Не снимаем поручение…» все еще удаляет задачу. |
| E3: salvage resurrects canceled task | Остается 0 задач; `extend(single.tasks)` сохраняет итог фильтрации | **FIXED** для воспроизведенной причины. Добавлена повторная проверка fallback; соответствующий существующий regression прошел. Это не доказательство полноты любых будущих state transitions. |
| E4: прежнее имя через отдельную реплику смены темы | Owner остается null | **FIXED narrowly / PARTIAL**: новый direct-address shortcut игнорирует большой временной разрыв и смену темы в самой целевой реплике. |
| E5: разные relative deadlines при обеих null dates | `deadline_errors=1`, когда gold содержит `due_text` | **FIXED для такого gold / PARTIAL evaluation**: поле optional, сравнение лексическое. «через две недели» / «через 14 дней» теперь считается ошибкой, хотя смысл одинаков. |
| V1: «Утвердить договор» / «Не утверждать договор» | В отдельном probe, с одинаковыми остальными полями, все error counters равны 0 | **STILL REPRODUCIBLE / CONFIRMED**. Greedy action matcher не изменился по существу. |

Старый combined probe смешивал negated action и разный deadline. Теперь его `deadline_errors=1` не означает исправления V1: отдельный action-only probe по-прежнему дает ложный идеальный score.

## Новые и соседние контрпримеры

### Даты и отмены

Anchor: 2026-09-23. Независимо выполнены:

- «не 2 октября, а 5 октября» → **2026-10-02, uncertain=False**;
- «не через три дня, а через пять дней» → **2026-09-26, uncertain=False**;
- «не 2026-10-02, а 5 октября» → **2026-10-02, uncertain=False**;
- «с 2 октября по 5 октября» → **2026-10-02, uncertain=False**, хотя это интервал;
- control: две ISO-даты «не 2026-10-02, а 2026-10-05» дают abstention — эта защита работает;
- «до 2 октября 2027 года» без meeting anchor дает `(None, True)`. Это неполнота поддержки абсолютной даты, а не неверная уверенная дата.

Для поручения «Подготовить договор поставки оборудования» следующая реплика «Не снимаем поручение подготовить договор поставки оборудования» оставляет **0 tasks**. `_explicit_cancellation` защищает `не отмен…`, но не `не снимаем`. Это **CONFIRMED**, серьезнее простой потери coverage: явно сохраненное поручение исчезает. Частоту на реальных встречах этот synthetic probe не устанавливает.

### Назначение из ручной вставки

Независимо повторен новый repro finder: `r00001` в 100–500 ms содержит только «Тимур Болатович», speaker=None; следующая по списку реплика находится в 600000–602000 ms и говорит «Теперь обсудим станки. Проверьте станок номер три». Task без ответственного получает **Тимур Болатович**, источники дополняются r00001. `needs_review=True`, поэтому ошибка не скрыта полностью, но поле owner заполнено без нужного подтверждения.

Причина — `_immediate_direct_address`: непосредственность по индексу принимается за непосредственность в диалоге; нет предела по времени, а смена темы в текущей реплике не блокирует shortcut. **CONFIRMED**. `speaker_id=None` у вставки сам по себе не гарантирует отсутствие дальнейшего угадывания владельца.

### Сохранение reviewed manifest

Предложения finder/researcher проверены своим отдельным harness с реальным runtime/review-кодом. Только дорогие стадии audio/VAD/diarization/ASR/Qwen подменены. Synthetic manifests и файлы создавались во временной директории:

| Сценарий | Наблюдение | Verdict |
|---|---|---|
| Входной manifest уже лежит в `output_dir/reviewed_corrections.json` | `SameFileError` после записи transcript, abstraction и summary; provenance не создан в новом каталоге | **CONFIRMED**. Повторный запуск может оставить частичный комплект. |
| Manifest меняется во время LLM-stage | Transcript использует исходную вставку; скопированный JSON содержит измененную; recorded manifest SHA и hash копии различаются | **CONFIRMED**. Следует сохранять точно прочитанные bytes, а не повторно читать mutable source в конце. |
| После corrected run тот же output используется без correction manifest | Запуск успешен, provenance не содержит correction, но старый `reviewed_corrections.json` остается | **CONFIRMED**, меньшая тяжесть. Provenance остается различимым, однако каталог содержит артефакт другого запуска. |

Эти результаты согласуются с findings других агентов, но получены независимым исполнением [дополнительного probe](recheck-extra-probes.py). Порядок исправления: snapshot входа, отдельные run directories/явная overwrite policy, атомарное завершение stage artifacts и сохранение raw transcript до LLM.

## Что проверяют тесты и что изменилось во время проверки

Первый запуск: **103 passed in 8.61s**, package с `abstraction.py=a542…`. Промежуточный запуск: **104 passed, 2 failed in 7.93s**, package hash `d36a…` неизменен до/после команды. Тогда два новых failed tests ожидали поддержку `replacements`, которой еще не было. Это историческое промежуточное наблюдение; далее `ReviewedManifest.replacements` и обработка замен появились.

По просьбе основного агента выполнен ровно один последний запуск тех же шести test modules после реализации replacements: **105 passed, 3 failed in 10.86s**, aggregate `60509a…` до/после одинаков. Причина уже другая: новые fixtures передают `replacements[0].utterance_id`, а протестированный `ReviewedReplacement` не содержит этого поля; получено Pydantic `extra_forbidden`. Pytest перечислил `test_reviewed_replacement_normalizes_only_the_audio_verified_span`, `test_reviewed_replacement_rejects_ambiguous_matches`, `test_reviewed_replacement_rejects_duplicate_phrase_in_one_utterance`. Во втором/третьем tests ожидаемые сообщения `exactly one` / `exactly once` не совпали с schema error. Названия/текст fixtures в traceback менялись относительно уже собранных test names: tests редактировались параллельно. Поэтому это наблюдение незавершенной синхронизации tests/implementation, а не заявление о стабильной финальной версии. Повторных запусков после этой границы не выполнялось.

Прежний probe и все дополнительные probes повторно выполнены на `d36a…`: JSON-результаты совпали с первым recheck целиком. Сохранены отдельно [latest old probes](recheck-latest-verifier-probe-results.json) и [latest extra probes](recheck-latest-extra-probe-results.json). Narrow-fixed и remaining findings в таблицах выше доказаны исполнением на `d36a…`; дополнительный однократный заключительный прогон на `60509a…` был ограничен существующим pytest suite и не повторял adversarial probes.

Команда запуска использовала текущие шесть modules: `test_ml_pipeline.py`, `test_ml_compare.py`, `test_ml_runtime.py`, `test_ml_audio_contract.py`, `test_ml_real_regressions.py`, `test_ml_reviewed_corrections.py`, с `-q -p no:cacheprovider` и отдельным basetemp. Из-за известных Windows ACL ошибок временных каталогов запуск выполнен вне sandbox. Project venv по-прежнему не содержит NumPy; подключена уже установленная локальная NumPy 1.26.4 через добавление ее Python312 site-packages в конец `sys.path`, без установки пакетов. Поэтому это не проверка clean dependency installation.

Новые correction tests проверяют audio hash mismatch, запрет speaker field, insertion ordering, pre-extraction wiring и обычное копирование manifest. Runtime тест заменяет реальные модели; code hash assertion проверяет формат 64 hex, а не связь hash с действительно загруженной версией при изменениях файлов во время запуска. Непересечение вставок, semantic correctness ручного текста и происхождение решения человека этими тестами не доказаны. `review_note` — объяснение, не удостоверение личности reviewer или качества прослушивания.

Audio tests подтверждают детерминированное объединение unlabeled gap между одинаковыми labels и сохранение известных opposing turns. Они не доказывают, что именно этот voice identity истинный на неизвестной записи. Новые «real regressions» расширяют текстовые cases на двух знакомых встречах; они не становятся независимым held-out ASR/LLM benchmark.

## Archive replay и assisted inference

Прежний ZIP M2 повторно проверен только текущим validator. По сравнению с сохраненным прежним replay из восьми tasks изменились две: у поиска поставщика добавился owner «Батагоз Нурлановна», у организации совещания с подрядчиками owner «Жандос Талгатович» стал null. Это наблюдение изменения эвристик; правильность каждого имени требует audio-grounded оценки. Нельзя оценивать улучшение одним счетчиком заполненных owner.

Новый `--reviewed-corrections` является явной ручной коррекцией **входного transcript до LLM**, не произвольным редактированием готового abstraction. Audio hash, inserted IDs и сохраненный manifest улучшают прозрачность. Но результат с восстановленным человеком именем нельзя приписывать повышению автоматической ASR accuracy. Необходимо отдельно хранить/сравнивать raw и assisted pipelines на том же аудио, указывать ручные spans и затраты проверки.

Изменение двух знакомых результатов, ручная вставка, либо проход текстовых regressions не подтверждают generalization на ru/kk/mixed. Новые серверные inference outputs и их hashes относятся к проверке основного агента; этот отчет их самостоятельно не запускал и не оценивал как human gold.

## Проверка обновленного направления работ

[recheck-plan-impact.md](recheck-plan-impact.md): **ACCEPT** как следующий ограниченный шаг — immutable raw/reviewed artifacts, snapshot manifest, stage persistence и честный paired raw/assisted comparison перед более крупной миграцией и заменой моделей. Статические риски same-file/mutable-input из этого документа теперь подтверждены исполнением; к tests нужно добавить stale manifest и direct-address time/topic cases. Полный прежний план не следует считать выполненным лишь потому, что несколько его локальных рекомендаций совпали с независимо сделанными изменениями.

Окончательный статус: **CHANGED и подтвержденные narrow FIXES; часть semantic families и V1 STILL REPRODUCIBLE; качество свежего автоматического model pipeline NEEDS EVIDENCE**.
