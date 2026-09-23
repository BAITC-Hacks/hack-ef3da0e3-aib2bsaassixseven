# Hackalem

AIB2BSaaSSixSeven hackathon team repository.

A hackathon-ready full-stack starter built with Next.js 16, FastAPI, and
Supabase. It includes email authentication, a protected dashboard, verified
JWTs, user-scoped database access, Row Level Security, tests, and CI.

## How the request stays user-scoped

```text
Browser → Next.js / Supabase Auth → FastAPI → Supabase PostgREST → PostgreSQL
              session cookie          JWT       same caller JWT        RLS
```

Next.js owns the Supabase session. The browser sends its access token to
FastAPI, which verifies the token and forwards that same token to Supabase.
PostgreSQL therefore evaluates RLS as the signed-in user. No service-role key
is used by the application.

## Prerequisites

- Node.js 22 and npm
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- A [Supabase](https://supabase.com/dashboard) project
- Supabase CLI and Docker Desktop only if you want the local database stack

## 1. Configure Supabase

Create a project, then copy these two values from **Project Settings → API**:

- Project URL
- Publishable key (the legacy `anon` key also works)

Use the same project URL and publishable key in both applications. Never put a
Supabase secret or privileged server key in a `NEXT_PUBLIC_*` variable.

For a hosted project, apply the database migration:

```bash
npx supabase link --project-ref your-project-ref
npx supabase db push
```

In **Authentication → URL Configuration**, set the site URL to the frontend
origin and allow the confirmation callback. For local development:

```text
Site URL:     http://localhost:3000
Redirect URL: http://localhost:3000/auth/confirm
```

## 2. Create local environment files

PowerShell:

```powershell
Copy-Item frontend/.env.local.example frontend/.env.local
Copy-Item backend/.env.example backend/.env
```

Bash:

```bash
cp frontend/.env.local.example frontend/.env.local
cp backend/.env.example backend/.env
```

Replace the placeholder project URL and publishable key in both files. The root
[`.env.example`](.env.example) lists every required variable in one place.

## 3. Install dependencies

```bash
uv sync --directory backend --locked --all-groups
npm --prefix frontend ci
```

## 4. Start the application

One command on Windows:

```powershell
./scripts/dev.ps1
```

One command on macOS or Linux:

```bash
./scripts/dev.sh
```

Or use two terminals:

```bash
uv run --directory backend fastapi dev app/main.py --port 8000
npm --prefix frontend run dev
```

Open:

- Web app: [http://localhost:3000](http://localhost:3000)
- FastAPI docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health check: [http://localhost:8000/health](http://localhost:8000/health)

## Local Supabase

Docker Desktop must be running.

```bash
npx supabase start
npx supabase db reset
npx supabase db lint
npx supabase test db
```

`supabase db reset` applies the migration and recreates the `profiles` table,
signup trigger, and owner-only RLS policies.

## Test everything

Backend:

```bash
uv run --directory backend pytest -q
uv run --directory backend ruff check .
uv run --directory backend pyright
```

Frontend:

```bash
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Database:

```bash
npx supabase db lint
npx supabase test db
```

## Authentication smoke test

1. Open `/login` and create an account with a password of at least eight
   characters.
2. Follow the confirmation link in the email.
3. Confirm `/dashboard` opens and shows the protected API as online.
4. Sign out and confirm `/dashboard` redirects back to `/login`.
5. In Supabase Table Editor, confirm the new user has exactly one `profiles`
   row with the same UUID.

If the dashboard says FastAPI is offline, check port `8000` and `SUPABASE_URL`.
If the session is rejected, ensure both apps use the same Supabase project.

## Project map

```text
backend/                  FastAPI application and Python tests
frontend/                 Next.js application and component tests
supabase/migrations/      PostgreSQL schema and RLS policies
supabase/tests/           pgTAP database contract tests
scripts/                  Cross-platform development launchers
.github/workflows/ci.yml  Backend and frontend CI
docs/superpowers/         Architecture spec and implementation plan
```

## Deployment

Deploy `frontend/` to Vercel (or another Next.js host) and `backend/` to an ASGI
host. Configure the same Supabase project in both deployments, set
`FRONTEND_ORIGIN` to the public frontend URL, set `NEXT_PUBLIC_API_URL` to the
public FastAPI URL, and add the production confirmation callback to Supabase.

Run `npx supabase db push` against the intended project before the first release.
Keep CORS restricted to the real frontend origin and keep privileged keys out
of the browser and source control.
