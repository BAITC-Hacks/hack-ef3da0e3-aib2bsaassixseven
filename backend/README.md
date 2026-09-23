# Tirke API

FastAPI service for authenticated business endpoints.

```bash
uv sync --locked --all-groups
uv run fastapi dev app/main.py --port 8000
```

The service exposes `GET /health`, interactive docs at `/docs`, and the
protected `GET /api/v1/me` endpoint. Protected requests require a Supabase
access token in `Authorization: Bearer <token>`.

Copy `.env.example` to `.env` and use the same Supabase URL and publishable key
as the frontend. The API deliberately has no privileged server key: it forwards
the caller's token to PostgREST so database RLS remains active.

Checks:

```bash
uv run pytest -q
uv run ruff check .
uv run pyright
```

See the [root README](../README.md) for full setup and deployment instructions.
