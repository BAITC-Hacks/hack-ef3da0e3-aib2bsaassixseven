# Контракт API встреч v1

## Статус и границы

Это **планируемый** контракт для загруженного локального аудио встречи. На текущей ветке реализованы авторизация Supabase и `GET /api/v1/me`; перечисленных ниже маршрутов встреч, worker и PDF-экспорта ещё нет. Контракт задаёт целевое поведение клиента и FastAPI для хакатонного демо. Потоковый захват живой встречи в v1 не входит.

Все маршруты ниже начинаются с `/api/v1`, принимают `Authorization: Bearer <supabase_access_token>` и доступны только владельцу встречи. FastAPI проверяет токен существующей зависимостью авторизации. Идентификатор владельца берётся из `sub` токена, не из тела запроса. Чужая встреча отвечает `404`, как и несуществующая. Токены, локальные пути аудио/JSON/TXT-артефактов и внутренние имена файлов никогда не входят в JSON, логи клиентских ошибок или PDF. FastAPI приложения передаёт задачу на выделенный NVIDIA-сервер команды, где worker вызывает собственную модель. Результат возвращается в локальный `data/` приложения; только после сохранения backend подтверждает получение и запускает очистку временного аудио на обеих сторонах. Доступ к артефактам и проверка владельца остаются на стороне FastAPI.

## Состояния и общие поля

`status` принимает только `queued`, `processing`, `review_required`, `approved`, `failed`:

| Состояние | Значение | Разрешённый следующий переход |
| --- | --- | --- |
| `queued` | Загрузка сохранена, задача ожидает worker. | `processing`, `failed` |
| `processing` | Worker выполняет текущую попытку. | `review_required`, `failed` |
| `review_required` | Расшифровка и выводы готовы; человек проверяет и редактирует. | `approved` |
| `approved` | Человек подтвердил текущую ревизию; PDF доступен. | `review_required` после сохранения новой правки через `PUT /review`. |
| `failed` | Загрузка или обработка завершилась ошибкой; сохранён безопасный код причины. | `queued` через `POST /retry` |

`stage` — отдельное поле: `uploading_to_gpu`, `ingesting`, `transcribing`, `diarizing`, `analyzing`, `saving_results`, `exporting` либо `null`. Этапы передачи, ML и сохранения допустимы при `processing` и идут в указанном порядке; `exporting` допустим только при `approved` во время синхронного создания PDF по запросу `GET /export.pdf`. При выдаче уже созданного PDF этап остаётся `null`. В остальных случаях `stage = null`. Этап не является процентом прогресса. Ошибка формирования PDF не меняет `approved`: запрос экспорта возвращает ошибку, `stage` снова становится `null`, повторный запрос разрешён. При повторе обработки `attempt` увеличивается, `status` возвращается в `queued`, `stage = null`; результаты прежней попытки не доступны через текущие `/transcript` и `/insights`.

Каждая встреча имеет `id` (UUID), `title` (1–120 символов), `meeting_date` (дата `YYYY-MM-DD`), `timezone` (идентификатор IANA, например `Asia/Almaty`), `participants` (список имён), `recording_notice_confirmed` (`true`), `language_hint` (`auto|ru|kk|mixed`), `created_at`, `updated_at` (UTC ISO 8601), `attempt` (целое от 1), `revision` (целое от 0), `status`, `stage`, `source` и `failure`. Дата встречи интерпретируется в указанном часовом поясе; `created_at` и `updated_at` остаются UTC. `source.kind` равен `uploaded_audio` для обработки загруженного файла или `demo_fixture` для заранее рассчитанного примера. При `demo_fixture` обязательны `source.label = "Подготовленный пример · обработка выполнена заранее"` и `source.fixture_id`; этот источник должен быть заметен в UI и PDF. Исходный набор артефактов примера неизменяем, а правки пользователя хранятся отдельной ревизией. Подготовленный пример привязан к конкретному демонстрационному аудио и не подставляется для произвольной загрузки. `failure` равен `null` либо `{ "code": "processing_failed", "message": "Не удалось обработать запись" }` с безопасным для показа текстом.

