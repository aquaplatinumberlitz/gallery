# Reload Debugging

## Why Reloads Happen on iPhone Safari

The gallery app occasionally reloads automatically on iPhone Safari. This is **not** caused by the app code calling `location.reload()`, and no JS crash was captured. Based on observed BlackBox reports:

- `currentNavigationType = "reload"`
- No JS reload call detected (`jsReload = false`)
- No errors (`errors = 0`)
- Vite HMR WebSocket was active (`hmrWebSocket = true`)
- `pagehideBeforeReload = true`
- Stack includes `@vite/client` waitForSuccessfulPing/handleMessage

**Root cause chain:**
1. iPhone Safari background/foregrounds the tab (memory pressure)
2. Vite HMR WebSocket disconnects on visibility change
3. Vite client attempts to reconnect (`waitForSuccessfulPing`)
4. On reconnect failure, Vite client triggers a full page reload

This is expected in Vite dev mode and should **not** be confused with a real app reload bug.

## Reload BlackBox Monitor

An in-repo persistent reload monitor that starts **before Vue initializes**, patches WebSocket to catch Vite HMR connections, and persists events in localStorage.

### How to Enable

```
https://150.230.56.153/?debugReload=1
```

Or via localStorage (survives tab close):

```js
localStorage.setItem("GALLERY_DEBUG_RELOAD", "1");
location.reload();
```

### How to Get a Report

```js
window.__galleryReloadBlackBox.report();
// or
window.__galleryReloadBlackBox.copyReport();
```

`copyReport()` copies to clipboard with iOS/HTTP-safe fallback (textarea + execCommand).

### How to Clear Stored Events

```js
window.__galleryReloadBlackBox.clear();
```

### How to Disable

```js
window.__galleryReloadBlackBox.disable();
// then remove the query param from URL and reload
```

Or manually:

```js
localStorage.removeItem("GALLERY_DEBUG_RELOAD");
location.reload();
```

### How to Check Status

```js
window.__galleryReloadBlackBox.status();
```

### How to Add Custom Log Marks

```js
window.__galleryReloadBlackBox.log("my-event", "user tapped search");
```

### API Reference

| Method      | Description                                              |
|-------------|----------------------------------------------------------|
| `report()`  | Print formatted report to console                        |
| `copyReport()` | Copy report to clipboard (iOS fallback included)      |
| `clear()`   | Wipe all stored events from localStorage                 |
| `status()`  | Print current monitor state                              |
| `enable()`  | Enable for next reload (sets localStorage flag)          |
| `disable()` | Disable and wipe all stored data                         |
| `log(tag, msg)` | Manually log a custom event                          |

### How to Interpret a Report

| Field | Value | Meaning |
|-------|-------|---------|
| `jsReload` | `true` | Code called `location.reload()` / `.assign()` / `.replace()` |
| `jsReload` | `false` | No JS navigation; reload came from browser or HMR |
| `hmrWebSocket` | `true` | Vite HMR WebSocket was active during session |
| `errors` | `> 0` | App crashed before reload; fix the error first |
| `pagehideBeforeReload` | `true` | Safari likely discarded/backgrounded the page |
| Stack includes `@vite/client` | — | Vite HMR client triggered the reload |

### How to Diagnose Pull-to-Refresh / Overscroll Reload

When reports show `"Browser-level reload"` with no HMR, no errors, and `pagehide(persisted=false)`, the cause may be **iOS Safari pull-to-refresh** (rubber-band overscroll at top of page).

**Steps to diagnose:**

1. Start mobile dev with HMR off:
   ```bash
   npm run dev:mobile
   ```

2. Open on iPhone:
   ```
   http://150.230.56.153/?debugReload=1
   ```

3. Clear previous logs:
   ```js
   window.__galleryReloadBlackBox.clear()
   ```

4. Reproduce the issue — scroll the gallery normally, switch tabs, etc.

5. After the reload, open the page again and copy the report:
   ```js
   window.__galleryReloadBlackBox.copyReport()
   ```
   (Use the floating "Copy Reload Report" button at bottom-right.)

