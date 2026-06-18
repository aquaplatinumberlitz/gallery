# Testing Strategy

Last verified against `.github/workflows/ci.yml` and `scripts/test-*.sh`: 2026-06-18.

## Stack

- **Backend**: Python FastAPI + SQLite — test pyramid (nhiều unit, ít integration, rất ít E2E)
- **Frontend**: Vue 3 + TypeScript — test trophy (static > unit/integration > E2E)

## Test Matrix

| Layer | Tool | Environment | PR/push CI | Nightly | Mục tiêu |
|-------|------|:-----------:|:----------:|:-------:|----------|
| Static | Ruff/ESLint/Prettier | none | ✅ `lint` | N/A (not configured) | syntax/style |
| Backend unit + API integration | pytest | SQLite/temp FS | ✅ `test:unit` | N/A (not configured) | backend behavior |
| Frontend unit/component | Vitest | jsdom | ✅ `test:unit` | N/A (not configured) | frontend logic/behavior |
| Frontend build/typecheck | vue-tsc/Vite | build environment | ✅ `test:unit` and `test:e2e` | N/A (not configured) | types/build |
| Browser integration | Playwright + mocked API | Chromium | ✅ selected specs in `test:e2e` | N/A (not configured) | critical UI workflows |
| Full-stack E2E | Playwright + backend | real app | ❌ | N/A (not configured) | system wiring |
| Perf | scripts/Playwright | fixture/real data | ❌ | N/A (not configured) | local performance checks |

## Test Selection Policy

- **Push/PR CI**: three jobs only: `lint`, `test:unit`, and `test:e2e`.
- **`test:e2e` CI selection**: four Chromium contract specs: lightbox loading policy, no-reload, cache revisit, and fielded-search UI.
- **Nightly**: N/A (not configured).
- **WebKit smoke**: N/A.
- **Full-stack/perf**: available through repository scripts where their prerequisites are met, but not selected by the current CI workflow.

## Coverage Baselines

- **Backend**: 85% line coverage (enforced in CI)
- **Frontend**: coverage artifacts are generated for the selected Playwright CI specs, but no numeric frontend coverage threshold is enforced.

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
| Performance regression | Playwright perf spec (local only) |
| Visual regression | Playwright snapshot (future) |
