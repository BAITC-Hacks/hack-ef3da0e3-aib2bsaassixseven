# Hackathon Starter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working Next.js, FastAPI, and Supabase starter with email authentication, a protected dashboard, RLS-backed profiles, tests, and local setup instructions.

**Architecture:** Next.js stores Supabase sessions in cookies and refreshes them through the Next.js 16 request proxy. The browser sends the access token to FastAPI, FastAPI verifies the token through Supabase claims verification, and a request-scoped Supabase client forwards the same token to PostgREST so RLS applies.

**Tech Stack:** Node.js 22, Next.js 16.3, React 19.2, TypeScript 5, Tailwind CSS 4, `@supabase/ssr`, Vitest, Python 3.12, FastAPI, Pydantic Settings, supabase-py, pytest, Ruff, uv, PostgreSQL SQL migrations.

**Spec:** `docs/superpowers/specs/2026-09-22-hackathon-starter-design.md`

## Global Constraints

- The browser must never receive a Supabase secret or service-role key.
- FastAPI must forward the caller's access token for profile queries so Supabase RLS evaluates the signed-in user.
- Tests and production builds must run without real Supabase credentials.
- Tracked environment files contain names and safe placeholders only.
- Next.js 16 uses `proxy.ts`, not `middleware.ts`.
- Product-specific entities, OAuth providers, billing, jobs, external observability, and production infrastructure stay out of scope.
- The root Git repository owns `frontend/`, `backend/`, `supabase/`, documentation, and automation.

---

### Task 1: Workspace Baseline and FastAPI Health Endpoint

**Files:**
- Create: `.gitignore`
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/routes/__init__.py`
- Create: `backend/app/api/routes/health.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_health.py`
- Create: `backend/.env.example`
- Create: `backend/README.md`
- Generate: `backend/uv.lock`

**Interfaces:**
- Produces: `Settings`, `get_settings() -> Settings`, `create_app() -> FastAPI`, and `GET /health -> {"status": "ok", "service": "api"}`.
- Consumes: no application interfaces.

- [ ] **Step 1: Add root ignore rules**

Ignore `.env`, `.env.local`, Python virtual environments and caches, Next.js build output, Node dependencies, coverage output, and editor files. Explicitly keep `!.env.example` and `!.env.local.example`.

- [ ] **Step 2: Define the Python project**

Create `backend/pyproject.toml` with Python `>=3.12`, runtime dependencies `fastapi[standard]`, `pydantic-settings`, and `supabase`; add development dependencies `pytest`, `pytest-asyncio`, `httpx`, `ruff`, and `pyright`. Configure Ruff for Python 3.12 with an 88-character line and configure pytest with `asyncio_mode = "auto"`.

Run: `uv lock --directory backend`

- [ ] **Step 3: Write the failing health test**

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_reports_api_is_ready() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}
```

Run: `uv run --directory backend pytest tests/test_health.py -q`
Expected: FAIL because `app.main` does not exist.

- [ ] **Step 4: Implement settings and the app factory**

Use safe placeholders so the app and tests start without secrets:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Tirke API"
    frontend_origin: str = "http://localhost:3000"
    supabase_url: str = "https://example.supabase.co"
    supabase_publishable_key: str = "replace-with-publishable-key"
    supabase_jwt_audience: str = "authenticated"
```

`create_app()` must register CORS for `settings.frontend_origin`, include the health router, and expose module-level `app = create_app()` for Uvicorn.

- [ ] **Step 5: Verify health and static checks**

Run:

```powershell
uv run --directory backend pytest -q
uv run --directory backend ruff check .
uv run --directory backend pyright
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit the baseline**

```powershell
git add .gitignore backend
git commit -m "feat: scaffold FastAPI service"
```

---

### Task 2: Supabase JWT Verification Dependency

**Files:**
- Create: `backend/app/core/auth.py`
- Create: `backend/tests/test_auth.py`
- Modify: `backend/app/core/config.py`