Результаты `/transcript` и `/insights` доступны при `review_required` и `approved`. До `approved` они являются черновиком. Экспорт разрешён только после отдельного человеческого подтверждения. Успешная правка утверждённой встречи увеличивает `revision`, удаляет кэш PDF прежней ревизии и атомарно возвращает статус в `review_required`; новый экспорт требует повторного `POST /approve`. Неуспешная правка не меняет утверждение и кэш.

## Маршруты

Все строки таблицы имеют статус **планируется**; других реализаций в текущей ветке нет.

| Метод и маршрут | Назначение | Успех | Ошибки помимо `401`/`404` |
| --- | --- | --- | --- |
| `POST /meetings` | Создать встречу из `multipart/form-data`: `audio` + `metadata` JSON. | `202` + `Meeting` | `413` размер; `415` формат; `422` поля; `503` очередь недоступна |
| `GET /meetings?limit=20&cursor=...` | Список встреч владельца, новые первыми. `limit` 1–100; `cursor` непрозрачен. | `200` + `{items: Meeting[], next_cursor: string|null}` | `422` параметры |
| `GET /meetings/{meeting_id}` | Состояние для polling, включая `stage`, `attempt` и `failure`. | `200` + `Meeting` | `422` неверный UUID |
| `GET /meetings/{meeting_id}/transcript` | Сегменты с таймкодами и голосами. | `200` + `TranscriptV1` | `409` результат ещё не готов |
| `GET /meetings/{meeting_id}/insights` | Итог и задачи с доказательствами. | `200` + `InsightsV1` | `409` результат ещё не готов |
| `PUT /meetings/{meeting_id}/review` | Целиком заменить правки при `review_required` или `approved`; после правки статус `review_required`. | `200` + `{revision, status}` | `409` другое состояние или устаревшая ревизия; `422` неверные ссылки/поля |
| `POST /meetings/{meeting_id}/approve` | Подтвердить проверенную ревизию. | `200` + `Meeting` | `409` состояние, ревизия или неполная проверка |
| `GET /meetings/{meeting_id}/export.pdf` | Синхронно сформировать и кэшировать PDF утверждённой ревизии либо скачать кэш. | `200` + `application/pdf` | `409` не утверждено; `503` экспорт не удался |
| `POST /meetings/{meeting_id}/retry` | Повторить failed при доступном временном исходнике, максимум три попытки. | `202` + `Meeting` | `409` не failed, лимит или source_expired; `503` GPU недоступен |
| `DELETE /meetings/{meeting_id}` | Удалить локальные результаты после завершения GPU-обработки и очистки. | `204`, без тела | `409` queued/processing или cleanup pending; `503` удаление не завершено |

Для `POST /meetings` обязательны две части формы: `audio` — бинарный файл и `metadata` — JSON-объект с `Content-Type: application/json`. В `metadata` обязательны `title` (1–120 символов), `meeting_date` (`YYYY-MM-DD`), `timezone` (действительный идентификатор IANA), `participants` (массив из 0–30 уникальных имён по 1–100 символов) и `recording_notice_confirmed: true`; `language_hint` необязателен, по умолчанию `auto`, значения `auto|ru|kk|mixed`. Отметка `recording_notice_confirmed` фиксирует подтверждение пользователя об уведомлении участников, но сама по себе не доказывает его получение. `false`, отсутствие обязательного поля, неверная дата или часовой пояс дают `422`. Принимаются `.wav`, `.mp3`, `.m4a`, `.ogg`, `.webm` с проверкой содержимого, не только расширения; максимум 100 MiB. Загрузка атомарна: после `202` аудио временно сохранено приложением и задача передачи на NVIDIA записана в manifest. Это ещё не подтверждение, что GPU принял задачу. Если временное сохранение upload и manifest не завершилось, встреча не появляется в списке. Имя загруженного файла не используется как путь хранения. Создание `demo_fixture` не открывается публичным маршрутом: пример заранее подготовлен для демонстрационного аккаунта и возвращается обычными `GET`-маршрутами с меткой источника.

Пример запроса загрузки:

