# Testing Strategy

Last verified against `.github/workflows/ci.yml` and `test.sh`: 2026-06-19.

## Stack

- **Backend**: Python FastAPI + SQLite — test pyramid (nhiều unit, ít integration, rất ít E2E)
- **Frontend**: Vue 3 + TypeScript — test trophy (static > unit/integration > E2E)

## Test Matrix

| Layer | Tool | Environment | PR/push CI | Nightly | Mục tiêu |
|-------|------|:-----------:|:----------:|:-------:|----------|
| Static | Ruff/ESLint/Prettier | none | ✅ `lint` | N/A (not configured) | syntax/style |
| Backend unit + API integration | pytest | SQLite/temp FS | ✅ `test:unit` | N/A (not configured) | backend behavior |
| Frontend unit/component | Vitest + V8 coverage | jsdom | ✅ `test:unit` | N/A (not configured) | frontend logic/behavior |
| Frontend build/typecheck | vue-tsc/Vite | build environment | ✅ `test:unit` | N/A (not configured) | types/build |
| Browser integration | Playwright | Chromium | ✅ full suite, 4 shards | N/A (not configured) | critical UI workflows |
| Full-stack E2E | Playwright + FastAPI | deterministic temp fixture | ✅ `test:e2e` | N/A (not configured) | system wiring |
| Perf | Playwright | deterministic temp fixture | ✅ `test:perf`, 1 worker | N/A (not configured) | performance budgets |

## Test Selection Policy

- **Push/PR CI**: full-codebase `lint`, `test:unit`, four `test:e2e` shards, and `test:perf`.
- **`test:e2e` CI selection**: every top-level `frontend/tests/e2e/*.spec.ts` functional spec. Playwright shards the suite across four parallel jobs.
- **`test:perf` CI selection**: every spec under `frontend/tests/e2e/perf/`, with one worker and a separate deterministic fixture.
- **Functional E2E coverage instrumentation is disabled** so browser behavior and timing are not distorted. Frontend coverage comes from Vitest/V8.
- **Nightly**: N/A (not configured).
- **WebKit smoke**: N/A.
- **Local parity**: `./test.sh full` runs the same full layers sequentially; `./test.sh fast` is the fast lint/unit/build gate.

## Coverage Baselines

- **Backend**: 85% line coverage (enforced in CI)
- **Frontend**: Vitest/V8 coverage is uploaded from `test:unit`; no numeric frontend threshold is enforced yet.

## Browser Matrix

- **PR CI**: Chromium (fastest)
- **Nightly**: N/A (not configured)
- **WebKit smoke**: N/A

## Flaky Test Policy

- Không có automation quarantine hoặc auto-create GitHub issue trong workflow hiện tại.
- Test flaky phải được triage; không được mô tả là tự động skip nếu chưa có workflow/config thực hiện việc đó.

## When to Use What

| Bạn muốn test | Dùng |
|---------------|------|
| Pure function logic | Vitest unit (frontend) / pytest unit (backend) |
| Store / composable behavior | Vitest (jsdom) |
| Vue component rendering + interaction | Playwright (browser integration) |
| API endpoint contract | pytest integration (SQLite + temp FS) |
| User flow (multi-page) | Playwright E2E |
| Performance regression | Playwright perf spec in `test:perf` and `./test.sh perf` |
| Visual regression | Playwright snapshot (future) |
