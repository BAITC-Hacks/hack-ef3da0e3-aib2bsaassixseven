# Meeting Intelligence MVP — дизайн системы

**Статус:** на проверке команды

**Дата:** 2026-09-23

**Ветка:** `yernur-backend`

**Владельцы:** Yernur — архитектура и backend, Erasyl — ML research и локальные
ML-адаптеры, Vlad — frontend и визуальный дизайн.

## 1. Цель

Собрать воспроизводимый хакатонный MVP, который принимает готовую аудиозапись
совещания и локально превращает её в проверяемый управленческий протокол:

1. транскрипт на русском, казахском или смешанной речи;
2. реплики с таймкодами и условными спикерами;
3. ручное сопоставление спикеров с участниками;
4. саммари с важными фактами и числами;
5. поручения с ответственными, сроками и ссылками на исходные реплики;
6. проверка и исправление результата человеком;
7. утверждённый PDF-протокол.

Аудио, транскрипт и результаты анализа не передаются во внешние AI API.
В MVP они сохраняются в локальной папке `data/` как аудиофайлы, JSON и TXT.

## 2. Решение в одном абзаце

Next.js отправляет аудиофайл и метаданные встречи в FastAPI. FastAPI проверяет
пользователя, безопасно сохраняет файл и `meeting.json`, помечает встречу как
`queued` и сразу возвращает её ID. Отдельный локальный worker последовательно
находит такие встречи, вызывает локальные ML-адаптеры и атомарно сохраняет
транскрипт и результат анализа. Frontend опрашивает FastAPI по ID, показывает
этап обработки, затем даёт секретарю исправить спикеров и поручения. PDF можно
сформировать только после явного утверждения результата.

## 3. Почему отдельный worker не усложняет MVP

Worker — обычный третий локальный процесс Python, а не отдельный облачный
сервис. Для запуска не нужны Docker, Redis, Kafka или база данных.

Он нужен по трём причинам:

- распознавание речи не держит HTTP-запрос открытым несколько минут;
- перезапуск FastAPI не удаляет загруженную запись и состояние задачи;
- Erasyl может менять ML-модели за стабильным Python-контрактом, не затрагивая
  API и frontend.

Для MVP worker обрабатывает задачи последовательно на одном компьютере. Это
соответствует ограниченному времени и доступному CPU/GPU. Масштабирование
достигается не ранними микросервисами, а чёткими границами: позже файловую
очередь можно заменить PostgreSQL/Redis, локальные файлы — object storage, а
один worker — пулом workers без изменения HTTP-контракта и доменных моделей.

## 4. Границы MVP

### P0 — реализуется сейчас

- существующая Supabase-аутентификация;
- создание встречи с датой, названием и участниками;
- подтверждение, что участников уведомили о записи;
- загрузка готового аудиофайла;
- локальная фоновая обработка;
- русский, казахский и смешанный транскрипт через ML-контракт;
- диаризация и таймкоды;
- ручное именование `Speaker 1`, `Speaker 2`;
- саммари, ключевые факты и поручения;
- `action → evidence segment → speaker → timestamp`;
- nullable ответственный и срок: отсутствующие значения не выдумываются;
- редактирование и утверждение человеком;
- PDF после утверждения;
- сохранение артефактов после перезапуска API;
- честно обозначенный deterministic demo adapter на случай, если реальная
  модель не готова или недоступна на демонстрационной машине.

### P1 — после рабочего основного сценария

- дедупликация повторных формулировок поручения;
- история изменения срока или ответственного;
- предупреждения о пропущенных полях и низкой уверенности;
- повторный запуск отдельного ML-этапа;
- простой список/статусы выполнения поручений;
- дополнительный DOCX-экспорт.

### Не входит в первую версию

- live-запись или streaming partial transcript;
- Teams, Zoom и Meet интеграции;
- биометрическая идентификация человека по голосу;
- СЭД, email-рассылки и напоминания;
- промышленный on-prem/Kubernetes;
- совместное редактирование несколькими пользователями;
- хранение meeting data в Supabase или другой базе.