```bash
curl -X POST 'http://localhost:8000/api/v1/meetings' \
  -H 'Authorization: Bearer <supabase_access_token>' \
  -F 'audio=@meeting.wav;type=audio/wav' \
  -F 'metadata={"title":"План запуска","meeting_date":"2026-09-23","timezone":"Asia/Almaty","participants":["Алия","Ернур"],"recording_notice_confirmed":true,"language_hint":"mixed"};type=application/json'
```

Ответ `202` имеет форму `Meeting`, приведённую ниже. В ходе обработки `GET /meetings/{id}` вернёт, например, `"status": "processing"` и `"stage": "diarizing"`; по окончании — `"status": "review_required"` и `"stage": null`.

Polling: клиент запрашивает `GET /meetings/{id}` раз в 2 секунды, пока статус `queued` или `processing`; после `review_required` загружает `/transcript` и `/insights`. `GET` не запускает повторную обработку аудио. Первый `GET /export.pdf` при `approved` синхронно создаёт PDF и сохраняет кэш для пары `(meeting_id, revision)` до отправки `200`; следующий запрос отдаёт кэш. Если несколько запросов экспорта приходят одновременно, PDF создаётся один раз. Правка через `PUT /review` удаляет кэш старой ревизии; конкурирующий экспорт не должен выдать PDF после успешного перехода встречи в `review_required`.

## Форматы ответов

`Meeting` (пример после загрузки; `source.label` и `source.fixture_id` обязательны только для `demo_fixture`):

```json
{
  "id": "81df6d39-16dd-4227-98b0-d45e531e091e",
  "title": "План запуска",
  "meeting_date": "2026-09-23",
  "timezone": "Asia/Almaty",
  "participants": ["Алия", "Ернур"],
  "recording_notice_confirmed": true,
  "language_hint": "mixed",
  "created_at": "2026-09-23T09:00:00Z",
  "updated_at": "2026-09-23T09:00:00Z",
  "attempt": 1,
  "revision": 0,
  "status": "queued",
  "stage": null,
  "source_available": true,
  "cleanup_status": "pending",
  "temporary_expires_at": "2026-09-24T09:00:00Z",
  "source": { "kind": "uploaded_audio" },
  "failure": null
}
```

### TranscriptV1 и InsightsV1

Обе схемы имеют обязательные `schema_version: 1`, `meeting_id` (UUID), `revision` (целое ≥ 0). GPU выдаёт только `revision: 0`; публичные GET возвращают эти же схемы с наложенными правками текущей ревизии. Поля примеров обязательны, в том числе поля со значением `null`; неизвестные поля и версии отклоняются. UUID записываются в стандартной строковой форме. Идентификаторы уникальны в своём списке и неизменны при review; новая попытка ML может создать новые идентификаторы. Машинные JSON не перезаписываются правками.

`TranscriptV1`: `speaker_id` — стабильная строковая метка голоса `speaker_1`, `speaker_2`, … (положительный номер, шаблон `^speaker_[1-9][0-9]*$`), не имя человека. Сегмент имеет UUID `id`, существующий `speaker_id`, целые миллисекунды `0 <= start_ms < end_ms`, язык `ru|kk|unknown`, непустой `text`, boolean `edited`. Сегменты упорядочены по `start_ms`; пересечение реплик разных голосов допустимо. Машинный вывод содержит `edited: false`; пользовательская правка текста или голоса даёт `true` и не меняет таймкоды.

Каждый голос и элемент `speaker_mappings` содержит `identity_status`:

| Значение | `display_name` | Утверждение |
| --- | --- | --- |
| `unreviewed` | `null` | Голос ещё не проверен; блокирует approval. Это начальное значение GPU. |
| `named` | Строка 1–100 символов после trim | Пользователь указал имя/метку. |
| `unknown` | `null` | Пользователь явно выбрал «Неизвестный спикер»; approval разрешён без выдуманной личности. |

UI/PDF показывают `unknown` как «Неизвестный спикер (speaker_N)», сохраняя различимость голосов. `participants` не устанавливает соответствие между голосом и человеком автоматически.

Синтетический пример `TranscriptV1`:

