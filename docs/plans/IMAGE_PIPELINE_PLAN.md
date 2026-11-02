# Image Pipeline Plan

Status: Active

Created: 2026-11-02

Source: album / scroll / lightbox measurements of 2026-11-02 on `main` (`3006515`).
The measurements used a 300-image photo-like fixture: thumb_512 webp ≈ 44 KB and
preview_1440 ≈ 250 KB. Three profiles were measured: desktop, mobile 4G (85 ms,
9 Mbps), and mobile slow 4G (150 ms, 1.6 Mbps). Both mobile profiles used 4× CPU
throttling.

## Goal

Make album open, fast scrolling, revisits and the lightbox fast on mobile and
desktop without any visual change. Keep the durable derivative job semantics
(claim tokens, leases, the single database writer) and all API response shapes,
except for the additive fields listed below.

## Findings

| ID | Finding | Evidence |
|----|---------|----------|
| IP-1 | Fast scrolling downloads every thumbnail it passes; nothing is cancelled. | Desktop fling of 8 viewports: 186 thumbs (8 MB) for 24 visible. Mobile slow 4G: 74 thumbs (3.2 MB); visible thumbs settle after 15 s. Album open on mobile requests 22 thumbs for 8 visible. |
| IP-2 | Thumbnail and preview URLs carry no version, so responses use `max-age=0, must-revalidate`. Every revisit costs one 304 round trip per image. | Revisit on slow 4G: 24 × 304, 1.6 s. |
| IP-3 | Derivative generation is slow. WebP uses `method=6`, each variant decodes the source separately, and each render does a DB write. | thumb_512 job ≈ 590 ms on the server. Cold album: 114 priority-0 jobs waited 11 s on average; desktop needed 15.9 s until visible thumbs were complete. Single-thread bench: method 4 is 1.9× (thumb) and 2.4× (preview) faster at +7 % bytes. One decode plus a cascade for all 3 variants takes 233 ms, against 611 ms for separate method-6 renders. |
| IP-4 | The mobile grid is not virtualized. | Album open renders 200 cards: a 635 ms long task at 4× CPU and 3,200 DOM nodes, which grow with every 200-item page. |
| IP-5 | The grid always uses the 512 px thumbnail. | Desktop cards are ≈ 230 CSS px at DPR 1, so the 512 px thumbnail carries ~5× the pixels needed. |
| IP-6 | The lightbox preloads neighbour previews in parallel with the current one. | Slow 4G: the current preview needs 2.9 s while 3 previews share the bandwidth. |
| IP-7 | Warm thumbnail serving is capped at ≈ 93 req/s whatever the concurrency. | Per request: path resolve + `find_asset_id` + `get_ready_derivative`, about 5 ms of DB. Also the `last_accessed_at` writer op and the middleware stack, about 10 ms of CPU per request. |
| IP-8 | The `related-assets` "lexical backfill regression" budget is noise-dominated. | 12 samples per window, so p95 ≈ max. Branch 24/28/46 % against main 0/0/3 % with identical backend code; CI passed. |
| IP-9 | The backend suite crashes on Python 3.13 (`backend/.venv_linux`, the VPS runtime). | `test_albums.py` `fake_stat` (audit GR-02). |
| IP-10 | `backend.log` (a runtime log) is committed. | Audit GR-05. |
| IP-11 | axios 1.18.0 in the lockfile has a known advisory (audit GR-04). axios is only used by `frontend/src/services/api.ts`. | `pnpm-lock.yaml`. |

## Tracks

Every track works in its own git worktree on its own branch and commits but
does not push. The reviewer (Opus) merges, runs the heavy validation (full
e2e, perf suite, album harness, screenshots) and pushes. Agents run only
targeted tests and the fast checks listed per task. Agents must not run
`./test.sh e2e`, `scripts/internal/test-perf.sh` or the album harness unless
the task says so: the sandbox has 4 cores and parallel tracks would distort
each other's numbers.

### Track B: backend derivatives (Sonnet, branch `perf/ip-backend`)

