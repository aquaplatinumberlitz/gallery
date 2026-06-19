# Test Strategy

> **DEPRECATED:** Xem [docs/testing/TESTING_STRATEGY.md](../testing/TESTING_STRATEGY.md)

This file is retained for historical tier details. Current CI selection, browser policy, and
coverage gates are defined by the canonical strategy linked above and were verified on
2026-06-19.

## Overview

The gallery test suite covers backend API endpoints, frontend UI contracts, and performance
budgets. Tests are categorized into deterministic (run in CI) and smoke/perf (require a running
app with real data).

---

## Current CI Policy

| CI job | Verified commands |
|---|---|
| `lint` | Full-codebase Ruff lint/format, ESLint source/tests, and Prettier |
| `test:unit` | Backend pytest with `--cov-fail-under=85`; frontend Vitest/V8 coverage; frontend build/typecheck |
| `test:e2e (1/4..4/4)` | Complete functional Playwright suite sharded across four Chromium jobs with deterministic FastAPI fixtures |
| `test:perf` | Complete Playwright perf suite, one worker, deterministic fixture |

- Nightly: N/A (not configured).
- WebKit smoke: N/A.
- Full-stack E2E and Playwright perf are selected on every push/PR.
- Backend coverage threshold: 85%, enforced in CI and `./test.sh unit`.
- Frontend Vitest coverage is uploaded; no numeric CI threshold is configured.

## Test Tiers

### Tier 0: Static Quality Gates

**Backend:**

- `./test.sh lint` runs Ruff lint and `ruff format --check` on all backend/script Python files.
- Install dev tooling with `pip install -r backend/requirements-dev.txt`.

Ruff is configured in `pyproject.toml` with correctness, bug-prone, import-order, and Python-upgrade rules.

**Frontend:**

- `corepack pnpm run lint` runs ESLint on source, tests, and config files.
- `corepack pnpm run format:check` runs Prettier across the full configured frontend scope.
- `corepack pnpm run typecheck` runs `vue-tsc --noEmit`.

Frontend package management is pinned through `frontend/package.json` (`packageManager: pnpm@11.5.2`) and `frontend/pnpm-lock.yaml`. Do not reintroduce `package-lock.json`.

---

### Tier 1: Backend Unit Tests

**Location:** `backend/tests/` (existing files)

**What they test:**
- Hot path contracts (scan must not open images)
- Derivative generation (thumbnail/preview size, cache key separation)
- Folder count scanning
- Warm indexed folder listing
- Scheduled refresh
- File watcher
- Metadata indexer staging
- Fielded search parser

**Run:**
```bash
cd backend && pytest -q
```

**Count:** 215 existing tests (before integration tests added)

---

### Tier 2: Backend API Integration Tests

**Location:** `backend/tests/test_api_integration_*.py`

**What they test:**
- Health endpoint and path safety enforcement
- `/api/scan` response shape, filtering, natural sort, pagination
- `/api/image`, `/api/thumbnail`, `/api/preview` with cache header/ETag/304
- Thumbnail vs preview cache key separation (512 must not reuse 1440)
- `/api/metadata` parsing of embedded PNG parameters
- `/api/search` plain and fielded queries (prompt:, seed:, model:)
- `/api/facets` deterministic counts
- `/api/index/status` with enabled/disabled indexer

**Fixtures (in `backend/tests/conftest.py`):**
- `isolated_gallery_root` — temp GALLERY_ROOT
- `isolated_metadata_db` — temp SQLite DB (GALLERY_METADATA_DB env var)
- `isolated_thumbnail_cache` — temp diskcache directory (GALLERY_THUMBNAIL_CACHE_DIR env var)
- `disable_background_services` — disables indexer/watcher/refresh/warm listing
- `isolated_app` — FastAPI TestClient with all paths isolated
- `temp_gallery` — album_a/ album_b/ with real JPEG and PNG test images
- `temp_gallery_with_metadata` — test PNGs with embedded AI metadata

**Test image helpers (in `backend/tests/conftest.py`):**
- `create_test_png(path)` — writes actual PNG bytes via PIL, asserts format
- `create_test_jpeg(path)` — writes actual JPEG bytes via PIL, asserts format
- `create_test_image(path)` — auto-detects format from extension; falls back to PNG for .webp (no WebP encoder in Pillow 12.0.0)
- `create_test_png_with_metadata(path, ...)` — writes PNG with A1111-style tEXt parameters chunk

