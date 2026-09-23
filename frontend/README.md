# Frontend

Next.js App Router frontend for the meeting auto-protocol system. This initial
commit establishes routes, module boundaries, runtime contracts, testing, and
CI-friendly commands. It intentionally does not implement the final visual
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
src/features/tasks/      Assignment contracts and UI
src/lib/api/             Transport and API-boundary helpers
src/lib/config/          Validated runtime configuration
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

See the repository-level `docs/PRD.md`, `docs/TRD.md`, and `AGENTS.md` before
implementing a feature.