- **B1 (IP-3), faster generation.**
  - WebP `method=4` for every variant.
  - When a derivative job renders a variant, reuse a single decode of the source for all sibling variants of the same asset that are queued or missing. Write their files and mark them ready through the existing claim-fenced writer ops; do not invent a new queue. If sibling batching cannot keep the fencing semantics, fall back to rendering only the claimed variant, but from the largest already-ready sibling (preview → thumb) instead of the source.
  - Skip `upsert_image_dimensions` when the stored dimensions already match.
  - Bump `DERIVATIVE_CACHE_VERSION` only if the bytes for an existing URL change in a way clients must not mix. Document the choice.
  - Target: thumb_512 render p50 ≤ 90 ms single-thread on the photo-like fixture.
- **B2 (IP-5, backend part), new `thumb_256` variant.**
  - Accept 256 in the public thumbnail size validation.
  - Add it to `DERIVATIVE_VARIANTS` and to reconcile/warm-up.
  - Generate it in the B1 cascade.
- **B3 (IP-2, backend part), versioned URLs.**
  - Browse, search and related responses already expose `mtime`. Add an additive per-item field `content_version` (string, `"<mtime_ns>-<size>"` of the asset identity). Also add `cover_versions` aligned with `cover_images` for folders.
  - `/api/thumbnail` and `/api/preview` accept an optional `v`. When `v` equals the current source identity, respond with `Cache-Control: public, max-age=31536000, immutable` and the same ETag. When `v` is absent or stale, keep today's `max-age=0, must-revalidate`.
  - Update `docs/ARCHITECTURE.md` and the API docs, and run `./test.sh backend-api`.
- **B4 (IP-7), serving fast path.**
  - Add a bounded in-process LRU from (path, kind, variant) to (asset_id, identity, cache_path, etag). Validate it with the `stat()` the handler already does, so a stale entry is impossible. It skips `find_asset_id` and `get_ready_derivative` on hits.
  - Coalesce `last_accessed_at` touches in memory and flush them as one normal-lane writer op every ≥ 5 s and at shutdown.
  - Target: ≥ 250 warm req/s at 32 concurrency on the sandbox (≈ 93 today), measured with a small script similar to the one in this plan's evidence.
- **Tests and checks.**
  - Every change gets fail-before / pass-after tests: render path, cascade, fencing, immutable headers only on a matching `v`, the LRU never serving a superseded file, touch flushing.
  - Run the targeted pytest, then the full backend suite on Python 3.11 with `--cov-fail-under=90`, plus `./test.sh lint`, `./test.sh docs` and `./test.sh backend-api`.

### Track F: frontend grid and lightbox (Sonnet, branch `perf/ip-frontend`)

- **F1 (IP-1), visibility-gated, cancellable thumbnail loads.**
  - `PhotoCard` and the album covers start loading only after the card has intersected the viewport (small rootMargin) for ≥ 120 ms.
  - When the card leaves before the image completes, or unmounts (desktop virtual rows), clear `src` so the browser cancels the request.
  - The first-row `fetchPriority="high"` cards from PR #7 load immediately.
  - Visuals stay identical: same skeleton/shimmer while loading.
- **F2 (IP-4), virtualize the mobile grid.**
  - Use TanStack Virtual with the same pattern as the desktop/tablet grid, keeping native window/container scroll, the album strip above the grid, the infinite-load sentinel and scroll restoration.
  - No visual change at 390×844 and 360×740.
  - Mind the earlier `content-visibility` Safari flicker note in `GalleryGrid.vue`.
- **F3 (IP-6), lightbox preview first.**
  - With PhotoSwipe `preload: [1, 1]`, the current slide's preview must be requested first. Neighbour previews start only after the current preview loaded (or failed).
  - Arrow and swipe navigation must stay instant once neighbours are loaded.
- **Tests and checks.**
  - Vitest for the new composable or logic, and the existing Playwright specs relevant to grid, lightbox and responsive.
  - Run single specs, not the whole suite: for example `corepack pnpm exec playwright test tests/e2e/lightbox-loading-policy.spec.ts`, using `PLAYWRIGHT_BROWSERS_PATH=/tmp/claude-0/-home-user-gallery/7ef502ed-3644-56aa-b068-4cbda454f8d3/scratchpad/pwb`.
  - Also run `./test.sh lint`.

