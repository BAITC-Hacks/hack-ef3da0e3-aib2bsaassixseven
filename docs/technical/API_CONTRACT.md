# Контракт API встреч v1

## Статус и границы

Это **планируемый** контракт для загруженного локального аудио встречи. На текущей ветке реализованы авторизация Supabase и `GET /api/v1/me`; перечисленных ниже маршрутов встреч, worker и PDF-экспорта ещё нет. Контракт задаёт целевое поведение клиента и FastAPI для хакатонного демо. Потоковый захват живой встречи в v1 не входит.

Все маршруты ниже начинаются с `/api/v1`, принимают `Authorization: Bearer <supabase_access_token>` и доступны только владельцу встречи. FastAPI проверяет токен существующей зависимостью авторизации. Идентификатор владельца берётся из `sub` токена, не из тела запроса. Чужая встреча отвечает `404`, как и несуществующая. Токены, локальные пути аудио/JSON/TXT-артефактов и внутренние имена файлов никогда не входят в JSON, логи клиентских ошибок или PDF. Артефакты хранит сервер локально; отдельный worker получает задачу по `meeting_id` и `attempt`, записывает результат атомарно и сообщает состояние API. Доступ к артефактам и проверка владельца остаются на стороне FastAPI.

## Состояния и общие поля

`status` принимает только `queued`, `processing`, `review_required`, `approved`, `failed`:

| Состояние | Значение | Разрешённый следующий переход |
| --- | --- | --- |
| `queued` | Загрузка сохранена, задача ожидает worker. | `processing`, `failed` |
| `processing` | Worker выполняет текущую попытку. | `review_required`, `failed` |
| `review_required` | Расшифровка и выводы готовы; человек проверяет и редактирует. | `approved` |
| `approved` | Человек подтвердил текущую ревизию; PDF доступен. | `review_required` после сохранения новой правки через `PUT /review`. |
| `failed` | Загрузка или обработка завершилась ошибкой; сохранён безопасный код причины. | `queued` через `POST /retry` |

`stage` — отдельное поле: `ingesting`, `transcribing`, `diarizing`, `analyzing`, `exporting` либо `null`. Первые четыре значения допустимы только при `processing` и идут в указанном порядке; `exporting` допустим только при `approved` во время синхронного создания PDF по запросу `GET /export.pdf`. При выдаче уже созданного PDF этап остаётся `null`. В остальных случаях `stage = null`. Этап не является процентом прогресса. Ошибка формирования PDF не меняет `approved`: запрос экспорта возвращает ошибку, `stage` снова становится `null`, повторный запрос разрешён. При повторе обработки `attempt` увеличивается, `status` возвращается в `queued`, `stage = null`; результаты прежней попытки не доступны через текущие `/transcript` и `/insights`.

Каждая встреча имеет `id` (UUID), `title` (1–120 символов), `meeting_date` (дата `YYYY-MM-DD`), `timezone` (идентификатор IANA, например `Asia/Almaty`), `participants` (список имён), `recording_notice_confirmed` (`true`), `language_hint` (`auto|ru|kk|mixed`), `created_at`, `updated_at` (UTC ISO 8601), `attempt` (целое от 1), `revision` (целое от 0), `status`, `stage`, `source` и `failure`. Дата встречи интерпретируется в указанном часовом поясе; `created_at` и `updated_at` остаются UTC. `source.kind` равен `uploaded_audio` для обработки загруженного файла или `demo_fixture` для заранее рассчитанного примера. При `demo_fixture` обязательны `source.label = "Подготовленный пример · обработка выполнена заранее"` и `source.fixture_id`; этот источник должен быть заметен в UI и PDF. Исходный набор артефактов примера неизменяем, а правки пользователя хранятся отдельной ревизией. Подготовленный пример привязан к конкретному демонстрационному аудио и не подставляется для произвольной загрузки. `failure` равен `null` либо `{ "code": "processing_failed", "message": "Не удалось обработать запись" }` с безопасным для показа текстом.

Результаты `/transcript` и `/insights` доступны при `review_required` и `approved`. До `approved` они являются черновиком. Экспорт разрешён только после отдельного человеческого подтверждения. Успешная правка утверждённой встречи увеличивает `revision`, удаляет кэш PDF прежней ревизии и атомарно возвращает статус в `review_required`; новый экспорт требует повторного `POST /approve`. Неуспешная правка не меняет утверждение и кэш.

## Маршруты

Все строки таблицы имеют статус **планируется**; других реализаций в текущей ветке нет.

