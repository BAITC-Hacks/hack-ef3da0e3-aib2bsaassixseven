# Meeting Intelligence MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Провести пользователя от загрузки записи RU/KK/mixed до проверенного человеком PDF с транскриптом, поручениями и доказательствами.

**Architecture:** Next.js обращается к защищённому FastAPI. FastAPI временно хранит загрузку, передаёт задачу на NVIDIA-сервер команды, проверяет результат и атомарно сохраняет его в локальном `data/`. GPU удаляет временные данные после подтверждения сохранения; review и PDF работают из локальных файлов без доступного GPU.

**Tech Stack:** Next.js 16, React 19, TypeScript, FastAPI, Python 3.12, Supabase Auth, файловое хранилище приложения, отдельный Python inference API/worker на NVIDIA.

**Spec:** `docs/superpowers/specs/2026-09-23-meeting-intelligence-mvp-design.md`; критерии — `docs/product/PRD.md`, `docs/technical/TRD.md`, маршруты — `docs/technical/API_CONTRACT.md`.

## Global Constraints

- P0: готовый аудиофайл до 100 MiB; WAV, MP3, M4A, OGG и WebM после проверки содержимого.
- Содержимое встреч хранится только в `data/` приложения; Supabase остаётся для Auth/profile.
- Нет Docker, Redis, продуктовой БД, внешних AI API и постоянного хранения аудио.
- GPU принимает только серверный credential по TLS или защищённому туннелю; браузер его не получает.
- Статусы: `queued`, `processing`, `review_required`, `approved`, `failed`; отдельные stage и cleanup status.
- Один GPU job одновременно; начальный TTL временных данных — 24 часа.
- PDF доступен только для утверждённой ревизии; правка сбрасывает утверждение.

## Review Focus

- Повтор submit после сетевого timeout должен вернуть тот же GPU job, без второго inference (задача 6).
- Сбой записи `data/` не должен вызвать ACK и удаление единственной копии результата (задача 6).
- Чужой UUID должен дать 404, а не раскрыть наличие встречи или файл (задачи 3, 5, 8).
- Истечение TTL во время работы должно остановить job и не опубликовать поздний результат (задача 7).
- Одновременный экспорт и новая правка не должны выдать устаревший PDF (задача 8).

---

### Task 1: Зафиксировать единый контракт данных

**Владелец:** Ернур вместе с Ерасылом и Владом.

**Файлы:** `docs/superpowers/specs/2026-09-23-meeting-intelligence-mvp-design.md`, `docs/product/PRD.md`, `docs/technical/API_CONTRACT.md`, `docs/technical/ARCHITECTURE.md`.

- [ ] Согласовать `TranscriptV1` и `InsightsV1`: стабильные метки `speaker_id`, UUID сегментов, evidence внутри сегмента, версии моделей и `result_hash`.
- [ ] Устранить расхождение: PRD допускает ответственного вне списка говорящих, а API сейчас хранит только `assignee_speaker_id`. Зафиксировать поле для имени человека/подразделения, не привязанного к голосу.
- [ ] Согласовать внутренние ответы GPU API, безопасные коды ошибок, повтор `Idempotency-Key`, ACK и TTL; закрепить тестовые JSON-примеры в контракте.

**Готово, когда:** frontend, backend и GPU команда могут реализовать свои части по одной схеме без догадок о полях и состояниях.

### Task 2: Проверить модели на реальном аудио

**Владелец:** Ерасыл.

**Файлы:** создать `gpu/app/ml/transcriber.py`, `gpu/app/ml/diarizer.py`, `gpu/app/ml/analyzer.py`, `gpu/tests/fixtures/README.md`; результаты контрольного прогона — `docs/technical/ML_EVALUATION.md`.

- [ ] Подготовить разрешённые для показа записи RU, KK и mixed, минимум с двумя голосами и проверяемым поручением.
- [ ] Выбрать локальные модели и замерить время, память, качество распознавания, диаризации и evidence на выделенном NVIDIA-сервере.
- [ ] Возвращать пустые/неопределённые поля, когда ответственного, срока или подтверждённого поручения в речи нет; не выдумывать значение ради демо.

**Готово, когда:** каждый контрольный файл даёт версионированный результат, который человек может сверить с аудио и таймкодами. Эту работу можно вести параллельно с задачами 3–5.

### Task 3: Локальные модели и надёжное хранилище

**Владелец:** Ернур.

**Файлы:** создать `backend/app/models/meeting.py`, `backend/app/models/transcript.py`, `backend/app/models/insights.py`, `backend/app/services/artifact_store.py`, `backend/tests/test_artifact_store.py`; изменить `backend/app/core/config.py`, `.gitignore`, `backend/.env.example`.

