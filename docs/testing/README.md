# Testing Guide

Last reviewed: 2026-06-17

This directory documents the test and debug surface for the gallery repo. Keep it focused on what each test protects, when to run it, and which debug helper to use before changing behavior.

## Test Categories

- Backend unit/integration tests: `backend/tests/test_*.py` cover FastAPI endpoint contracts, metadata parsing/search, scan behavior, indexer staging, warm listing, refresh, watcher, facets, and derivatives.
- Frontend Playwright/contract tests: `frontend/tests/*.spec.ts` cover gallery UI contracts with stubbed API responses, selected real-backend smoke paths, UI regressions, and diagnostics.
- Rebuild/index tests: `frontend/tests/index-rebuild-flow.spec.ts`, `frontend/tests/index-status-panel.spec.ts`, `backend/tests/test_api_integration_index_status.py`, `backend/tests/test_indexer_staging.py`, `backend/tests/test_warm_folder_listing.py`, and `backend/tests/test_scan_hot_path.py`.
- Library Inspector tests: `frontend/tests/library-inspector.spec.ts` and `backend/tests/test_library_inspector.py`.
- Metadata performance diagnostics: `frontend/tests/metadata-performance.spec.ts` measures `/metadata` navigation, sort, search, rendered row counts, thumbnail requests, and state restoration against a running gallery app.
- Lightbox tests: `frontend/tests/lightbox-loading-policy.spec.ts`, `frontend/tests/lightbox-visual-layer.spec.ts`, `frontend/tests/mobile-lightbox-sheet.spec.ts`, and derivative backend tests.
- Responsive tests: `frontend/tests/responsive-breakpoints.spec.ts`, `frontend/tests/sidebar-trigger.spec.ts`, mobile lightbox tests, and Tailwind migration/preflight tests.
- Performance contract tests: backend pytest hot-path tests such as `backend/tests/test_scan_hot_path.py` and `backend/tests/test_warm_folder_listing.py` prevent known slow-path regressions without relying on wall-clock timing.
- Performance diagnostics: `frontend/tests/metadata-performance.spec.ts`, `scripts/perf_scan.py`, `scripts/perf_library_inspector.py`, and `scripts/perf_warm_listing.py` emit compact timing reports.
- Gated performance smoke tests: `scripts/test_perf_smoke.sh` runs backend scan p95, backend Library Inspector p95, warm listing, album-open, and lightbox budgets against a running app/backend.
- Debug/diagnostic scripts: `frontend/src/debug/`, `scripts/debug_*`, perf fixture helpers, and perf scripts under `scripts/` and `frontend/tests/perf/`.

## Performance Fixtures

Use the deterministic fixture when comparing perf over time or before release:

`backend/.venv_linux/bin/python scripts/create_perf_fixture.py --clean --env-file /tmp/gallery_perf_fixture.env`

The generated env file contains `GALLERY_ROOT`, `GALLERY_METADATA_DB`, `GALLERY_THUMBNAIL_CACHE_DIR`, `GALLERY_PERF_ALBUM_NAME`, `GALLERY_PERF_ALBUM_PATH`, and scan/inspector defaults. Source it before starting the backend, or let the perf smoke runner do both:

`GALLERY_PERF_USE_FIXTURE=1 GALLERY_PERF_START_BACKEND=1 bash scripts/test_perf_smoke.sh`

Useful runner controls:

- `GALLERY_PERF_BACKEND_PORT=<port>` runs the managed backend on a non-default port.
- `GALLERY_PERF_REUSE_BACKEND=1` allows reusing an already-running backend at `GALLERY_API_BASE_URL`; leave it unset when using a fresh fixture so accidental DB/root mismatches fail clearly.
- `GALLERY_PERF_FIXTURE_IMAGES=<count>` changes deterministic fixture size.
- `GALLERY_PERF_WARM_LISTING_IMAGES=<count>` changes the local warm-listing benchmark size.
- `GALLERY_PERF_PYTHON=<python>` overrides the interpreter; by default the runner uses `backend/.venv_linux/bin/python` when available.
- `GALLERY_PERF_SKIP_FRONTEND=1` runs only backend scan, backend inspector, and warm-listing gates.

The perf smoke runner writes individual JSON reports plus aggregate summaries to `frontend/test-results/perf/`:

