# Perf Stretch Plan

Status: Active

Created: 2026-11-02

Source: "Status snapshot (2026-11-02)" in
`docs/testing/PERFORMANCE_TESTING.md`. That section also defines the
user-facing standard used here: Core Web Vitals, Nielsen limits and RAIL
animation.

## Goal

Close the remaining stretch gaps on `main` (`5991830`) with **no visual
change**. Same pixels, same layout, same animations, at 390×844, 1024×768 and
1440×900. No regression on any metric that already passes.

| ID | Gap | Now | Target |
|----|-----|-----|--------|
| ST-1 | Home LCP, mobile slow 4G | 2.7–2.8 s | ≤ 2.5 s |
| ST-2 | Home FCP, mobile slow 4G | 2.4 s | ≤ 1.8 s (diagnostic; best effort) |
| ST-3 | Album open → visible thumbnails, mobile typical 4G | 0.9–1.3 s | ≤ 1.0 s in every run |
| ST-4 | Mobile album-open long task | 123 ms | ≤ 50 ms, or explain the irreducible part |
| ST-5 | Mobile click INP (album open, lightbox open) | 128–160 ms | ≤ 100 ms (RAIL response) |

## Measurement harness (all tracks)

Today the harness only exists as scratch scripts, so the first task commits it
to the repo. Every track then measures with it, against `main` and its own
branch, on the same machine and in the same run.

Profiles come from `docs/testing/PERFORMANCE_TESTING.md`:
- desktop unthrottled
- mobile typical 4G (85 ms RTT, 9 Mbps, 4× CPU)
- mobile slow 4G (150 ms RTT, 1.6 Mbps, 4× CPU)

All profiles run over HTTP/2 + gzip with immutable `/assets/`. Use
photo-like fixtures: thumb_512 ≈ 44 KB, preview ≈ 250 KB.

## Tracks

Each track works in its own worktree and branch. Commit there; do not push.
Agents run targeted checks and their own before/after harness numbers. The
reviewer (Opus) merges the branches and runs the full e2e and perf suites,
the harness, and a pixel diff.

### Track H: harness into the repo (Haiku, branch `perf/st-harness`)

H1. Add `scripts/perf/web_vitals/`. Port the scratch scripts listed below,
keep their behaviour, and replace hard-coded `/tmp` paths with CLI arguments.

| Script | Origin |
|--------|--------|
| `serve_dist.cjs` | `server.cjs` (HTTP/1.1, modes `asis`/`tuned`/`dev`) |
| `serve_dist_h2.cjs` | `h2server2.cjs` (self-signed TLS + HTTP/2) |
| `home_waterfall.cjs` | `waterfall.cjs` (cold + repeat home load; `NET=4g` or slow 4G; `LIST=1` prints the waterfall) |
| `album_flow.cjs` | `album.cjs` (album open, two fast scrolls, lightbox open, 3× next) |
| `album_revisit.cjs` | `revisit.cjs` |
| `album_open_profile.cjs` | `openprof.cjs` (long tasks + API timings during album open) |
| `make_photo_fixture.py` | the PIL generator used for the photo-like fixture |

Sources are in
`/tmp/claude-0/-home-user-gallery/7ef502ed-3644-56aa-b068-4cbda454f8d3/scratchpad/perf/cwv/`
and `/tmp/claude-0/-home-user-gallery/7ef502ed-3644-56aa-b068-4cbda454f8d3/scratchpad/album/`.

H2. Add `scripts/perf/web_vitals/README.md`. It covers:
- how to start the backend on a fixture (env vars, the proxy-secret header)
- how to serve `frontend/dist`
- how to run each script, and what each prints

Also link it from `docs/testing/PERFORMANCE_TESTING.md` and list it in
`docs/testing/TEST_CATALOG.md` if that catalog covers scripts.

These are manual tools, not CI gates.

H3. Smoke-run each script once against a backend started on a tiny fixture.
Report the output. The scripts must pass `./test.sh lint` (Python and ESLint
scope permitting) and `./test.sh docs`.

### Track L: home LCP / FCP (Sonnet, branch `perf/st-home`)

The LCP element on the home page is an album cover thumbnail (512 px). The
request chain is: HTML → entry JS → `/api/libraries` → mount →
`/api/browse` (root) → cover `<img>`. On slow 4G, fonts (≈ 66 KB) and route
chunks compete for bandwidth with that chain.

Investigate with `home_waterfall.cjs` `LIST=1` first, then apply whichever of
these the evidence supports:

- **L1. Smaller cover bytes.** Album covers get the same 256/512 `srcset` +
  `sizes` treatment as `PhotoCard`, so covers on DPR-1 desktop and small mobile
  cards pick 256 when that renders identically. Keep `object-fit` softness in
  mind; this is the rule A2 used.
