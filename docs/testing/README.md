# Testing Guide

This directory documents the test and debug surface for the gallery repo. Keep it focused on what each test protects, when to run it, and which debug helper to use before changing behavior.

## Test Categories

- Backend unit/integration tests: `backend/tests/test_*.py` cover FastAPI endpoint contracts, metadata parsing/search, scan behavior, indexer staging, warm listing, refresh, watcher, facets, and derivatives.
- Frontend Playwright/contract tests: `frontend/tests/*.spec.ts` cover gallery UI contracts with stubbed API responses and selected real-backend smoke paths.
- Rebuild/index tests: `frontend/tests/index-rebuild-flow.spec.ts`, `frontend/tests/index-status-panel.spec.ts`, `backend/tests/test_api_integration_index_status.py`, `backend/tests/test_indexer_staging.py`, `backend/tests/test_warm_folder_listing.py`, and `backend/tests/test_scan_hot_path.py`.
- Library Inspector tests: `frontend/tests/library-inspector.spec.ts` and `backend/tests/test_library_inspector.py`.
- Lightbox tests: `frontend/tests/lightbox-loading-policy.spec.ts`, `frontend/tests/lightbox-visual-layer.spec.ts`, `frontend/tests/mobile-lightbox-sheet.spec.ts`, and derivative backend tests.
- Responsive tests: `frontend/tests/responsive-breakpoints.spec.ts`, `frontend/tests/sidebar-trigger.spec.ts`, mobile lightbox tests, and Tailwind migration/preflight tests.
- Debug/diagnostic scripts: `frontend/src/debug/`, `scripts/debug_*`, and perf scripts under `scripts/` and `frontend/tests/perf/`.

## Common Commands

Run from the repo root unless a command changes directory explicitly.

| Purpose | Command |
| --- | --- |
| Backend tests | `cd backend && python -m pytest -q` |
| Backend API integration subset | `bash scripts/test_backend_api_integration.sh` |
| Frontend typecheck | `cd frontend && npm run typecheck` |
| Frontend build | `cd frontend && npm run build` |
| Frontend Playwright test | `cd frontend && npx playwright test --project=chromium` |
| Targeted Playwright test | `cd frontend && npx playwright test tests/lightbox-loading-policy.spec.ts --project=chromium` |
| Frontend contract subset | `bash scripts/test_frontend_contract.sh` |
| Deterministic suite | `bash scripts/test_all.sh` |
| Perf smoke suite | `bash scripts/test_perf_smoke.sh` |
| Album perf test | `cd frontend && npm run perf:album` |
| Lightbox perf test | `cd frontend && npm run perf:lightbox` |
| Test/debug header checker | `python3 scripts/check_test_docs.py` |
| List files checked by header checker | `python3 scripts/check_test_docs.py --list` |

Playwright starts Vite through `frontend/playwright.config.ts`. Backend-backed Playwright tests require a running backend and appropriate fixture paths.

## When Changing X, Run Y

| Change area | Run |
| --- | --- |
| `LibraryInspector.vue`, inspector query hooks, inspector metadata details | `cd frontend && npx playwright test tests/library-inspector.spec.ts --project=chromium`; `cd backend && python -m pytest -q tests/test_library_inspector.py` |
| `IndexStatusPanel.vue`, rebuild controls, index status copy | `cd frontend && npx playwright test tests/index-status-panel.spec.ts tests/index-rebuild-flow.spec.ts --project=chromium`; `cd backend && python -m pytest -q tests/test_api_integration_index_status.py tests/test_indexer_staging.py` |
| Metadata index backend, rebuild/index queue, warm listing | `cd backend && python -m pytest -q tests/test_indexer_staging.py tests/test_warm_folder_listing.py tests/test_scan_hot_path.py tests/test_api_integration_index_status.py` |
| `/api/scan`, ignore policy, natural sort, pagination | `cd backend && python -m pytest -q tests/test_api_integration_scan.py tests/test_scan_hot_path.py tests/test_warm_folder_listing.py`; `cd frontend && npx playwright test tests/gallery-cache-revisit.spec.ts --project=chromium` |
| Metadata parsing/search/facets | `cd backend && python -m pytest -q tests/test_api_integration_metadata_search_facets.py tests/test_fielded_search_parser.py tests/test_facets.py tests/test_app.py`; `cd frontend && npx playwright test tests/search-fielded-ui.spec.ts tests/advanced-search-drawer.spec.ts --project=chromium` |
| PhotoSwipe/lightbox source policy | `cd frontend && npx playwright test tests/lightbox-loading-policy.spec.ts tests/lightbox-visual-layer.spec.ts tests/mobile-lightbox-sheet.spec.ts --project=chromium`; `cd backend && python -m pytest -q tests/test_derivatives.py tests/test_api_integration_derivatives.py` |
| Responsive/sidebar layout | `cd frontend && npx playwright test tests/responsive-breakpoints.spec.ts tests/sidebar-trigger.spec.ts tests/mobile-lightbox-sheet.spec.ts --project=chromium` |
| Query keys/cache behavior | `cd frontend && npx playwright test tests/gallery-no-reload.spec.ts tests/gallery-cache-revisit.spec.ts tests/index-rebuild-flow.spec.ts --project=chromium` |
| Settings/localStorage preferences | `cd frontend && npx playwright test tests/settings-modal.spec.ts tests/lightbox-loading-policy.spec.ts --project=chromium` |
| Tailwind/token/global CSS | `cd frontend && npm run build`; `cd frontend && npx playwright test tests/tailwind-phase0.spec.ts tests/tailwind-preflight.spec.ts --project=chromium` |
| Debug helpers or test docs | `python3 scripts/check_test_docs.py`; `cd frontend && npm run typecheck` |

Before committing a new important test or debug helper, add a file header with `Purpose:`, `Guarantees:`, and `Run when:`. The checker enforces this for Playwright specs, backend test modules, `backend/debug/**/*.py`, and `frontend/src/debug/**/*.ts`.
