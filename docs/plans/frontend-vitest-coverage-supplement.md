# Frontend Vitest Coverage Supplement Plan

Status: Proposed

Last reviewed: 2026-06-26

## Summary

This supplement extends `ci-first-test-coverage-hardening.md` with a concrete
frontend-only path to raise Vitest V8 coverage above the project target while
keeping tests behavior-focused. The current Phase 3 implementation should be
treated as incomplete until the final thresholds pass or the remaining blockers
are explicitly documented.

Current frontend baseline from the Phase 3 audit:

- Vitest: 485 tests in 40 files.
- Lines: 19.69%.
- Statements: 18.94%.
- Functions: 14.08%.
- Branches: 14.27%.

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
| F3 - Component workflow coverage | Pending | Large Vue components and page workflows. |
| F4 - Final thresholds and CI/local gate | Pending | Raise thresholds to final target and wire gates. |

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

### Phase F4 - Final Thresholds and Gate Integration

Tasks:

- Inspect `frontend/coverage/vitest/coverage-summary.json` after F2 and F3.
- Raise `coverage:unit:check` thresholds in ratchet steps until final targets
  are reached:
  lines >= 90,
  statements >= 90,
  functions >= 85,
  branches >= 80.
- Wire frontend coverage checks into local and CI gates in the main Phase 4:
  `./test.sh unit` and the CI `test-unit` job must enforce the same command
  path.
- Regenerate `docs/testing/test-gap-report.md` and `.json`.
- Add `docs/testing/TEST_CATALOG.md` entries for every new important test file.

Acceptance:

- `cd frontend && pnpm test:unit:coverage` passes.
- `cd frontend && pnpm run coverage:unit:check` passes with final thresholds.
- `./test.sh lint`, `./test.sh docs`, and `./test.sh unit` pass.
- CI and local commands enforce the same frontend thresholds.
- No production source is excluded solely to satisfy coverage.

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
