# Test Strategy

## Overview

The gallery test suite covers backend API endpoints, frontend UI contracts, and performance
budgets. Tests are categorized into deterministic (run in CI) and smoke/perf (require a running
app with real data).

---

## Test Tiers

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
bash scripts/test_backend_api_integration.sh
```
Or directly:
```bash
cd backend && pytest tests/test_api_integration_*.py -v
```

**Count:** 71 tests (5 files)

---

### Tier 3: Frontend Playwright Contract Tests

**Location:** `frontend/tests/`

**Existing:**
- `lightbox-loading-policy.spec.ts` — grid thumbnails, normal lightbox, zoom/fullscreen, preview fallback (7 tests)

**New:**
- `gallery-no-reload.spec.ts` — boot ID persistence, no full page reload, cursor-zero scan tracking (4 tests)
- `gallery-no-reload-real-backend.spec.ts` — no-reload E2E against real backend (requires running app) (2 tests)
- `gallery-cache-revisit.spec.ts` — soft navigation revisit, no duplicate cursor-zero scans (3 tests)
- `mobile-lightbox-sheet.spec.ts` — mobile lightbox, image navigation, metadata sheet open/close/repeat, copy buttons (6 tests)
- `search-fielded-ui.spec.ts` — plain search, fielded search, seed search, clear/restore, no-results, special chars (6 tests)
- `responsive-breakpoints.spec.ts` — mobile (375), tablet (768/834), desktop (1200/1920), resize transitions (10 tests)

**All Playwright tests use mocked API routes** (`page.route("**/api/**")`) for deterministic
behavior without requiring a running backend.

**Run (all contract tests):**
```bash
bash scripts/test_frontend_contract.sh
```
Or directly:
```bash
cd frontend && npm run build && npx playwright test tests/lightbox-loading-policy.spec.ts tests/gallery-no-reload.spec.ts tests/gallery-cache-revisit.spec.ts tests/mobile-lightbox-sheet.spec.ts tests/search-fielded-ui.spec.ts tests/responsive-breakpoints.spec.ts
```

---

### Tier 4: Perf Smoke Tests

**Location:** `frontend/tests/perf/`

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
bash scripts/test_perf_smoke.sh
```
Or individually:
```bash
cd frontend && npm run perf:album && npm run perf:lightbox
```

**Requires:** Running gallery app (`GALLERY_BASE_URL`), real album data
(`GALLERY_PERF_ALBUM_NAME`, `GALLERY_PERF_ALBUM_PATH`).

---

## Test Runner Scripts

| Script | Purpose | Requirements |
|---|---|---|
| `scripts/test_all.sh` | Run all deterministic tests (Tiers 1-3) | Python venv + npm |
| `scripts/test_backend_api_integration.sh` | Backend API integration tests | Python venv |
| `scripts/test_frontend_contract.sh` | Playwright contract tests | `npm run build` first |
| `scripts/test_perf_smoke.sh` | Perf smoke tests | Running app + real data |

---

## Missing / Remaining Gaps

1. **iPhone Safari real-device checks** — Mobile PhotoSwipe + VSBS metadata sheet gesture
   conflicts (swipe vs scroll) can only be fully validated on a real device with Safari
   WebKit. Playwright iPhone emulation approximates but does not perfectly replicate
   iOS gesture handling.

2. **No-reload E2E with real backend** — `gallery-no-reload-real-backend.spec.ts` exists
   but requires a running backend with `GALLERY_ROOT=/home/ubuntu/gallery-repo/test-images`.
   Not included in `test_all.sh` since it needs a real backend.

3. **Mobile sheet gesture conflict regression** — No automated test verifies that
   PhotoSwipe swipe and VSBS scroll do not conflict on mobile. Manual testing required.

4. **Warm indexed folder listing end-to-end** — No integration test verifies the full
   cycle: scan → index → warm listing → scan returns warm_db source.

5. **Thumbnail/preview cache separation with real backend** — Current cache separation
   tests verify cache key logic but not actual file-based cache serving with
   If-None-Match across multiple requests.
