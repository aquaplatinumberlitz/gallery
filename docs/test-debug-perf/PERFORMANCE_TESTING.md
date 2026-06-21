# Performance Testing

This document describes how to measure and profile Gallery API performance.

## Perf budgets — single source of truth

Every perf budget in the repo lives in **`scripts/perf_budgets.toml`**. That file
is the canonical source for all numeric budgets consumed by:

- `scripts/perf_scan.py` — `[scan]`
- `scripts/perf_library_inspector.py` — `[inspector]`
- `scripts/perf_warm_listing.py` — `[warm_listing]`
- `scripts/bench_search.py` — `[search]` + `[inspector_metadata]`
- `scripts/bench_thumbnail.py` — `[thumbnail]`
- `frontend/tests/e2e/perf/album-open.perf.spec.ts` — `[album_open]`
- `frontend/tests/e2e/perf/lightbox.perf.spec.ts` — `[lightbox]`
- `frontend/tests/e2e/metadata-performance.spec.ts` (documented) — `[metadata_nav]`

The Playwright specs read their budgets from
`frontend/tests/e2e/perf/perf-budgets.json`, which mirrors the relevant TOML
sections. The Python scripts read the TOML directly via `scripts/perf_lib.py`.

### Adding a new budget

1. Add a `[section]` block to `scripts/perf_budgets.toml` with the numeric
   fields and a `description`.
2. If a Playwright spec consumes it, mirror the section into
   `frontend/tests/e2e/perf/perf-budgets.json`.
3. Register the consumer in `BUDGET_CONSUMERS` inside
   `scripts/check_perf_budgets.py`.
4. Run `python scripts/check_perf_budgets.py` — it must pass. The validator
   enforces both directions: every TOML section needs a consumer, and every
   perf test's budget env vars need a TOML entry.

### Validating budget coverage

```bash
python scripts/check_perf_budgets.py
# perf budget coverage OK: 9 sections, 3 mirrored into perf-budgets.json
```

The validator checks that:

- every TOML section has at least one registered consumer file
- every consumer file actually exists
- the env-var overrides for each section appear in at least one consumer
- `perf-budgets.json` is in sync with the TOML for the mirrored sections
- perf specs only reference registered budget env vars

### Overriding a budget locally

All scripts and specs accept env-var overrides that take precedence over the
TOML defaults — see the "Env Var Reference" table at the bottom of this doc
for the override names. The TOML remains the source of truth for committed
budgets; env vars are for one-off local runs.

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
# Default settings (budget read from scripts/perf_budgets.toml[scan].p95_ms)
python scripts/perf_scan.py

