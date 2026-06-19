# Debug Tools

Debug helpers must stay gated and off by default. Prefer these tools before adding new console logging, and remove temporary investigation code once the diagnosis is complete.

## Runtime Debug Flags

### `SCAN_PERF_LOGS`

Location: `backend/debug/scan_perf.py`, called from `backend/scan.py`

Purpose: Emits `/api/scan` timing diagnostics for direct scans and warm SQLite listing hits.

Enable:

```bash
SCAN_PERF_LOGS=1 python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Disable:

```bash
SCAN_PERF_LOGS=0 python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Output: stdout lines prefixed with `[SCAN PERF]`, including path, limit, cursor, total time, warm/direct source, serialization time, and scan phase timings.

Use when:

- `/api/scan` is slow for large folders.
- Warm listing falls back to direct scan unexpectedly.
- Pagination or serialization timing needs to be separated from filesystem scan time.

Safety: Controlled by `SCAN_PERF_LOGS`. Defaults on outside production and off when `PRODUCTION=1`.

### `debug-index-rebuild`

Location: `frontend/src/debug/indexRebuildDebug.ts`

Purpose: Logs Library Inspector rebuild markers, query invalidation, refetches, and Index Status convergence.

Enable:

```js
localStorage.setItem("debug-index-rebuild", "true");
location.reload();
```

Alternative one-session enable:

```js
window.__GALLERY_DEBUG_INDEX_REBUILD = true;
```

Disable:

```js
localStorage.removeItem("debug-index-rebuild");
location.reload();
```

Output: `console.info` lines prefixed with `[index-rebuild-debug]`, including query cache snapshots.

Use when:

- Library Inspector shows stale rows after rebuild.
- Index Status and Library Inspector counts mismatch.
- Route navigation appears to fix stale inspector data.

Safety: Off by default. Normal UI exposes debug API traces only when this flag is enabled.

### `debug-lightbox-nav`

Location: `frontend/src/debug/lightboxNavDebug.ts`

Purpose: Logs lightbox navigation index/path synchronization across Library Inspector, the lightbox store, `Lightbox.vue`, and PhotoSwipe.

Enable:

```js
localStorage.setItem("debug-lightbox-nav", "true");
location.reload();
```

Alternative one-session enable:

```js
window.__GALLERY_DEBUG_LIGHTBOX_NAV = true;
```

Disable:

```js
localStorage.removeItem("debug-lightbox-nav");
location.reload();
```

Output: `console.info` lines prefixed with `[lightbox-nav-debug]`, each containing JSON with `seq`, `rel_ms`, `event`, index values, paths, and item windows around the focused image.

Use when:

- Library Inspector lightbox swipe skips from 1 to 3 to 5 or alternates on even indexes.
- The visible counter and displayed PhotoSwipe image disagree.
- Sorting/refetching inspector rows may be changing the lightbox item order while open.

Safety: Off by default. It logs local paths and image names, so enable only during local debugging.

### `?debugReload=1` / `GALLERY_DEBUG_RELOAD`

Location: `frontend/src/debug/reloadBlackBox.ts`, installed from `frontend/src/main.ts`.

Purpose: Captures page lifecycle, WebSocket/HMR activity, errors, navigation, touch/scroll evidence, and reload suspects before Vue app initialization.

Enable:

```text
http://localhost:5173/?debugReload=1
```

Persistent enable:

```js
localStorage.setItem("GALLERY_DEBUG_RELOAD", "1");
location.reload();
```

Disable:

```js
window.__galleryReloadBlackBox.disable();
localStorage.removeItem("GALLERY_DEBUG_RELOAD");
location.reload();
```

Output: Console report via:

```js
__galleryReloadBlackBox.report();
__galleryReloadBlackBox.copyReport();
__galleryReloadBlackBox.status();
```

Use when:

- A full page reload occurs during album navigation or lightbox use.
- Mobile Safari appears to discard or reload the page.
- HMR or WebSocket messages may be causing reloads in development.

Safety: Off by default. When enabled it stores bounded diagnostic events in localStorage and displays a debug UI.

### `startReloadMonitor`

