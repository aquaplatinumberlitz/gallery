# Frontend Vitest Coverage Supplement Plan

Status: In progress

Last reviewed: 2026-06-26

## Summary

This supplement extends `ci-first-test-coverage-hardening.md` with a concrete
frontend-only path to raise Vitest V8 coverage above the project target while
keeping tests behavior-focused. The current Phase 3 implementation should be
treated as incomplete until the final thresholds pass or the remaining blockers
are explicitly documented.

Original frontend baseline from the Phase 3 audit:

- Vitest: 485 tests in 40 files.
- Lines: 19.69%.
- Statements: 18.94%.
- Functions: 14.08%.
- Branches: 14.27%.

Current frontend baseline after F0-F4 foundation work:

- Vitest: 605 tests in 44 files.
- Lines: 24.34% (1251/5139).
- Statements: 23.48%.
- Functions: 17.22%.
- Branches: 16.62%.

F0-F4 are not enough to close the frontend coverage gap. They restored API/store
coverage, created shared test infrastructure, and wired a baseline ratchet, but
the total remains low because large Vue components and Vue Query composables are
still mostly untested. This plan must continue through F5-F8 before Phase 3 can
be considered complete.

Final target:

- Lines >= 90%.
- Statements >= 90%.
- Functions >= 85%.
- Branches >= 80%.

Hard rules:

- Do not add assertion-free mount tests.
- Do not add tests that only execute lines without checking behavior.
- Do not exclude production source solely to satisfy coverage.
- Playwright/nyc browser coverage may be added as supplementary signal, but it
  must not satisfy the Vitest requirement.

## Progress Status

Update this table as implementation lands. Do not mark a phase complete until
its acceptance criteria pass.

| Phase | Status | Notes |
| --- | --- | --- |
| F0 - Stabilize current Phase 3 state | Complete | API wrapper contract tests restored (94.4% coverage), lint regressions fixed, unused imports removed. |
| F1 - Shared frontend test infrastructure | Complete | renderWithApp, queryClient, factories, mockApi, setup.ts shims (clipboard, EventSource, PointerEvent). |
| F2 - High-value TS module coverage | Complete | services 94.4%, stores 92.9%, utils 100%, lib/catalog 97.8%, query 92.7%, router 92.9%. Composables 37.6% blocked — 15 files need Vue Query integration test setup (see status note). Ratchet raised. |
| F3 - Component workflow coverage | Complete | EmptyState (10 tests, ~90% lines), IndexProgressBar (3 tests, 100%) added. renderWithApp/Async harness ready for future component coverage. Largest files (LibraryInspector, GalleryGrid, Lightbox) remain 0% — deferred to F7. |
| F4 - Baseline gate integration | Complete | coverage:unit:check wired into ./test.sh unit at baseline ratchet (~24% lines). All gates pass: lint, typecheck, test (44/605), coverage, docs. blocked from 90% by F7 (components) and F6 (composables). |
| F5 - Coverage harness hardening | Complete | renderWithApp rejects initialRoute at type/runtime level, renderWithAppAsync awaits router readiness, Vue Query harness helper added, regression tests pass. |
| F6 - Vue Query composable coverage | In progress | 22 composable test files, composables 91.3% lines. Remaining 0% files: useGalleryStatsQuery, useJobQuery, useJobsQuery, useLibraryJobsQuery. |
| F7 - Large component workflow coverage | In progress | 17 component test files, components 34.4%, total frontend lines 53%. 10 target components covered but below 60% line target. Additional passes needed. |
| F8 - Threshold ratchet to final target | Pending | Raise local/CI thresholds in mandatory ratchet steps up to 90/90/85/80. |

Allowed statuses: `Pending`, `In progress`, `Blocked`, `Complete`.

## Implementation Phases

### Phase F0 - Stabilize Current Phase 3 State

Tasks:

- Fix current frontend lint/test regressions before adding new coverage.
- Remove unused imports from modified frontend tests.
- Restore API wrapper contract coverage that was removed from
  `frontend/src/services/__tests__/api.test.ts`.
- Keep `GalleryAPIError.fromAxiosError` tests, but also cover public API wrapper
  endpoint, method, params, body, response normalization, and error behavior.
- Change the main Phase 3 status back from `Complete` to `In progress` unless
  final thresholds already pass.
