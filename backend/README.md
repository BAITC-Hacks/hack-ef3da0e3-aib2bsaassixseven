# Hackalem API

FastAPI service for authenticated business endpoints.

```bash
uv sync --locked --all-groups
uv run fastapi dev app/main.py --port 8000
```

The service exposes `/health`, `/docs`, `/api/v1/me`, and owner-scoped
`/api/v1/meetings` upload, polling, transcript, insights, review, approval and
PDF export endpoints. Protected requests require a Supabase access token in
`Authorization: Bearer <token>`. The exact payloads are in
[API_CONTRACT.md](../docs/technical/API_CONTRACT.md).

Copy `.env.example` to `.env` and use the same Supabase URL and publishable key
as the frontend. The API deliberately has no privileged server key: it forwards
the caller's token to PostgREST so database RLS remains active.

Configure `DATA_ROOT` for local artifacts. Live inference requires backend-only
`GPU_API_URL` and `GPU_API_TOKEN` pointing to the separately deployed NVIDIA
service; both must be set together. Without them, the API can still serve
already saved meetings, but new uploads remain queued. Never place audio,
private transcript data or service credentials in Git.

The prepared-example seeder is an explicit offline operation for a dedicated
demo owner and an audio SHA-256-pinned JSON fixture. The checked-in synthetic
fixture is only for tests; a consented, manually verified private fixture is
required for a stage demo. See [ML_EVALUATION.md](../docs/technical/ML_EVALUATION.md).

Checks:

```bash
uv run pytest -q
uv run ruff check .
uv run pyright
```

See the [root README](../README.md) for full setup and deployment instructions.
