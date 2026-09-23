# Документация Hackalem

Hackalem превращает запись совещания на русском, казахском или смешанной речи
в проверяемый протокол: транскрипт, спикеры, саммари, поручения с источниками и
утверждённый PDF.

## Перед реализацией

Документы ниже описывают целевой MVP. Маршруты встреч, worker, локальное
хранилище и PDF ещё не реализованы, пока явно не отмечено обратное.

### Продукт

- [PRD](product/PRD.md) — проблема, границы MVP и критерии приёмки.
- [Целевые пользователи](product/TARGET_USERS.md) — персоны и их задачи.
- [Demo-flow](product/DEMO_FLOW.md) — сценарий показа за 3–5 минут.

### Техническая часть

- [TRD](technical/TRD.md) — технические требования и Definition of Done.
- [Архитектура](technical/ARCHITECTURE.md) — компоненты, данные и потоки.
- [API contract](technical/API_CONTRACT.md) — интерфейс FastAPI для frontend.

### Процесс разработки

- [MVP design spec](superpowers/specs/2026-09-23-meeting-intelligence-mvp-design.md)
  — единое архитектурное решение, которое команда проверяет перед планом
  реализации.
- `superpowers/plans/` — планы реализации после утверждения design spec.

## Источники истины

- Продуктовые приоритеты и критерии приёмки: `product/PRD.md`.
- Runtime-компоненты и технические ограничения: `technical/ARCHITECTURE.md` и
  `technical/TRD.md`.
- HTTP schemas и ошибки frontend/backend: FastAPI OpenAPI после реализации;
  до этого — `technical/API_CONTRACT.md` со статусом `planned`.
- ML schemas: versioned модели `TranscriptV1` и `InsightsV1`, описанные в
  архитектуре и будущем implementation plan.

Если документы расходятся, команда сначала обновляет design spec, затем PRD,
TRD/архитектуру и API contract в одном согласованном pull request.