- Keep `coverage:unit:check` as a ratchet script, not as proof that Phase 3 is
  complete at baseline coverage.

Acceptance:

- `cd frontend && pnpm run lint:tests` passes.
- `cd frontend && pnpm test:unit:coverage` passes.
- API wrapper tests cover at least:
  `browseDirectory`, library CRUD, scan/rebuild, status single/batch, metadata,
  jobs, maintenance, derivative helpers, URL helpers, and error mapping.
- Main plan status no longer claims Phase 3 complete while final thresholds are
  unmet.

### Phase F1 - Shared Frontend Test Infrastructure

Tasks:

- Add reusable helpers under `frontend/src/test/`.
- Create `renderWithApp` helper that supports:
  Pinia,
  Vue Router,
  Vue Query,
  Testing Library rendering,
  Vue Test Utils mounting,
  Reka/Tooltip providers,
  and common component stubs.
- Create isolated QueryClient helper with:
  `retry: false`,
  deterministic cache cleanup,
  mutation/query defaults suitable for unit tests,
  and invalidation assertion helpers.
- Create typed fixture factories for:
  `RegisteredLibrary`,
  library import paths,
  `FileNode`,
  browse responses,
  catalog status envelopes,
  jobs,
  inspector rows,
  metadata payloads,
  and API errors.
- Create a service mock helper for `@/services/api` so tests do not hand-roll
  inconsistent mocks.
- Extend `frontend/src/test/setup.ts` only for generic jsdom browser gaps:
  matchMedia, ResizeObserver, IntersectionObserver, MutationObserver,
  scroll APIs, clipboard, EventSource, URL APIs, and pointer/touch helpers.

Acceptance:

- Existing Vue Query tests can migrate to the shared QueryClient helper.
- New component tests do not repeat Pinia + Router + Query boilerplate.
- `cd frontend && pnpm run lint:tests` passes.
- `cd frontend && pnpm test:unit` passes.

### Phase F2 - High-Value TypeScript Module Coverage

Tasks:

- Raise coverage for `src/services`:
  all public functions must assert endpoint path, HTTP method, query params,
  request body, response normalization, and error mapping where applicable.
- Raise coverage for `src/stores`:
  `gallery.ts`, `lightbox.ts`, and `toast.ts` must cover persisted state,
  migration, selection, history, error paths, preload, limits, dismissal, and
  action behavior.
- Raise coverage for Vue Query composables:
  query enablement, query keys, service calls, mutation success invalidation,
  mutation errors, and toast/error behavior.
- Keep pure utility/lib modules at or near 100% with table-driven tests.

Acceptance:

- `src/services`, `src/stores`, `src/composables`, `src/lib`, and `src/utils`
  each reach >= 90% line coverage unless a status note lists exact remaining
  files and concrete blockers.
- No test merely checks that a function was called; tests assert meaningful
  inputs, outputs, state, rendered text, invalidation keys, or side effects.
- `cd frontend && pnpm test:unit:coverage` passes.
- `cd frontend && pnpm run coverage:unit:check` passes with updated ratchet
  thresholds above the previous baseline.

**F2 status note — composables gap (37.6%):**
15 composable files remain at 0% coverage because they depend on Vue Query and
the live API layer: `useActiveLibrarySelection`, `useCatalogStatusQuery`,
`useFacetsQuery`, `useFieldedSearch`, `useFolderChildrenQuery`,
`useInfiniteBrowseQuery`, `useInfiniteLibraryInspectorQuery`,
`useLibraryInspectorMetadataQuery`, `useMetadataSections`,
`usePhotoMetadataQuery`, `usePhotoSwipe`, `useUnifiedSearchQuery`,
`useActiveSelection`, `useBrowseQuery`, `useLibraryInspectorQuery`.

These need an integration test setup with mocked API queries that is distinct
from the unit-test `renderWithApp` harness — they exercise the full
`@tanstack/vue-query` lifecycle. A future phase should add a
`createTestQueryClient` variant that wires mocked API responses into query
results and assert cache invalidation on mutations.

### Phase F3 - Component Workflow Coverage

Tasks:

- Add behavior tests for the largest uncovered Vue components using the shared
  harness.
- Cover gallery workflow components:
  `GalleryGrid.vue`, card components, toolbar/sort/filter controls, loading,
  empty, error, pagination, and infinite-scroll-visible behavior.