6. Check the **Pull-to-Refresh Analysis** section:
   - `likelyPullToRefresh` — true if heuristics fire
   - `wasAtTopBeforePagehide` — was scrollY ≤ 20px?
   - `wasPullingDownBeforePagehide` — was touch moving downward at top?
   - `lastTouchMoveDeltaY` — how far was the last swipe (positive = down)
   - `scrollYBeforePagehide` — scroll position when page was hidden
   - `timeFromTouch->pagehide` — how recently was the user touching?

**How to read the results:**

| Pattern | Likely cause |
|---------|-------------|
| `wasAtTop=true`, `wasPullingDown=true`, recent touch | Pull-to-refresh (Safari rubber-band) |
| No touch events, `wasAtTop=false` | Tab discard / browser-level |
| `pagehide(persisted=true)` then reload | bfcache eviction, not pull-to-refresh |
| `location.*` call in timeline | JS-triggered reload |

**⚠️ Warnings:**
- Do not paste `copyReport()` into Safari address bar — use Eruda Console or the floating button.
- Eruda itself adds `beforeunload`/`unload`/`pagehide` listeners that can affect bfcache. For clean pull-to-refresh testing, prefer the built-in blackbox floating UI.

## Pull-to-Refresh Evidence Fields

When you generate a report, the `pullToRefresh` section provides these fields:

| Field | Description |
|-------|-------------|
| `likely` | Boolean — heuristic score ≥ 4 |
| `confidence` | String: `"high"`, `"medium"`, `"low"`, `"none"` |
| `reason` | Human-readable signal summary |
| `lastTouchMoveDeltaY` | Last recorded touch movement delta Y (px) |
| `lastTouchMoveDirection` | `"down"`, `"up"`, `"left"`, `"right"`, `"none"` |
| `scrollYBeforePagehide` | Document scroll Y when pagehide fired |
| `wasAtTopBeforePagehide` | `scrollY ≤ 20` when pagehide fired |
| `wasPullingDownBeforePagehide` | Last gesture had downward movement at top |
| `timeFromLastTouchMoveToPagehideMs` | ms since last touchmove when pagehide fired |
| `timeFromLastScrollToPagehideMs` | ms since last scroll when pagehide fired |
| `visualViewportChangedBeforePagehide` | Whether iOS visual viewport resized/scrolled |

### Test Cases

| Setup | Expected |
|-------|----------|
| HTTP dev (HMR on) + iPhone hide/show | May reload (Vite HMR reconnect) |
| HTTP dev (HMR off) + iPhone hide/show | No reload |
| Production build, HTTP | No reload |
| Production build, HTTPS | No reload |

## Mobile Dev Mode (No HMR)

For iPhone testing without Vite HMR auto-reload:

```bash
npm run dev:mobile
```

This starts the Vite dev server with HMR disabled:

- `server.hmr = false`
- `host = "0.0.0.0"`
- normal proxy, hot module replacement off

The iPhone still benefits from Vite's fast refresh; it just needs a manual Safari refresh to pick up code changes.

### Nginx Config for HTTP Dev

On VPS, the nginx site uses HTTP on port 80 proxying to the Vite dev server on port 4173. HTTPS self-signed certs are not used because iOS Safari handles HTTP tab restore better.

## Eruda Warning

Eruda adds `beforeunload`/`unload`/`pagehide` listeners that can affect bfcache behavior. For clean reload testing, prefer the in-repo BlackBox monitor over pasted console scripts or Eruda.

## File Locations

- **BlackBox monitor:** `frontend/src/debug/reloadBlackBox.ts`
  - Phases 1-2: WebSocket patching + boot recording
  - Phases 3-4: Lifecycle + error tracking
  - Phases 5-6: Location/History API monkeypatching
  - Phase 7: Global API (`window.__galleryReloadBlackBox`)
  - Phase 8: Floating debug buttons
  - Phase 9: Gesture/scroll tracking (touch, wheel, visualViewport, orientation)
- **Old monitor (legacy):** `frontend/src/debug/reloadMonitor.ts`
- **Type declarations:** `frontend/src/env.d.ts`
- **Initialization:** `frontend/src/main.ts` (called before `createApp()`)
- **Config:** `frontend/vite.config.ts` (conditional hmr)
- **Scripts:** `frontend/package.json` (`dev`, `dev:mobile`)
