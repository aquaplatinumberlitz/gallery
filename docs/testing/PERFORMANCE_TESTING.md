# Performance Testing

Status: Maintained

Last reviewed: 2026-07-15

This document describes how to measure and profile Gallery API performance.

## Perf budgets — single source of truth

Every perf budget in the repo lives in **`scripts/perf_budgets.toml`**. That file
is the canonical source for all numeric budgets consumed by:

- `scripts/perf_library_inspector.py` + `scripts/perf_inspector_store.py` — `[inspector]`
- `scripts/perf_facets.py` — `[facets]`
- `scripts/perf_warm_listing.py` — `[warm_listing]`
- `scripts/bench_search.py` — `[search]` + `[inspector_metadata]`
- `scripts/bench_related_assets.py` — `[related_assets]`
- `scripts/bench_thumbnail.py` — `[thumbnail]`
- `scripts/bench_preview.py` — `[preview]`
- `frontend/tests/e2e/perf/album-open.perf.spec.ts` — `[album_open]`
- `frontend/tests/e2e/perf/lightbox.perf.spec.ts` — `[lightbox]`
- `frontend/tests/e2e/metadata-performance.spec.ts` (env-gated, requires `GALLERY_PERF_METADATA=1`) — `[metadata_nav]`

The Playwright specs read their budgets from
`frontend/tests/e2e/perf/perf-budgets.json`, which mirrors the relevant TOML
sections. The Python scripts read the TOML directly via `scripts/perf_lib.py`.

### Budget provenance and calculation policy

Every committed budget must be classified as one of these two types:

1. **Published-standard-derived**: use a published threshold unchanged and
   record the organization, metric definition, percentile, and source URL in
   `scripts/perf_budgets.toml`. A lab proxy must be labelled as a proxy; it must
   not be described as passing the corresponding field metric.
2. **Baseline-derived**: use this only when no organization publishes a
   threshold for the exact workload, such as SQLite query latency or derivative
   cache service time. The report and documentation must identify the fixture,
   hardware/runtime assumptions, sample count, percentile, and calibration
   formula. Historical budgets without provenance metadata remain legacy
   baseline budgets and must not be loosened without new calibration evidence.