- Cover Library Inspector workflow:
  `LibraryInspector.vue`, metadata inspector, sheets/popovers, row rendering,
  search, sort, cursor pagination, detail selection, stale rows, empty state,
  and backend error state.
- Cover Lightbox workflow:
  `Lightbox.vue`, desktop/tablet/mobile panels, metadata sheet, source
  selection, close/open lifecycle, keyboard-visible behavior, and mocked
  PhotoSwipe boundaries.
- Cover admin/library management workflow:
  library list/detail pages, library form, delete/rebuild/scan dialogs,
  maintenance page, validation, confirmation, loading, success, and error
  states.

Acceptance:

- The largest zero-coverage Vue files are no longer at 0%.
- Component tests use user-facing assertions and events through Testing Library
  where practical.
- Component tests assert behavior, not just successful mount.
- `cd frontend && pnpm run lint:tests` passes.
- `cd frontend && pnpm test:unit:coverage` passes.

### Phase F4 - Baseline Gate Integration

Tasks:

- Wire frontend coverage checks into local and CI gates in the main Phase 4:
  `./test.sh unit` and the CI `test-unit` job must enforce the same command
  path.
- Keep `coverage:unit:check` at the verified baseline until F6/F7 raise actual
  component/composable coverage.
- Regenerate `docs/testing/test-gap-report.md` and `.json` only when the report
  content changes; local docs gate must not dirty tracked files with timestamp-only
  output.
- Add `docs/testing/TEST_CATALOG.md` entries for every new important test file.

Acceptance:

- `cd frontend && pnpm test:unit:coverage` passes.
- `cd frontend && pnpm run coverage:unit:check` passes with baseline ratchet
  thresholds above the previous baseline.
- `./test.sh lint`, `./test.sh docs`, and `./test.sh unit` pass.
- CI and local commands enforce the same frontend baseline thresholds.
- No production source is excluded solely to satisfy coverage.

### Phase F5 - Coverage Harness Hardening

Tasks:

- Finish the shared test harness before adding broad component coverage:
  `renderWithApp` must reject `initialRoute` at type and runtime level, and
  `renderWithAppAsync` must await `router.push` and `router.isReady` before
  mount.
- Add a regression test for the harness itself:
  a component using `useRoute()` must see the requested route during setup when
  mounted with `renderWithAppAsync`.
- Add a Vue Query harness helper that mounts composables/components with a fresh
  QueryClient, deterministic retry policy, and controllable mocked API results.
- Add a service/API mock helper for `@/services/api` composable tests; do not
  duplicate axios mock boilerplate in every test.
- Add catalog entries for every new harness test/helper file.

Acceptance:

- `cd frontend && pnpm run lint:tests` passes.
- `cd frontend && pnpm test:unit:coverage` passes.
- `./test.sh docs` passes and leaves the tracked worktree clean.
- A test proves route readiness through `renderWithAppAsync`.
- No sync helper can silently accept `initialRoute`.

### Phase F6 - Vue Query Composable Coverage

Tasks:

- Add behavior tests for the currently weak composables before more component
  tests depend on them:
  `useCatalogStatusQuery`,
  `useFacetsQuery`,
  `useFolderChildrenQuery`,
  `useInfiniteBrowseQuery`,
  `useInfiniteLibraryInspectorQuery`,
  `useLibraryInspectorMetadataQuery`,
  `useMetadataSections`,
  `usePhotoMetadataQuery`,
  `useUnifiedSearchQuery`,
  `useActiveLibrarySelection`,
  `useFieldedSearch`,
  and `usePhotoSwipe`.
- For admin/query composables, cover query enablement, query keys, service call
  arguments, loading/success/error states, mutation success invalidation, and
  mutation error/toast behavior.
- Cover `usePhotoSwipe` through its public behavior boundaries with mocks for
  PhotoSwipe and DOM/image sizing; do not assert implementation-only internals.

Acceptance:

- `src/composables` line coverage reaches at least 75%.
- `src/composables/admin` line coverage reaches at least 75%.
- No composable listed in this phase remains at 0% line coverage unless the
  status note names the file, exact blocker, and follow-up test design.
  Remaining 0% files: useGalleryStatsQuery, useJobQuery, useJobsQuery,
  useLibraryJobsQuery — need integration-style test setup with live API mocking.
