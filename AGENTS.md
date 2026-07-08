# AI Agent Handoff

Status: Maintained

Last reviewed: 2026-07-08

This file is the repo working contract for AI agents and new automation-driven
contributors. Read it before planning or editing.

## Reading Order

1. `README.md` for product scope, quick start, API summary, and project shape.
2. `docs/README.md` for the current documentation map and source-of-truth rules.
3. `docs/ARCHITECTURE.md` for runtime ownership, routes, data flow, and state boundaries.
4. The domain reference for the task:
   - `docs/CONFIGURATION.md` for env vars, nginx, production/dev topology.
   - `docs/METADATA_PARSING.md` for parser support and normalized metadata.
   - `docs/UI_UX_GUIDELINES.md` for responsive, lightbox, and interaction rules.
   - `docs/THIRD_PARTY_LIBRARIES.md` for framework/library integration contracts.
   - `docs/testing/README.md` for test selection, perf, coverage, and debug helpers.

## Source Of Truth

- Current behavior lives in code, maintained docs, test contracts, and generated
  reports that say how to regenerate them.
- `docs/archived/` is historical. Do not treat it as current behavior unless
  code and maintained docs confirm it.
- `docs/research/` is upstream analysis and design context. Do not copy its API
  names, route names, or implementation status into current work without
  verifying against code.
- If `rg` finds conflicting answers, prefer non-archived maintained docs and the
  implementation. Update maintained docs when implementation changes.

## Working Rules

- Never revert user changes or unrelated local work. If a file is already dirty,
  inspect it and preserve changes outside your task.
- Keep edits scoped to the requested behavior. Do not refactor unrelated modules
  or churn generated reports unless the task requires it.
- Use `rg`/`rg --files` for search. Read the relevant code before changing it.
- Prefer existing local patterns, helpers, components, and test style over new
  abstractions.
- Use `apply_patch` for manual edits. Do not use destructive git commands unless
  the user explicitly asks for them.

## Runtime Ownership

- Backend is FastAPI with SQLite as the durable runtime store for catalog jobs,
  metadata index jobs, derivative jobs, integrity summaries, and startup
  recovery.
- Metadata lifecycle ownership is in `backend/indexer.py`; durable queue
  primitives live under `backend/metadata_store/`.
- Catalog scan and rebuild work is durable and library-scoped. Do not reintroduce
  removed legacy `/api/scan`, `/api/index/status`, or in-memory queue contracts.
- Frontend server state belongs in TanStack Query. Pinia owns UI/navigation
  state. TanStack Virtual/Table/Form are active where documented.
- Production serves the built SPA; nginx proxies `/api` to FastAPI. Vite is for
  development only.

## Test Minimums

- Docs-only changes: run `./test.sh docs`.
- Backend API, lifecycle, catalog, metadata, search, or derivative changes: run a
  targeted pytest for the touched area, then `./test.sh backend-api` when route
  contracts are affected.
- Frontend logic/composable/store changes: run the targeted Vitest file or
  `cd frontend && corepack pnpm run test:unit`.
- Frontend user-flow or responsive changes: run the relevant Playwright spec;
  use `./test.sh e2e` for broad UI changes.
- Lint-sensitive or cross-stack changes: run `./test.sh lint`; use
  `./test.sh fast` before handing off larger changes.
- Full release-style validation is `./test.sh full`.

## Docs Checklist

- API, route, env var, runtime, or ownership changes must update maintained docs.
- Test file additions/removals or changed guarantees must update
  `docs/testing/TEST_CATALOG.md`.
- Test count or coverage snapshots must be regenerated with the documented
  script, not edited by hand.
- Dependency role changes must update `docs/THIRD_PARTY_LIBRARIES.md`.
- Completed plans move to `docs/archived/`; active/proposed/blocked work stays
  in `docs/plans/`.