Location: `frontend/src/debug/reloadMonitor.ts`

Purpose: Alternate reload/navigation monitor with a `window.__galleryReloadDebug` API. This is not currently imported by app boot.

Enable: Import and call `startReloadMonitor()` from a local investigation build, or temporarily wire it into a dev-only path.

Disable:

```js
__galleryReloadDebug.disable();
localStorage.removeItem("GALLERY_DEBUG_RELOAD");
location.reload();
```

Output: Console report via `__galleryReloadDebug.report()` and `copyReport()`.

Use when:

- The black box monitor is too broad and a smaller reload event log is easier to inspect.
- Comparing old reload monitor output with the current black box monitor.

Safety: Keep unwired unless actively investigating. Do not enable in normal production UI.

### `?eruda=1` / `gallery-debug-eruda`

Location: `frontend/src/debug/erudaDebug.ts`, dynamically imported from `frontend/src/main.ts`.

Purpose: Loads the Eruda mobile console for mobile browser debugging.

Enable:

```text
http://localhost:5173/?eruda=1
```

Disable:

```text
http://localhost:5173/?eruda=0
```

or:

```js
localStorage.removeItem("gallery-debug-eruda");
location.reload();
```

Output: Eruda in-page console plus `[Eruda]` console initialization messages.

Use when:

- Debugging mobile Safari/Chrome without desktop DevTools.
- Inspecting localStorage, network, or console state on device.

Safety: Requires explicit opt-in. The module is dynamically imported only after the flag check.

### `?iconDebug=1`

Location: `frontend/src/debug/iconDebugOverlay.ts`, dynamically imported from `frontend/src/main.ts` in dev mode.

Purpose: Displays a local overlay with SVG icon metrics for tablet/mobile header and toolbar investigation.

Enable:

```text
http://localhost:5173/?iconDebug=1
```

Disable: Remove `iconDebug=1` from the URL and reload.

Output: In-page overlay with viewport, layout, and SVG metrics. Buttons can refresh or copy data.

Use when:

- Tablet or mobile icons render at the wrong size.
- Header/toolbar icon metrics need to be compared across breakpoints.

Safety: DEV-only and URL-gated. No backend calls.

### `gallery-lightbox-always-load-original`

Location: `frontend/src/utils/lightbox.ts`, controlled by `frontend/src/components/SettingsModal.vue`.

Purpose: Forces lightbox items to load original images instead of the derivative-first preview policy.

Enable:

```js
localStorage.setItem("gallery-lightbox-always-load-original", "true");
location.reload();
```

Disable:

```js
localStorage.removeItem("gallery-lightbox-always-load-original");
location.reload();
```

Output: Network requests to `/api/image` appear during normal lightbox open; Settings shows the matching preference.

Use when:

- Comparing original image behavior against preview-derived behavior.
- Reproducing bugs that only happen with full-size source images.

Safety: User-facing setting, but off by default. It can increase bandwidth and memory use.

### `__galleryLightboxDOMReport`

Location: `frontend/src/debug/lightboxDomReport.ts`, registered from `frontend/src/composables/usePhotoSwipe.ts`

Purpose: Prints a DOM report for PhotoSwipe roots, items, images, placeholders, and active slide.

Enable: Open the lightbox, then run:

```js
__galleryLightboxDOMReport();
```

Disable: No persistent state; close DevTools output or reload.

Output: Console groups listing PhotoSwipe DOM nodes and visibility heuristics.

Use when:

- Diagnosing duplicate visible PhotoSwipe images.
- Checking placeholder/active slide DOM after open, close, or reopen.

Safety: Read-only console report. The global is attached during `usePhotoSwipe` setup.

### DEV lifecycle logs

Location: `frontend/src/debug/lifecycleDebug.ts`, installed from `frontend/src/main.ts` in DEV mode

Purpose: Logs `pageshow`, `pagehide`, `visibilitychange`, `freeze`, and `resume` events in development builds.

Enable: Run the Vite dev server (`cd frontend && npm run dev`).

Disable: Use a production build or remove the local dev investigation logging in a follow-up refactor.