### Track S: small fixes (Haiku, branch `perf/ip-small`)

- **S1 (IP-8)**
  - Make `scripts/bench_related_assets.py` lexical backfill robust: ≥ 40 samples per window (env override kept), pool the before+after samples as the baseline, and compute the regression on p95 of the pooled baseline against p95 during.
  - Keep the 20 % budget and update `docs/testing/PERFORMANCE_TESTING.md`.
  - Run only the script's unit tests or a dry syntax check. The reviewer runs the perf suite.
- **S2 (IP-9)**
  - Fix `backend/tests/test_albums.py` `fake_stat` for Python 3.13 without weakening assertions.
  - Prove it with `backend/.venv_linux/bin/python -m pytest backend/tests/test_albums.py` (3.13) and the 3.11 venv.
- **S3 (IP-10)**
  - `git rm --cached` committed runtime logs (`backend.log` and any other `*.log` that is runtime output, not a fixture).
  - Add ignore rules.

### Track A: axios → fetch (Sonnet, wave 2, branch `perf/ip-fetch`, after F and B3 are merged)

- **A1 (IP-11)**
  - Replace axios in `frontend/src/services/api.ts` with a small `fetch` wrapper that keeps every exported function signature and behaviour:
    - same query serialisation as axios (array/undefined handling)
    - error shapes and `APIError` mapping
    - `AbortSignal` support
    - timeouts
    - credentials and headers
  - Remove axios from `package.json`. If `@douxcode/vue-spring-bottom-sheet` needs axios as a peer, keep resolution sane and report it.
  - If A1 is not safe, do A2 instead: upgrade axios to the patched release.
- **A2 (frontend part of IP-2 and IP-5), wire the backend contract.**
  - Done in the same wave because it touches `api.ts`.
  - `getThumbnailUrl` and `getPreviewUrl` take the optional version and append `v`.
  - `PhotoCard` gets `srcset` with 256w and 512w plus a correct `sizes`.
  - Album covers use `cover_versions`.

## Review gates (Opus)

1. Every edit to a pre-existing test is quoted before/after with its justification. No assertion is weakened.
2. Fail-before / pass-after for every new regression test.
3. After each merge wave, the reviewer runs:
   - the full backend suite (3.11; 3.13 after S2)
   - Vitest
   - `./test.sh e2e`
   - the perf suite
   - the album harness, in all 3 profiles: warm, cold (newly imported album), and revisit
   - a pixel diff of 390/1024/1440 screenshots against `main`
4. Targets on the album harness:
   - **Fast scroll, mobile slow 4G:** visible-thumb settle ≤ 4 s (15 s today), with no more than 2× the visible thumbs requested per stop.
   - **Revisit:** 0 thumbnail network requests for versioned URLs.
   - **Cold album open, desktop:** ≤ 5 s (15.9 s today).
   - **Mobile album open:** no long task > 200 ms.
   - **Lightbox current preview, slow 4G:** ≤ 1.6 s (2.9 s today).
   - **Warm thumbnail throughput:** ≥ 250 req/s.

## Deploy (item 1)

After each merged wave, the VPS pulls main, builds `frontend/`, reloads nginx
with `frontend/gallery-nginx-prod.conf`, and restarts the backend on
`127.0.0.1:4701`, as in `AGENTS.md`.

## Progress log

