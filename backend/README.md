# Tirke API

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

Set `FRONTEND_ORIGIN` to the exact browser origin of the Next.js app, including
its scheme and port but no path (for local development, `http://localhost:3000`).
This is the allowed CORS origin. `DATA_ROOT=data` stores meeting artifacts in
`backend/data` when the backend is launched with the command above; use an
absolute private path if it runs from another working directory.

`ffprobe` and `ffmpeg` must be installed on the backend host. Audio uploads are
validated locally; MP4, MOV, MKV, and video-bearing WebM uploads are converted
locally to a private audio-only M4A before the NVIDIA service is contacted.

Live inference requires backend-only `GPU_API_URL` and `GPU_API_TOKEN` in
`backend/.env`; set both together. `GPU_API_URL` is the base URL of the team's
authenticated inference HTTP API. The backend appends `/internal/v1/jobs` and
the other [GPU API paths](../docs/technical/API_CONTRACT.md) to it. Use HTTPS
or a protected tunnel between the backend and NVIDIA server. The supplied
screenshots show an HTTPS link forwarding to port 8888 (Jupyter) and a TCP link
forwarding to port 22 (SSH). Neither link establishes an inference HTTP API;
obtain the deployed API's reachable base URL before configuring it. Keep the
service token out of the frontend and Git. Without these settings, the API can
still serve saved meetings, but new uploads remain queued. Never place audio
or private transcript data in Git.

### SSH tunnel to the NVIDIA host

If the inference API listens only on the NVIDIA host, run the tunnel on the
**same machine as this backend**. The SSH address shown in the screenshot is
`global.prd.ga.run.brev.nvidia.com` on port `26330` (forwarded to SSH port 22).
You still need the SSH username and the port on which the inference HTTP API
listens inside that host. From the repository root, replace the two uppercase
placeholders after the team confirms that port:

```bash
GPU_SSH_HOST=global.prd.ga.run.brev.nvidia.com \
GPU_SSH_PORT=26330 \
GPU_SSH_USER=YOUR_SSH_USER \
GPU_INFERENCE_PORT=YOUR_HTTP_PORT \
backend/scripts/gpu-ssh-tunnel.sh
```

Keep that command running. In `backend/.env` set `GPU_API_URL=http://127.0.0.1:8765`
and set `GPU_API_TOKEN` to the service token configured **on the inference API**.
The tunnel binds only to loopback on the backend host; the service still checks
its bearer token. The Jupyter HTTPS link redirects unauthenticated requests to
the Brev login and cannot replace this backend-to-backend channel. If the
inference API has not been deployed, a tunnel alone does not process recordings.

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