**Testability patches made to backend/config.py:**
- `GALLERY_THUMBNAIL_CACHE_DIR` env var → `THUMBNAIL_CACHE_DIR`
- `GALLERY_METADATA_DB` env var → `GALLERY_METADATA_DB`

**Run:**
```bash
./test.sh backend-api
```
Or directly:
```bash
cd backend && pytest tests/test_api_integration_*.py -v
```

**Count:** 71 tests (5 files)

---

### Tier 3: Frontend Playwright Contract Tests

**Location:** `frontend/tests/e2e/`

**Existing:**
- `lightbox-loading-policy.spec.ts` — grid thumbnails, normal lightbox, zoom/fullscreen, preview fallback (7 tests)

**New:**
- `gallery-no-reload.spec.ts` — boot ID persistence, no full page reload, cursor-zero scan tracking (4 tests)
- `gallery-no-reload-real-backend.spec.ts` — no-reload E2E against real backend (requires running app) (2 tests)
- `gallery-cache-revisit.spec.ts` — soft navigation revisit, no duplicate cursor-zero scans (3 tests)
- `mobile-lightbox-sheet.spec.ts` — mobile lightbox, image navigation, metadata sheet open/close/repeat, copy buttons (6 tests)
- `search-fielded-ui.spec.ts` — plain search, fielded search, seed search, clear/restore, no-results, special chars (6 tests)
- `responsive-breakpoints.spec.ts` — mobile (375), tablet (768/834), desktop (1200/1920), resize transitions (10 tests)

Most Playwright contract tests mock API routes; selected full-stack specs use the managed
deterministic FastAPI fixture.

**Run (all contract tests):**
```bash
./test.sh e2e
```
Or directly:
```bash
cd frontend && corepack pnpm run build && corepack pnpm exec playwright test tests/e2e/lightbox-loading-policy.spec.ts tests/e2e/gallery-no-reload.spec.ts tests/e2e/gallery-cache-revisit.spec.ts tests/e2e/mobile-lightbox-sheet.spec.ts tests/e2e/search-fielded-ui.spec.ts tests/e2e/responsive-breakpoints.spec.ts
```

---

### Tier 4: Perf Smoke Tests

**Location:** `frontend/tests/e2e/perf/`

**Existing:**
- `album-open.perf.spec.ts` — scan latency, first thumbnail visible, thumbnail P95 (1 test)
- `lightbox.perf.spec.ts` — lightbox open budget, transition budget, preview vs original checks (2 tests)

**Perf fail conditions:**
- Duplicate initial `/api/scan` (cursor=0 count > 1)
- Normal lightbox open loads `/api/image` instead of `/api/preview`
- `/api/preview` does not load at all
- First visible thumbnails regress beyond budget
- Transition loads original instead of preview

**Run:**
```bash
./test.sh perf-smoke
```
Or individually:
```bash
cd frontend && corepack pnpm run perf:album && corepack pnpm run perf:lightbox
```

**Requires:** Running gallery app (`GALLERY_BASE_URL`), real album data
(`GALLERY_PERF_ALBUM_NAME`, `GALLERY_PERF_ALBUM_PATH`).

---

## Test Runner

Use `./test.sh help` as the single developer entrypoint. The primary commands are:

| Command | Purpose |
|---|---|
| `./test.sh fast` | Full lint/format, unit coverage, and frontend build |
| `./test.sh full` | Sequential local equivalent of all CI layers |
| `./test.sh e2e` | Managed deterministic functional Playwright suite |
| `./test.sh perf` | Managed deterministic Playwright perf suite |
| `./test.sh perf-smoke` | Extended backend + browser performance diagnostics |

Shell implementation details are kept under `scripts/internal/` and are not public developer commands.

---

## Missing / Remaining Gaps

1. **iPhone Safari real-device checks** — Mobile PhotoSwipe + VSBS metadata sheet gesture
   conflicts (swipe vs scroll) can only be fully validated on a real device with Safari
   WebKit. Playwright iPhone emulation approximates but does not perfectly replicate
   iOS gesture handling.

2. **Mobile sheet gesture conflict regression** — No automated test verifies that
   PhotoSwipe swipe and VSBS scroll do not conflict on mobile. Manual testing required.

3. **Warm indexed folder listing end-to-end** — No integration test verifies the full
   cycle: scan → index → warm listing → scan returns warm_db source.

4. **Thumbnail/preview cache separation with real backend** — Current cache separation
   tests verify cache key logic but not actual file-based cache serving with
   If-None-Match across multiple requests.
