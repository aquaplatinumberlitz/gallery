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
PROFILE_ENDPOINTS=/api/scan,/api/metadata,/api/thumbnail

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
- duplicate scan cursor=0 count > 1
- scan duration > `GALLERY_PERF_SCAN_BUDGET_MS` (default 500ms)
- first thumbnail start > `GALLERY_PERF_FIRST_THUMB_BUDGET_MS` (default 1000ms)
- thumbnail p95 > `GALLERY_PERF_THUMB_P95_BUDGET_MS` (default 1200ms)

## SQLite Metadata Cache

The image dimension cache lives in the same SQLite DB as the search index.

```bash
# Default location
ls -la backend/.cache/gallery_metadata.db

# Override via env var:
GALLERY_METADATA_DB=/custom/path/gallery_metadata.db
```

Inspect cache contents:
```bash
sqlite3 backend/.cache/gallery_metadata.db \
  "SELECT path, mtime, size, width, height, format, mode, updated_at
   FROM image_metadata
   WHERE width IS NOT NULL
   ORDER BY updated_at DESC
   LIMIT 10;"
```

### Cache schema (image_metadata table)

| Column | Type | Description |
|--------|------|-------------|
| path | TEXT PRIMARY KEY | Resolved absolute path |
| mtime | REAL | File modification time (for staleness check) |
| size | INTEGER | File size in bytes (for staleness check) |
| width | INTEGER | Image width in pixels |
| height | INTEGER | Image height in pixels |
| format | TEXT | Image format (PNG, JPEG, WebP, etc.) |
| mode | TEXT | PIL image mode (RGB, RGBA, etc.) |
| has_alpha | INTEGER | 1 if image has alpha channel |
| prompt / negative_prompt / model / sampler / seed | TEXT | AI generation metadata |
| indexed_at / updated_at | REAL | Timestamps |

### Cache population

- **Thumbnail endpoint** (`/api/thumbnail`) — when it opens an image with PIL to render a WebP thumbnail, it calls `upsert_image_dimensions()` to cache width/height.
- **Metadata endpoint** (`/api/metadata`) — when it parses full AI generation metadata, it calls `upsert_metadata_result()` to cache everything.
- **Scan endpoint** (`/api/scan`) — does a batch lookup via `get_cached_dimensions_for_files()`, returns cached dimensions if mtime+size match. Does NOT open images.

Stale entries (mtime/size changed) are automatically ignored — the cache query validates both fields.

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
| `PROFILE_ENDPOINTS` | `/api/scan,/api/metadata,/api/thumbnail` | Comma-separated endpoints to profile |
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