**Interfaces:**
- Consumes: `Settings` and `get_settings()` from Task 1.
- Produces: `AuthenticatedUser(id: UUID, email: str | None, role: str)`, `TokenVerifier.verify(token: str) -> AuthenticatedUser`, `get_access_token() -> str`, and `get_current_user() -> AuthenticatedUser`.

- [ ] **Step 1: Write failing authentication tests**

Cover these behaviors with dependency overrides and an in-memory fake verifier:

```python
def test_missing_bearer_token_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Missing bearer token"}


def test_invalid_token_returns_401(client: TestClient) -> None:
    response = client.get(
        "/api/v1/me", headers={"Authorization": "Bearer invalid"}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired access token"}
```

Add verifier unit cases for missing `sub`, unexpected `iss`, and missing configured audience. Use a fake `get_claims()` response so tests do not call Supabase.

Run: `uv run --directory backend pytest tests/test_auth.py -q`
Expected: FAIL because the authentication module and protected route do not exist.

- [ ] **Step 2: Implement bearer extraction and claims validation**

Use `HTTPBearer(auto_error=False)`. `SupabaseTokenVerifier` creates an async Supabase client and calls `client.auth.get_claims(jwt=token)`. Normalize the returned claims into a plain mapping, then enforce:

```python
expected_issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
audiences = {audience} if isinstance(audience, str) else set(audience)
if claims.get("iss") != expected_issuer:
    raise InvalidTokenError
if settings.supabase_jwt_audience not in audiences:
    raise InvalidTokenError
user_id = UUID(str(claims["sub"]))
```

Map Supabase, UUID, issuer, audience, and expiration failures to the same `401` response. Do not include the rejected token or library error text in the response.

- [ ] **Step 3: Add a temporary identity-only `/api/v1/me` route**

Return the verified identity while Task 3 adds profile lookup:

```python
@router.get("/me")
async def read_me(user: Annotated[AuthenticatedUser, Depends(get_current_user)]):
    return {"id": str(user.id), "email": user.email, "role": user.role}
```

Register the API router under `/api/v1`.

- [ ] **Step 4: Verify the auth tests and backend checks**

Run:

```powershell
uv run --directory backend pytest -q
uv run --directory backend ruff check .
uv run --directory backend pyright
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit authentication**

```powershell
git add backend
git commit -m "feat: verify Supabase access tokens"
```

---

### Task 3: RLS-Aware Profile Service and Protected API

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/profile.py`
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/profiles.py`
- Create: `backend/app/api/routes/me.py`
- Create: `backend/tests/test_profiles.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: the bearer token and `AuthenticatedUser` from Task 2.
- Produces: `Profile(id: UUID, display_name: str | None, created_at: datetime, updated_at: datetime)`, `ProfileRepository.get_for_user(user_id: UUID, access_token: str) -> Profile | None`, and `GET /api/v1/me` with `user` and `profile` fields.

- [ ] **Step 1: Write failing route tests with a fake repository**

```python
def test_me_returns_identity_and_own_profile(authenticated_client: TestClient) -> None:
    response = authenticated_client.get(
        "/api/v1/me", headers={"Authorization": "Bearer valid"}
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "hacker@example.com"
    assert response.json()["profile"]["display_name"] == "Hacker"
```

Also assert that a missing profile returns `profile: null` and a Supabase/PostgREST failure returns `502` with `{"detail": "Supabase profile request failed"}`.

Run: `uv run --directory backend pytest tests/test_profiles.py -q`
Expected: FAIL because the profile service does not exist.

- [ ] **Step 2: Implement request-scoped RLS access**

`SupabaseProfileRepository.get_for_user()` must create an async client with the publishable key, call `client.postgrest.auth(access_token)`, and then query:

```python
response = await (
    client.table("profiles")
    .select("id,display_name,created_at,updated_at")
    .eq("id", str(user_id))
    .maybe_single()
    .execute()
)
```

Validate returned data with `Profile.model_validate`. Never use a service-role key.

- [ ] **Step 3: Replace the temporary `/me` response**

The final response shape is:

```json
{
  "user": {
    "id": "00000000-0000-0000-0000-000000000000",
    "email": "hacker@example.com",
    "role": "authenticated"
  },
  "profile": {
    "id": "00000000-0000-0000-0000-000000000000",
    "display_name": "Hacker",
    "created_at": "2026-09-22T00:00:00Z",
    "updated_at": "2026-09-22T00:00:00Z"
  }
}
```

- [ ] **Step 4: Run backend verification**

Run:

```powershell
uv run --directory backend pytest -q
uv run --directory backend ruff check .
uv run --directory backend pyright
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit profile access**

```powershell
git add backend
git commit -m "feat: add RLS-aware profile endpoint"
```

---

### Task 4: Supabase Profile Schema and RLS Policies

**Files:**
- Create: `supabase/config.toml`
- Create: `supabase/migrations/20260922000000_create_profiles.sql`
- Create: `supabase/tests/profiles_rls.sql`

**Interfaces:**
- Consumes: `auth.users`, `auth.uid()`, and the `authenticated` Postgres role.
- Produces: `public.profiles`, `public.handle_new_user()`, `public.set_updated_at()`, and owner-only select/update policies.

- [ ] **Step 1: Write the SQL behavior test**

Use a transaction and pgTAP assertions to confirm RLS is enabled, the authenticated role has select/update grants, and both policy predicates equal `(select auth.uid()) = id`. Roll the transaction back after the assertions.

Run: `supabase test db`
Expected before migration: FAIL because `public.profiles` does not exist. If the local Supabase CLI is unavailable, retain this expected failure in the task notes and validate the migration with `supabase db lint` after installing the CLI.

- [ ] **Step 2: Create the migration**

Create `public.profiles` with `id`, `display_name`, `created_at`, and `updated_at`. Add:

```sql
alter table public.profiles enable row level security;

create policy "Users can view their own profile"
on public.profiles for select
to authenticated
using ((select auth.uid()) = id);

create policy "Users can update their own profile"
on public.profiles for update
to authenticated
using ((select auth.uid()) = id)
with check ((select auth.uid()) = id);
```

Grant `select, update` to `authenticated`. The signup trigger inserts `new.id` and reads `display_name` from `new.raw_user_meta_data` when present. Use `security definer set search_path = ''` and schema-qualified table names in trigger functions.

- [ ] **Step 3: Validate migration syntax and policies**

Run:

```powershell
supabase db reset
supabase db lint
supabase test db
```

Expected: reset succeeds, lint reports no errors, and pgTAP passes.

- [ ] **Step 4: Commit the database contract**

```powershell
git add supabase
git commit -m "feat: add profile schema and RLS"
```

---

### Task 5: Next.js Supabase SSR Authentication

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/.env.local.example`
- Create: `frontend/lib/env.ts`
- Create: `frontend/lib/supabase/client.ts`
- Create: `frontend/lib/supabase/server.ts`
- Create: `frontend/lib/supabase/proxy.ts`
- Create: `frontend/proxy.ts`
- Create: `frontend/app/auth/actions.ts`
- Create: `frontend/app/auth/confirm/route.ts`
- Create: `frontend/app/login/page.tsx`
- Create: `frontend/components/auth-form.tsx`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/vitest.setup.ts`
- Create: `frontend/lib/env.test.ts`
- Create: `frontend/app/auth/actions.test.ts`

**Interfaces:**
- Consumes: Supabase URL and publishable key from public environment values.
- Produces: `createBrowserSupabaseClient()`, `createServerSupabaseClient()`, `updateSession(request)`, `signIn(previousState, formData)`, `signUp(previousState, formData)`, and `signOut()`.

- [ ] **Step 1: Install auth and test dependencies**

Run:

```powershell
npm --prefix frontend install @supabase/ssr @supabase/supabase-js
npm --prefix frontend install --save-dev vitest jsdom @vitejs/plugin-react @testing-library/react @testing-library/jest-dom
```

Add scripts: `test`, `test:watch`, and `typecheck`.

- [ ] **Step 2: Write failing environment and auth-action tests**

The environment test must prove missing values return safe placeholders and configured values pass through unchanged. Auth-action tests mock the server Supabase client and assert:

```typescript
expect(supabase.auth.signInWithPassword).toHaveBeenCalledWith({
  email: "hacker@example.com",
  password: "eightchars",
});
```

Also cover short passwords, Supabase errors, sign-up with `emailRedirectTo`, and sign-out.

Run: `npm --prefix frontend test -- --run`
Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement browser and server clients**

`server.ts` must call `await cookies()` and pass `getAll`/`setAll` to `createServerClient`. The write path catches cookie mutation errors from Server Components because the request proxy handles refreshes.

`proxy.ts` must create a response, forward all Supabase cookie writes to both the request and response, apply response headers supplied by current `@supabase/ssr`, and call `supabase.auth.getClaims()` before route decisions. Redirect unauthenticated `/dashboard` requests to `/login` and authenticated `/login` requests to `/dashboard`.

- [ ] **Step 4: Implement auth actions and confirmation**

Use server actions for sign-in, sign-up, and sign-out. Validate email with the browser-supported email input and enforce password length `>= 8` on the server. Return serializable state for expected Supabase errors. Redirect on success.

The callback route supports both `code` via `exchangeCodeForSession(code)` and `token_hash` plus `type` via `verifyOtp`. Redirect failures to `/login?error=confirmation`.

- [ ] **Step 5: Build an accessible login page**

The form requires labeled email and password controls, a visible submit state, an `aria-live="polite"` error region, sign-in and registration actions, keyboard focus rings, and a link back to the landing page.

- [ ] **Step 6: Verify frontend auth**

Run:

```powershell
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: all commands exit 0 without real Supabase credentials.

