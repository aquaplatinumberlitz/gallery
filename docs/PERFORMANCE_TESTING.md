# Performance Testing

This document describes how to measure and profile Gallery API performance.

## Quick Start

### Prometheus Metrics

The backend exposes Prometheus metrics at `/metrics` when enabled.

```bash
# Default: enabled in dev, disabled in PRODUCTION=1
# Override:
ENABLE_METRICS=1

# Check it works:
curl http://localhost:8000/metrics
```

Metrics include:
- `http_request_duration_seconds` (latency histogram)
- `http_request_count_total` (request count by method/status/route)
- Route-level labels only — no per-path cardinality

Disable in production:
```bash
ENABLE_METRICS=0
```

### pyinstrument Profiling

Profile individual API endpoints to find bottlenecks.

```bash
# Enable profiler
ENABLE_PROFILER=1

# Which endpoints to profile (comma-separated, default shown)
PROFILE_ENDPOINTS=/api/scan,/api/metadata,/api/thumbnail,/api/preview

# Then make a request — HTML profile will be saved to:
ls backend/profiles/
# e.g. _api_scan_20260409_142530.html
```

Profiles are saved to `backend/profiles/` (gitignored). Open the HTML files in a browser to view the flame chart / call tree.

Profiling is off by default and adds zero overhead when disabled.

### Backend Scan Perf Script

Measure `/api/scan` latency directly without the frontend.

```bash
# Default settings
python scripts/perf_scan.py

# Or with custom env vars:
GALLERY_API_BASE_URL=http://localhost:8000 \
GALLERY_PERF_SCAN_PATH="/home/ubuntu/gallery-repo/test mika" \
GALLERY_PERF_SCAN_ITERATIONS=10 \
GALLERY_PERF_SCAN_P95_BUDGET_MS=500 \
python scripts/perf_scan.py
```

Output (compact JSON):
```json
{"url":"http://localhost:8000/api/scan","path":"...","iterations":10,
 "min_ms":12.34,"p50_ms":13.56,"p95_ms":15.78,"max_ms":18.90,
 "image_count":50,"folder_count":0,"total_images":50,"next_cursor":null,
 "budget_p95_ms":500}
```

Exit code 1 if p95 exceeds budget.

### Playwright Album Open Perf Test

Measures end-to-end album open performance: scan duration, thumbnail loading.

```bash
# Install browser (one-time)
cd frontend
npm install
npx playwright install chromium

# Run perf test (headless)
npm run perf:album

# Run with browser visible (debug)
npm run perf:album:headed
```

### How the test works

1. Opens the app at `GALLERY_BASE_URL`.
2. Waits for the target album card to be visible.
3. **Clears the network tracker** and sets `clickTime` — this ensures *only* network activity caused by the album click is measured.
4. Clicks the album card.
5. Collects all `/api/scan` and `/api/thumbnail` requests.
6. Filters samples by album path when `GALLERY_PERF_ALBUM_PATH` is set (prevents root `/api/scan` or unrelated thumbnails from polluting results).
7. Asserts budgets and prints a structured JSON report.

**Pre-click network is intentionally ignored** — the tracker refuses to record samples before `clickTime` is set. This prevents false duplicates and wrong `scanSamples[0]`.

Config via env vars:
```bash
GALLERY_BASE_URL=https://150.230.56.153 \
GALLERY_PERF_ALBUM_NAME="test mika" \
GALLERY_PERF_ALBUM_PATH="/home/ubuntu/gallery-repo/test mika" \
GALLERY_PERF_SCAN_BUDGET_MS=500 \
GALLERY_PERF_FIRST_THUMB_BUDGET_MS=1000 \
GALLERY_PERF_THUMB_P95_BUDGET_MS=1200 \
npm run perf:album
```

Test measures:
- scan start after click (ms)
- scan duration (ms)
- first thumbnail start after click (ms)
- last thumbnail end after click (ms)
- thumbnail count
- thumbnail p50/p95/max latency (ms)
- duplicate `/api/scan` cursor=0 count

Fail budgets:
- thumbnail p95 > `GALLERY_PERF_THUMB_P95_BUDGET_MS` (default 1200ms)

## Lightbox Perf Test

Measures lightbox open and transition performance with the derivative-first policy: time to visible, preview load latency, on-demand original load after zoom, transition preview load latency, endpoint usage, and aspect ratio integrity.

```bash
# Run lightbox perf tests (headless)
npm run perf:lightbox

# Run with browser visible (debug)
npm run perf:lightbox:headed
```

### How the tests work