- [ ] Описать статусы, ревизии, версии схем, владельца, GPU job ID, попытку, источник, ошибки и cleanup status.
- [ ] Сохранять `meeting.json`, исходные `transcript.json`/`insights.json`, `transcript.txt`, отдельный `review.json` и PDF в `data/users/<owner>/meetings/<id>/`; manifest готовности публиковать последним после атомарной записи и проверки хешей.
- [ ] Проверить восстановление после прерванной записи и перезапуска, отсутствие доступа к чужому владельцу, запрет symlink/path traversal; игнорировать `data/` в Git.

**Готово, когда:** тесты читают полные результаты после перезапуска и не принимают частично записанную встречу за готовую.

### Task 4: NVIDIA inference API и один worker

**Владелец:** Ерасыл.

**Файлы:** создать `gpu/pyproject.toml`, `gpu/app/main.py`, `gpu/app/jobs.py`, `gpu/app/worker.py`, `gpu/app/storage.py`, `gpu/tests/test_jobs.py`, `gpu/.env.example`; изменить `.gitignore` для `GPU_TEMP_ROOT`.

- [ ] Реализовать защищённые `POST /internal/v1/jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/result`, `POST /jobs/{id}/ack` по согласованному контракту.
- [ ] Сохранять временный job перед ответом `202`; одинаковый idempotency key с одинаковым содержимым возвращает тот же job, с другим — `409`; один worker обрабатывает один job за раз.
- [ ] Подключить адаптеры задачи 2; результат включает `TranscriptV1`, `InsightsV1`, версии моделей и `result_hash`.

**Готово, когда:** contract tests проходят submit → status → result → ACK; повтор submit не запускает вторую обработку.

### Task 5: Публичная загрузка и чтение встреч

**Владелец:** Ернур.

**Файлы:** создать `backend/app/api/routes/meetings.py`, `backend/app/services/uploads.py`, `backend/tests/test_meetings_api.py`; изменить `backend/app/api/router.py`.

- [ ] Реализовать `POST /api/v1/meetings`: metadata, согласие на запись, 100 MiB, содержимое файла, безопасное имя, временный upload и manifest до `202`.
- [ ] Реализовать список, статус, транскрипт и insights с owner check, пагинацией и точными `401/404/409/413/415/422` из API contract.
- [ ] Проверить повреждённый файл, неверные дату/часовой пояс, чужой UUID, отсутствие частичной встречи после ошибки upload.

**Готово, когда:** пользователь может загрузить файл и видеть свою `queued` встречу; чужие данные и незавершённый результат недоступны.

### Task 6: Coordinator: передача, результат и восстановление

**Владелец:** Ернур совместно с Ерасылом.

**Файлы:** создать `backend/app/services/gpu_client.py`, `backend/app/services/coordinator.py`, `backend/tests/test_coordinator.py`; изменить `backend/app/main.py`, `backend/app/core/config.py`, `backend/.env.example`.

- [ ] После `202` отправлять файл с ключом `meeting_id:attempt`, сохранять job ID, опрашивать status и забирать результат без повторного запуска ML.
- [ ] Валидировать схему, таймкоды, speaker и evidence; надёжно сохранить JSON/TXT, опубликовать готовность и только затем отправить ACK с `result_hash`.
- [ ] При старте API восстанавливать незавершённые submit/poll/result/ACK по manifest и не допускать двух coordinator для одной встречи; тестировать timeout, потерю связи и сбой диска до ACK.

**Готово, когда:** сетевой обрыв и рестарт не создают дубликат job, а готовый локальный результат открывается при отключённом GPU.

### Task 7: Очистка, retry и удаление

**Владелец:** Ернур и Ерасыл на своих машинах.

**Файлы:** изменить `gpu/app/jobs.py`, `gpu/app/storage.py`, `backend/app/services/coordinator.py`, `backend/app/api/routes/meetings.py`; создать `gpu/tests/test_cleanup.py`, `backend/tests/test_lifecycle.py`.

- [ ] После успешного ACK удалять GPU audio/chunks/result и upload приложения; при ошибке сохранять `cleanup_status=pending` и повторять очистку.
- [ ] Через 24 часа очищать и брошенные/failed jobs; останавливать активный job до удаления; отражать `expired` и предлагать новую загрузку при `source_expired`.
- [ ] Реализовать `POST /retry` с лимитом трёх попыток только пока есть исходник и `DELETE /meetings/{id}` только после завершения обработки и очистки.

**Готово, когда:** тесты подтверждают удаление обеих временных копий, безопасный повтор ACK, TTL и сохранность постоянных JSON/TXT.