- `scan-report.json`
- `library-inspector-report.json`
- `warm-listing-report.json`
- `album-open-report.json`
- `lightbox-open-report.json`
- `lightbox-transition-report.json`
- `metadata-navigation-report.json`, `metadata-sort-report.json`, and `metadata-search-report.json` when metadata perf is run
- `perf-summary.json`
- `perf-summary.md`

For existing real data, keep setting `GALLERY_BASE_URL`, `GALLERY_API_BASE_URL`, `GALLERY_PERF_ALBUM_NAME`, `GALLERY_PERF_ALBUM_PATH`, and any budget overrides explicitly.

## Common Commands

Run from the repo root unless a command changes directory explicitly.

| Purpose | Command |
| --- | --- |
| Backend tests | `cd backend && python -m pytest -q` |
| Backend API integration subset | `bash scripts/test_backend_api_integration.sh` |
| Backend lint changed files | `bash scripts/lint_backend.sh` |
| Backend format check changed files | `bash scripts/format_backend_check.sh` |
| Frontend lint | `cd frontend && corepack pnpm run lint` |
| Frontend format check changed files | `cd frontend && corepack pnpm run format:check` |
| Frontend typecheck | `cd frontend && corepack pnpm run typecheck` |
| Frontend build | `cd frontend && corepack pnpm run build` |
| Frontend Playwright test | `cd frontend && corepack pnpm exec playwright test --project=chromium` |
| Targeted Playwright test | `cd frontend && corepack pnpm exec playwright test tests/lightbox-loading-policy.spec.ts --project=chromium` |
| Metadata performance diagnostic | `cd frontend && GALLERY_BASE_URL=http://localhost:5173 corepack pnpm exec playwright test tests/metadata-performance.spec.ts --project=chromium --headed` |
| Metadata performance strict gate | `cd frontend && GALLERY_PERF_METADATA_STRICT=1 corepack pnpm run perf:metadata` |
| Frontend contract subset | `bash scripts/test_frontend_contract.sh` |
| Deterministic suite | `bash scripts/test_all.sh` |
| Perf fixture generation | `backend/.venv_linux/bin/python scripts/create_perf_fixture.py --clean --env-file /tmp/gallery_perf_fixture.env` |
| Backend scan p95 perf | `GALLERY_API_BASE_URL=http://localhost:4180 GALLERY_PERF_SCAN_PATH=/path/to/album backend/.venv_linux/bin/python scripts/perf_scan.py` |
| Backend inspector p95 perf | `GALLERY_API_BASE_URL=http://localhost:4180 backend/.venv_linux/bin/python scripts/perf_library_inspector.py` |
| Warm listing local perf | `backend/.venv_linux/bin/python scripts/perf_warm_listing.py --images 5000` |
| Perf report summary | `backend/.venv_linux/bin/python scripts/summarize_perf_reports.py --results-dir frontend/test-results/perf` |
| Test gap audit | `python3 scripts/audit_test_matrix.py` |
| Perf smoke suite | `GALLERY_PERF_USE_FIXTURE=1 GALLERY_PERF_START_BACKEND=1 bash scripts/test_perf_smoke.sh` |
| Album perf test | `cd frontend && corepack pnpm run perf:album` |
| Lightbox perf test | `cd frontend && corepack pnpm run perf:lightbox` |
| Test/debug header checker | `python3 scripts/check_test_docs.py` |
| List files checked by header checker | `python3 scripts/check_test_docs.py --list` |

Playwright starts Vite through `frontend/playwright.config.ts`. Backend-backed Playwright tests require a running backend and appropriate fixture paths.

Ruff backend lint/format checks and frontend Prettier checks are intentionally changed-file checks. They use `origin/main` as the default comparison base when it exists, plus local working-tree and untracked files. Override the backend base with `RUFF_BASE=<ref>` and the frontend Prettier base with `PRETTIER_BASE=<ref>`.

## When Changing X, Run Y

