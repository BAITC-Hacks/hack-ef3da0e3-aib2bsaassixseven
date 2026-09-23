# Hackathon Starter Design

## Goal

Prepare `tirke` as a starter for a hackathon team using Next.js, FastAPI, and Supabase. A developer should be able to add Supabase credentials, start both applications, create an account, sign in, open a protected dashboard, and call a protected FastAPI endpoint.

## Scope

The starter includes:

- Next.js App Router with TypeScript and Tailwind CSS
- Supabase email and password authentication
- Server-side session refresh and protected routes
- FastAPI with versioned routes, CORS, typed settings, and health checks
- JWT verification in FastAPI using the Supabase project JWKS endpoint
- Supabase access from FastAPI with the user's bearer token so Row Level Security applies
- A `profiles` migration, trigger, and owner-only RLS policies
- A protected dashboard that calls FastAPI
- Environment templates, local run commands, tests, and setup documentation

The starter excludes product-specific entities, OAuth providers, billing, background jobs, observability services, and production infrastructure. The team can add those after choosing the hackathon product.

## Architecture

The browser uses the Supabase client for sign-up, sign-in, sign-out, and session persistence. Next.js server code reads the authenticated session and redirects unauthenticated users away from protected pages.

The browser sends business requests to FastAPI with the Supabase access token in the `Authorization: Bearer` header. FastAPI verifies the JWT signature and claims against Supabase JWKS. A request-scoped Supabase client uses the public anon key and the same bearer token. Supabase then evaluates RLS policies for the signed-in user.

The browser does not receive the Supabase service-role key. The starter does not use a service-role key for user-facing requests.

## Repository Layout

```text
tirke/
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   ├── core/
│   │   ├── services/
│   │   └── main.py
│   ├── tests/
│   ├── .env.example
│   └── pyproject.toml
├── frontend/
│   ├── app/
│   │   ├── auth/
│   │   ├── dashboard/
│   │   └── login/
│   ├── components/
│   ├── lib/
│   └── .env.local.example
├── supabase/
│   └── migrations/
├── scripts/
├── .github/workflows/
├── .env.example
└── README.md
```

The existing `frontend/.git` history stays intact. This setup does not delete or rewrite it. Root-repository consolidation remains a separate decision because the parent directory has no Git repository.

## Backend Design

FastAPI exposes:

- `GET /health`: process health without authentication
- `GET /api/v1/me`: verified JWT claims and the user's profile

Pydantic Settings loads the Supabase URL, anon key, frontend origin, and JWT audience. The authentication dependency rejects missing, expired, malformed, or incorrectly issued tokens with a JSON `401` response. Application errors use a stable `{ "detail": "..." }` shape.

The protected route creates a Supabase client for one request and forwards the caller's access token. Tests replace network-facing dependencies, while JWT unit tests use generated signing keys and a local JWKS fixture.

## Frontend Design

Next.js uses `@supabase/ssr` for browser and server clients. The login page supports sign-in and registration. Auth callbacks exchange verification codes for sessions. Protected layouts redirect guests to `/login`; authenticated users can sign out from the dashboard.

The dashboard shows the current user's identity and the result of `GET /api/v1/me`. It handles loading, unauthorized, backend-unavailable, and success states without exposing tokens in rendered output.

The visual direction uses a compact technical cockpit: dark ink background, warm off-white surfaces, lime status accents, strong typography, a restrained grid texture, and clear focus states. Motion uses CSS and respects `prefers-reduced-motion`.

## Database Design

The initial migration creates `public.profiles` with:

- `id uuid primary key references auth.users(id) on delete cascade`
- `display_name text`
- `created_at timestamptz`
- `updated_at timestamptz`

A trigger inserts a profile after signup. RLS allows authenticated users to select and update their own row. The migration grants no cross-user access.

## Configuration and Secrets

Tracked environment files contain names and safe defaults only. Developers copy them to ignored local files and add:

- Supabase project URL
- Supabase anon or publishable key
- FastAPI base URL
- allowed frontend origin

The implementation keeps the service-role key out of the starter because the accepted request flow does not need it.

## Testing and Verification

Backend tests cover the health endpoint, rejected unauthenticated calls, accepted JWTs, invalid issuer or audience claims, and profile lookup behavior. Frontend tests cover the API client and auth-state UI. ESLint, TypeScript, Vitest, Pytest, and production builds run through documented commands and a CI workflow.

Supabase-dependent end-to-end checks require project credentials. The README provides a manual smoke test: sign up, confirm the email if required, open the dashboard, call FastAPI, sign out, and confirm that the protected route redirects to login.

## Completion Criteria

The starter is complete when:

1. Backend and frontend checks pass without credentials.
2. Both development servers start from documented commands.
3. Environment templates list each required value.
4. A configured Supabase project supports sign-up, sign-in, profile creation, protected API access, and sign-out.
5. No tracked file contains a secret.
