# Frontend

Next.js App Router frontend for the meeting auto-protocol system. This initial
scaffold establishes routes, Sass architecture, runtime contracts, testing,
and CI-friendly commands. It intentionally does not implement the final visual
design yet.

## Start

```bash
cp .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Structure

```text
src/app/                 Routes, layouts, metadata, global styles
src/components/layout/   Product shell and navigation
src/components/providers Global client-side providers
src/components/ui/       Reusable presentation primitives
src/features/meetings/   Meeting, participant, transcript contracts and UI
src/features/assignments/ Assignment/evidence contracts and review UI
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
