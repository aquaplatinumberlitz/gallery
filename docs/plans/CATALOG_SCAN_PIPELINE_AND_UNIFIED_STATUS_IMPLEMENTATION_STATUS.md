# Catalog Scan Pipeline and Unified Status Implementation Status

Last updated: 2026-06-21

Current milestone: Phase 1 complete

Next milestone: Phase 2 — v8→v9 migration, path helpers, job schema/indexes,
rebuild staging, and migration tests

SQLite schema version currently implemented: `PRAGMA user_version = 8`

## Verified Git Baseline

Phase 1 implementation commit:

```text
d0a2b736bac5eb96cad5071e4b0a7c513857f8a4
test: lock catalog status contract phase 1
```

The commit contains test and fixture changes only. It does not change runtime,
API, database, frontend production, or configuration behavior.

Verification completed before the implementation commit:

```text
./test.sh fast
641 backend tests passed; backend coverage 86.15%
394 frontend unit tests passed
frontend typecheck and production build passed
backend/frontend lint and format checks passed
```

The FastAPI lifecycle, Sass import, Rollup annotation, bundle-size, and `eval`
warnings emitted by the existing suite remain unchanged and are not Phase 1
failures.

## Phase Progress

| Phase | Status | Delivered |
| --- | --- | --- |
| 1. Contract fixtures and precedence tests | Complete | Shared v1 fixtures for all four required statuses; shared precedence vectors covering every summary state and locked edge cases; backend and frontend contract tests |
| 2. v9 migration and path/job schema | Not started | Next milestone |
| 3–10. Pipeline, triggers, rebuild, status, browse, frontend hard cut, cleanup/docs | Not started | Follow the master plan sequence |

## Phase 1 Delivered

Shared fixtures:

- `tests/fixtures/catalog_status/unified_status_v1.json` contains the four
  required `UnifiedStatus` examples from plan §12.
- `tests/fixtures/catalog_status/summary_precedence_v1.json` contains 18
  precedence scenarios covering every `SummaryState`.

Contract coverage includes:

- exact v1 fixture names and required top-level status fields;
- metadata count and issue-count invariants;
- inclusive 0–100 progress values;
- all ten precedence branches from plan §7.4;
- queued/running catalog and metadata work;
- active retry precedence over historical failure;
- cancelled catalog jobs ignored by semantic status;
- metadata-disabled completed and never-scanned scopes;
- failed rebuild with a previously usable catalog.

Backend and frontend tests consume the same JSON files. The precedence logic in
these tests is a test oracle only; the production shared status builder remains
Phase 6 work.

## Working Tree Note

At handoff, `frontend/src/lib/tanstack/README.md` has an unrelated pre-existing
user modification. It was intentionally excluded from the Phase 1 and status
commits.