| Метод и маршрут | Назначение | Успех | Ошибки помимо `401`/`404` |
| --- | --- | --- | --- |
| `POST /meetings` | Создать встречу из `multipart/form-data`: `audio` + `metadata` JSON. | `202` + `Meeting` | `413` размер; `415` формат; `422` поля; `503` очередь недоступна |
| `GET /meetings?limit=20&cursor=...` | Список встреч владельца, новые первыми. `limit` 1–100; `cursor` непрозрачен. | `200` + `{items: Meeting[], next_cursor: string|null}` | `422` параметры |
| `GET /meetings/{meeting_id}` | Состояние для polling, включая `stage`, `attempt` и `failure`. | `200` + `Meeting` | `422` неверный UUID |
| `GET /meetings/{meeting_id}/transcript` | Сегменты с таймкодами и голосами. | `200` + `Transcript` | `409` результат ещё не готов |
| `GET /meetings/{meeting_id}/insights` | Итог и задачи с доказательствами. | `200` + `Insights` | `409` результат ещё не готов |
| `PUT /meetings/{meeting_id}/review` | Целиком заменить правки при `review_required` или `approved`; после правки статус `review_required`. | `200` + `{revision, status}` | `409` другое состояние или устаревшая ревизия; `422` неверные ссылки/поля |
| `POST /meetings/{meeting_id}/approve` | Подтвердить проверенную ревизию. | `200` + `Meeting` | `409` состояние, ревизия или неполная проверка |
| `GET /meetings/{meeting_id}/export.pdf` | Синхронно сформировать и кэшировать PDF утверждённой ревизии либо скачать кэш. | `200` + `application/pdf` | `409` не утверждено; `503` экспорт не удался |
| `POST /meetings/{meeting_id}/retry` | Повторить неудачную обработку того же аудио, максимум три попытки. | `202` + `Meeting` | `409` не `failed` или лимит попыток; `503` очередь недоступна |
| `DELETE /meetings/{meeting_id}` | Удалить встречу и локальные аудио/артефакты владельца; worker прекращает запись. | `204`, без тела | `503` удаление не завершено |

Для `POST /meetings` обязательны две части формы: `audio` — бинарный файл и `metadata` — JSON-объект с `Content-Type: application/json`. В `metadata` обязательны `title` (1–120 символов), `meeting_date` (`YYYY-MM-DD`), `timezone` (действительный идентификатор IANA), `participants` (массив из 0–30 уникальных имён по 1–100 символов) и `recording_notice_confirmed: true`; `language_hint` необязателен, по умолчанию `auto`, значения `auto|ru|kk|mixed`. Отметка `recording_notice_confirmed` фиксирует подтверждение пользователя об уведомлении участников, но сама по себе не доказывает его получение. `false`, отсутствие обязательного поля, неверная дата или часовой пояс дают `422`. Принимаются `.wav`, `.mp3`, `.m4a`, `.ogg`, `.webm` с проверкой содержимого, не только расширения; максимум 100 MiB. Загрузка атомарна: после `202` аудио сохранено и задача поставлена в очередь. Если этого не произошло, встреча не появляется в списке. Имя загруженного файла не используется как путь хранения. Создание `demo_fixture` не открывается публичным маршрутом: пример заранее подготовлен для демонстрационного аккаунта и возвращается обычными `GET`-маршрутами с меткой источника.

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
  "source": { "kind": "uploaded_audio" },
  "failure": null
}
```

`Transcript` содержит `meeting_id`, `revision`, `speakers` и `segments`. `speaker_id` — стабильная метка голоса в пределах встречи (`speaker_1`, `speaker_2`); `display_name` меняет человек. Каждый сегмент имеет стабильный UUID, `start_ms` и `end_ms` от начала аудио (`0 <= start_ms < end_ms`), исходный язык `ru|kk|unknown`, актуальный `text` и флаг `edited`. Таймкоды не зависят от отображения минут и секунд в UI.

```json
{
  "meeting_id": "81df6d39-16dd-4227-98b0-d45e531e091e",
  "revision": 0,
  "speakers": [
    { "speaker_id": "speaker_1", "display_name": null },
    { "speaker_id": "speaker_2", "display_name": null }
  ],
  "segments": [
    {
      "id": "76424ccb-f8d4-46f2-b7fc-81e888a01775",
      "start_ms": 6600,
      "end_ms": 11400,
      "speaker_id": "speaker_1",
      "language": "ru",
      "text": "Отправим смету в пятницу.",
      "edited": false
    }
  ]
}
```

`Insights` содержит `meeting_id`, `revision`, `summary` и `action_items`. Каждый пункт содержит UUID, непустой `text` и минимум одно `evidence` вида `{segment_id, start_ms, end_ms}`; интервал доказательства должен лежать внутри названного сегмента. У задачи также есть `assignee_speaker_id` (существующий голос либо `null`) и `due_date` (дата `YYYY-MM-DD` либо `null`). Пустые списки допустимы, когда запись не содержит надёжных выводов или задач; выдумывать их ради демо нельзя.

```json
{
  "meeting_id": "81df6d39-16dd-4227-98b0-d45e531e091e",
  "revision": 0,
  "summary": [
    {
      "id": "dc2c962f-8914-4fca-932d-5fbbcc4933cb",
      "text": "Команда согласовала отправку сметы в пятницу.",
      "evidence": [
        { "segment_id": "76424ccb-f8d4-46f2-b7fc-81e888a01775", "start_ms": 6600, "end_ms": 11400 }
      ]
    }
  ],
  "action_items": [
    {
      "id": "f9a6be39-bf63-4aba-98d7-b9fe11fd30db",
      "text": "Отправить смету",
      "assignee_speaker_id": "speaker_1",
      "due_date": null,
      "evidence": [
        { "segment_id": "76424ccb-f8d4-46f2-b7fc-81e888a01775", "start_ms": 6600, "end_ms": 11400 }
      ]
    }
  ]
}
```

`PUT /review` разрешён при `review_required` и `approved` и принимает полный текущий набор отображаемых имён, правок сегментов и выводов. `segment_edits` перечисляет только исправленные сегменты; пустой список снимает прежние текстовые/голосовые правки. `summary` и `action_items` заменяются целиком. Для новых пунктов клиент создаёт UUID; повтор запроса с тем же `base_revision` после успешного сохранения вернёт `409`, чтобы случайно не применить правку дважды. Поля `speaker_mappings` должны покрывать все обнаруженные голоса, допускается `display_name: null` до утверждения. Сервер проверяет существование всех голосов и сегментов, границы доказательств и принадлежность данных одной встрече. После успешного сохранения `revision` увеличивается на 1, статус становится `review_required`; если прежде было `approved`, кэш PDF удаляется в той же операции.

```http
PUT /api/v1/meetings/81df6d39-16dd-4227-98b0-d45e531e091e/review
Authorization: Bearer <supabase_access_token>
Content-Type: application/json