```json
{
  "schema_version": 1,
  "meeting_id": "81df6d39-16dd-4227-98b0-d45e531e091e",
  "revision": 0,
  "speakers": [
    { "speaker_id": "speaker_1", "display_name": null, "identity_status": "unreviewed" },
    { "speaker_id": "speaker_2", "display_name": null, "identity_status": "unreviewed" }
  ],
  "segments": [
    {
      "id": "76424ccb-f8d4-46f2-b7fc-81e888a01775",
      "start_ms": 6600,
      "end_ms": 11400,
      "speaker_id": "speaker_1",
      "language": "ru",
      "text": "Бухгалтерия отправит смету в пятницу.",
      "edited": false
    },
    {
      "id": "5400365d-5c1d-4f09-a0a3-3c6dc2aef5ba",
      "start_ms": 12000,
      "end_ms": 13000,
      "speaker_id": "speaker_2",
      "language": "kk",
      "text": "Жақсы.",
      "edited": false
    }
  ]
}
```

`InsightsV1` содержит массивы `summary` и `action_items`. Каждый пункт имеет UUID `id`, непустой `text` и непустой массив `evidence` с `{segment_id, start_ms, end_ms}`. Ссылка принадлежит тому же транскрипту; `segment.start_ms <= evidence.start_ms < evidence.end_ms <= segment.end_ms`. Цитата берётся из текста указанного сегмента текущей ревизии; интервал evidence не задаёт границы символов. UI/PDF показывают весь текст сегмента, не выдумывают дословную подстроку по времени. Пустые списки итогов и задач допустимы.

У каждой задачи обязательны следующие nullable-поля:

| Поля | Правило |
| --- | --- |
| `assignee_speaker_id`, `assignee_name` | Существующий голос + `null`; либо `null` + имя человека/подразделения вне голосов (1–100 символов после trim); либо оба `null` — ответственный неизвестен. Два непустых значения дают `422 invalid_request`. Автор реплики не становится ответственным автоматически. |
| `due_date` | Валидная дата `YYYY-MM-DD` либо `null`; неясный срок нельзя молча превращать в дату. |
| `due_date_text` | Исходная формулировка срока (непустая строка) либо `null`, если в речи срока нет. Сохраняется даже при нормализации даты; ручной срок без исходной формулировки может иметь `due_date_text: null`. |

Синтетический пример `InsightsV1` с ответственным-подразделением и неуточнённой датой:

```json
{
  "schema_version": 1,
  "meeting_id": "81df6d39-16dd-4227-98b0-d45e531e091e",
  "revision": 0,
  "summary": [
    {
      "id": "dc2c962f-8914-4fca-932d-5fbbcc4933cb",
      "text": "Бухгалтерия отправит смету в пятницу.",
      "evidence": [
        { "segment_id": "76424ccb-f8d4-46f2-b7fc-81e888a01775", "start_ms": 6600, "end_ms": 11400 }
      ]
    }
  ],
  "action_items": [
    {
      "id": "f9a6be39-bf63-4aba-98d7-b9fe11fd30db",
      "text": "Отправить смету",
      "assignee_speaker_id": null,
      "assignee_name": "Бухгалтерия",
      "due_date": null,
      "due_date_text": "в пятницу",
      "evidence": [
        { "segment_id": "76424ccb-f8d4-46f2-b7fc-81e888a01775", "start_ms": 6600, "end_ms": 11400 }
      ]
    }
  ]
}
```

Для задачи с известным голосом поля будут `"assignee_speaker_id": "speaker_1", "assignee_name": null`; для неизвестного ответственного — оба `null`. Неопределённые ответственный и срок не блокируют approval: человек подтверждает сохранённую неопределённость.

`PUT /review` разрешён при `review_required` и `approved` и принимает полный текущий набор отображаемых имён, правок сегментов и выводов. `segment_edits` перечисляет только исправленные сегменты; пустой список снимает прежние текстовые/голосовые правки. `summary` и `action_items` заменяются целиком. Для новых пунктов клиент создаёт UUID; повтор запроса с тем же `base_revision` после успешного сохранения вернёт `409`, чтобы случайно не применить правку дважды. Массив `speaker_mappings` должен покрывать все обнаруженные голоса ровно по одному разу, по правилам `identity_status` выше; дубли `segment_edits` запрещены. Поля итогов и задач совпадают с `InsightsV1`. Сервер проверяет существование всех голосов и сегментов, границы доказательств и принадлежность данных одной встрече. После успешного сохранения `revision` увеличивается на 1, статус становится `review_required`; если прежде было `approved`, кэш PDF удаляется в той же операции.