## 5. Архитектура

```text
Browser
  │
  ▼
Next.js 16
  │ Bearer JWT + versioned HTTP schemas
  ▼
FastAPI
  ├── Auth/owner checks
  ├── Meeting API
  ├── Upload ingestion
  ├── Review/approval
  └── PDF export
        │
        ▼
LocalArtifactStore ───────────────┐
  data/users/.../meeting.json     │ persisted job state
  data/users/.../audio/*          │
  data/users/.../*.json|*.txt     │
                                  ▼
                           Local Worker
                             ├── Transcriber port
                             ├── Diarizer port
                             └── Analyzer port
                                      │
                                      ▼
                              Erasyl ML adapters
```

### Runtime-процессы

1. **Next.js** — интерфейс загрузки, прогресса, проверки и экспорта.
2. **FastAPI** — единственная бизнес-точка доступа к meeting data.
3. **Worker** — тяжёлая локальная обработка одной встречи за раз.

Supabase сохраняет текущую роль: аутентификация и профиль. Аудио, транскрипт и
аналитика в Supabase не отправляются.

## 6. Backend-модули

```text
backend/app/
├── api/routes/          HTTP endpoints и response mapping
├── core/                config, auth, logging
├── meetings/            доменные модели и state transitions
├── ingestion/           upload validation и RecordingRef
├── storage/             безопасные пути и атомарные file operations
├── processing/          pipeline orchestration
├── ml/                  Protocol-интерфейсы и adapters
├── exports/             PDF renderer
└── worker/              polling, claim, retry, recovery
```

Правила зависимостей:

- routes вызывают use cases, но не работают с файлами напрямую;
- domain не импортирует FastAPI, Supabase или конкретные ML-библиотеки;
- ML adapter не владеет HTTP, авторизацией или файловой раскладкой;
- frontend никогда не получает абсолютные пути файлов или детали моделей.

## 7. Локальное хранение

```text
data/
└── users/<owner_uuid>/meetings/<meeting_uuid>/
    ├── meeting.json
    ├── audio/
    │   └── original.<validated_extension>
    ├── transcript.json
    ├── transcript.txt
    ├── insights.json
    ├── review.json
    └── exports/
        └── protocol.pdf
```

Папка `data/` целиком игнорируется Git. Файл `data/README.md` описывает формат,
но реальные пользовательские данные никогда не коммитятся.

### Обязательные свойства файлового слоя

- имена каталогов строятся только из UUID, а не из клиентских путей;
- upload сначала пишется как временный `.part`, затем атомарно переименовывается;
- JSON сначала пишется во временный файл, затем заменяет старый через atomic
  replace;
- `schema_version` присутствует во всех JSON-артефактах;
- API проверяет `owner_id` до чтения любого артефакта;
- пользователь другой встречи получает `404`, а не подтверждение её наличия;
- удаление блокируется во время обработки;
- аудио и транскрипт не попадают в application logs.

## 8. Доменные данные

### Meeting

- `id`, `owner_id`, `title`, `meeting_date`, `timezone`;
- `participants[]`;
- `recording_notice_confirmed`;
- `source.kind` (`upload` в MVP);
- `status`, `processing_stage`, `error`;
- `created_at`, `updated_at`;
- версии схемы, pipeline и моделей.

### TranscriptSegment

- стабильный `id`;
- `start_ms`, `end_ms`;
- исходный `text`;
- `speaker_label`;
- language tag и nullable confidence.

### ActionItem

- `id`, `text`;
- nullable `assignee` и `deadline`;
- исходная формулировка срока;
- `evidence_segment_ids[]`;
- nullable confidence;
- `review_status`.

### Insights

- краткое саммари;
- ключевые факты и числа;
- решения;
- поручения;
- warnings для неоднозначных или отсутствующих данных.