{
  "base_revision": 0,
  "speaker_mappings": [
    { "speaker_id": "speaker_1", "display_name": "Алия" },
    { "speaker_id": "speaker_2", "display_name": "Ернур" }
  ],
  "segment_edits": [
    { "segment_id": "76424ccb-f8d4-46f2-b7fc-81e888a01775", "text": "Отправим смету в пятницу.", "speaker_id": "speaker_1" }
  ],
  "summary": [
    {
      "id": "dc2c962f-8914-4fca-932d-5fbbcc4933cb",
      "text": "Команда согласовала отправку сметы в пятницу.",
      "evidence": [
        { "segment_id": "76424ccb-f8d4-46f2-b7fc-81e888a01775", "start_ms": 6600, "end_ms": 11400 }
      ]
    }
  ],
  "action_items": [
    {
      "id": "f9a6be39-bf63-4aba-98d7-b9fe11fd30db",
      "text": "Отправить смету",
      "assignee_speaker_id": "speaker_1",
      "due_date": null,
      "evidence": [
        { "segment_id": "76424ccb-f8d4-46f2-b7fc-81e888a01775", "start_ms": 6600, "end_ms": 11400 }
      ]
    }
  ]
}
```

Ответ: `200 {"revision": 1, "status": "review_required"}`. Это же состояние возвращается после успешной правки ранее утверждённой встречи, но с новой ревизией. `POST /approve` принимает `{"base_revision": 1}`. Подтверждение возможно, только если все обнаруженные голоса получили непустые имена, все сохранённые пункты имеют валидные доказательства, а встреча находится в `review_required`. Пустые списки итогов и задач сами по себе не блокируют утверждение. Ответ — `Meeting` со статусом `approved`, той же `revision` и временем обновления. PDF синхронно строится при первом запросе `/export.pdf` после утверждения из этой ревизии и затем отдаётся из кэша; до подтверждения запрос возвращает `409`.

## Ошибки и приватность

Для доменных ошибок маршрутов встреч тело имеет вид `{"detail":"Нельзя экспортировать до утверждения","code":"review_required"}`. Код стабилен для клиента; текст предназначен для человека. `401` сохраняет уже реализованную в FastAPI форму `{"detail":"Missing bearer token"}` или `{"detail":"Invalid or expired access token"}`. `422` для маршрутов встреч нормализуется в `{"detail":"Некорректные данные запроса","code":"invalid_request"}` без отражения содержимого файла. `413` — `file_too_large`, `415` — `unsupported_media_type`, `409` — `invalid_state`, `stale_revision` или `review_required`, `503` — `queue_unavailable`, `export_failed` или `delete_failed`. Сервер не раскрывает traceback, локальные пути, содержимое приватных артефактов и токены. Неизвестный или чужой `meeting_id` всегда даёт `404 {"detail":"Встреча не найдена","code":"meeting_not_found"}`.

Удаление делает встречу недоступной для дальнейших `GET` сразу после успешного `204`; worker обязан игнорировать поздний результат отменённой задачи. При временной ошибке удаления возвращается `503`, а ресурс остаётся доступен владельцу для повторного запроса. JSON/TXT и аудио нельзя скачивать прямым URL. PDF отдаётся только через защищённый маршрут с `Content-Disposition: attachment` и безопасным именем, основанным на UUID встречи.