# Or with custom env vars (env var overrides the TOML budget):
GALLERY_API_BASE_URL=http://localhost:8000 \
GALLERY_PERF_SCAN_PATH="/home/ubuntu/gallery-repo/test mika" \
GALLERY_PERF_SCAN_ITERATIONS=10 \
GALLERY_PERF_SCAN_P95_BUDGET_MS=500 \
python scripts/perf_scan.py
```

Output (compact JSON):

```json
{
  "url": "http://localhost:8000/api/scan",
  "path": "...",
  "iterations": 10,
  "min_ms": 12.34,
  "p50_ms": 13.56,
  "p95_ms": 15.78,
  "max_ms": 18.9,
  "image_count": 50,
  "folder_count": 0,
  "total_images": 50,
  "next_media_cursor": null,
  "budget_p95_ms": 500,
  "budget_source": "scripts/perf_budgets.toml[scan].p95_ms"
}
```

Exit code 1 if p95 exceeds budget.

### Library Inspector Perf Script

```bash
python scripts/perf_library_inspector.py
# budget: scripts/perf_budgets.toml[inspector].p95_ms (default 500)
```

### Warm Listing Perf Script

```bash
python scripts/perf_warm_listing.py --images 5000
# budget: scripts/perf_budgets.toml[warm_listing].budget_ms (default 500)
```

### Search Bench

```bash
python scripts/bench_search.py
# budgets: [search].p95_ms (default 300) + [inspector_metadata].p95_ms (default 200)
```

### Thumbnail Cold/Warm Bench

```bash
python scripts/bench_thumbnail.py
# budgets: [thumbnail].cold_p95_ms (default 1000) + [thumbnail].warm_p95_ms (default 50)
# samples 5 distinct images from test-images/a1111 by default
```

### Playwright Album Open Perf Test

For the deterministic CI-equivalent browser perf suite, run from the repository root:

```bash
./test.sh perf
```

This command creates a temporary fixture, starts FastAPI and Vite on free ports, runs all
`frontend/tests/e2e/perf/` specs with one worker, and cleans up. Use the lower-level commands
below only when profiling an already-running app or custom real dataset.

Measures end-to-end album open performance: scan duration, thumbnail loading.
Runs `SAMPLE_COUNT` (default 5) iterations and reports p95 across iterations.
The first iteration is reported as a cold-cache diagnostic. The thumbnail p95 budget is
enforced on subsequent warm-cache iterations so derivative generation time is not mixed
with cache-serving latency.

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
3. **Clears the network tracker** and sets `clickTime` — this ensures _only_ network activity caused by the album click is measured.
4. Clicks the album card.
5. Collects all `/api/scan` and `/api/thumbnail` requests.
6. Filters samples by album path when `GALLERY_PERF_ALBUM_PATH` is set (prevents root `/api/scan` or unrelated thumbnails from polluting results).
7. Repeats for `GALLERY_PERF_ALBUM_SAMPLES` (default 5) iterations.
8. Aggregates scan duration / first-thumbnail-start / thumbnail-p95 across iterations as p95.
9. Asserts budgets and prints a structured JSON report.

**Pre-click network is intentionally ignored** — the tracker refuses to record samples before `clickTime` is set. This prevents false duplicates and wrong `scanSamples[0]`.

**Timing uses `performance.now()`** (monotonic, sub-millisecond) everywhere, never `Date.now()`, so NTP or manual clock adjustments cannot corrupt measurements.

Config via env vars (override defaults from `perf-budgets.json[album_open]`):

```bash
GALLERY_BASE_URL=https://150.230.56.153 \
GALLERY_PERF_ALBUM_NAME="test mika" \
GALLERY_PERF_ALBUM_PATH="/home/ubuntu/gallery-repo/test mika" \
GALLERY_PERF_ALBUM_SAMPLES=5 \
GALLERY_PERF_SCAN_BUDGET_MS=500 \
GALLERY_PERF_FIRST_THUMB_BUDGET_MS=1000 \
GALLERY_PERF_THUMB_P95_BUDGET_MS=1200 \
npm run perf:album
```

Test measures (per iteration + p95 across iterations):

- scan duration (ms)
- first thumbnail start after click (ms)
- thumbnail p50/p95/max latency (ms)
- duplicate `/api/scan` cursor=0 count

Fail budgets (from `[album_open]`):

- scan p95 > `scan_p95_ms` (default 2000ms)
- first thumbnail start p95 > `first_thumbnail_ms` (default 3000ms)
- thumbnail p95-of-p95 > `thumbnail_p95_ms` (default 200ms)

## Lightbox Perf Test

Measures lightbox open and transition performance with the derivative-first policy: time to visible, preview load latency, on-demand original load after zoom, transition preview load latency, endpoint usage, and aspect ratio integrity. Runs `SAMPLE_COUNT` (default 5) iterations per test and reports p95 across iterations.

```bash
# Run lightbox perf tests (headless)
npm run perf:lightbox