```http
PUT /api/v1/meetings/81df6d39-16dd-4227-98b0-d45e531e091e/review
Authorization: Bearer <supabase_access_token>
Content-Type: application/json

{
  "base_revision": 0,
  "speaker_mappings": [
    { "speaker_id": "speaker_1", "display_name": "Алия", "identity_status": "named" },
    { "speaker_id": "speaker_2", "display_name": null, "identity_status": "unknown" }
  ],
  "segment_edits": [
    { "segment_id": "76424ccb-f8d4-46f2-b7fc-81e888a01775", "text": "Бухгалтерия отправит смету в пятницу.", "speaker_id": "speaker_1" }
  ],
  "summary": [
    {
      "id": "dc2c962f-8914-4fca-932d-5fbbcc4933cb",
      "text": "Бухгалтерия отправит смету в пятницу.",
      "evidence": [
        { "segment_id": "76424ccb-f8d4-46f2-b7fc-81e888a01775", "start_ms": 6600, "end_ms": 11400 }
      ]
    }
  ],
  "action_items": [
    {
      "id": "f9a6be39-bf63-4aba-98d7-b9fe11fd30db",
      "text": "Отправить смету",
      "assignee_speaker_id": null,
      "assignee_name": "Бухгалтерия",
      "due_date": null,
      "due_date_text": "в пятницу",
      "evidence": [
        { "segment_id": "76424ccb-f8d4-46f2-b7fc-81e888a01775", "start_ms": 6600, "end_ms": 11400 }
      ]
    }
  ]
}
```

Ответ: `200 {"revision": 1, "status": "review_required"}`. Это же состояние возвращается после успешной правки ранее утверждённой встречи, но с новой ревизией. `POST /approve` принимает `{"base_revision": 1}`. Подтверждение возможно, только если все обнаруженные голоса проверены (`named` с именем или явно `unknown` без имени), все сохранённые пункты имеют валидные доказательства, а встреча находится в `review_required`. Пустые списки итогов и задач сами по себе не блокируют утверждение. Ответ — `Meeting` со статусом `approved`, той же `revision` и временем обновления. PDF синхронно строится при первом запросе `/export.pdf` после утверждения из этой ревизии и затем отдаётся из кэша; до подтверждения запрос возвращает `409`.

## Ошибки и приватность

Для доменных ошибок маршрутов встреч тело имеет вид `{"detail":"Нельзя экспортировать до утверждения","code":"review_required"}`. Код стабилен для клиента; текст предназначен для человека. `401` сохраняет уже реализованную в FastAPI форму `{"detail":"Missing bearer token"}` или `{"detail":"Invalid or expired access token"}`. `422` для маршрутов встреч нормализуется в `{"detail":"Некорректные данные запроса","code":"invalid_request"}` без отражения содержимого файла. `413` — `file_too_large`, `415` — `unsupported_media_type`; `409` — `invalid_state`, `stale_revision`, `review_required`, `source_expired`, `attempts_exhausted` или `cleanup_pending`; `503` — `queue_unavailable`, `gpu_unavailable`, `storage_failed`, `export_failed` или `delete_failed`. До готовности transcript/insights возвращают `409 invalid_state`; неполная проверка при approval — `409 review_required`. Retry сверх трёх попыток даёт `409 attempts_exhausted`; удаление при незавершённой очистке — `409 cleanup_pending`. Сервер не раскрывает traceback, локальные пути, содержимое приватных артефактов и токены. Неизвестный или чужой `meeting_id` всегда даёт `404 {"detail":"Встреча не найдена","code":"meeting_not_found"}`.

Удаление делает встречу недоступной для дальнейших `GET` после успешного `204`; при queued/processing или cleanup_status=pending возвращается 409, чтобы не потерять учёт временных данных GPU. При временной ошибке удаления возвращается `503`, а ресурс остаётся доступен владельцу для повторного запроса. JSON/TXT и аудио нельзя скачивать прямым URL. PDF отдаётся только через защищённый маршрут с `Content-Disposition: attachment` и безопасным именем, основанным на UUID встречи.

