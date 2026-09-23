# Hackalem Web

Next.js 16 interface with Supabase SSR authentication and a protected dashboard.
Meeting upload, review, approval and PDF screens are being integrated separately.
Live inference also requires the backend and deployed NVIDIA service.

```bash
npm ci
npm run dev
```

Copy `.env.local.example` to `.env.local`. The browser receives only the
Supabase project URL, publishable key, and public FastAPI URL. Never expose a
secret or privileged server key through `NEXT_PUBLIC_*`.

The request proxy refreshes Supabase sessions, server pages verify claims, and
the browser forwards the access token to FastAPI for business requests. The
meeting UI must show the `demo_fixture` source label before a prepared example
is used in the dedicated demo account. See the
[demo checklist](../docs/product/DEMO_FLOW.md).

Checks:

```bash
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

See the [root README](../README.md) for database setup, the auth smoke test, and
deployment instructions.
