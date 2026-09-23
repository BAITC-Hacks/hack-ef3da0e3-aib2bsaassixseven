# Frontend

Next.js App Router frontend for the meeting auto-protocol system. It includes
Supabase authentication, a local demo session, Sass architecture, runtime
contracts, testing, and the complete MVP workspace flow.

## Start

```bash
cp .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

For signed-in meetings, set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to
the browser-reachable **FastAPI application** origin (for example,
`http://localhost:8000`). The client adds `/api/v1` automatically. Use the same
Supabase URL and publishable key as `backend/.env`; the backend must allow the
frontend's exact origin with `FRONTEND_ORIGIN`. Do not put the NVIDIA service
address or token in frontend variables.

Choose **Continue in demo mode** on the login page at any time, with or without
Supabase credentials. The demo covers creating and processing a meeting, reviewing
the transcript and assignments, approval, sharing/printing, task tracking,
deletion, and profile editing. Demo changes remain intentionally in-memory and
never call the backend. Signed-in sessions use the authenticated meeting API.

## Structure

```text
src/app/                 Routes, layouts, metadata, global styles
src/components/layout/   Product shell and navigation
src/components/providers Global client-side providers
src/components/ui/       Reusable presentation primitives
src/features/auth/       Supabase and demo authentication flow
src/features/dashboard/  Workspace overview
src/features/meetings/   Meeting creation, lists, and review UI
src/features/assignments/ Task list and assignment contracts
src/features/profile/    User settings
src/features/demo-workspace/ Temporary UI state adapter for backend handoff
src/lib/api/             Transport and API-boundary helpers
src/lib/config/          Validated runtime configuration
src/styles/              Sass tokens and reusable mixins
src/test/                Test environment setup
```

Keep business rules in feature modules or the backend. Route files should
compose features rather than becoming large implementation files.

## Quality gates

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

See `docs/product/PRD.md`, `docs/technical/TRD.md`, and the repository-level
`AGENTS.md` before implementing a feature.