- [ ] **Step 7: Commit authentication UI**

```powershell
git add frontend
git commit -m "feat: add Supabase SSR authentication"
```

---

### Task 6: Protected Dashboard and FastAPI Client

**Files:**
- Create: `frontend/lib/api.ts`
- Create: `frontend/lib/api.test.ts`
- Create: `frontend/app/dashboard/page.tsx`
- Create: `frontend/components/api-status.tsx`
- Create: `frontend/components/api-status.test.tsx`
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/app/globals.css`

**Interfaces:**
- Consumes: browser Supabase session, `GET /api/v1/me`, and `signOut()`.
- Produces: `fetchCurrentUser(accessToken, fetcher?) -> Promise<MeResponse>`, public landing page, protected dashboard, and API status states.

- [ ] **Step 1: Write failing API client tests**

```typescript
it("sends the Supabase token to FastAPI", async () => {
  const fetcher = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(meFixture), { status: 200 }),
  );

  await fetchCurrentUser("access-token", fetcher);

  expect(fetcher).toHaveBeenCalledWith(
    "http://localhost:8000/api/v1/me",
    expect.objectContaining({
      headers: { Authorization: "Bearer access-token" },
    }),
  );
});
```

Cover `401` as `UnauthorizedApiError`, non-OK responses as `ApiError`, and malformed JSON as `ApiError`.

Run: `npm --prefix frontend test -- --run lib/api.test.ts`
Expected: FAIL because `fetchCurrentUser` does not exist.

- [ ] **Step 2: Implement the typed API client**

Define `MeResponse` with user and nullable profile fields. Read `NEXT_PUBLIC_API_URL` with `http://localhost:8000` as the safe default. Set `cache: "no-store"` and do not log the access token.

- [ ] **Step 3: Write failing dashboard state tests**

Mock the browser Supabase client and API client. Assert loading copy, successful profile rendering, unauthorized copy with a login link, and backend-unavailable copy with a retry button.

Run: `npm --prefix frontend test -- --run components/api-status.test.tsx`
Expected: FAIL because `ApiStatus` does not exist.

- [ ] **Step 4: Implement protected dashboard data flow**

The server page calls `supabase.auth.getClaims()` and redirects missing claims to `/login`. It passes only the user's email to presentational markup. `ApiStatus` runs in the browser, gets the current session token, calls FastAPI, and keeps the token out of state rendered to the DOM.