| Track | Item | Status | Evidence |
|-------|------|--------|----------|
| B | B1 faster generation (IP-3) | Done, awaiting merge (`perf/ip-backend`) | WebP `method=4`. A claimed job also claims the queued sibling variants of the same asset (own claim token and lease each; an interactive job only takes interactive siblings) and renders them from one decode as a cascade, the requested variant first; the dimension upsert is skipped when the catalog holds the values. `DERIVATIVE_CACHE_VERSION` stays `v3` (bytes behind a URL are interchangeable). Single-thread thumb_512 p50 on the 1024² PNG fixture: 128.8 ms -> 85.6 ms (target ≤ 90). Cold 150-image album (600 derivatives, 3 workers, sandbox under load): 66-81 s -> 23-25 s until all ready. Tests: `test_image_pipeline_derivatives.py`. |
| B | B2 `thumb_256` (IP-5, backend) | Done, awaiting merge | Configured variant (`thumb_128`, `thumb_512`, `thumb_256`), accepted by `/api/thumbnail`, scheduled by reconcile, rendered in the cascade. Existing tests that pinned three variants were updated (see the commit message). |
| B | B3 versioned URLs (IP-2, backend) | Done, awaiting merge | `content_version` on browse/search/related items, `cover_versions` aligned with `cover_images` (folder listing, virtual root, search albums); `v` on `/api/thumbnail` and `/api/preview` gives `public, max-age=31536000, immutable` only when it equals the on-disk identity (200 and 304). Tests: `test_image_pipeline_versions.py`. |
| B | B4 serving fast path (IP-7) | Done, awaiting merge | Bounded LRU validated by the source `stat()` and `try_acquire_serving`, TTL 5 s for catalog-side deactivation; `last_accessed_at` touches coalesced into one op per 5 s window (flushed by the next window, supervisor tick, eviction and `stop()`). Warm thumbnail throughput (own backend, 150 requests, median of 3): 57 / 79 / 84 req/s -> 410 / 478 / 426 req/s at concurrency 1 / 6 / 32 (target ≥ 250). The first request per image after a restart or TTL expiry still takes the full path (≈ 88 req/s at 32). Tests: `test_image_pipeline_fastpath.py`. |
| F | F1 visibility-gated, cancellable thumbnails | Implemented on `perf/ip-frontend`, awaiting review | Sandbox, 250 ms stub thumbs, 12-viewport fling in ~0.9 s. Desktop 1440x900: 182 thumbnail requests, 0 aborted (main) vs 88 started, 62 aborted, 26 completed (branch); initial open 48 vs 24 requests for 24 visible. Mobile 390x844: 110 requests vs 36 started, 22 aborted, 14 completed; open 20 vs 8 for 8 visible. Visible thumbs all loaded after the stop in both. The 120 ms dwell applies only while the scroll root is scrolling (scroll event within 150 ms); cards in range at rest, including album open, load at once. Tests `useVisibleLoadGate`, `PhotoCardLoadGate`, `AlbumCardLoadGate`. |
| F | F2 virtualized mobile grid | Implemented on `perf/ip-frontend`, awaiting review | Same `useVirtualGridRows` as desktop/tablet; row height and scroll margin measured from the DOM. Mobile 390x844 open: 200 cards / ~1265 DOM nodes (main) vs 16 cards / ~280 nodes. Card rects, `scrollHeight` and infinite load identical to main at 6 scroll stops each for 390x844 and 360x740, also with the album strip collapsed, resized 390 to 360 and 3 columns; desktop 1024x768 and 1440x900 rects identical. Pixel diff vs main on mobile screenshots: max 3/255 on card corner pixels. Tests `GalleryGrid` mobile, `useVirtualGridMetrics`, `useVirtualGridRows`. |
| F | F3 lightbox current preview first | Implemented on `perf/ip-frontend`, awaiting review | `utils/lightboxPreviewOrder.ts` defers non-current `contentLoadImage` until the current slide loaded or failed. New e2e `neighbour previews wait for the current preview, then preload` fails on main (a and c requested with b held) and passes on the branch; `lightboxPreviewOrder.test.ts` runs against the real PhotoSwipe core. Slow-4G timing not measured here; the reviewer's harness owns that gate. |
| B | B1 follow-up: preemptible background batches | Done, awaiting merge (`perf/ip-backend`) | Reviewer album harness: two 120-image albums, desktop visible thumbs 24.3 s vs 15.9 s on main. Fix: background batches (leader priority ≥ 2) check for runnable priority 0-1 work between variants and release unrendered sibling claims (one fenced writer op, no attempt consumed); leader and siblings are claimed in one op; the request-side wait polls with backoff. Own harness (no browser, 4 cores, quiet), 30 concurrent `thumb_512` requests on album A after both albums are scanned: time-to-200 p50/max main 3.49/4.86 s, pre-fix branch 4.18/5.84 s, fix 2.71/3.59 s; all derivatives ready after 65.5 s (main, 3 variants) / 36.2 s (pre-fix) / 34.8 s (fix). 72 requests: main 11.5/21.6 s, pre-fix 11.2/16.1 s, fix 6.6/9.5 s. Tests: `test_image_pipeline_preemption.py`. |
| A | A2 wire the contract (IP-2, IP-5 frontend) | Implemented on `perf/ip-fetch`, awaiting review | `getThumbnailUrl` / `getPreviewUrl` take the optional version (`&v=` after `max_long_edge`; empty or missing keeps today's URL). Passed by `PhotoCard` (grid, search, related), the album covers (`cover_versions[i]`), the lightbox (`src`, `previewSrc`, `msrc`, dimension probe). `PhotoCard` offers `srcset` 256w + 512w with `src` = 512; `sizes` = measured card width x the image's long/short ratio (the card is `object-fit: cover`, so the 256 px derivative of a 3:2 photo, 171 px high, must not be picked for a 230 px card). Sandbox, stubbed backend, 24 cards: desktop 1440x900 DPR 1 requested exactly one thumbnail per card (24 requests, all 256 px for 163 px cards, 3:2 and square) and no 512 fallback request, including the first (eager) row; mobile 390x844 DPR 3 requested 10 thumbnails, all 512. Tests: `apiUrls`, `thumbnailSizes`, `PhotoCardSrcset`, `ContentVersionCallSites`. |
| A | A1 axios -> fetch (IP-11) | Implemented on `perf/ip-fetch`, awaiting review | Path taken: **A1 (axios removed)**, not the axios upgrade. `services/http.ts` is a ~280-line `fetch` client with `get/post/patch/delete` and axios' query serialiser, error codes/messages, JSON parsing, timeout and abort; `api.ts` endpoint wrappers are untouched. Parity: 64 request/response/error cases (query encoding, bodies, headers, 2xx/4xx/5xx, network error, timeout, mid-flight and pre-aborted cancel) run against real axios 1.18.0 (XHR adapter) and against the wrapper in headless Chromium for 3 base URLs (none, absolute, absolute with trailing slash): 0 differences after one fix (a `null` POST body must keep axios' `Content-Type: application/x-www-form-urlencoded`). The serialiser was also fuzzed byte-for-byte against `axios.getUri` (40,000 random nested params; it found two key-trimming edge cases, fixed). Cancelled requests still reject as the `network` `GalleryAPIError` (axios mapped `CanceledError` the same way). `@douxcode/vue-spring-bottom-sheet` does not use axios: it only imports `@vueuse/integrations/useFocusTrap`; axios was an optional peer of `@vueuse/integrations` that pnpm had auto-resolved. The lockfile was re-resolved (remove and re-add the sheet with `@vueuse/integrations` held at 14.3.0) so `axios`, `follow-redirects` and `form-data` are gone; side effect: the sheet's transitive `remeda` 2.39.0 -> 2.57.1 and `tabbable` 6.4.0 -> 6.5.1. Tests: `http`, `apiFetch`; `api.test.ts` retargeted from the axios mock to the `http` module mock. |
| A | A3 retry failed thumbnails and covers | Implemented on `perf/ip-fetch`, awaiting review | On a cold album `/api/thumbnail` answers 503 after its 10 s generation wait and tiles stayed on the placeholder. `useImageRetry` retries every real `<img>` error (the status is not visible) 3 times after 1.5 s / 4 s / 10 s with a throwaway `&r=<n>` on `src` and `srcset` (the backend ignores unknown query parameters; checked with an ad hoc TestClient request: same 200, bytes and ETag with and without `r`). The shimmer / cover skeleton stays while retrying; the placeholder shows only after the last retry failed; leaving the viewport, unmounting or a new image cancels the pending retry and restarts the budget; the cleared-`src` error is still ignored. Tests: `useImageRetry`, `PhotoCardRetry`, `AlbumCardRetry`, `apiUrls`; `PhotoCardLoadGate` and `AlbumCardLoadGate` "real error" tests now run the retries out first. |