### Task 8: Review, approval и PDF на backend

**Владелец:** Ернур.

**Файлы:** создать `backend/app/services/reviews.py`, `backend/app/services/pdf_export.py`, `backend/tests/test_review_export.py`; изменить `backend/app/api/routes/meetings.py`, `backend/pyproject.toml`, `backend/uv.lock`.

- [ ] Реализовать `PUT /review` как полную замену правок с `base_revision`, проверкой всех ссылок и сбросом approval при новой правке.
- [ ] Реализовать `POST /approve` только для проверенной ревизии, где каждый голос назван либо явно обозначен неизвестным, а evidence корректно; `GET /export.pdf` должен содержать читаемые русские/казахские символы, цитаты, таймкоды и метку `demo_fixture`.
- [ ] Кэшировать PDF по ревизии, исключить выдачу старого кэша при конкурентной правке; ошибка экспорта не отменяет approval.

**Готово, когда:** PDF содержит сохранённые правки, недоступен до approval и после новой правки требует повторного утверждения.

### Task 9: Загрузка, список и прогресс на frontend

**Владелец:** Влад.

**Файлы:** создать `frontend/lib/meetings-api.ts`, `frontend/components/meeting-upload.tsx`, `frontend/components/meeting-list.tsx`, `frontend/app/dashboard/meetings/[id]/page.tsx` и тесты рядом; изменить `frontend/app/dashboard/page.tsx`, `frontend/app/globals.css`.

- [ ] Показать допустимые форматы, лимит, metadata и подтверждение уведомления; обрабатывать ошибки upload понятным текстом.
- [ ] Показывать список своих встреч, `queued`/`processing`/`failed`, реальный stage и polling раз в 2 секунды без выдуманного процента.
- [ ] Для `failed` показать безопасную причину и `retry` при доступном исходнике; при `source_expired` предложить новую загрузку. Готовые результаты открывать и при недоступном GPU; завершённую встречу можно удалить после cleanup.

**Готово, когда:** защищённый пользователь проходит upload → ожидание → открытие локально сохранённой встречи.

### Task 10: Экран проверки и экспорт на frontend

**Владелец:** Влад.

**Файлы:** создать `frontend/components/transcript-review.tsx`, `frontend/components/insights-review.tsx`, `frontend/components/meeting-export.tsx` и тесты рядом; изменить `frontend/app/dashboard/meetings/[id]/page.tsx`, `frontend/lib/meetings-api.ts`.

- [ ] Показать сегменты, спикеров, summary, поручения и evidence с цитатой/таймкодом; различать неизвестного говорящего и пустой срок.
- [ ] Дать исправить текст транскрипта, имя/метку спикера, summary, ответственного и срок, добавить или удалить поручение с выбором evidence; сохранить полную review-ревизию, обработать конфликт `409 stale_revision`.
- [ ] Дать явное утверждение и скачать PDF только после `approved`; новая правка сразу скрывает старый экспорт.

**Готово, когда:** правки видны после обновления страницы, а скачанный PDF совпадает с проверенной версией.

### Task 11: Сквозная приёмка и честное демо

**Владельцы:** Ернур — интеграция, Ерасыл — ML, Влад — UI.

**Файлы:** создать `backend/tests/test_meeting_flow.py`, `backend/app/services/demo_fixture.py`, `backend/tests/fixtures/demo_meeting/`, `docs/technical/ML_EVALUATION.md`; изменить `docs/product/DEMO_FLOW.md`, `README.md`, `backend/README.md`, `frontend/README.md`, `.github/workflows/ci.yml`.

- [ ] Пройти на одной сборке RU, KK и mixed запись: upload → NVIDIA → review → approval → PDF; сверить evidence с реальной речью.
- [ ] Проверить owner isolation, рестарт, потерю сети, сбой диска до ACK, повтор ACK, TTL, отсутствие GPU при чтении готового результата и кириллицу/казахские символы в PDF; убедиться, что секреты и содержимое встреч не попали в логи.
- [ ] Подготовить отдельный неизменяемый `demo_fixture` для демонстрационного аккаунта с явной меткой на экране и в PDF; в демо не подменять им результат произвольной загрузки.

**Готово, когда:** критерии P0 из PRD и чеклист `DEMO_FLOW.md` пройдены; CI запускает backend/frontend/GPU checks и интеграционные тесты без реальных секретов.

## После P0

P1 отдельным планом: улучшение моделей на сложных записях, переход от поручения к сегменту, безопасное сравнение повторной обработки с правками, настройка PDF. Запись в браузере, конференц-боты, streaming, DOCX и интеграции не входят в этот план.