Google recommends defining performance budgets from explicit goals and a
real-device/network baseline, then continuously measuring them; it does not
publish universal latency limits for project-specific backend workloads. See
[Performance Budgets 101](https://web.dev/articles/performance-budgets-101).

This private project does not claim official field INP because it has no
representative production RUM population. The committed lightbox gates are
controlled-lab regression contracts derived from published Google guidance.

#### Percentile calculation

Python and Playwright use the same linear-interpolation percentile algorithm.
For sorted samples `x[0] ... x[n-1]`:

```text
k = percentile / 100 * (n - 1)
result = x[floor(k)] + (k - floor(k)) * (x[ceil(k)] - x[floor(k)])
```

Consequently, p95 over the default five samples is close to the maximum sample;
it is useful as a strict regression gate but insufficient for calibrating a new
baseline. A baseline-derived budget change requires at least 30 measured
samples across at least six clean managed runs on the same machine/runtime.

For custom metrics without a published product threshold, the repository's
calibration rule is:

```text
candidate budget = round up to 10 ms (baseline p95 + 3 * MAD)
MAD = median(abs(sample - median(samples)))
```

MAD is used as a robust dispersion measure rather than selecting an arbitrary
percentage. See the
[NIST definition of median absolute deviation](https://www.itl.nist.gov/div898/handbook/eda/section3/eda356.htm).
NIST defines MAD; the minimum sample count, six-run requirement, multiplier
`3`, and 10 ms rounding are this repository's explicit calibration policy, not
vendor-published performance thresholds.
Any proposed increase must include the raw reports and must not replace a known
product or published-standard ceiling with a weaker baseline ceiling.

### Adding a new budget

1. Add a `[section]` block to `scripts/perf_budgets.toml` with the numeric
   fields and a `description`.
2. If a Playwright spec consumes it, mirror the section into
   `frontend/tests/e2e/perf/perf-budgets.json`.
3. Register the workload, consumer, suite, and report in
   `scripts/perf_manifest.toml`.
4. Record whether the budget is published-standard-derived or baseline-derived.
   For a baseline-derived change, retain the raw reports and calculation.
5. Run `python3 scripts/check_perf_budgets.py` — it must pass. The validator
   enforces both directions: every TOML section needs a consumer, and every
   perf test's budget env vars need a TOML entry.

### Validating budget coverage

```bash
python3 scripts/check_perf_budgets.py
# perf budget coverage OK: 11 sections, 11 workloads, 3 browser mirrors
```

The validator checks that:

- every TOML section has at least one registered consumer file
- every consumer file actually exists
- the env-var overrides for each section appear in at least one consumer
- `perf-budgets.json` is in sync with the TOML for the mirrored sections
- perf specs only reference registered budget env vars
- every managed workload declares its suite and required reports

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
curl http://localhost:4701/metrics
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
PROFILE_ENDPOINTS=/api/browse,/api/metadata,/api/thumbnail,/api/preview

# Then make a request — HTML profile will be saved to:
ls backend/profiles/
# e.g. _api_browse_20260409_142530.html
```

Profiles are saved to `backend/profiles/` (gitignored). Open the HTML files in a browser to view the flame chart / call tree.

Profiling is off by default and adds zero overhead when disabled.

### Direct Catalog Browse Probe

Measure `/api/browse` latency directly without the frontend. The browse route is
catalog-backed and requires a registered `library_id`.

```bash
# Replace library_id/path with values from your local catalog.
time curl -sS \
  "http://localhost:4701/api/browse?library_id=1&path=/absolute/path/to/local/album&limit=200" \
  >/tmp/gallery-browse.json
```

Response shape:

```json
{
  "index_source": "catalog",
  "library_id": 1,
  "path": "/absolute/path/to/local/album",
  "folders": [],
  "media": [],
  "total_images": 50,
  "total_videos": 0,
  "total_assets": 50,
  "next_cursor": null
}
```

### Library Inspector Perf Script

```bash
python3 scripts/perf_library_inspector.py
# budget: scripts/perf_budgets.toml[inspector].p95_ms (default 500)
```

### Warm Listing Perf Script

```bash
python3 scripts/perf_warm_listing.py --images 5000
# budget: scripts/perf_budgets.toml[warm_listing].budget_ms (default 500)
```

### Search Bench

```bash
python3 scripts/bench_search.py
# budgets: [search].p95_ms (default 300) + [inspector_metadata].p95_ms (default 200)
```

The managed fixture creates only the small set of real PNGs needed by browser
tests, then inserts active synthetic catalog/file-index/metadata rows directly
into SQLite. Its relation corpus is always 100,000 active assets; these are
database rows, not 100,000 image files. Within that
corpus, the CI lexical cohort is 5,000 rows and the opt-in scheduled/local
cohort is 25,000 rows:

```bash
./test.sh perf
GALLERY_PERF_SEARCH_PROFILE=scheduled ./test.sh perf
```

`bench_search.py` runs after the managed backend health check and reports broad
filename, prompt-heavy, album-heavy, combined fielded, model-only,
sampler-only, mixed-short-token, CJK, and repeated opaque-keyset page classes.
Every class requires non-empty fixture matches and retains the 300 ms lexical
p95 budget. Its `search-benchmark-report.json` is written to the configured
artifact directory and understood by `scripts/summarize_perf_reports.py`.

The same managed flow runs the API Inspector benchmark against a real fixture
PNG, the DB-only Inspector store benchmark over all 100,000 catalog rows, and
the all-library facets benchmark. This prevents synthetic missing files from
silently skipping Inspector coverage or turning filesystem cleanup into the
database latency measurement.

### Related Assets Bench

```bash
python3 scripts/bench_related_assets.py
# budgets: scripts/perf_budgets.toml[related_assets]
```

The same managed database contains deterministic exact, recipe, family,
distinctive-prompt, same-model-unrelated, visual-exact, one-bit, eight-bit, and
unrelated groups with precomputed signatures, observed model identities,
fingerprints, and hash bands. The benchmark measures warm metadata API,
combined API, direct metadata and visual candidate retrieval, lexical search
before/during/after bounded writes across signatures, fingerprints, bands, and
extraction lifecycle rows, relation-owned SQLite growth, and incremental
Pillow fingerprint-worker RSS. It fails closed against the 150/75/200/300 ms,
10%, 100 MiB, and 64 MiB budgets and verifies that the controlled same-model
unrelated asset is excluded. Fixture validation derives row count from SQLite,
requires eight bands and two lifecycle extraction rows per asset, and rejects
environment counts that disagree with persisted data. At the release fixture
size that means 800,000 synthetic hash-band rows and 200,000 synthetic
extraction-lifecycle rows in the temporary SQLite database. Its report is
`related-assets-benchmark-report.json` in the managed artifact directory.

### Thumbnail Cold/Warm Bench

```bash
python3 scripts/bench_thumbnail.py
# budgets: [thumbnail].cold_p95_ms (default 1000) + [thumbnail].warm_p95_ms (default 50)
# samples 5 distinct images from test-images/a1111 by default
```

### Preview Cold/Warm Bench

```bash
python3 scripts/bench_preview.py
# budgets: [preview].cold_p95_ms (default 1500) + [preview].warm_p95_ms (default 100)
```

These direct derivative benchmarks gate backend generation and persisted-cache
latency. Browser specs gate user-perceived visual readiness and batch
completion, so browser request queueing is not misclassified as backend cache
service latency.

### Playwright Album Open Perf Test

For the deterministic CI-equivalent browser perf suite, run from the repository root:

```bash
./test.sh perf
```

This command creates a temporary 100,000-asset SQLite fixture, starts FastAPI on
a free port, validates the performance manifest, runs every registered backend
benchmark, builds the frontend and serves it with `vite preview`, then runs all
`frontend/tests/e2e/perf/` specs with one worker and zero retries. Reports live
outside Playwright's cleanup directory, are checked against the manifest, and
are uploaded by CI. Managed perf disables catalog, metadata,
derived-search, derivative-reconcile, watcher, and integrity background writers
so benchmark writes are the only intentional concurrent mutation. Use the
lower-level commands below only when profiling an already-running app or custom
real dataset.

Measures end-to-end album open performance: catalog browse duration and thumbnail loading.
Runs `SAMPLE_COUNT` (default 5) iterations and reports p95 across iterations.
Per-request thumbnail timings remain diagnostic; the browser gate measures the
warm visible-thumbnail batch while the direct benchmark owns cold/warm backend
latency budgets.

```bash
# Install browser (one-time)
cd frontend
corepack pnpm install
corepack pnpm exec playwright install chromium

# Run perf test (headless)
corepack pnpm run perf:album

# Run with browser visible (debug)
corepack pnpm run perf:album:headed
```

### How the test works

1. Opens the app at `GALLERY_BASE_URL`.
2. Waits for the target album card to be visible.
3. **Clears the network tracker** and sets `clickTime` — this ensures _only_ network activity caused by the album click is measured.
4. Clicks the album card.
5. Collects all `/api/browse` and `/api/thumbnail` requests.
6. Filters samples by album path when `GALLERY_PERF_ALBUM_PATH` is set (prevents root `/api/browse` or unrelated thumbnails from polluting results).
7. Repeats for `GALLERY_PERF_ALBUM_SAMPLES` (default 5) iterations.
8. Aggregates browse duration / first-thumbnail-start / thumbnail-p95 across iterations as p95.
9. Asserts budgets and prints a structured JSON report.

**Pre-click network is intentionally ignored** — the tracker refuses to record samples before `clickTime` is set. This prevents false duplicates and wrong first browse samples.

Album-open uses the runner's monotonic `performance.now()` clock around the
workflow plus independently settled network samples. It is a controlled browser
workflow budget, not an INP proxy. The browser-native input marks described
below apply specifically to the lightbox tests.

Config via env vars (override defaults from `perf-budgets.json[album_open]`):

```bash
GALLERY_BASE_URL=https://150.230.56.153 \
GALLERY_PERF_ALBUM_NAME="Local Perf Album" \
GALLERY_PERF_ALBUM_PATH="/absolute/path/to/local/album" \
GALLERY_PERF_ALBUM_SAMPLES=5 \
GALLERY_PERF_SCAN_BUDGET_MS=500 \
GALLERY_PERF_FIRST_THUMB_BUDGET_MS=1000 \
GALLERY_PERF_THUMB_BATCH_BUDGET_MS=500 \
corepack pnpm run perf:album
```

Test measures (per iteration + p95 across iterations):

- browse duration (ms)
- first thumbnail start after click (ms)
- thumbnail p50/p95/max latency (ms)
- duplicate `/api/browse` cursor=0 count

Fail budgets (from `[album_open]`):

- browse p95 > `scan_p95_ms` (default 2000ms; budget key retained for compatibility)
- first thumbnail start p95 > `first_thumbnail_ms` (default 3000ms)
- warm visible-thumbnail batch completion p95 > `warm_batch_complete_ms` (default 500ms)

## Lightbox Perf Test

Measures lightbox open and transition performance with the derivative-first policy: time to visible, preview load latency, on-demand original load after zoom, transition preview load latency, endpoint usage, and aspect ratio integrity. Runs `SAMPLE_COUNT` (default 5) iterations per test and reports p95 across iterations.

```bash
# Run lightbox perf tests (headless)
corepack pnpm run perf:lightbox

# Run with browser visible (debug)
corepack pnpm run perf:lightbox:headed
```

### Browser-native metric definitions

Before the refactor, the test started its clock immediately before
`locator.click()` / `keyboard.press()`. That included Playwright actionability,
scrolling, and command-dispatch time and inflated the reported application
latency by roughly 450 ms on the managed fixture.

The current test separates the clocks:

- a capturing listener on the real photo-card DOM `click` writes
  `gallery:lightbox-open-start`;
- the Vue lightbox writes `gallery:lightbox-overlay-painted` after the DOM update
  and two animation frames, excluding Playwright visibility polling;
- the actual captured ArrowRight `keydown` writes
  `gallery:lightbox-transition-start`;
- decoded readiness is recorded in the browser after `HTMLImageElement.decode()`;
- Resource Timing separates image resource loading from response-to-decode time;
- the Playwright network tracker independently validates `/api/preview`,
  `/api/image`, and `/api/metadata` completion, status, and failure state.

All durations within a metric use the browser's monotonic performance timeline;
browser and Node clocks are never subtracted from each other.

### How the tests work

**Test 1: lightbox opens first photo (5 iterations, p95)**

1. Navigates to album and waits for photo cards.
2. Arms the browser click mark and clears the independent network tracker.
3. Clicks the first photo card; timing begins only when the DOM click is dispatched.
4. Measures click → first painted overlay from browser marks.
5. Waits for the active `/api/preview` image to complete and for `img.decode()`.
6. Reports browser resource-load and response-to-decode phases separately.
7. Verifies normal open used `/api/preview` and did not request `/api/image`.
8. Repeats for `GALLERY_PERF_LIGHTBOX_SAMPLES` iterations and aggregates p95.
9. Checks display dimensions are reasonable (>300px in both axes) on the representative sample.

**Test 2: lightbox transitions to next image (5 iterations, p95)**

1. Opens the lightbox on the first photo (reuses setup).
2. Clears the tracker and presses ArrowRight; timing begins at the captured DOM keydown.
3. Reports source-change time diagnostically.
4. Measures keydown → decoded active preview using the browser clock.
5. Verifies the displayed aspect ratio matches the natural aspect ratio within 20% on every iteration.
6. Verifies transition navigation does not request `/api/image` on every iteration.

### Config via env vars (override defaults from `perf-budgets.json[lightbox]`)

```bash
GALLERY_BASE_URL=http://localhost:5173 \
GALLERY_PERF_ALBUM_NAME="Local Perf Album" \
GALLERY_PERF_ALBUM_PATH="/absolute/path/to/local/album" \
GALLERY_PERF_LIGHTBOX_SAMPLES=5 \
GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS=200 \
GALLERY_PERF_LIGHTBOX_VISUAL_READY_BUDGET_MS=1000 \
GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS=200 \
corepack pnpm run perf:lightbox
```

### Budgets (from `scripts/perf_budgets.toml[lightbox]`)

| Field             | Default | Env Var Override                               | Contract and published basis                                                                                  |
| ----------------- | ------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `open_ms`         | `200`   | `GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS`         | Browser click → first overlay paint. Controlled-lab proxy for Google's good-INP target of ≤200ms at p75.      |
| `visual_ready_ms` | `1000`  | `GALLERY_PERF_LIGHTBOX_VISUAL_READY_BUDGET_MS` | Browser click → decoded preview. Custom metric using the upper bound of Google's 100–1000ms RAIL view window. |
| `transition_ms`   | `200`   | `GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS`   | Actual ArrowRight keydown → decoded next preview; a stricter lab proxy aligned with the interaction target.   |

Sources: [Google INP](https://web.dev/articles/inp) and
[Google RAIL](https://web.dev/articles/rail). `visual_ready_ms` is explicitly a
project SLO derived from RAIL, not a Core Web Vital. Production responsiveness
would need representative RUM to make an official INP p75 claim; this private
project intentionally makes no such claim. The lab p95 gates are regression
checks derived from the published targets.

### Frontend critical-path refactor

The lightbox performance refactor also changed runtime ownership:

- PhotoSwipe is the only image-neighbor preloader; the Pinia store no longer
  duplicates thumbnail, preview, and metadata preload requests.
- PhotoSwipe initializes immediately with scan/remembered/fallback geometry.
  Metadata and preview dimensions resolve asynchronously and repair active
  geometry in place without recreating the image.
- GalleryGrid supplies a precomputed preferred index; the store does not clone
  every query-owned `FileNode` on click and keeps discovered dimensions in a
  separate map.
- expensive navigation summaries are constructed only when lightbox debug mode
  is enabled.
- production perf verification uses `vite build` + `vite preview`, one Chromium
  worker, zero retries, and manifest-validated reports outside Playwright's
  cleanup directory.

The managed closure run produced overlay p95 54 ms, decoded visual-ready p95
944 ms, and ArrowRight-to-decoded-preview p95 105 ms against the 200/1000/200 ms
contracts. These values are evidence for the implementation, not the source of
the published-standard-derived limits.

## Known Limitations

- **Cold catalog rows**: When first browsing a newly imported album, `/api/browse` can return `width=null` and `height=null` until catalog/metadata/derivative work records dimensions.
- **Background indexing**: Catalog discovery can stage paths before full metadata extraction finishes, so prompts/models may appear after background metadata workers catch up.
- **SQLite concurrency**: WAL mode + busy_timeout=5000 handle concurrent FastAPI workers. Derivative/cache failures should not break catalog browse responses.
- **Metrics cardinality**: Route-level labels only. Adding per-path labels would create high-cardinality metrics and is intentionally avoided.
- **Multi-sample variance**: Playwright perf specs now run 5 iterations by default. P95 over 5 samples is heavily influenced by the max; raise `GALLERY_PERF_*_SAMPLES` for tighter percentiles.

## Env Var Reference (override-only — defaults live in `scripts/perf_budgets.toml`)

| Env Var                                         | TOML default                                            | Description                                                                   |
| ----------------------------------------------- | ------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `ENABLE_METRICS`                                | `1` (dev), `0` (prod)                                   | Enable Prometheus metrics at `/metrics`                                       |
| `ENABLE_PROFILER`                               | `0`                                                     | Enable pyinstrument profiling                                                 |
| `PROFILE_ENDPOINTS`                             | `/api/browse,/api/metadata,/api/thumbnail,/api/preview` | Comma-separated endpoints to profile                                          |
| `GALLERY_METADATA_DB`                           | `backend/.cache/gallery_metadata.db`                    | Path to SQLite metadata cache DB                                              |
| `GALLERY_BASE_URL`                              | `http://localhost:5173`                                 | Frontend URL for Playwright tests                                             |
| `GALLERY_API_BASE_URL`                          | `http://localhost:4701`                                 | Backend API URL for standalone perf scripts                                   |
| `GALLERY_PERF_ALBUM_NAME`                       | `Test Album`                                            | Album name for Playwright test                                                |
| `GALLERY_PERF_ALBUM_PATH`                       | `""`                                                    | Album path to filter browse/thumbnail samples; prevents root-browse pollution |
| `GALLERY_PERF_ALBUM_SAMPLES`                    | `5`                                                     | Iterations for album-open perf spec (p95 aggregation)                         |
| `GALLERY_PERF_LIGHTBOX_SAMPLES`                 | `5`                                                     | Iterations for lightbox perf specs (p95 aggregation)                          |
| `GALLERY_PERF_SCAN_BUDGET_MS`                   | `[album_open].scan_p95_ms` (`2000`)                     | Max acceptable album-open browse p95; env name retained for compatibility     |
| `GALLERY_PERF_FIRST_THUMB_BUDGET_MS`            | `[album_open].first_thumbnail_ms` (`3000`)              | Max acceptable first-thumbnail-start p95                                      |
| `GALLERY_PERF_THUMB_BATCH_BUDGET_MS`            | `[album_open].warm_batch_complete_ms` (`500`)           | Max warm visible-thumbnail batch completion p95                               |
| `GALLERY_PERF_INSPECTOR_P95_BUDGET_MS`          | `[inspector].p95_ms` (`500`)                            | p95 budget for `perf_library_inspector.py`                                    |
| `GALLERY_PERF_WARM_LISTING_BUDGET_MS`           | `[warm_listing].budget_ms` (`500`)                      | Warm listing budget                                                           |
| `GALLERY_PERF_SEARCH_P95_BUDGET_MS`             | `[search].p95_ms` (`300`)                               | p95 budget for `/api/search` in `bench_search.py`                             |
| `GALLERY_PERF_SEARCH_PROFILE`                   | `ci`                                                    | `ci` seeds 5,000 synthetic search rows; `scheduled` seeds 25,000              |
| `GALLERY_PERF_SEARCH_ROWS`                      | profile-derived                                         | Explicit synthetic search-row override for managed fixture runs               |
| `GALLERY_PERF_RELATED_ROWS`                     | `[related_assets].rows` (`100000`)                      | Synthetic active relation-corpus size; release evidence uses exactly 100,000  |
| `GALLERY_PERF_RELATED_ITERATIONS`               | `12`                                                    | Iterations for each Related Assets latency sample class                       |
| `GALLERY_PERF_INSPECTOR_METADATA_P95_BUDGET_MS` | `[inspector_metadata].p95_ms` (`200`)                   | p95 budget for `/api/library/inspector/metadata`                              |
| `GALLERY_PERF_BENCH_THUMBNAIL_COLD_P95_MS`      | `[thumbnail].cold_p95_ms` (`1000`)                      | Cold thumbnail p95 budget                                                     |
| `GALLERY_PERF_BENCH_THUMBNAIL_WARM_P95_MS`      | `[thumbnail].warm_p95_ms` (`50`)                        | Warm thumbnail p95 budget                                                     |
| `GALLERY_PERF_BENCH_PREVIEW_COLD_P95_MS`        | `[preview].cold_p95_ms` (`1500`)                        | Cold preview p95 budget                                                       |
| `GALLERY_PERF_BENCH_PREVIEW_WARM_P95_MS`        | `[preview].warm_p95_ms` (`100`)                         | Warm preview p95 budget                                                       |
| `GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS`          | `[lightbox].open_ms` (`200`)                            | Max browser-native click-to-overlay-paint p95                                 |
| `GALLERY_PERF_LIGHTBOX_VISUAL_READY_BUDGET_MS`  | `[lightbox].visual_ready_ms` (`1000`)                   | Max browser-native click-to-decoded-preview p95                               |
| `GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS`    | `[lightbox].transition_ms` (`200`)                      | Max actual-keydown-to-decoded-prefetched-preview p95                          |