- **L2. Earlier root browse.** Start the root `/api/browse` request for the
  last active library before mount. The library id persisted by
  `useActiveLibrarySelection` / localStorage is the source. Use the exact
  TanStack query key and function, so the mounted query reuses the result, and
  fall back silently when there is no stored library.
- **L3. Earlier LCP image.** Once root browse data exists, start the first
  covers immediately: `fetchpriority=high`, an `Image()` warm-up or a
  `<link rel=preload as=image>`. They must not wait for the card component's
  visibility gate.
- **L4. Fonts off the critical path.** Measure whether the Cinzel /
  JetBrains Mono woff2 delay the LCP image. If they do:
  - preload only the latin subset used above the fold, or
  - keep the `swap` behaviour but lower their fetch priority.
  The rendered glyphs must be identical.
- **L5. FCP.** Check whether the 30 KB render-blocking main CSS can be split
  so above-the-fold CSS arrives first. Only do it if the pixel diff stays
  clean.

Report before/after on all three profiles: home LCP, FCP and bytes, each the
median of 3 runs.

### Track M: album open, long task, INP (Sonnet, branch `perf/st-album`, after H is merged)

- **M1. Profile first.** Run `album_open_profile.cjs` on mobile typical 4G
  and capture a CPU profile (CDP `Profiler` or `Tracing`) of album open and of
  the lightbox click. Attribute the 123 ms long task and the 128–160 ms INP to
  functions:
  - JSON parse
  - TanStack Query structural sharing
  - Vue reactivity over 200 items
  - virtualizer measure
  - `PhotoCard` setup
  - lightbox/PhotoSwipe init
  - the metadata panel

  Put the attribution table in the report.
- **M2. Fix the top items without visual change.** Candidates, only if the
  profile shows they matter:
  - `shallowRef` / `markRaw` for browse items, or `structuralSharing: false`
    on the browse query when the data is replaced, not merged
  - a smaller first page (e.g. 60 items, then 200 per page) if JSON and
    render cost scale with the page. Keep infinite load and scroll
    restoration intact.
  - deferring non-visible work (metadata panel, related prefetch) to after the
    first paint via `requestAnimationFrame` / `scheduler.yield()` for the
    lightbox click
  - splitting a long synchronous setup into chunks that yield
- **M3. Targets.** ST-3 ≤ 1.0 s, ST-4 ≤ 50 ms (or a documented floor),
  ST-5 ≤ 100 ms on mobile typical 4G. No regression on desktop or on other
  flows.

### Track P: mount-critical payload (Sonnet, branch `perf/st-payload`, after the CLS fix is merged)

Track L measured about 305 KB gzip that must arrive before the app mounts. On
slow 4G each ~20 KB removed from that chain moves LCP about 0.1 s.
Target: ST-1 ≤ 2.5 s (Track L reached 2.58 s), with no visual change and no
regression elsewhere.

- **P1. Brotli.**
  - Emit pre-compressed `.br` (and keep `.gz`) for `/assets/` at build time,
    via a Vite compression plugin or a post-build script. Document the new
    dependency in `docs/THIRD_PARTY_LIBRARIES.md`.
  - Add `brotli_static on;` / `gzip_static on;` for `/assets/` in
    `frontend/gallery-nginx-prod.conf`.
  - In `docs/CONFIGURATION.md`, document the Ubuntu nginx Brotli module
    package and its `load_module` lines, and keep dynamic gzip as the fallback.
  - Teach `scripts/perf/web_vitals/serve_dist_h2.cjs` to serve `.br` when the
    client accepts it, so the lab matches.
  - Deploying the nginx module on the VPS is a separate step, done by the
    VPS session after review.
- **P2. Tooltip and popover content off the critical path.**
  - Tooltip and popover triggers keep rendering immediately.
  - Their content and positioning code (reka-ui content components,
    floating-ui) load on first hover/focus, or after load + idle.
  - Nothing changes visually or in behaviour; the first tooltip shown keeps
    its delay and position.
- **P3. Search-only code off the home critical path.**
  - Move fuse.js, the search results panel and other search-only modules
    out of the home route's static graph.
  - Load them when search becomes active, and warm them after load + idle.
- **P4. motion-v investigation only.**
  - Check whether the installed motion-v supports a LazyMotion / `m` /
    feature-bundle pattern like framer-motion's.
  - If it does, and switching keeps animations identical, implement it.
  - If not, document why, and leave motion-v as it is. Do not replace
    animations with CSS.
- **Evidence.** Show the effect of each item on mount-critical bytes and on
  slow-4G LCP, main against the branch, median of 3. Keep only the items
  that help.

## Rules (all tracks)

- No visual change. Never weaken, delete or skip assertions. Quote
  before/after for any edit to a pre-existing test, with its justification.
