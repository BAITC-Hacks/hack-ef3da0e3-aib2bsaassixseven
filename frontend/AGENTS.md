<!-- BEGIN:nextjs-agent-rules -->

# Next.js version awareness

This project may use Next.js APIs newer than training data. After dependencies
are installed, read the relevant local guide in `node_modules/next/dist/docs/`
before changing framework conventions. Follow deprecation notices and preserve
the async request APIs used by the installed version.

<!-- END:nextjs-agent-rules -->

# Frontend working agreement

- Use App Router and TypeScript strict mode.
- Prefer server components. Add `"use client"` only for browser APIs, local
  interaction state, or client data orchestration.
- Route files compose feature modules; domain logic belongs in `src/features`.
- Parse environment variables and untrusted API data with Zod.
- Keep the browser free of model inference, storage credentials, and secrets.
- All audio and transcript operations go through the self-hosted backend.
- Preserve source segment IDs and confidence/review states in assignment UI.
- User-facing product copy is Russian-first and must support Kazakh text.
- Do not infer visual requirements beyond `docs/design-references/README.md`.
- Avoid decorative gradients, glass panels, oversized radii, and generic KPI
  card grids. Build direct, accessible product interfaces.
- Add or update tests with feature contracts and state transitions.
- Before handoff, run `npm run lint`, `npm run typecheck`, `npm run test`, and
  `npm run build`.
