<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Frontend working agreement

- Use App Router and TypeScript strict mode.
- Prefer server components. Add `"use client"` only for browser APIs, local
  interaction state, or client data orchestration.
- Route files compose feature modules; domain logic belongs in `src/features`.
- Use Sass modules for component styles and `src/styles` for shared tokens and
  mixins. Do not add Tailwind or runtime CSS-in-JS.
- Parse environment variables and untrusted API data with Zod.
- Keep the browser free of model inference, storage credentials, and secrets.
- All audio and transcript operations go through the self-hosted backend.
- Preserve source segment IDs and confidence/review states in assignment UI.
- User-interface chrome is English-only; meeting titles, participant names,
  transcripts, evidence, summaries, and assignments must preserve Russian,
  Kazakh, and mixed-language text.
- Do not infer visual requirements beyond `docs/design-references/README.md`.
- Avoid decorative gradients, glass panels, oversized radii, and generic KPI
  card grids. Build direct, accessible product interfaces.
- Add or update tests with feature contracts and state transitions.
- Before handoff, run `npm run lint`, `npm run typecheck`, `npm run test`, and
  `npm run build`.