Output: Console lines prefixed with `[LIFECYCLE]`.

Use when:

- Comparing page lifecycle events with reload black box output.
- Debugging mobile tab/background behavior.

Safety: DEV-only. Avoid adding `beforeunload` or `unload` listeners because those can hurt bfcache behavior.

## Standalone Diagnostic Scripts

### `scripts/debug_page_reloads.js`

Purpose: Copy-paste reload/navigation debugger for browser DevTools.

Enable: Paste the full file into DevTools console on the running gallery page.

Disable:

```js
__reloadDebug.stop();
__reloadDebug.clear();
```

Output: `__reloadDebug.report()` and `copyReport()` produce console/clipboard reports.

Use when:

- You need a no-build reload trace.
- The app-integrated reload black box was not enabled before the page loaded.

Safety: No localStorage persistence. Data is lost across reloads.

### `scripts/debug_lightbox_image_loads.js`

Purpose: Copy-paste lightbox image load debugger for `/api/thumbnail`, `/api/preview`, and `/api/image`.

Enable: Paste the full file into DevTools console, then run:

```js
__galleryLightboxDebug.start();
```

Disable:

```js
__galleryLightboxDebug.stop();
__galleryLightboxDebug.clear();
```

Output: `report()`, `copyReport()`, `json()`, and `status()` on `__galleryLightboxDebug`.

Use when:

- Normal lightbox open unexpectedly requests `/api/image`.
- Neighbor preloads use original images instead of thumbnail/preview derivatives.
- Duplicate image loads need to be grouped by path.

Safety: Monkeypatches fetch/XHR while active and restores on stop. Use only for local investigation.

### `scripts/debug_lightbox_image_loads_playwright.ts`

Purpose: Playwright diagnostic for lightbox image load behavior with JSON output.

Enable:

```bash
cd frontend
npx playwright test ../scripts/debug_lightbox_image_loads_playwright.ts --project=chromium
```

Optional environment variables: `GALLERY_BASE_URL`, `PATH_SAFETY_ROOT_PATH`, `GALLERY_DEBUG_ALBUM`, `GALLERY_DEBUG_ALBUM_PATH`, `GALLERY_DEBUG_LIGHTBOX_WAIT_MS`, `GALLERY_DEBUG_OUTPUT`.

Disable: No persistent state; stop the Playwright run.

Output: Console summary plus `debug-lightbox-image-loads.json` or `GALLERY_DEBUG_OUTPUT`.

Use when:

- You need reproducible lightbox endpoint evidence outside manual DevTools.
- Comparing suspicious `/api/image` requests across branches.

Safety: Diagnostic-only Playwright script. Requires a running app/backend with useful image data.

### `scripts/perf_scan.py`

Purpose: Measures `/api/scan` latency against a p95 budget.

Enable:

```bash
GALLERY_API_BASE_URL=http://localhost:8000 \
GALLERY_PERF_SCAN_PATH=/path/to/gallery \
python scripts/perf_scan.py
```

Disable: No persistent state.

Output: Compact JSON report on stdout; non-zero exit if p95 exceeds `GALLERY_PERF_SCAN_P95_BUDGET_MS`.

Use when:

- Changing scan performance, warm listing, or folder traversal.
- Checking real folder scan latency.

Safety: Read-only API calls against the configured backend.

### `scripts/perf_warm_listing.py`

Purpose: Compares cold direct scan and warm SQLite listing performance.

Enable:

```bash
python scripts/perf_warm_listing.py --path /path/to/folder --images 5000
```

Disable: No persistent state beyond any test fixtures it creates in the requested path.

Output: Timing report for cold and warm listing paths.

Use when:

- Changing warm indexed listing.
- Validating large-folder first-page performance.

Safety: Can create fixture files when pointed at a generated test folder. Do not run against a folder where synthetic files would be unsafe.

## Debug Organization

- Runtime-wired debug modules live in `frontend/src/debug/`.
- Mixed runtime utilities stay in their normal locations and only their debug flags are documented here.
- Standalone browser or Playwright diagnostics live under `scripts/`.
- Debug output should remain off by default and should not expose internal fields in normal production UI.