## Уточнение: NVIDIA и временное хранение

Все маршруты встреч выше принадлежат FastAPI приложения. Дашборд читает постоянные результаты из `data/` приложения. Собственная модель работает на NVIDIA-сервере команды; соединение только backend ↔ GPU, с серверным credential по TLS или защищённому туннелю. Browser не получает GPU credential.

Meeting дополнительно возвращает `source_available: boolean` (локальный временный upload существует и его TTL не истёк), `cleanup_status: pending|deleted|expired` и `temporary_expires_at: ISO8601|null` (фиксированный срок локального upload; `null` для примера без upload). Cleanup относится ко всем временным копиям всех попыток: `pending`, пока хотя бы одна копия не подтверждена как удалённая; `deleted`, если все удалены до TTL; `expired`, если все удалены и хотя бы одна по TTL. Один таймер без подтверждённого удаления не меняет cleanup на `expired`. Истечение TTL немедленно запрещает чтение/новую обработку временного payload даже при сбое физического удаления. Готовые постоянные результаты сохраняют свой статус и доступны при cleanup pending.

Начальный TTL — 24 часа от приёма на каждой машине. Повтор submit, polling, result, ACK и retry не продлевают срок существующего upload/job. Новая GPU-попытка имеет собственный deadline; локальный upload сохраняет исходный. После удаления/истечения локального исходника `POST /retry` возвращает `409 {"detail":"Загрузите запись повторно","code":"source_expired"}`. Таймкоды и цитаты сохраняются, серверное прослушивание удалённой записи недоступно.

### Внутренний GPU-контракт — planned

Все маршруты имеют префикс `/internal/v1`, требуют `Authorization: Bearer <service_token>` и не принимают пользовательский JWT. Тела ошибок — `{detail, code}` со статическим безопасным текстом, без исходного запроса, путей или traceback. `job_id` — UUID.

| Метод | Запрос | Успех / доменные ошибки |
| --- | --- | --- |
| `POST /jobs` | Multipart `audio` + `context` JSON; обязательный `Idempotency-Key: <meeting_id>:<attempt>`. | `202 JobV1` только после надёжного сохранения. Повтор того же ключа и содержимого: тот же job и текущий `JobV1`, без нового inference. Другое содержимое: `409 idempotency_conflict`. |
| `GET /jobs/{job_id}` | Нет тела. | `200 JobV1`, включая квитанцию после очистки. |
| `GET /jobs/{job_id}/result` | Нет тела. | `200 ResultBundleV1`; `409 result_not_ready` при queued/processing, `409 job_failed` при failed; `410 payload_deleted` после ACK, `410 source_expired` после TTL. |
| `POST /jobs/{job_id}/ack` | JSON `{result_hash}`. | `200 AckV1` только после удаления; `409 result_not_ready` при queued/processing, `409 job_failed` при failed; после TTL — правила квитанции ниже; `409 result_hash_mismatch` при неверном хеше; `503 cleanup_failed` при незавершённом удалении. |

Общие ошибки: `401 unauthorized`, `404 job_not_found`, `413 file_too_large`, `415 unsupported_media_type`, `422 invalid_request`, `503 queue_unavailable`. Неверные UUID, context, ключ или версия схемы — `422`. Внутренний `401` никогда не выдаётся браузеру как ошибка пользовательского входа; приложение показывает `gpu_unavailable`.

`context` содержит ровно поля примера ниже. `meeting_id`, `attempt` совпадают с ключом; остальные ограничения совпадают с публичной metadata. `audio_sha256` вычисляет coordinator по байтам audio, GPU проверяет его (`422 invalid_request` при расхождении). Идентичность запроса определяется хешем audio и всеми полями context; имя файла и multipart boundary не участвуют. Пример синтетический: audio hash соответствует тестовым байтам `abc`, не является допустимым аудиофайлом.

```json
{
  "schema_version": 1,
  "meeting_id": "81df6d39-16dd-4227-98b0-d45e531e091e",
  "attempt": 1,
  "meeting_date": "2026-09-23",
  "timezone": "Asia/Almaty",
  "participants": ["Алия", "Ернур"],
  "language_hint": "mixed",
  "audio_sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
}
```