### Review

- mapping условных спикеров на участников;
- исправленные action items;
- решение `accepted`, `edited` или `rejected` для каждого поручения;
- пользователь и время утверждения.

## 9. Состояния встречи

```text
upload accepted
      │
      ▼
   queued ───────────────┐
      │                  │ retry
      ▼                  │
 processing ────────► failed
      │
      ▼
review_required
      │ human approval
      ▼
   approved
      │ on-demand export
      ▼
  PDF available
```

`status` остаётся крупным состоянием: `queued`, `processing`,
`review_required`, `approved`, `failed`. Текущий `processing_stage` хранится
отдельно: `ingesting`, `transcribing`, `diarizing`, `analyzing`, `exporting`
или `null`. UI не показывает выдуманный процент.

## 10. Worker и восстановление

Worker циклически сканирует meeting manifests со статусом `queued`, атомарно
помечает выбранную встречу как `processing` и выполняет pipeline. В MVP
запускается ровно один worker, поэтому распределённая блокировка не нужна.

Каждый этап идемпотентен:

- source audio неизменяемо;
- производные артефакты полностью пересоздаются;
- частично записанный JSON никогда не считается готовым;
- после перезапуска worker находит прерванный `processing`, проверяет готовые
  артефакты и безопасно повторяет незавершённый этап;
- понятная безопасная ошибка сохраняется в `meeting.json`, а полный traceback
  остаётся только в локальном server log без содержимого встречи.

## 11. ML-контракты

Backend определяет стабильные versioned ports:

```text
Transcriber.transcribe(RecordingRef, language_hint) -> TranscriptV1
Diarizer.assign_speakers(RecordingRef, TranscriptV1) -> TranscriptV1
Analyzer.analyze(TranscriptV1, MeetingContext) -> InsightsV1
```

Контракты принимают и возвращают типизированные JSON-serializable модели.
Конкретная модель может работать в том же процессе worker, через локальный
subprocess или локальный HTTP endpoint. Сетевой вызов внешнего AI API запрещён.

Для параллельной работы создаётся `DemoPipelineAdapter`: он читает заранее
подготовленный результат для конкретного демонстрационного файла и явно
помечает его `processing_mode: demo_fixture`. Он нужен для разработки API/UI и
аварийного demo fallback, но не выдаётся за реальную транскрибацию.

## 12. HTTP API

Все product endpoints находятся под `/api/v1`, требуют существующий Supabase
Bearer token и проверяют владельца.

- `POST /meetings` — multipart upload + metadata, ответ `202 queued`;
- `GET /meetings` — встречи текущего пользователя;
- `GET /meetings/{id}` — состояние и этап;
- `GET /meetings/{id}/transcript` — транскрипт после готовности;
- `GET /meetings/{id}/insights` — саммари и поручения;
- `PUT /meetings/{id}/review` — сохранить исправления;
- `POST /meetings/{id}/approve` — утвердить результат;
- `POST /meetings/{id}/retry` — повторить failed pipeline;
- `GET /meetings/{id}/export.pdf` — создать/получить PDF после approval;
- `DELETE /meetings/{id}` — удалить встречу и все артефакты.

FastAPI OpenAPI — источник истины для Vlad. Полные примеры и error responses
описаны в `docs/technical/API_CONTRACT.md`.

## 13. Frontend-flow

Планируемые продуктовые экраны без привязки к визуальному стилю:

1. список встреч;
2. создание встречи, участники, уведомление о записи и upload;
3. processing state с текущим этапом и retry при ошибке;
4. review workspace: transcript, speaker mapping, summary, action items и
   evidence jump;
5. approval и PDF export.

Vlad владеет реализацией и дизайном `frontend/`. Backend не меняет визуальные
компоненты без согласования; API-схемы передаются до frontend-интеграции.

## 14. Будущий live-режим

Источник аудио изолируется интерфейсом:

```text
UploadedAudioSource ─┐
LiveCaptureSource ───┼──► RecordingRef ─► тот же pipeline
Teams/Zoom/Meet ─────┘
```

Текущий upload adapter сразу создаёт финальный `RecordingRef`. Будущий live
adapter создаст capture session, будет писать входящий поток в локальный файл,
а после завершения встречи финализирует тот же `RecordingRef` и поставит
обычную задачу в очередь. Поэтому транскрипция, анализ, review и export не
меняются.

Настоящий realtime partial transcript является отдельным будущим контуром и
не считается автоматически решённым этой batch-архитектурой.

## 15. Ошибки и поведение UI

- `401` — отсутствующая или невалидная сессия;
- `404` — встреча отсутствует или принадлежит другому пользователю;
- `409` — операция невозможна в текущем состоянии;
- `413` — файл превышает конфигурируемый лимит;
- `415` — неподдерживаемый формат;
- `422` — невалидные metadata/review;
- `507` — недостаточно локального дискового пространства, если это обнаружено;
- `500` — безопасная общая ошибка без текста/аудио/секретов.

Если анализ не удался после успешной транскрибации, готовый транскрипт
сохраняется. Retry не удаляет исходное аудио и успешные проверенные артефакты.
Ошибка PDF не меняет утверждённые данные.

## 16. Demo-flow

Целевой путь укладывается в 3–5 минут:

1. создать встречу и загрузить подготовленный mixed RU/KK аудиофайл;
2. увидеть `queued → processing` и реальные названия этапов;
3. открыть транскрипт со спикерами и таймкодами;
4. открыть поручение и перейти к evidence segment;
5. назвать спикера, исправить ответственного или срок;
6. утвердить протокол;
7. скачать PDF.

Если локальная ML-модель не готова или слишком медленна, ведущий переключает
встречу на заранее подготовленный результат с явной отметкой «демонстрационные
данные». Это сохраняет честность показа и позволяет продемонстрировать весь
управленческий flow.

## 17. Тестирование

### Backend

- domain state transitions;
- owner isolation и path traversal protection;
- atomic storage/recovery;
- upload validation и лимиты;
- API status/error contracts;
- fake ML adapters и pipeline orchestration;
- review/approval rules;
- PDF generation smoke test.

### Frontend

- API client schema handling;
- polling и terminal states;
- review editing;
- evidence navigation;
- error/retry/fallback states.

### Contract/e2e

- sample upload → completed artifacts → review → PDF;
- OpenAPI schema проверяется в CI;
- golden fixtures для TranscriptV1/InsightsV1;
- один анонимизированный mixed-language demo recording с ожидаемыми фактами и
  поручениями.

## 18. Документация и ownership

- `docs/product/PRD.md` — продуктовые требования;
- `docs/product/TARGET_USERS.md` — пользователи и jobs-to-be-done;
- `docs/product/DEMO_FLOW.md` — сценарий демонстрации;
- `docs/technical/TRD.md` — технические требования;
- `docs/technical/ARCHITECTURE.md` — компоненты и потоки;
- `docs/technical/API_CONTRACT.md` — контракт frontend/backend;
- этот файл — утверждаемое архитектурное решение для MVP.

Общие API-схемы меняются только после уведомления Vlad. ML-схемы меняются
только после согласования Yernur и Erasyl. В MVP Yernur является владельцем
интеграции end-to-end.

## 19. Критерии готовности дизайна

Документация готова к переходу в implementation plan, если команда согласна,
что:

1. P0 ограничен одним честным flow от upload до PDF;
2. meeting data хранится только локально в `data/`;
3. worker — отдельный простой Python-процесс без Docker и broker;
4. Erasyl интегрируется через versioned ML ports;
5. Vlad получает versioned HTTP contract и product states;
6. human approval обязателен перед PDF;
7. live capture проектируется как новый source adapter после MVP;
8. demo adapter всегда явно обозначается и не маскируется под реальный ML.