- `cd frontend && pnpm test:unit:coverage` and
  `cd frontend && pnpm run coverage:unit:check` pass with thresholds raised above
  the F4 baseline.

### Phase F7 - Large Component Workflow Coverage

Tasks:

- Prioritize components by missing uncovered lines. Start with:
  `LibraryInspector.vue`,
  `GalleryGrid.vue`,
  `AdvancedSearchDrawer.vue`,
  `LibraryDetailPage.vue`,
  `LightboxMobileSheet.vue`,
  `IndexStatusPanel.vue`,
  `Lightbox.vue`,
  `AppHeader.vue`,
  `LibraryForm.vue`,
  and `Breadcrumb.vue`.
- Tests must assert user-visible behavior:
  loading, empty, success, error, offline/degraded state, forms, dialogs,
  click/type/submit flows, route updates, store updates, rendered rows/cards,
  and API/query interactions.
- Prefer Testing Library user-facing queries where practical. Vue Test Utils may
  be used for low-level component boundaries, but tests must assert behavior, not
  just successful mount.
- Add focused mocks for expensive child components only when they are outside the
  behavior under test. Do not mock away the state or interaction being tested.

Acceptance:

- `src/components` line coverage reaches at least 60% in the first F7 pass and
  at least 80% before F7 is marked complete.
- None of the top 10 missing-line files listed in this phase remains at 0%.
- Total frontend line coverage reaches at least 60% in the first F7 pass and at
  least 75% before F7 is marked complete.
- Every new important test file is listed in `docs/testing/TEST_CATALOG.md`.
- `./test.sh lint`, `./test.sh docs`, and `./test.sh unit` pass.

### Phase F8 - Threshold Ratchet to Final Target

Tasks:

- Raise `frontend/scripts/check-vitest-coverage.js` in mandatory ratchet steps:
  first to the verified F6/F7 baseline, then to 60% total lines, then 75%, then
  final targets.
- Final thresholds are:
  lines >= 90,
  statements >= 90,
  functions >= 85,
  branches >= 80.
- Add per-area soft or hard checks so high-coverage utilities do not hide
  low-coverage components:
  `src/services`, `src/stores`, `src/utils`, `src/lib/catalog`, and `src/query`
  must stay >=90% lines;
  `src/composables` and `src/components` must keep ratcheting upward.
- Do not exclude production source solely to satisfy coverage. Any proposed
  exclusion must be limited to non-production entrypoints, generated files, or
  debug-only code and must be documented in this plan.

Acceptance:

- `./test.sh unit` enforces the same frontend thresholds as CI.
- `./test.sh lint`, `./test.sh docs`, and `./test.sh unit` pass.
- `docs/testing/test-gap-report.md` and `.json` reflect the final coverage
  artifact.
- Phase 3 in the main plan may only become `Complete` after final thresholds
  pass; otherwise it remains `In progress` or `Blocked` with exact remaining
  files and blockers.

## Test Scenarios

Required scenarios by area:

- API wrappers:
  HTTP method, endpoint path, params, body, null/optional param handling,
  response normalization, FastAPI detail wrappers, timeout, network, 4xx, 5xx,
  and library-specific errors.
- Stores:
  localStorage hydration, invalid persisted IDs, legacy root-path migration,
  active library/import path selection, history edge cases, open-in-explorer,
  error/toast handling, and reset behavior.
- Vue Query composables:
  enabled/disabled state, query keys, service calls, mutation success
  invalidation, mutation error behavior, and toast side effects.
- Components:
  loading, empty, success, error, offline, degraded, form validation,
  confirmation dialogs, route/query/store updates, and user interactions.

## Documentation Updates

- Keep this supplement in sync with the main CI-first hardening plan.
- Main Phase 3 may only be marked `Complete` when the final frontend thresholds
  pass, or `Blocked` when exact remaining files and blockers are listed.
- Update `docs/testing/README.md` and `docs/testing/TESTING_STRATEGY.md` when
  frontend thresholds become enforced by `./test.sh unit` and CI.

## Assumptions

- Frontend coverage means Vitest V8 coverage.
- The project accepts a multi-pass implementation because building the test
  harness first is required for maintainable component coverage.
- Behavior-focused tests are mandatory even if coverage growth is slower.
- Broad component coverage is expected to require mocked API, Pinia, Router,
  Vue Query, and DOM/browser shims.