`JobV1` возвращает ровно поля следующего примера. `status` — `queued|processing|completed|failed|expired`. `stage` — `ingesting|transcribing|diarizing|analyzing` только при processing, иначе `null`; `failure` — `null` либо `{code, message}`. `result_hash` доступен после completed и сохраняется в квитанции; до результата — `null`. `expires_at` фиксируется при первом приёме (UTC + 24 часа); `receipt_expires_at` — `null` до очистки и время успешной очистки + 7 суток после неё. ACK сохраняет `status: completed`; TTL переводит ещё не очищенный job в expired. Уже удалённая по ACK квитанция остаётся completed/deleted до receipt_expires_at, исходный expires_at её не меняет. Сбой физической очистки оставляет cleanup pending, даже при status expired.

```json
{
  "job_id": "c0b59629-8ca7-453d-812c-70e3c9e970ac",
  "status": "queued",
  "stage": null,
  "failure": null,
  "result_hash": null,
  "cleanup_status": "pending",
  "expires_at": "2026-09-24T09:00:10Z",
  "receipt_expires_at": null
}
```

### ResultBundleV1 и хеш

Bundle имеет обязательные поля `schema_version: 1`, `job_id`, `transcript: TranscriptV1`, `insights: InsightsV1`, `model_versions` и `result_hash`. Оба артефакта относятся к meeting_id отправленного context, имеют revision 0. `model_versions` содержит ровно `asr`, `diarization`, `analysis`: непустые строки с неизменяемым идентификатором модели/весов и версии pipeline (пример `fixture-asr@1`; это не реальные выбранные модели). Имена путей и токены в версии не входят.

`result_hash` — SHA-256 в виде 64 строчных hex-символов от UTF-8 JSON всего bundle **без** поля `result_hash`. Каноническая сериализация Python: `json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")`; JSON здесь использует только строки, целые числа, boolean, null, массивы и объекты. Никакой дополнительной Unicode-нормализации или завершающего перевода строки. Хеш проверяется до публикации и относится к исходному bundle; review его не изменяет. Версии моделей и хеш сохраняются в локальном manifest, публичные review-ответы не выдают правки за новый машинный bundle.

Полный минимальный синтетический bundle (пустые выводы допустимы; хеш вычислен по указанному правилу):

```json
{
  "schema_version": 1,
  "job_id": "c0b59629-8ca7-453d-812c-70e3c9e970ac",
  "transcript": {
    "schema_version": 1,
    "meeting_id": "81df6d39-16dd-4227-98b0-d45e531e091e",
    "revision": 0,
    "speakers": [],
    "segments": []
  },
  "insights": {
    "schema_version": 1,
    "meeting_id": "81df6d39-16dd-4227-98b0-d45e531e091e",
    "revision": 0,
    "summary": [],
    "action_items": []
  },
  "model_versions": {
    "asr": "fixture-asr@1",
    "diarization": "fixture-diarization@1",
    "analysis": "fixture-analysis@1"
  },
  "result_hash": "d25981e522342820a7f13aa73ef6ad1cd92f432fd06b5cd31fe46786fcb11a94"
}
```

### ACK, квитанция и восстановление

После сохранения проверенного bundle и JSON/TXT coordinator публикует manifest готовности последним, затем отправляет `{result_hash}`. Сбой локальной записи запрещает ACK: coordinator повторяет получение/сохранение того же job в processing/saving_results до TTL. Неисправимая ошибка сохранения переводит встречу в failed с публичным `failure.code: storage_failed`. Повторы submit/poll/result/ACK не увеличивают attempt; новая попытка inference создаётся только через разрешённый retry.

GPU сначала надёжно фиксирует принятый хеш и намерение очистки; payload больше не выдаётся. Удаляются audio, chunks, рабочие файлы и result. Только после подтверждённой очистки сохраняется квитанция и отправляется `200 AckV1`. При частичном удалении — `503 cleanup_failed`, GET /result уже возвращает `410 payload_deleted`, повтор ACK завершает очистку по сохранённому хешу. Backend удаляет свой upload после надёжного локального сохранения, независимо от доступности ответа ACK; общий cleanup остаётся pending до подтверждения обеих сторон.