- [ ] **Step 5: Apply the technical-cockpit visual system**

Replace the Create Next App screen. Define CSS tokens for ink, paper, lime, cyan, borders, radii, shadows, spacing, and motion. Use a grid-texture background, asymmetric status rail, mono labels, responsive cards, visible focus styles, one `h1` per page, and a reduced-motion override. Keep all copy product-neutral under the name "Tirke Launchpad".

Update metadata to `Tirke Launchpad` with the description `Next.js, FastAPI, and Supabase hackathon starter`.

- [ ] **Step 6: Verify dashboard and production build**

Run:

```powershell
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: all commands exit 0 and build output includes `/`, `/login`, `/auth/confirm`, and `/dashboard`.

- [ ] **Step 7: Commit the dashboard**

```powershell
git add frontend
git commit -m "feat: add protected hackathon dashboard"
```

---

### Task 7: Unified Developer Workflow, CI, and Documentation

**Files:**
- Create: `.env.example`
- Create: `scripts/dev.ps1`
- Create: `scripts/dev.sh`
- Create: `.github/workflows/ci.yml`
- Create: `README.md`
- Modify: `frontend/README.md`
- Modify: `backend/README.md`

**Interfaces:**
- Consumes: frontend and backend commands from Tasks 1 through 6.
- Produces: one documented setup path, cross-platform development launchers, and CI checks.

- [ ] **Step 1: Add environment templates**

Document these mappings without secrets:

```dotenv
# frontend/.env.local
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your-publishable-key
NEXT_PUBLIC_API_URL=http://localhost:8000

# backend/.env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=your-publishable-key
SUPABASE_JWT_AUDIENCE=authenticated
FRONTEND_ORIGIN=http://localhost:3000
```

- [ ] **Step 2: Add cross-platform launch scripts**

`scripts/dev.ps1` starts `uv run --directory backend fastapi dev app/main.py --port 8000` and `npm --prefix frontend run dev` as child processes, forwards Ctrl+C, and stops both children on exit. `scripts/dev.sh` uses traps to provide the same cleanup behavior.

- [ ] **Step 3: Add CI**

GitHub Actions uses Node 22 and Python 3.12. Backend job runs `uv sync --directory backend --locked --all-groups`, pytest, Ruff, and Pyright. Frontend job runs `npm ci`, Vitest, ESLint, TypeScript, and `next build`. Supply the safe placeholder public environment values during the frontend build.

- [ ] **Step 4: Write the root README**

Document prerequisites, Supabase project creation, environment file copying, migration application, one-command and two-terminal startup, URLs, test commands, auth smoke test, directory map, security boundary, and deployment notes for Vercel plus any ASGI host. State that developers must use matching Supabase URL and publishable key values in both applications.

- [ ] **Step 5: Run the complete verification matrix**

Run:

```powershell
uv sync --directory backend --locked --all-groups
uv run --directory backend pytest -q
uv run --directory backend ruff check .
uv run --directory backend pyright
npm --prefix frontend ci
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
git status --short
```

Expected: each check exits 0. `git status --short` lists only intentional uncommitted plan-tracking changes, if any.

- [ ] **Step 6: Scan tracked content for likely secrets**

Run:

```powershell
git grep -n -E 'service_role|SUPABASE_SECRET_KEY|eyJ[A-Za-z0-9_-]{20,}' -- ':!package-lock.json' ':!uv.lock'
```

Expected: no matches in tracked application or documentation files.

- [ ] **Step 7: Commit workflow and docs**

```powershell
git add .env.example .github README.md scripts frontend/README.md backend/README.md
git commit -m "docs: add hackathon developer workflow"
```

## Plan Self-Review

- Every spec requirement maps to at least one task.
- Tasks 1 through 3 and 5 through 6 start with a failing automated test.
- Task 4 starts with a failing database behavior test.
- Function and type names stay consistent between producers and consumers.
- Real Supabase credentials are unnecessary for unit tests and builds.
- The implementation uses Next.js 16 `proxy.ts` and Supabase's current claims verification flow.
