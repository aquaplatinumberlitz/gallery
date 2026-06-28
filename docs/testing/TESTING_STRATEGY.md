# Testing Strategy

Status: Maintained

Last verified against `.github/workflows/ci.yml` and `test.sh`: 2026-06-27.

## Stack

- **Backend**: Python FastAPI + SQLite — test pyramid (many unit tests, fewer integration tests, very few E2E tests)
- **Frontend**: Vue 3 + TypeScript — test trophy (static > unit/integration > E2E)

## Test Matrix

| Layer                          | Tool                 |        Environment         |        PR/push CI        |       Nightly        | Goal                    |
| ------------------------------ | -------------------- | :------------------------: | :----------------------: | :------------------: | ----------------------- |
| Static                         | Ruff/ESLint/Prettier |            none            |        ✅ `lint`         | N/A (not configured) | syntax/style            |
| Backend unit + API integration | pytest               |       SQLite/temp FS       |      ✅ `test:unit`      | N/A (not configured) | backend behavior        |
| Frontend unit/component        | Vitest + V8 coverage |           jsdom            |      ✅ `test:unit`      | N/A (not configured) | frontend logic/behavior |
| Frontend build/typecheck       | vue-tsc/Vite         |     build environment      |      ✅ `test:unit`      | N/A (not configured) | types/build             |
| Browser integration            | Playwright           |          Chromium          | ✅ full suite, 4 shards  | N/A (not configured) | critical UI workflows   |
| Full-stack E2E                 | Playwright + FastAPI | deterministic temp fixture |      ✅ `test:e2e`       | N/A (not configured) | system wiring           |
| Perf                           | Playwright           | deterministic temp fixture | ✅ `test:perf`, 1 worker | N/A (not configured) | performance budgets     |
| Diagnostic E2E (env-gated)     | Playwright           | deterministic temp fixture |            —            | N/A (not configured) | env-gated diagnostics   |

## Test Selection Policy

- **Push/PR CI**: full-codebase `lint`, `test:unit`, four `test:e2e` shards, and `test:perf`.
- **`test:e2e` CI selection**: every top-level `frontend/tests/e2e/*.spec.ts` spec. Env-gated diagnostic files are collected by Playwright but skipped unless their gate variable is set. Playwright shards the suite across four parallel jobs.
- **`test:perf` CI selection**: every spec under `frontend/tests/e2e/perf/`, with one worker and a separate deterministic fixture.
- **Diagnostic env gates**: `metadata-performance.spec.ts` requires `GALLERY_PERF_METADATA=1` or `GALLERY_PERF_METADATA_STRICT=1`; `gallery-no-reload-real-backend.spec.ts` requires `GALLERY_E2E_DIAGNOSTICS=1`. These are skipped by default `test:e2e` CI shards.
- **Functional E2E coverage instrumentation is disabled** so browser behavior and timing are not distorted. Frontend coverage comes from Vitest/V8.
- **Nightly**: N/A (not configured).
- **WebKit smoke**: N/A.
- **Local parity**: CI test execution delegates to `./test.sh`; `./test.sh full` runs the same full layers sequentially, including docs/test-catalog checks. `./test.sh fast` is the fast lint/unit/build gate.

## Coverage Baselines

- **Backend**: 90% line coverage (enforced in CI and `./test.sh unit`)
- **Frontend**: Vitest/V8 coverage is uploaded from `test:unit`; `coverage:unit:check` enforces repository ratchet thresholds, while per-area frontend thresholds are advisory.

## Browser Matrix

- **PR CI**: Chromium (fastest)
- **Nightly**: N/A (not configured)
- **WebKit smoke**: N/A

## Flaky Test Policy

- There is no automated quarantine or auto-created GitHub issue flow in the current workflow.
- Flaky tests must be triaged; do not describe them as automatically skipped unless a workflow/config actually does that.

## When to Use What

| What you want to test                 | Use                                                      |
| ------------------------------------- | -------------------------------------------------------- |
| Pure function logic                   | Vitest unit (frontend) / pytest unit (backend)           |
| Store / composable behavior           | Vitest (jsdom)                                           |
| Vue component rendering + interaction | Playwright (browser integration)                         |
| API endpoint contract                 | pytest integration (SQLite + temp FS)                    |
| User flow (multi-page)                | Playwright E2E                                           |
| Performance regression                | Playwright perf spec in `test:perf` and `./test.sh perf` |
| Visual regression                     | Playwright snapshot (future)                             |