| Change area | Run |
| --- | --- |
| `LibraryInspector.vue`, inspector query hooks, inspector metadata details | `cd frontend && corepack pnpm exec playwright test tests/library-inspector.spec.ts --project=chromium`; `cd backend && python -m pytest -q tests/test_library_inspector.py`; for performance diagnostics with a running app, `cd frontend && GALLERY_BASE_URL=http://localhost:5173 corepack pnpm exec playwright test tests/metadata-performance.spec.ts --project=chromium --headed`; for budget gating, `cd frontend && GALLERY_PERF_METADATA_STRICT=1 corepack pnpm run perf:metadata` and `GALLERY_API_BASE_URL=http://localhost:4180 python3 scripts/perf_library_inspector.py` |
| `IndexStatusPanel.vue`, rebuild controls, index status copy | `cd frontend && corepack pnpm exec playwright test tests/index-status-panel.spec.ts tests/index-rebuild-flow.spec.ts --project=chromium`; `cd backend && python -m pytest -q tests/test_api_integration_index_status.py tests/test_indexer_staging.py` |
| Metadata index backend, rebuild/index queue, warm listing | `cd backend && python -m pytest -q tests/test_indexer_staging.py tests/test_warm_folder_listing.py tests/test_scan_hot_path.py tests/test_api_integration_index_status.py`; `python3 scripts/perf_warm_listing.py --images 5000` |
| `/api/scan`, ignore policy, natural sort, pagination | `cd backend && python -m pytest -q tests/test_api_integration_scan.py tests/test_scan_hot_path.py tests/test_warm_folder_listing.py`; `cd frontend && corepack pnpm exec playwright test tests/gallery-cache-revisit.spec.ts --project=chromium`; with a running backend, `GALLERY_API_BASE_URL=http://localhost:4180 GALLERY_PERF_SCAN_PATH=/path/to/album python3 scripts/perf_scan.py` |
| Metadata parsing/search/facets | `cd backend && python -m pytest -q tests/test_api_integration_metadata_search_facets.py tests/test_fielded_search_parser.py tests/test_facets.py tests/test_metadata_binary_sanitizer.py tests/test_app.py`; `cd frontend && corepack pnpm exec playwright test tests/search-fielded-ui.spec.ts tests/advanced-search-drawer.spec.ts --project=chromium` |
| Metadata toolbar Select controls or sort controls | `cd frontend && corepack pnpm exec playwright test tests/library-inspector.spec.ts --project=chromium`; `cd frontend && corepack pnpm exec playwright test tests/metadata-performance.spec.ts --project=chromium --headed` with a running app |
| PhotoSwipe/lightbox source policy | `cd frontend && corepack pnpm exec playwright test tests/lightbox-loading-policy.spec.ts tests/lightbox-visual-layer.spec.ts tests/mobile-lightbox-sheet.spec.ts --project=chromium`; `cd backend && python -m pytest -q tests/test_derivatives.py tests/test_api_integration_derivatives.py` |
| Responsive/sidebar layout | `cd frontend && corepack pnpm exec playwright test tests/responsive-breakpoints.spec.ts tests/sidebar-trigger.spec.ts tests/mobile-lightbox-sheet.spec.ts --project=chromium` |
| Query keys/cache behavior | `cd frontend && corepack pnpm exec playwright test tests/gallery-no-reload.spec.ts tests/gallery-cache-revisit.spec.ts tests/index-rebuild-flow.spec.ts --project=chromium` |
| Settings/localStorage preferences | `cd frontend && corepack pnpm exec playwright test tests/settings-modal.spec.ts tests/lightbox-loading-policy.spec.ts --project=chromium` |
| Tailwind/token/global CSS | `cd frontend && corepack pnpm run build`; `cd frontend && corepack pnpm exec playwright test tests/tailwind-phase0.spec.ts tests/tailwind-preflight.spec.ts --project=chromium` |
| Debug helpers or test docs | `python3 scripts/check_test_docs.py`; `cd frontend && corepack pnpm run typecheck` |

Before committing a new important test or debug helper, add a file header with `Purpose:`, `Guarantees:`, and `Run when:`. The checker enforces this for Playwright specs, backend test modules, `backend/debug/**/*.py`, and `frontend/src/debug/**/*.ts`.

Use `python3 scripts/audit_test_matrix.py` when you need an inventory of collected tests, catalog drift, backend coverage gaps, frontend coverage artifact status, and available perf JSON reports. It writes `docs/testing/test-gap-report.md` and `docs/testing/test-gap-report.json`.