# Run with browser visible (debug)
npm run perf:lightbox:headed
```

### How the tests work

**Test 1: lightbox opens first photo (5 iterations, p95)**

1. Navigates to album and waits for photo cards.
2. Clears the network tracker and sets clickTime.
3. Clicks the first photo card.
4. Measures `lightboxVisible`: time until lightbox overlay is visible.
5. Measures `lightboxPreviewLoaded`: time until the main `.pswp__img` is fully loaded (`img.complete`).
6. Verifies normal open used `/api/preview` and did not request `/api/image`.
7. Repeats for `GALLERY_PERF_LIGHTBOX_SAMPLES` iterations and aggregates p95.
8. Checks display dimensions are reasonable (>300px in both axes) on the representative sample.

**Test 2: lightbox transitions to next image (5 iterations, p95)**

1. Opens the lightbox on the first photo (reuses setup).
2. Clears the tracker, presses ArrowRight.
3. Measures time until the image `src` changes (next photo starts loading).
4. Measures `transitionPreviewLoaded`: time until the new image is fully loaded.
5. Verifies the displayed aspect ratio matches the natural aspect ratio within 20% on every iteration.
6. Verifies transition navigation does not request `/api/image` on every iteration.

### Config via env vars (override defaults from `perf-budgets.json[lightbox]`)

```bash
GALLERY_BASE_URL=http://localhost:5173 \
GALLERY_PERF_ALBUM_NAME="test mika" \
GALLERY_PERF_ALBUM_PATH="/home/ubuntu/gallery-repo/test mika" \
GALLERY_PERF_LIGHTBOX_SAMPLES=5 \
GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS=800 \
GALLERY_PERF_LIGHTBOX_PREVIEW_BUDGET_MS=1500 \
GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS=700 \
npm run perf:lightbox
```

### Budgets (from `scripts/perf_budgets.toml[lightbox]`)

| Field              | Default | Env Var Override                             | Description                                                                                          |
| ------------------ | ------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `open_ms`          | `500`   | `GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS`       | Max p95 ms for lightbox to become visible after click                                                |
| `preview_check_ms` | `200`   | `GALLERY_PERF_LIGHTBOX_PREVIEW_BUDGET_MS`    | Max warm-cache p95 duration of the `/api/preview` request; the initial sample is reported separately |
| `transition_ms`    | `1000`  | `GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS` | Max p95 ms for next preview image to load after ArrowRight                                           |

## Known Limitations

- **Cold cache**: When first browsing a new album, `/api/scan` returns `width=null, height=null` for all images because the cache hasn't been populated yet. Dimensions appear after the first thumbnail load or metadata fetch.
- **Background indexing**: Directory tree index runs with `include_metadata=False` during scan, meaning full metadata (prompt, models) is only indexed when images are actually opened in the lightbox or thumbnailed.
- **SQLite concurrency**: WAL mode + busy_timeout=5000 handle concurrent FastAPI workers. Cache failure never breaks scan — errors are silently caught and dimensions return null.
- **Metrics cardinality**: Route-level labels only. Adding per-path labels would create high-cardinality metrics and is intentionally avoided.
- **Multi-sample variance**: Playwright perf specs now run 5 iterations by default. P95 over 5 samples is heavily influenced by the max; raise `GALLERY_PERF_*_SAMPLES` for tighter percentiles.

## Env Var Reference (override-only — defaults live in `scripts/perf_budgets.toml`)

| Env Var                                         | TOML default                                          | Description                                                               |
| ----------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------- |
| `ENABLE_METRICS`                                | `1` (dev), `0` (prod)                                 | Enable Prometheus metrics at `/metrics`                                   |
| `ENABLE_PROFILER`                               | `0`                                                   | Enable pyinstrument profiling                                             |
| `PROFILE_ENDPOINTS`                             | `/api/scan,/api/metadata,/api/thumbnail,/api/preview` | Comma-separated endpoints to profile                                      |
| `GALLERY_METADATA_DB`                           | `backend/.cache/gallery_metadata.db`                  | Path to SQLite metadata cache DB                                          |
| `SCAN_PERF_LOGS`                                | `1` (dev), `0` (prod)                                 | Enable verbose scan performance log output                                |
| `GALLERY_BASE_URL`                              | `http://localhost:5173`                               | Frontend URL for Playwright tests                                         |
| `GALLERY_API_BASE_URL`                          | `http://localhost:8000`                               | Backend API URL for perf scripts                                          |
| `GALLERY_PERF_ALBUM_NAME`                       | `test mika`                                           | Album name for Playwright test                                            |
| `GALLERY_PERF_ALBUM_PATH`                       | `""`                                                  | Album path to filter scan/thumbnail samples; prevents root-scan pollution |
| `GALLERY_PERF_ALBUM_SAMPLES`                    | `5`                                                   | Iterations for album-open perf spec (p95 aggregation)                     |
| `GALLERY_PERF_LIGHTBOX_SAMPLES`                 | `5`                                                   | Iterations for lightbox perf specs (p95 aggregation)                      |
| `GALLERY_PERF_SCAN_BUDGET_MS`                   | `[album_open].scan_p95_ms` (`2000`)                   | Max acceptable album-open scan p95                                        |
| `GALLERY_PERF_FIRST_THUMB_BUDGET_MS`            | `[album_open].first_thumbnail_ms` (`3000`)            | Max acceptable first-thumbnail-start p95                                  |
| `GALLERY_PERF_THUMB_P95_BUDGET_MS`              | `[album_open].thumbnail_p95_ms` (`200`)               | Max acceptable thumbnail p95-of-p95                                       |
| `GALLERY_PERF_SCAN_ITERATIONS`                  | `10`                                                  | Iterations for `perf_scan.py`                                             |
| `GALLERY_PERF_SCAN_P95_BUDGET_MS`               | `[scan].p95_ms` (`500`)                               | p95 budget for `perf_scan.py`                                             |
| `GALLERY_PERF_INSPECTOR_P95_BUDGET_MS`          | `[inspector].p95_ms` (`500`)                          | p95 budget for `perf_library_inspector.py`                                |
| `GALLERY_PERF_WARM_LISTING_BUDGET_MS`           | `[warm_listing].budget_ms` (`500`)                    | Warm listing budget                                                       |
| `GALLERY_PERF_SEARCH_P95_BUDGET_MS`             | `[search].p95_ms` (`300`)                             | p95 budget for `/api/search` in `bench_search.py`                         |
| `GALLERY_PERF_INSPECTOR_METADATA_P95_BUDGET_MS` | `[inspector_metadata].p95_ms` (`200`)                 | p95 budget for `/api/library/inspector/metadata`                          |
| `GALLERY_PERF_BENCH_THUMBNAIL_COLD_P95_MS`      | `[thumbnail].cold_p95_ms` (`1000`)                    | Cold thumbnail p95 budget                                                 |
| `GALLERY_PERF_BENCH_THUMBNAIL_WARM_P95_MS`      | `[thumbnail].warm_p95_ms` (`50`)                      | Warm thumbnail p95 budget                                                 |
| `GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS`          | `[lightbox].open_ms` (`500`)                          | Max p95 lightbox open visible time                                        |
| `GALLERY_PERF_LIGHTBOX_PREVIEW_BUDGET_MS`       | `[lightbox].preview_check_ms` (`200`)                 | Max warm-cache p95 duration of the `/api/preview` request                 |
| `GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS`    | `[lightbox].transition_ms` (`1000`)                   | Max p95 lightbox next-preview transition time                             |
