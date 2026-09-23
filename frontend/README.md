# Hackalem Web

Next.js 16 interface with Supabase SSR authentication and a protected dashboard.

```bash
npm ci
npm run dev
```

Copy `.env.local.example` to `.env.local`. The browser receives only the
Supabase project URL, publishable key, and public FastAPI URL. Never expose a
secret or privileged server key through `NEXT_PUBLIC_*`.

The request proxy refreshes Supabase sessions, server pages verify claims, and
the browser forwards the access token to FastAPI for business requests.

Checks:

```bash
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

See the [root README](../README.md) for database setup, the auth smoke test, and
deployment instructions.