**Test 1: lightbox opens first photo**
1. Navigates to album and waits for photo cards.
2. Clears the network tracker and sets clickTime.
3. Clicks the first photo card.
4. Measures `lightboxVisible`: time until lightbox overlay is visible.
5. Measures `lightboxPreviewLoaded`: time until the main `.pswp__img` is fully loaded (`img.complete`).
6. Verifies normal open used `/api/preview` and did not request `/api/image`.
7. Presses the PhotoSwipe zoom shortcut and measures `lightboxOriginalLoadedOnZoom`.
8. Checks display dimensions are reasonable (>300px in both axes).

**Test 2: lightbox transitions to next image**
1. Opens the lightbox on the first photo (reuses setup).
2. Clears the tracker, presses ArrowRight.
3. Measures time until the image `src` changes (next photo starts loading).
4. Measures `transitionPreviewLoaded`: time until the new image is fully loaded.
5. Verifies the displayed aspect ratio matches the natural aspect ratio within 20%.
6. Verifies transition navigation does not request `/api/image`.

### Config via env vars
```bash
GALLERY_BASE_URL=http://localhost:5173 \
GALLERY_PERF_ALBUM_NAME="test mika" \
GALLERY_PERF_ALBUM_PATH="/home/ubuntu/gallery-repo/test mika" \
GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS=800 \
GALLERY_PERF_LIGHTBOX_PREVIEW_BUDGET_MS=1500 \
GALLERY_PERF_LIGHTBOX_ORIGINAL_ZOOM_BUDGET_MS=2500 \
GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS=700 \
npm run perf:lightbox
```

### Budgets
| Env Var | Default | Description |
|---------|---------|-------------|
| `GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS` | `1500` | Max ms for lightbox to become visible after click |
| `GALLERY_PERF_LIGHTBOX_PREVIEW_BUDGET_MS` | `4000` | Max ms for preview image to load after click |
| `GALLERY_PERF_LIGHTBOX_ORIGINAL_ZOOM_BUDGET_MS` | `5000` | Max ms for original image to load after zoom trigger |
| `GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS` | `3000` | Max ms for next preview image to load after ArrowRight |

## Known Limitations

- **Cold cache**: When first browsing a new album, `/api/scan` returns `width=null, height=null` for all images because the cache hasn't been populated yet. Dimensions appear after the first thumbnail load or metadata fetch.
- **Background indexing**: Directory tree index runs with `include_metadata=False` during scan, meaning full metadata (prompt, models) is only indexed when images are actually opened in the lightbox or thumbnailed.
- **SQLite concurrency**: WAL mode + busy_timeout=5000 handle concurrent FastAPI workers. Cache failure never breaks scan — errors are silently caught and dimensions return null.
- **Metrics cardinality**: Route-level labels only. Adding per-path labels would create high-cardinality metrics and is intentionally avoided.

## Env Var Reference

| Env Var | Default | Description |
|---------|---------|-------------|
| `ENABLE_METRICS` | `1` (dev), `0` (prod) | Enable Prometheus metrics at `/metrics` |
| `ENABLE_PROFILER` | `0` | Enable pyinstrument profiling |
| `PROFILE_ENDPOINTS` | `/api/scan,/api/metadata,/api/thumbnail,/api/preview` | Comma-separated endpoints to profile |
| `GALLERY_METADATA_DB` | `backend/.cache/gallery_metadata.db` | Path to SQLite metadata cache DB |
| `SCAN_PERF_LOGS` | `1` (dev), `0` (prod) | Enable verbose scan performance log output |
| `GALLERY_BASE_URL` | `http://localhost:5173` | Frontend URL for Playwright tests |
| `GALLERY_API_BASE_URL` | `http://localhost:8000` | Backend API URL for perf scripts |
| `GALLERY_PERF_ALBUM_NAME` | `test mika` | Album name for Playwright test |
| `GALLERY_PERF_ALBUM_PATH` | `""` | Album path to filter scan/thumbnail samples; prevents root-scan pollution |
| `GALLERY_PERF_SCAN_BUDGET_MS` | `500` | Max acceptable scan duration |
| `GALLERY_PERF_FIRST_THUMB_BUDGET_MS` | `1000` | Max acceptable first thumbnail start |
| `GALLERY_PERF_THUMB_P95_BUDGET_MS` | `1200` | Max acceptable thumbnail p95 latency |
| `GALLERY_PERF_SCAN_ITERATIONS` | `10` | Iterations for backend perf script |
| `GALLERY_PERF_SCAN_P95_BUDGET_MS` | `500` | p95 budget for backend perf script |
| `GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS` | `1500` | Max acceptable lightbox open visible time |
| `GALLERY_PERF_LIGHTBOX_PREVIEW_BUDGET_MS` | `4000` | Max acceptable lightbox preview load time |
| `GALLERY_PERF_LIGHTBOX_ORIGINAL_ZOOM_BUDGET_MS` | `5000` | Max acceptable original load time after zoom |
| `GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS` | `3000` | Max acceptable lightbox next-preview transition time |