- Every behaviour change gets a Vitest/pytest test that fails before and
  passes after.
- Checks:
  - `cd frontend && corepack pnpm run test:unit`
  - `./test.sh lint`
  - `corepack pnpm run build`
  - `./test.sh docs`
  - relevant single Playwright specs, with
    `PLAYWRIGHT_BROWSERS_PATH=/tmp/claude-0/-home-user-gallery/7ef502ed-3644-56aa-b068-4cbda454f8d3/scratchpad/pwb`
- Backend changes, if any, also need the targeted pytest and
  `./test.sh backend-api`.
- Do not run `./test.sh e2e` or the perf suite; the reviewer does.
- Update the maintained docs: `docs/ARCHITECTURE.md` "Initial Load Path" /
  "Grid Image Loading", and the status snapshot in
  `docs/testing/PERFORMANCE_TESTING.md` with measured numbers, date and
  commit.

## Review gates (Opus)

1. Merge each track, then:
   - full backend suite (3.11 and 3.13) if backend changed
   - Vitest
   - `./test.sh e2e`
   - the perf suite
2. Harness on all three profiles against `main`, same run: home, album flow,
   revisit, cold album.
3. Pixel diff at 390/1024/1440: home, album (flat and photo-like) and
   lightbox.
4. Targets ST-1 to ST-5 met, or each miss explained with evidence of the
   floor.

## Progress log

| Track | Item | Status | Evidence |
|-------|------|--------|----------|
| H | H1-H3: harness in `scripts/perf/web_vitals/` (six scripts, `lib.cjs`, `make_photo_fixture.py`, README); linked from `PERFORMANCE_TESTING.md`; `TEST_CATALOG.md` rows | Done | `perf/st-harness` @ `125789c`. Smoke run: 20-image fixture, backend on 127.0.0.1 with `PRODUCTION=1`, `serve_dist.cjs --mode tuned` and `serve_dist_h2.cjs`, all six scripts ran, backend and servers stopped by PID. `./test.sh lint` and `./test.sh docs` exit 0. |
| L | L1 cover srcset/sizes | Skipped | Covers have no dimensions in the browse API, so the unknown-aspect rule (2×) keeps 512 for every card wider than 128 px at DPR 1. Rendered cover widths: 140 px at 390 (DPR 2), 198 px at 1024, 165 px at 1440; all resolve to 512. A 256 candidate would upscale tall images. Needs cover dimensions in the API first. |
| L | L2 early root browse | Done (`d8911d1`) | `utils/homeBrowsePrefetch.ts` + `main.ts`; exact infinite-query key/function shared with `useInfiniteBrowseQuery`. Browse request starts at 1.45 s instead of 2.3 s on slow 4G. 25 Vitest tests. |
| L | L3 early LCP image | Done (`d8911d1`) | The visibility-gate bypass for `priority` covers already existed in the cards; the new part is the pre-mount `Image()` request (high priority, card's URL) for the first cover. Photo-first slow-4G LCP 4.44 s to 2.58 s; flat-first 2.76 s to 2.58 s. |
| L | L4 fonts | Skipped | Fonts (66 KB) are requested after the first render (2.55 s), after the LCP image has loaded. Preloading adds 66 KB to the pre-mount pipe (+0.33 s at 1.6 Mbps). |
| L | L5 FCP / critical CSS | Skipped | The main CSS finishes at 0.85 s, FCP is 2.4-2.6 s; nothing paints before the app mounts, so splitting CSS cannot move FCP. FCP rose 0.15 s because the first frame now includes the data. |
| L | Early preload script position | Rejected experiment | Moving the inline preload script before the stylesheet (it waits for the CSS) started 45 preloads at t = 0, delayed the entry from 1.0 s to 2.0 s and made LCP 3.2 s against 2.75 s. |
| L | ST-1 / ST-2 | Not met | Slow 4G LCP 2.58 s (target 2.5), FCP 2.58 s (target 1.8). Floor: ≈ 305 KB gzip before mount plus ≈ 0.5 s CPU. See `docs/testing/PERFORMANCE_TESTING.md`. |
| CLS | Desktop CLS regression (post-merge finding) | Done (`perf/st-cls`) | Home 1440×900 CLS 0.03–0.2 on `fada31d` (PR 7 introduced 0.04, PR 9 let it reach 0.2). Cause 1: Cinzel swap wraps the brand title (+63 px); fixed with a `local()` fallback face + `size-adjust`. Cause 2: sidebar/breadcrumb/toolbar painted before active-library hydration (+81 px); fixed by holding mount ≤ 300 ms for the library list. CLS 0.0004 at 1440, 0 at 1024, 0.0001 at 390; LCP not regressed. Guard `tests/e2e/perf/home-layout-shift.spec.ts` fails (0.0305) before, passes after. |
