# Testing Guide

Status: Maintained

Last reviewed: 2026-07-13

This directory documents the test and debug surface for the gallery repo. Keep it focused on what each test protects, when to run it, and which debug helper to use before changing behavior.

The repository-wide layer, CI selection, browser, coverage, and flaky-test policies are defined in [TESTING_STRATEGY.md](TESTING_STRATEGY.md).
Frontend testing principles from the official Vue, Vue Test Utils, Pinia, and
Playwright guidance are summarized in
[FRONTEND_TESTING_PRINCIPLES.md](FRONTEND_TESTING_PRINCIPLES.md).
Performance budgets and profiling workflows are documented in
[PERFORMANCE_TESTING.md](PERFORMANCE_TESTING.md), and runtime diagnostics are
documented in [DEBUG_TOOLS.md](DEBUG_TOOLS.md).

## Test Selection

- Push/PR CI runs full-codebase static checks, backend and frontend unit/integration tests, the complete Chromium functional suite split into four shards, deterministic performance tests, and docs/test-catalog drift checks.
- CI delegates to `./test.sh` for lint, unit, docs, functional E2E, and performance checks so local and CI commands stay in sync. Docs/test inventory drift and metadata lifecycle ownership are guarded by `scripts/check_docs_staleness.py`, `scripts/check_test_docs.py`, `scripts/audit_test_matrix.py --fail-on-gaps`, and `scripts/check_metadata_lifecycle_ownership.py` (run via `./test.sh docs`).
- Functional Playwright runs without Istanbul instrumentation. Frontend coverage is produced by Vitest/V8 in the unit job.
- Backend line coverage has an enforced 90% baseline. Frontend Vitest enforces
  the measured 2026-07-15 global ratchets (70% lines, 68% statements, 62%
  functions, 58% branches), and `coverage:unit:check` also enforces the
  measured per-area line ratchets documented in
  [TESTING_STRATEGY.md](TESTING_STRATEGY.md#coverage-baselines).
- Nightly and WebKit jobs are not currently configured.

## Test Categories

- Backend unit/integration tests: `backend/tests/test_*.py` cover FastAPI endpoint contracts, metadata parsing/search, catalog browse behavior, indexed catalog-only query boundaries, secure precedence-aware sidecar reads, claim-fenced indexer/rebuild staging, atomic catalog job/library completion, metadata lifecycle recovery/diagnostics, integrity checking, warm listing, scheduled-attempt fairness, watcher callback containment/sidecar casing, facets, and derivative/poster response leases.
- Frontend Playwright/contract tests: `frontend/tests/e2e/*.spec.ts` cover gallery UI contracts with stubbed API responses, UI regressions, and diagnostics. Real-backend smoke tests (`gallery-no-reload-real-backend.spec.ts`) and metadata performance diagnostics (`metadata-performance.spec.ts`) are env-gated and skipped by default.
- Frontend vitest unit tests: `frontend/src/**/__tests__/*.test.ts` cover pure utilities, Pinia stores, and Vue composables with jsdom + `@vue/test-utils`. Run with `cd frontend && pnpm test:unit`. See the "Frontend Vitest Unit Tests" section below for the testing-trophy rationale and per-tier inventory.
- Rebuild/catalog status tests: `frontend/tests/e2e/index-rebuild-flow.spec.ts`, `frontend/tests/e2e/index-status-panel.spec.ts`, `backend/tests/test_catalog_status_contract.py`, `backend/tests/test_catalog_status_endpoints.py`, `backend/tests/test_catalog_status_ready_assets.py`, `backend/tests/test_catalog_trigger_routing.py`, `backend/tests/test_indexer_staging.py`, `backend/tests/test_metadata_lifecycle.py`, `backend/tests/test_integrity_checker.py`, and `backend/tests/test_warm_folder_listing.py`.
- Maintenance file-health tests: `backend/tests/test_maintenance_file_health_api.py`, `backend/tests/test_integrity_checker_contract.py`, `backend/tests/test_schema_check.py`, `frontend/src/contracts/__tests__/maintenanceFileHealthContract.test.ts`, and `frontend/src/composables/admin/__tests__/useFileHealthQuery.test.ts`.
- Library Inspector tests: `frontend/tests/e2e/library-inspector.spec.ts` and `backend/tests/test_library_inspector.py`.
- Metadata performance diagnostics: `frontend/tests/e2e/metadata-performance.spec.ts` measures `/metadata` navigation, sort, search, rendered row counts, thumbnail requests, and state restoration against a running gallery app. Requires `GALLERY_PERF_METADATA=1`.
- Lightbox tests: `frontend/tests/e2e/lightbox-loading-policy.spec.ts`, `frontend/tests/e2e/lightbox-visual-layer.spec.ts`, `frontend/tests/e2e/mobile-lightbox-sheet.spec.ts`, and derivative backend tests.
- Responsive tests: `frontend/tests/e2e/responsive-breakpoints.spec.ts`, `frontend/tests/e2e/sidebar-trigger.spec.ts`, mobile lightbox tests, and Tailwind migration/preflight tests.
- Search discovery tests: `frontend/tests/e2e/search-discovery-evolution.spec.ts`
  covers Search V2 reload/history, automatic recent-search replay/clear, prompt groups, typed
  same-node workflow predicates, raw acknowledgement, index lifecycle actions,
  hydrated URL-result row measurement, and desktop/tablet/mobile parity.
- Related Assets frontend tests: `frontend/tests/e2e/related-assets.spec.ts`
  covers card/lightbox entry points, the single combined request/list, absence
  of match-type selectors, stable evidence copy, canonical scope,
  changed-seed comparison, resized/re-encoded variants,
  unrelated/inactive/cross-library exclusion, missing-visual recovery,
  existing-lightbox handoff, badge sizing, and mobile overflow.
  Component/composable/store units cover cancellation, typed one-retry policy,
  reference isolation, defensive dedupe/reason union with stable ordering,
  recorded-setting comparisons, smart-collection request descriptors, partial
  metadata/visual coverage, polling/refetch, keyboard semantics, and no
  match-type or saved-search persistence.
- Related Assets contract tests: `backend/tests/test_related_assets_contract.py`
  lock the bounded reference request, canonical scope authorization, typed
  readiness/error models, unified partial results, legacy profile compatibility,
  stable reason codes, deterministic metadata/visual fixtures, and the stable API envelope.
- Generation-signature tests: `backend/tests/test_generation_signatures.py`
  cover bounded Unicode/emphasis prompt atoms, canonical numeric inputs,
  layered hash sensitivity, weak-metadata rejection, schema-v10
  backup/rollback, active-only durable backfill, idempotence, and metadata-write
  invalidation/repair scheduling.
- Related metadata ranking tests: `backend/tests/test_related_assets_ranking.py`
  drive the deterministic fixture through exact/recipe/overlap tiers, stable
  reasons, scope/activity/source filtering, recipe-profile behavior, bounded
  candidate loading, and optional-workflow degradation.
- Visual fingerprint tests: `backend/tests/test_visual_fingerprints.py` cover
  fixed-size Pillow hashes/color grids, v11/v12 migration rollback, compact
  `WITHOUT ROWID` bands, atomic bands,
  durable derivative-backed extraction, indexed near-duplicate lookup,
  resize/re-encode/light-change fixtures, crop/mirror/rotation limits, typed
  reference coverage, disabled isolation, and the no-HTTP-decode guarantee.
- Performance contract tests: backend pytest hot-path tests such as `backend/tests/test_browse_api.py`, `backend/tests/test_search_ranked_pagination.py`, `backend/tests/test_related_assets_perf_tooling.py`, and `backend/tests/test_warm_folder_listing.py` prevent known slow-path regressions and lock the deterministic 100,000-row relation fixture, including both lifecycle extraction rows per asset, and budget registry.
- Performance diagnostics: browser specs measure user-visible album/lightbox readiness, while `scripts/bench_thumbnail.py` and `scripts/bench_preview.py` independently gate cold generation and warm persisted-cache latency.
- Album-open performance gates warm visible-thumbnail batch completion; per-request browser timings remain diagnostic because browser queueing is not backend service time.
- Gated performance tests: `./test.sh perf` uses a production frontend build, one Playwright worker, zero retries, manifest-declared reports, and a deterministic managed fixture.
- Budget provenance, percentile interpolation, baseline calibration, private-project RUM limitations, and the browser-native lightbox timing refactor are specified in [Performance Testing](PERFORMANCE_TESTING.md#budget-provenance-and-calculation-policy).
- Debug/diagnostic scripts: `frontend/src/debug/`, `scripts/debug_*`, perf fixture helpers, and perf scripts under `scripts/` and `frontend/tests/e2e/perf/`.

## Frontend Vitest Unit Tests

Vitest fills the integration/unit tier of Kent C. Dodds' Testing Trophy. The repo already had the surrounding tiers (`TypeScript + ESLint` static checks at the top, `Playwright` E2E at the bottom) but was missing the middle tier where pure logic, Pinia stores, and composables are exercised quickly and deterministically without a browser.

```
TypeScript + ESLint              <- static checks (pre-existing)
Integration/Unit (vitest)        <- NEW: src/**/__tests__/*.test.ts
E2E (Playwright)                 <- pre-existing: frontend/tests/e2e/*.spec.ts
```

### Conventions

- Test files live next to the source they exercise, under a per-folder `__tests__/` subfolder (e.g. `frontend/src/utils/__tests__/fuzzySearch.test.ts`).
- File naming: `*.test.ts` for vitest, `*.spec.ts` for Playwright. The two suites never overlap because vitest only collects `src/**/__tests__/**/*.test.ts` and Playwright only collects `tests/**/*.spec.ts`.
- Global setup: `frontend/src/test/setup.ts` polyfills jsdom gaps, automatically
  unmounts Vue Test Utils wrappers, resets browser state, and fails tests on
  unexpected console errors or Vue warnings.
- Composables that use lifecycle hooks are mounted through the `withSetup` helper in `frontend/src/test/withSetup.ts` so `onMounted`/`onBeforeUnmount`/`watch` run normally.
- ESLint relaxes `no-empty`, `no-useless-assignment`, `@typescript-eslint/no-explicit-any`, and `vue/one-component-per-file` for `src/**/__tests__/**/*.test.ts` and `src/test/**/*.ts` so test scaffolding (inline components, intentional empty catches, etc.) does not trip production rules.
- Lint policy: `pnpm lint` excludes `src/**/__tests__/**` and `src/test/**` so production rules run against production code only. `pnpm lint:tests` lints all test files (Playwright `tests/**`, vitest `src/**/__tests__/**/*.test.ts`, and helpers `src/test/**`).

### Test inventory

See [test-gap-report.md](test-gap-report.md) for the generated snapshot. The per-file tables below describe what each test protects but do not replace the generated report for accurate counts.

Tier 1 — pure utilities (logic-only, no mocking, fast):

| File                                                                     | Protects                                                                                                                |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `frontend/src/utils/__tests__/assetType.test.ts`                         | Canonical/legacy asset type normalization and comparisons.                                                              |
| `frontend/src/utils/__tests__/format.test.ts`                            | Human-readable percent, fraction, and byte formatting edge cases.                                                       |
| `frontend/src/utils/__tests__/fuzzySearch.test.ts`                       | Fuse-backed fuzzy name/path matching, empty/whitespace queries, includePath branching, cache reuse, special chars, CJK. |
| `frontend/src/utils/__tests__/gallery.test.ts`                           | Gallery utility behavior for path/media helpers.                                                                        |
| `frontend/src/utils/__tests__/indexMaintenance.test.ts`                  | Scope rebuild marker mark/get/clear across nested roots, finite-timestamp guards, root-path boundary checks.            |
| `frontend/src/utils/__tests__/infiniteScroll.int.test.ts`                | Infinite-scroll guard behavior and fetch-trigger integration.                                                           |
| `frontend/src/utils/__tests__/serializeAdvancedSearchToQuery.test.ts`    | Fielded search serialization, literal-field operator omission, value quoting/escaping, parse round-trips.               |
| `frontend/src/utils/__tests__/loraHighlighter.test.ts`                   | `<lora:...>` tokenization, HTML escaping of plain text and token contents, weight/name handling.                        |
| `frontend/src/utils/__tests__/lightbox.test.ts`                          | PhotoSwipe item building, dimension validation, animated-asset detection, localStorage preference reads.                |
| `frontend/src/lib/catalog/__tests__/contractGuard.test.ts`               | Runtime validation for catalog status envelopes and metadata lifecycle counters.                                        |
| `frontend/src/lib/catalog/__tests__/labels.test.ts`                      | User-facing status labels and presentation mapping.                                                                     |
| `frontend/src/lib/catalog/__tests__/polling.test.ts`                     | Catalog status polling interval policy.                                                                                 |
| `frontend/src/lib/related/__tests__/smartCollections.test.ts`            | Relation facts and canonical Search V2 model/LoRA smart-collection descriptors without materialized membership.         |
| `frontend/src/contracts/__tests__/catalogStatusContract.test.ts`         | Shared backend status fixtures, schema validation, summary precedence, and frontend contract compatibility.             |
| `frontend/src/contracts/__tests__/maintenanceFileHealthContract.test.ts` | Maintenance file-health backend fixtures, JSON schema validation, exact key sets, and frontend contract compatibility.  |

Tier 2 — Pinia stores (state mutations + async actions with mocked services):

| File                                                  | Protects                                                                                                                               |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/src/stores/__tests__/gallery.test.ts`       | Active library lifecycle, sidebar tree normalization, history navigation, sort persistence, error/toast handling for `openInExplorer`. |
| `frontend/src/stores/__tests__/toast.test.ts`         | Toast store adapts Gallery API to Sonner: IDs, variants, durations, dismiss, clear, actions, and visible-toast limit.                  |
| `frontend/src/stores/__tests__/lightbox.test.ts`      | Open/close, immutable image-list handling, index resolution, navigation, and separate dimension memory.                                |
| `frontend/src/stores/__tests__/relatedAssets.test.ts` | Ephemeral reference/scope session behavior with no match-type selection state.                                                         |

Tier 3 — composables (mounted via `withSetup`, lifecycle + reactive state):

| File                                                                                 | Protects                                                                                                                   |
| ------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| `frontend/src/composables/__tests__/useToast.test.ts`                                | Convenience wrappers and promise-based toast flow on top of the toast store adapter.                                       |
| `frontend/src/composables/__tests__/usePullToRefresh.test.ts`                        | Pull gesture state machine, axis lock, threshold/max distance, haptic feedback, refresh in-flight guard.                   |
| `frontend/src/composables/__tests__/useGalleryTheme.test.ts`                         | Theme mode persistence, set/toggle/cycle, view-transition selection, prefers-reduced-motion fallback.                      |
| `frontend/src/composables/__tests__/useNaturalSort.test.ts`                          | Natural-sort key generation and comparator.                                                                                |
| `frontend/src/composables/__tests__/useDelayedBoolean.test.ts`                       | Timer-based boolean with cancellation, rescheduling, unmount cleanup.                                                      |
| `frontend/src/composables/__tests__/useHaptic.test.ts`                               | `navigator.vibrate` guards and light/medium patterns.                                                                      |
| `frontend/src/composables/__tests__/useClipboard.test.ts`                            | Modern Clipboard API path, per-id labels, error toasts, status reset timer.                                                |
| `frontend/src/composables/__tests__/useColumnResize.test.ts`                         | Slider level mapping per device category, localStorage persistence, legacy migration, and row-height recompute.            |
| `frontend/src/composables/__tests__/useScrollVisibility.test.ts`                     | Scroll-driven bar visibility, bottom guard, polling-vs-container-ref attach paths, unmount cleanup.                        |
| `frontend/src/composables/__tests__/useRelatedAssetsQuery.test.ts`                   | Adaptable request input, cancellation-ready API calls, retry policy, stale success retention, and reference-key isolation. |
| `frontend/src/composables/admin/__tests__/useGeneratedImagesStatusQuery.test.ts`     | Generated-image status query enablement and API call shape.                                                                |
| `frontend/src/composables/admin/__tests__/useGeneratedImagesMutations.test.ts`       | Library-scoped generated-image warm mutation and invalidation behavior.                                                    |
| `frontend/src/composables/admin/__tests__/useGeneratedImagesGlobalMutations.test.ts` | All-library generated-image refresh/clear mutations and invalidation behavior.                                             |
| `frontend/src/composables/admin/__tests__/useFileHealthQuery.test.ts`                | Maintenance file-health query/mutation API calls and query invalidation behavior.                                          |
| `frontend/src/composables/admin/__tests__/useLibraryEvents.test.ts`                  | Admin SSE/event invalidation behavior.                                                                                     |
| `frontend/src/composables/admin/__tests__/useLibraryMutations.test.ts`               | Library create/update/scan/delete mutation side effects and invalidation behavior.                                         |
| `frontend/src/components/__tests__/Lightbox.test.ts`                                 | FocusScope focus trapping and focus restore on unmount.                                                                    |
| `frontend/src/components/__tests__/PhotoCardRelatedAction.test.ts`                   | Separate focusable image-card and Find Related action semantics.                                                           |
| `frontend/src/components/__tests__/RelationReasonList.test.ts`                       | Stable accessible copy for every typed relation reason.                                                                    |
| `frontend/src/components/__tests__/RelatedAssetsPanel.test.ts`                       | Explicit profiles, coverage/fallback states, evidence, reference changes, and existing-lightbox handoff.                   |

### Running vitest

| Purpose                          | Command                                                                 |
| -------------------------------- | ----------------------------------------------------------------------- |
| Run all unit tests once          | `cd frontend && pnpm test:unit`                                         |
| Watch mode for local development | `cd frontend && pnpm test:unit:watch`                                   |
| Run a single test file           | `cd frontend && pnpm test:unit src/utils/__tests__/fuzzySearch.test.ts` |
| Run with v8 coverage             | `cd frontend && pnpm test:unit:coverage`                                |
| Lint test files only             | `cd frontend && pnpm lint:tests`                                        |

Coverage output is written to `frontend/coverage/vitest/` (text, html, lcov, json-summary). The coverage scope is `src/**/*.{ts,vue}` minus debug, test, and app-entry files. CI uploads this directory from the unit job. `./test.sh unit` also runs `coverage:unit:check`, which enforces the repository's current frontend ratchet thresholds. Functional Playwright does not use Istanbul instrumentation.

Vitest runs test files in parallel with at most three workers by default
(`VITEST_MAX_WORKERS` overrides the cap). Playwright screenshots functional
failures, records a trace on first retry, and fails CI when `.only` is present.

## Performance Fixtures

Use the deterministic fixture when comparing perf over time or before release:

`backend/.venv_linux/bin/python scripts/create_perf_fixture.py --clean --env-file /tmp/gallery_perf_fixture.env`

Add `--search-rows 100000 --related-assets --search-cohort-rows 5000` for the
CI-equivalent profile or use `--search-cohort-rows 25000` for the opt-in
scheduled/local lexical cohort. All 100,000 active rows are seeded directly
into the SQLite catalog and relation indexes, so the fixture creates only the
small real-image set required by browser and extraction tests.

The generated env file contains `PATH_SAFETY_ROOT`, `GALLERY_METADATA_DB`, `GALLERY_THUMBNAIL_CACHE_DIR`, `GALLERY_PERF_ALBUM_NAME`, `GALLERY_PERF_ALBUM_PATH`, and catalog/inspector defaults. Source it before starting the backend, or let the perf smoke runner do both:

`GALLERY_PERF_USE_FIXTURE=1 GALLERY_PERF_START_BACKEND=1 ./test.sh perf-smoke`

Useful runner controls:

- `GALLERY_PERF_BACKEND_PORT=<port>` runs the managed backend on a non-default port.
- `GALLERY_PERF_REUSE_BACKEND=1` allows reusing an already-running backend at `GALLERY_API_BASE_URL`; leave it unset when using a fresh fixture so accidental DB/root mismatches fail clearly.
- `GALLERY_PERF_FIXTURE_IMAGES=<count>` changes deterministic fixture size.
- `GALLERY_PERF_SEARCH_PROFILE=scheduled` selects the 25,000-row search profile; the default `ci` profile uses 5,000.
- `GALLERY_PERF_SEARCH_ROWS=<count>` overrides the selected synthetic search-row profile.
- `GALLERY_PERF_RELATED_ROWS=<count>` overrides the relation corpus size; release validation uses 100,000.
- `GALLERY_PERF_WARM_LISTING_IMAGES=<count>` changes the local warm-listing benchmark size.
- `GALLERY_PERF_PYTHON=<python>` overrides the interpreter; by default the runner uses `backend/.venv_linux/bin/python` when available.
- `GALLERY_PERF_SKIP_FRONTEND=1` runs only backend inspector and warm-listing gates.

The perf smoke runner writes individual JSON reports plus aggregate summaries to
`GALLERY_PERF_RESULTS_DIR` (default `test-results/perf-smoke/`). The managed CI
runner uses a temporary artifact directory outside Playwright cleanup:

- `library-inspector-report.json`
- `warm-listing-report.json`
- `search-benchmark-report.json`
- `related-assets-benchmark-report.json`
- `thumbnail-benchmark-report.json`
- `preview-benchmark-report.json`
- `album-open-report.json`
- `lightbox-open-report.json`
- `lightbox-transition-report.json`
- `metadata-navigation-report.json`, `metadata-sort-report.json`, and `metadata-search-report.json` when metadata perf is run
- `perf-summary.json`
- `perf-summary.md`

For existing real data, keep setting `GALLERY_BASE_URL`, `GALLERY_API_BASE_URL`, `GALLERY_PERF_ALBUM_NAME`, `GALLERY_PERF_ALBUM_PATH`, and any budget overrides explicitly.

## Common Commands

Run from the repo root unless a command changes directory explicitly.

| Purpose                                    | Command                                                                                                                                                                               |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Fast local gate (recommended before push)  | `./test.sh fast`                                                                                                                                                                      |
| Full CI-equivalent suite                   | `./test.sh full`                                                                                                                                                                      |
| Show all test commands                     | `./test.sh help`                                                                                                                                                                      |
| Backend tests                              | `cd backend && python -m pytest -q`                                                                                                                                                   |
| Backend API integration subset             | `./test.sh backend-api`                                                                                                                                                               |
| Frontend lint                              | `cd frontend && corepack pnpm run lint`                                                                                                                                               |
| Frontend lint test files only              | `cd frontend && corepack pnpm run lint:tests`                                                                                                                                         |
| Frontend format check full codebase        | `cd frontend && corepack pnpm run format:check`                                                                                                                                       |
| Frontend typecheck                         | `cd frontend && corepack pnpm run typecheck`                                                                                                                                          |
| Frontend build                             | `cd frontend && corepack pnpm run build`                                                                                                                                              |
| Frontend vitest unit tests                 | `cd frontend && corepack pnpm run test:unit`                                                                                                                                          |
| Frontend vitest unit tests (watch)         | `cd frontend && corepack pnpm run test:unit:watch`                                                                                                                                    |
| Frontend vitest unit tests with coverage   | `cd frontend && corepack pnpm run test:unit:coverage`                                                                                                                                 |
| Frontend Playwright test                   | `cd frontend && corepack pnpm exec playwright test --project=chromium`                                                                                                                |
| Targeted Playwright test                   | `cd frontend && corepack pnpm exec playwright test tests/e2e/lightbox-loading-policy.spec.ts --project=chromium`                                                                      |
| Metadata performance diagnostic            | `cd frontend && GALLERY_PERF_METADATA=1 GALLERY_BASE_URL=http://localhost:5173 corepack pnpm exec playwright test tests/e2e/metadata-performance.spec.ts --project=chromium --headed` |
| Real-backend diagnostic E2E                | `GALLERY_E2E_DIAGNOSTICS=1 ./test.sh e2e tests/e2e/gallery-no-reload-real-backend.spec.ts`                                                                                            |
| Metadata performance strict gate           | `GALLERY_PERF_METADATA_STRICT=1 ./test.sh e2e tests/e2e/metadata-performance.spec.ts`                                                                                                 |
| Managed functional E2E suite               | `./test.sh e2e`                                                                                                                                                                       |
| Managed performance suite                  | `./test.sh perf`                                                                                                                                                                      |
| Managed 25k search profile                 | `GALLERY_PERF_SEARCH_PROFILE=scheduled ./test.sh perf`                                                                                                                                |
| Lint and format checks                     | `./test.sh lint`                                                                                                                                                                      |
| Backend and frontend unit suite            | `./test.sh unit`                                                                                                                                                                      |
| Docs staleness, test headers, matrix audit | `./test.sh docs`                                                                                                                                                                      |
| Perf fixture generation                    | `backend/.venv_linux/bin/python scripts/create_perf_fixture.py --clean --env-file /tmp/gallery_perf_fixture.env`                                                                      |
| Backend inspector p95 perf                 | `GALLERY_API_BASE_URL=http://localhost:4180 backend/.venv_linux/bin/python scripts/perf_library_inspector.py`                                                                         |
| Warm listing local perf                    | `backend/.venv_linux/bin/python scripts/perf_warm_listing.py --images 5000`                                                                                                           |
| Perf report summary                        | `backend/.venv_linux/bin/python scripts/summarize_perf_reports.py --results-dir test-results/perf-smoke`                                                                              |
| Test gap audit                             | `python3 scripts/audit_test_matrix.py`                                                                                                                                                |
| Docs staleness + test gap audit            | `./test.sh docs`                                                                                                                                                                      |
| Perf smoke suite                           | `GALLERY_PERF_USE_FIXTURE=1 GALLERY_PERF_START_BACKEND=1 ./test.sh perf-smoke`                                                                                                        |
| Album perf test                            | `cd frontend && corepack pnpm run perf:album`                                                                                                                                         |
| Lightbox perf test                         | `cd frontend && corepack pnpm run perf:lightbox`                                                                                                                                      |
| Test/debug header checker                  | `python3 scripts/check_test_docs.py`                                                                                                                                                  |
| List files checked by header checker       | `python3 scripts/check_test_docs.py --list`                                                                                                                                           |

`./test.sh e2e` and `./test.sh perf` create a deterministic temporary gallery,
start FastAPI and Vite on free local ports, set all required paths, and clean up
afterward. The perf path also seeds 5,000 synthetic search assets and runs
`scripts/bench_search.py` after backend health succeeds. Internal shell helpers
live under `scripts/internal/`; developers should use `test.sh` as the stable
entrypoint. Use `GALLERY_TEST_KEEP_TMP=1` to retain artifacts or
`GALLERY_TEST_TMPDIR=<path>` to choose the workspace.

Additional controls:

- `GALLERY_TEST_SHARD=1/4` runs one functional Playwright shard locally.
- `GALLERY_TEST_FIXTURE_IMAGES=<count>` changes fixture size.
- `GALLERY_TEST_SKIP_BUILD=1` skips the pre-Playwright build when it already passed.
- `PLAYWRIGHT_RETRIES=<count>` overrides retries; `./test.sh full` defaults to the CI value of `1`.

Ruff, ESLint, and Prettier checks scan the full codebase locally and in CI.

### CI sync

CI lint, unit, docs, functional E2E, and performance jobs delegate to `./test.sh` rather than duplicating commands inline.
Add new test commands to `test.sh` first, then wire them into CI.
Docs/test inventory drift is caught by `./test.sh docs`:

## When Changing X, Run Y

| Change area                                                                                                                                                                            | Run                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/src/utils/*.ts` (asset type, formatting, fuzzySearch, gallery helpers, indexMaintenance, infinite scroll, fielded-search serialization, LoRA highlighting, lightbox helpers) | `cd frontend && pnpm test:unit src/utils/__tests__`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `frontend/src/stores/*.ts` (gallery, toast, lightbox)                                                                                                                                  | `cd frontend && pnpm test:unit src/stores/__tests__`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `frontend/src/composables/*.ts` (useToast, usePullToRefresh, useGalleryTheme, useNaturalSort, useDelayedBoolean, useHaptic, useClipboard, useColumnResize, useScrollVisibility)        | `cd frontend && pnpm test:unit src/composables/__tests__`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `frontend/src/utils/fuzzySearch.ts` (Fuse options, includePath branching, cache)                                                                                                       | `cd frontend && pnpm test:unit src/utils/__tests__/fuzzySearch.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Catalog status frontend contract, labels, polling, or guards                                                                                                                           | `cd frontend && pnpm test:unit src/lib/catalog/__tests__ src/contracts/__tests__/catalogStatusContract.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `frontend/src/utils/serializeAdvancedSearchToQuery.ts` (fielded search parser/serializer)                                                                                              | `cd frontend && pnpm test:unit src/utils/__tests__/serializeAdvancedSearchToQuery.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `frontend/src/utils/loraHighlighter.ts` (lora pill tokenizer)                                                                                                                          | `cd frontend && pnpm test:unit src/utils/__tests__/loraHighlighter.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `frontend/src/utils/lightbox.ts` (PhotoSwipe item builder, dimension helpers)                                                                                                          | `cd frontend && pnpm test:unit src/utils/__tests__/lightbox.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `frontend/src/stores/gallery.ts` (root path, sort, history, expanded folders, error handling)                                                                                          | `cd frontend && pnpm test:unit src/stores/__tests__/gallery.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `frontend/src/stores/toast.ts` (toast adapter, durations, convenience helpers)                                                                                                         | `cd frontend && pnpm test:unit src/stores/__tests__/toast.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `frontend/src/stores/lightbox.ts` (open/close, navigation, dimension memory)                                                                                                           | `cd frontend && pnpm test:unit src/stores/__tests__/lightbox.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `frontend/src/composables/usePullToRefresh.ts` (pull gesture state machine)                                                                                                            | `cd frontend && pnpm test:unit src/composables/__tests__/usePullToRefresh.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `frontend/src/composables/useGalleryTheme.ts` (theme toggle/persist, view transitions)                                                                                                 | `cd frontend && pnpm test:unit src/composables/__tests__/useGalleryTheme.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `frontend/src/composables/useNaturalSort.ts` (natural sort key/comparator)                                                                                                             | `cd frontend && pnpm test:unit src/composables/__tests__/useNaturalSort.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `frontend/src/composables/useDelayedBoolean.ts` (timer-based boolean)                                                                                                                  | `cd frontend && pnpm test:unit src/composables/__tests__/useDelayedBoolean.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `frontend/src/composables/useHaptic.ts` (navigator.vibrate wrapper)                                                                                                                    | `cd frontend && pnpm test:unit src/composables/__tests__/useHaptic.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `frontend/src/composables/useClipboard.ts` (Modern Clipboard API path)                                                                                                                 | `cd frontend && pnpm test:unit src/composables/__tests__/useClipboard.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `frontend/src/composables/useColumnResize.ts` (grid slider levels, legacy migration)                                                                                                   | `cd frontend && pnpm test:unit src/composables/__tests__/useColumnResize.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `frontend/src/composables/useScrollVisibility.ts` (scroll-driven bar visibility)                                                                                                       | `cd frontend && pnpm test:unit src/composables/__tests__/useScrollVisibility.test.ts`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Admin generated-image lifecycle/status/actions                                                                                                                                         | `cd frontend && corepack pnpm exec vitest run src/composables/admin/__tests__/useGeneratedImagesStatusQuery.test.ts src/composables/admin/__tests__/useGeneratedImagesMutations.test.ts src/components/admin/__tests__/LibraryDetailPage.test.ts src/components/admin/__tests__/MaintenancePage.test.ts`; `backend/.venv_linux/bin/python -m pytest -q backend/tests/test_derivative_scheduler.py backend/tests/test_integrity_checker.py backend/tests/test_libraries_coverage.py backend/tests/test_maintenance_runtime_api.py`                                                                                                             |
| Admin Maintenance file-health API, contract, or query wiring                                                                                                                           | `cd backend && python -m pytest -q tests/test_integrity_checker.py tests/test_integrity_checker_contract.py tests/test_maintenance_file_health_api.py tests/test_schema_check.py`; `cd frontend && pnpm test:unit src/contracts/__tests__/maintenanceFileHealthContract.test.ts src/composables/admin/__tests__/useFileHealthQuery.test.ts`                                                                                                                                                                                                                                                                                                   |
| `LibraryInspector.vue`, inspector query hooks, inspector metadata details                                                                                                              | `cd frontend && corepack pnpm exec playwright test tests/e2e/library-inspector.spec.ts --project=chromium`; `cd backend && python -m pytest -q tests/test_library_inspector.py`; for performance diagnostics with a running app, `cd frontend && GALLERY_PERF_METADATA=1 GALLERY_BASE_URL=http://localhost:5173 corepack pnpm exec playwright test tests/e2e/metadata-performance.spec.ts --project=chromium --headed`; for budget gating, `cd frontend && GALLERY_PERF_METADATA=1 GALLERY_PERF_METADATA_STRICT=1 corepack pnpm run perf:metadata` and `GALLERY_API_BASE_URL=http://localhost:4180 python3 scripts/perf_library_inspector.py` |
| `IndexStatusPanel.vue`, rebuild controls, index status copy                                                                                                                            | `cd frontend && corepack pnpm exec playwright test tests/e2e/index-status-panel.spec.ts tests/e2e/index-rebuild-flow.spec.ts --project=chromium`; `cd backend && python -m pytest -q tests/test_catalog_status_contract.py tests/test_catalog_status_endpoints.py tests/test_indexer_staging.py`                                                                                                                                                                                                                                                                                                                                              |
| Metadata index backend, rebuild/index queue, warm listing                                                                                                                              | `cd backend && python -m pytest -q tests/test_indexer_staging.py tests/test_warm_folder_listing.py tests/test_catalog_trigger_routing.py tests/test_catalog_status_endpoints.py`; `python3 scripts/perf_warm_listing.py --images 5000`                                                                                                                                                                                                                                                                                                                                                                                                        |
| `/api/browse`, ignore policy, natural sort, pagination                                                                                                                                 | `cd backend && python -m pytest -q tests/test_browse_api.py tests/test_warm_folder_listing.py`; `cd frontend && corepack pnpm exec playwright test tests/e2e/gallery-cache-revisit.spec.ts --project=chromium`                                                                                                                                                                                                                                                                                                                                                                                                                                |
| Metadata parsing/search/facets and Search V2 discovery                                                                                                                                 | `cd backend && python -m pytest -q tests/test_api_integration_metadata_search_facets.py tests/test_fielded_search_parser.py tests/test_facets.py tests/test_metadata_binary_sanitizer.py tests/test_app.py`; `cd frontend && corepack pnpm exec playwright test tests/e2e/search-fielded-ui.spec.ts tests/e2e/advanced-search-drawer.spec.ts tests/e2e/search-discovery-evolution.spec.ts --project=chromium`                                                                                                                                                                                                                                 |
| Metadata toolbar Select controls or sort controls                                                                                                                                      | `cd frontend && corepack pnpm exec playwright test tests/e2e/library-inspector.spec.ts --project=chromium`; `cd frontend && GALLERY_PERF_METADATA=1 corepack pnpm exec playwright test tests/e2e/metadata-performance.spec.ts --project=chromium --headed` with a running app                                                                                                                                                                                                                                                                                                                                                                 |
| PhotoSwipe/lightbox source policy                                                                                                                                                      | `cd frontend && corepack pnpm exec playwright test tests/e2e/lightbox-loading-policy.spec.ts tests/e2e/lightbox-visual-layer.spec.ts tests/e2e/mobile-lightbox-sheet.spec.ts --project=chromium`; `cd backend && python -m pytest -q tests/test_derivatives.py tests/test_api_integration_derivatives.py`                                                                                                                                                                                                                                                                                                                                     |
| Responsive/sidebar layout                                                                                                                                                              | `cd frontend && corepack pnpm exec playwright test tests/e2e/responsive-breakpoints.spec.ts tests/e2e/sidebar-trigger.spec.ts tests/e2e/mobile-lightbox-sheet.spec.ts --project=chromium`                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Query keys/cache behavior                                                                                                                                                              | `cd frontend && corepack pnpm exec playwright test tests/e2e/gallery-no-reload.spec.ts tests/e2e/gallery-cache-revisit.spec.ts tests/e2e/index-rebuild-flow.spec.ts --project=chromium`                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Settings/localStorage preferences                                                                                                                                                      | `cd frontend && corepack pnpm exec playwright test tests/e2e/settings-modal.spec.ts tests/e2e/lightbox-loading-policy.spec.ts --project=chromium`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| Tailwind/token/global CSS                                                                                                                                                              | `cd frontend && corepack pnpm run build`; `cd frontend && corepack pnpm exec playwright test tests/e2e/tailwind-phase0.spec.ts tests/e2e/tailwind-preflight.spec.ts --project=chromium`                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Debug helpers or test docs                                                                                                                                                             | `python3 scripts/check_test_docs.py`; `cd frontend && corepack pnpm run typecheck`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |

Before committing a new important test or debug helper, add a file header with `Purpose:`, `Guarantees:`, and `Run when:`. The checker enforces this for Playwright specs, backend test modules, `backend/debug/**/*.py`, and `frontend/src/debug/**/*.ts`.

Use `./test.sh docs` for the combined docs staleness, test header, matrix catalog drift, and metadata lifecycle ownership checks (equivalent to `python scripts/check_docs_staleness.py && python scripts/check_test_docs.py && python scripts/audit_test_matrix.py --fail-on-gaps && python scripts/check_metadata_lifecycle_ownership.py`).
Use `python3 scripts/audit_test_matrix.py` (without `--fail-on-gaps`) for a non-failing inventory that writes `docs/testing/test-gap-report.md` and `docs/testing/test-gap-report.json`.