Тело ACK содержит только `result_hash` из bundle. `AckV1` содержит ровно четыре поля ниже; cleanup_status допускает только `deleted|expired`. Пример для хеша bundle выше:

```json
{
  "job_id": "c0b59629-8ca7-453d-812c-70e3c9e970ac",
  "result_hash": "d25981e522342820a7f13aa73ef6ad1cd92f432fd06b5cd31fe46786fcb11a94",
  "cleanup_status": "deleted",
  "receipt_expires_at": "2026-09-30T09:05:00Z"
}
```

Квитанция без содержимого встречи хранит job_id, ключ и fingerprint запроса, result_hash (либо null, если результата не было), status, cleanup_status, expires_at, receipt_expires_at. До receipt_expires_at повтор ACK с тем же хешем возвращает ту же квитанцию без нового inference; другой хеш — `409 result_hash_mismatch`. После TTL известный хеш может быть подтверждён ответом `200 AckV1` с `cleanup_status: expired`, только если очистка действительно завершена; это подтверждение удаления, не получение результата. Если результата не было (`result_hash: null`), ACK даёт `410 source_expired`. При cleanup pending повторяется удаление; `503` никогда не означает успешное удаление.

Повтор submit по сохранённому ключу после ACK возвращает `202 JobV1` той же completed-задачи, для expired-задачи — `410 source_expired`; изменение содержимого при существующем ключе всегда `409 idempotency_conflict`. Гарантия дедупликации действует до receipt_expires_at. Клиент не переиспользует ключи и не отправляет исходник после локального TTL. После удаления квитанции GET/result/ACK возвращают `404 job_not_found`: backend не считает это подтверждением удаления, сохраняет cleanup pending для сверки оператором. Нельзя переводить pending в deleted по timeout или одному 404.

Перед TTL-очисткой GPU останавливает активный job и запрещает публикацию позднего результата. Истечение TTL независимо от ACK и доступности приложения. На restart coordinator продолжает submit/poll/result/ACK из manifest; повторное получение результата не запускает ML. Готовые локальные результаты и PDF остаются доступны при недоступном GPU и после TTL.

Пример безопасной внутренней ошибки `503` (не подтверждает удаление):

```json
{
  "detail": "Не удалось завершить очистку временных данных",
  "code": "cleanup_failed"
}
```

### Отображение внутренних ошибок приложением

`JobV1.failure` использует безопасные коды `invalid_audio|processing_failed|storage_failed|source_expired`; произвольный текст модели не пробрасывается. Public `Meeting.failure` имеет ту же форму `{code, message}` и допускает эти коды плюс `gpu_unavailable|invalid_result`. Невалидные схема, ссылки или хеш bundle дают `invalid_result` и запрещают ACK. Очистка и временное ожидание сети не снимают review/approval и не становятся ошибкой ML; потеря связи возобновляет ту же операцию. При окончательном сбое stage сбрасывается в null, безопасное сообщение объясняет причину.

| GPU / coordinator | Публичное поведение |
| --- | --- |
| queued / processing | Meeting processing; stage uploading_to_gpu, затем фактический ML-stage. |
| completed, bundle ещё не сохранён | processing / saving_results. |
| Bundle надёжно сохранён | review_required / null, независимо от ACK. |
| failed | failed / null, безопасный failure из разрешённого списка. |
| expired без локального результата | failed / null, failure.code source_expired; новая загрузка. |
| Timeout / HTTP 503 / внутренний 401 | Возобновить ту же операцию; при окончательной ошибке до готовности — failure.code gpu_unavailable. |
| ACK 503 / неизвестная квитанция | Готовый результат не меняется, cleanup_status pending. |

Контрактные проверки: примеры JSON и хеш; ссылки/границы evidence; оба assignee null и внешний assignee; approval с unknown и запрет unreviewed; повтор submit без inference и конфликт содержимого; сбой записи без ACK; повтор ACK после потерянного ответа; TTL во время processing; 404 после истечения квитанции без ложного успеха cleanup.
