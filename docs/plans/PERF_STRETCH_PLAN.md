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
| M | M1: attribution (CDP trace with the V8 CPU profile, `album_cpu_profile.cjs`, mobile typical 4G, 4x CPU, unminified build, 3 runs; traced ms are about 1.4x the untraced ones, so read the shares) | Done | Album render task (the 123 ms long task; 208 ms traced): Vue mount/patch/reactivity of the page and ~18 cards 79 ms (38%); forced layout inside `setGridRef` (`getBoundingClientRect` after the rows are mounted) 67 ms (32%); `PhotoCard` setup/render/watchers/observers 23 ms (11%); `GalleryGrid` computeds (three sorts, chunking, filters) 11 ms (5%); virtualizer range/measure/total size 10 ms (5%); TanStack Query `setOptions`/notify 10 ms (5%); thumbnail URL building, native and other 9 ms (4%). JSON parse of the 87.6 KB browse body: 0.2 ms at 4x (it is its own sub-millisecond task); structural sharing 0.7 ms (first fetch has no previous data); both under 1%, so no `markRaw`, `shallowRef`, `structuralSharing: false` or smaller first page. Album click task (the 58-84 ms task at the click; 82 ms traced): native style/layout/paint 29 ms (35%), Vue skeleton mount plus unmount of the home view 24 ms (29%), Playwright hit-target script 10 ms (12%, harness), Query `setOptions`/fetch start 8 ms (9%), `GalleryGrid` computeds 7 ms (8%). Album click INP (untraced 72-144 ms) is that click task plus the next paint: input delay 15-50, processing 10-48, presentation 25-100 (traced). Lightbox click task (194 ms traced, INP 96-152 ms): PhotoSwipe init/UI 53 ms (27%), forced layout in `getViewportSize`/`updateSize` 35 ms (18%), Vue mount of the lightbox and panels 29 ms (15%), building the 200 PhotoSwipe items (two URLs, animated check and dimension lookup each) 26 ms (13%), Reka `FocusScope` focus trap 17 ms (9%), native 11 ms, `images`/index computeds in the click handler 9 ms, metadata query start 2.5 ms. Timeline of the album open (4G): browse request starts 14-25 ms after the click and ends ~190 ms, render task 190-400 ms, thumbnails requested only at ~350-470 ms and done at ~850-1000 ms. |
| M | M2: fixes (all with Vitest tests that fail before) | Done | (1) Thumbnail warm-up: the first viewport's thumbnails start as preload links when the first page is fetched (hook in the query function, geometry from the skeleton), so they overlap the render; visible thumbnails 920 -> 764 ms median (main 0.87-1.33 s, branch 0.65-0.88 s in every run). (2) Staged row mount: `rowBudget` on `useVirtualGridRows`, container first, then 1 row, then 4 cards per step (doubling when a step takes under 20 ms): the 120-170 ms render task is gone, steps are 47-59 ms traced. (3) Lazy PhotoSwipe data source (`createLazyList`): lightbox click task 194 -> 124 ms traced, item build 26 -> 0 ms; lightbox click INP 104 -> 96 ms median. Tried and not kept: warm-up from a pre-flush watcher in `GalleryGrid` (it ran inside the render task, +25 ms traced there; moved to the query function and ended the task with a promise); fixed `overscan: 1` then 5 after a frame (long task still 105-140 ms, replaced by the row budget); lazy per-property accessors on each PhotoSwipe item (14 ms to define 6 accessors x 200 items, replaced by the `Proxy` list). Not applied, no evidence for them: `markRaw`/`shallowRef`, `structuralSharing: false`, a 60-item first page (parse 0.2 ms; it would only save ~55 ms of browse transfer and ST-3 is met), deferring the metadata query (2.5 ms). |
| M | M3: targets | ST-3 met, ST-4 met in the median with a documented floor, ST-5 met in the median | ST-3: typical 4G visible thumbnails 0.65-0.88 s in every branch run (main up to 1.33 s). ST-4: longest task after the click 166 -> none in 3 of 4 runs (worst 59 ms); the remaining > 50 ms task is the click task (pointer handlers, skeleton mount, home unmount, query start, style/layout) at 50-81 ms with the harness hit-target script included, a floor without a visual change. ST-5: album click INP median 88 ms, lightbox click INP median 96 ms (range 80-120 ms; 120 ms in 1 of 4 runs), floor is PhotoSwipe `init` plus the focus trap. Slow 4G, desktop, scroll settle, revisit and next/previous unchanged within noise. Pixel diff against `main` at 390x844, 1024x768, 1440x900 (album and lightbox, fonts loaded, mouse parked): 0 pixels above 16 and above 48, mean difference 0.0000 (0.0008 at 1440 album, same as `main` against itself). Branch `perf/st-album` @ `0b7425a` plus docs. |
