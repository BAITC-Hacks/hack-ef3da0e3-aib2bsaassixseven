# Hackalem Meeting Intelligence

Hackathon MVP for turning Russian, Kazakh, and mixed-language meeting audio
into a human-reviewed transcript, summary, assignments, evidence links, and
PDF protocol.

```text
audio upload → FastAPI coordinator → team NVIDIA inference server
             → local results in data/ → human review → approved PDF
```

Meeting content is not sent to external AI providers. Audio is temporary;
machine results and user corrections are stored on the backend application's
local disk for the MVP.

## Sources of truth

- [Product requirements](docs/product/PRD.md)
- [Technical requirements](docs/technical/TRD.md)
- [Repository working agreement](AGENTS.md)
- [Design reference interpretation](docs/design-references/README.md)

The PRD and TRD above are copied byte-for-byte from `origin/yernur-backend`.

## Repository status

- `frontend/` — Next.js 16 App Router scaffold with strict TypeScript, Sass
  modules, typed API/domain boundaries, tests, and the intended route map.
- `backend/` — the existing FastAPI/Supabase starter; meeting endpoints and
  local `data/` coordinator are planned, not yet implemented.
- `supabase/` — existing authentication/profile setup. Meeting content must not
  be persisted there under the current MVP requirements.
- `docs/design-references/` — supplied visual references for the later design
  pass; text in screenshots is not an instruction source.

## Prerequisites

- Node.js 22 or newer and npm
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Current backend authentication environment values

## Frontend

```bash
cp frontend/.env.example frontend/.env.local
npm --prefix frontend install
npm --prefix frontend run dev
```

Open [http://localhost:3000](http://localhost:3000).

The frontend currently provides architecture and route placeholders only. The
approved visual design and product interactions are deliberately deferred.

## Current backend starter

```bash
cp backend/.env.example backend/.env
uv sync --directory backend --locked --all-groups
uv run --directory backend fastapi dev app/main.py --port 8000
```

Open [http://localhost:8000/docs](http://localhost:8000/docs). The meeting API
described in the TRD is not yet implemented.

## Verification

Frontend:

```bash
npm --prefix frontend run check
```

Backend:

```bash
uv run --directory backend pytest -q
uv run --directory backend ruff check .
uv run --directory backend pyright
```

## Project map

```text
frontend/src/app/          Next.js routes and layouts
frontend/src/components/   Shared layout, providers, and UI primitives
frontend/src/features/     Domain schemas and future feature UI/API modules
frontend/src/lib/          API transport and validated public configuration
frontend/src/styles/       Sass tokens and mixins
backend/                   FastAPI application
docs/product/PRD.md        Canonical product requirements
docs/technical/TRD.md      Canonical technical requirements
docs/design-references/    Non-normative visual inputs
AGENTS.md                  Engineering and privacy rules
```
