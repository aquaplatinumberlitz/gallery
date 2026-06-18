# Testing Strategy

## Stack

- **Backend**: Python FastAPI + SQLite — test pyramid (nhiều unit, ít integration, rất ít E2E)
- **Frontend**: Vue 3 + TypeScript — test trophy (static > unit/integration > E2E)

## Test Matrix

| Layer | Tool | Environment | PR CI | Nightly | Mục tiêu |
|-------|------|:-----------:|:-----:|:-------:|----------|
| Static | Ruff/ESLint/vue-tsc | none | ✅ | ✅ | syntax/types |
| Unit | pytest/Vitest | isolated | ✅ | ✅ | pure logic |
| Component integration | Vitest | jsdom | ✅ | ✅ | component behavior |
| API integration | pytest | SQLite/temp FS | ✅ | ✅ | backend behavior |
| Browser integration | Playwright + mocks | Chromium | subset | full | UI workflows |
| Full-stack E2E | Playwright + backend | real app | critical only | ✅ | system wiring |
| Perf | scripts/Playwright | fixture/real data | ❌ | scheduled | budgets |

## Test Selection Policy

- **PR CI**: lint + unit + component integration + browser integration (subset) + full-stack E2E (critical only)
- **Merge/Full CI**: tất cả ở trên + full browser integration
- **Nightly**: perf tests + WebKit smoke + full-stack E2E (full)

## Coverage Baselines

- **Backend**: 85% line coverage (enforced in CI)
- **Frontend**: TBD — chờ baseline ổn định sau khi vitest + Playwright coverage merged

## Browser Matrix

- **PR CI**: Chromium (fastest)
- **Nightly**: Chromium + WebKit smoke (5-10 critical specs)

## Flaky Test Policy

- 3 lần fail liên tiếp → tự động quarantine (skip) + tạo GitHub issue
- Owner chịu trách nhiệm fix trong vòng 1 tuần

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
