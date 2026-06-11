/**
 * Persistent Reload BlackBox monitor.
 *
 * Captures page lifecycle, WebSocket/HMR activity, errors, and navigation
 * BEFORE the Vite client or Vue app initializes. Persists events in localStorage
 * so they survive page reloads.
 *
 * Enable:  ?debugReload=1                  (URL query param, one-shot)
 *          localStorage.setItem("GALLERY_DEBUG_RELOAD", "1")   (persistent)
 * Disable: window.__galleryReloadBlackBox.disable()
 *          localStorage.removeItem("GALLERY_DEBUG_RELOAD")
 *          location.reload()
 *
 * API (via window.__galleryReloadBlackBox):
 *   report()       — print formatted report to console
 *   copyReport()   — copy report to clipboard (iOS-safe fallback)
 *   clear()        — wipe stored events
 *   status()       — print status summary
 *   enable()       — re-enable (set localStorage + reinstall listeners)
 *   disable()      — disable and wipe data
 *   log(tag, msg)  — manual event log
 */

const STORAGE_KEY = "__gallery_reload_blackbox_v2";
const STORAGE_ENABLED_KEY = "GALLERY_DEBUG_RELOAD";
const MAX_EVENTS = 500;

/* ── Types ─────────────────────────────────────────────────────────── */

interface BBEvent {
  t: number;            // timestamp
  type: string;         // event type
  detail: string;       // JSON serialized detail (limited to 500 chars)
}

interface BootRecord {
  ts: number;
  url: string;
  navType: string;
  referrer: string;
  ua: string;
  vw: number;
  vh: number;
  dpr: number;
  vis: string;
  online: boolean;
  bootCount: number;
  sessionId: string;
}

/* ── Gesture/scroll types ──────────────────────────────────────────── */

interface GestureEvent {
  t: number;
  type: string;
  target: string;
  x: number;
  y: number;
  deltaY: number;
  deltaX: number;
  direction: string;       // "up" | "down" | "left" | "right" | "none"
  scrollY: number;
  nearTop: boolean;         // scrollTop <= 20
  pullingDownAtTop: boolean; // at or near top AND moving downward
  docScrollTop: number;
  docScrollHeight: number;
  docClientHeight: number;
}

const GESTURE_BUF_MAX = 80;

interface ScrollSnapshot {
  scrollY: number;
  scrollX: number;
  scrollHeight: number;
  clientHeight: number;
  nearTop: boolean;
  nearBottom: boolean;
  target: string;          // element id/class
}

interface PullToRefreshEvidence {
  likely: boolean;
  confidence: string;      // "high" | "medium" | "low"
  reason: string;
  lastTouchMoveDeltaY: number;
  lastTouchMoveDirection: string;
  scrollYBeforePagehide: number;
  wasAtTopBeforePagehide: boolean;
  wasPullingDownBeforePagehide: boolean;
  timeFromLastTouchMoveToPagehideMs: number;
  timeFromLastScrollToPagehideMs: number;
  visualViewportChangedBeforePagehide: boolean;
}

interface Report {
  meta: { generatedAt: string; sessionId: string; bootCount: number; currentUrl: string };
  summary: {
    totalEvents: number;
    beforeUnloadCount: number;
    pageHideCount: number;
    errorCount: number;
    rejectionCount: number;
    wsOpenCount: number;
    wsCloseCount: number;
    locationChangeCount: number;
    jsReload: boolean;
    hmrWebSocket: boolean;
    pagehideBeforeReload: boolean;
    errors: number;
    totalTouchMoves: number;
    totalScrolls: number;
  };
  suspects: string[];
  pullToRefresh: PullToRefreshEvidence;
  timeline: { rel: number; type: string; detail: string }[];
  lastEvents: { rel: number; type: string; detail: string }[];
  gestureLastEvents: { rel: number; type: string; detail: string }[];
  scrollLastEvents: { rel: number; type: string; detail: string }[];
  lastGestureBeforeUnload: { rel: number; type: string; detail: string } | null;
  lastScrollBeforeUnload: { rel: number; type: string; detail: string } | null;
  raw: BBEvent[];
}

/* ── Storage helpers ───────────────────────────────────────────────── */

function safeGet<K = string>(key: string): K | null {
  try { return JSON.parse(localStorage.getItem(key)!) as K; } catch { return null; }
}
function safeSet(key: string, val: unknown) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch { /* quota */ }
}
function safeRemove(key: string) {
  try { localStorage.removeItem(key); } catch { /* ignore */ }
}

/* ── Local state ───────────────────────────────────────────────────── */

let _bootCount = 0;
let _sessionId = "";
let _events: BBEvent[] = [];
let _bootTime = 0;
let _installed = false;
let _disableHandlers: (() => void)[] = [];

/* ── Gesture/scroll state ──────────────────────────────────────────── */

let _gestureEvents: GestureEvent[] = [];
let _totalTouchMoves = 0;
let _totalScrolls = 0;
let _lastTouchMove: { t: number; x: number; y: number; deltaY: number; direction: string; nearTop: boolean; pullingDownAtTop: boolean } | null = null;
let _lastScrollSnapshot: ScrollSnapshot | null = null;
let _lastGestureBeforePagehide: GestureEvent | null = null;
let _lastScrollBeforePagehide: ScrollSnapshot | null = null;
let _visualViewportChangedBeforePagehide = false;
let _vvInitialHeight = 0;
let _vvInitialWidth = 0;

/* ── Event logging ─────────────────────────────────────────────────── */

function addEvent(type: string, detail: Record<string, unknown> = {}) {
  let detailStr = JSON.stringify(detail);
  if (detailStr.length > 500) detailStr = detailStr.slice(0, 497) + "...";
  _events.push({ t: Date.now(), type, detail: detailStr });
  if (_events.length > MAX_EVENTS) _events.splice(0, _events.length - MAX_EVENTS);
  safeSet(STORAGE_KEY, _events);
}

/* ── Stack trace (lightweight) ─────────────────────────────────────── */

function getStack(depth = 3): string {
  try {
    const e = new Error();
    const lines = (e.stack || "").split("\n").slice(2, 2 + depth);
    return lines.map(l => l.trim()).join(" | ");
  } catch { return "(stack n/a)"; }
}

/* ── Navigation type ───────────────────────────────────────────────── */

function getNavType(): string {
  try {
    const e = performance.getEntriesByType("navigation") as PerformanceNavigationTiming[];
    return e.length ? e[0].type : "unknown";
  } catch { return "unknown"; }
}

/* ── Scroll/gesture helpers ─────────────────────────────────────────── */

function getTargetSummary(el: EventTarget | null): string {
  if (!el || !(el instanceof Element)) return "(global)";
  const tag = el.tagName.toLowerCase();
  const id = el.id ? `#${el.id}` : "";
  const cls = typeof el.className === "string"
    ? el.className.split(/\s+/).slice(0, 2).join(".").slice(0, 40)
    : "";
  return `${tag}${id}${cls ? "." + cls : ""}`;
}

function getScrollSnapshot(target?: EventTarget | null): ScrollSnapshot {
  const scrollY = window.scrollY || window.pageYOffset || document.documentElement.scrollTop || 0;
  const docEl = document.documentElement;
  const scrollHeight = docEl.scrollHeight;
  const clientHeight = docEl.clientHeight;
  return {
    scrollY: Math.round(scrollY),
    scrollX: Math.round(window.scrollX || 0),
    scrollHeight: Math.round(scrollHeight),
    clientHeight: Math.round(clientHeight),
    nearTop: scrollY <= 20,
    nearBottom: scrollY + clientHeight >= scrollHeight - 20,
    target: target ? getTargetSummary(target) : "document"
  };
}

function isAtTop(): boolean {
  return (window.scrollY || document.documentElement.scrollTop || 0) <= 20;
}

function recordGesture(gesture: GestureEvent): void {
  _gestureEvents.push(gesture);
  if (_gestureEvents.length > GESTURE_BUF_MAX) {
    _gestureEvents.splice(0, _gestureEvents.length - GESTURE_BUF_MAX);
  }
  _lastTouchMove = {
    t: gesture.t,
    x: gesture.x,
    y: gesture.y,
    deltaY: gesture.deltaY,
    direction: gesture.direction,
    nearTop: gesture.nearTop,
    pullingDownAtTop: gesture.pullingDownAtTop
  };
}

/* ── Pull-to-refresh detection ─────────────────────────────────────── */

function detectPullToRefresh(boot: BootRecord, hasJsReload: boolean, hasHmrWS: boolean): PullToRefreshEvidence {
  const ev = _events;
  const types = ev.map(e => e.type);
  const errs = types.filter(t => t === "error" || t === "unhandledrejection").length;

  const lastPH = _events.filter(e => e.type === "pagehide").pop();
  const phPersistedFalse = lastPH ? lastPH.detail.includes('"persisted":false') : false;

  const lastTM = _lastTouchMove;
  const now = Date.now();
  const timeFromTouch = lastTM ? now - lastTM.t : -1;
  const timeFromScroll = _lastScrollSnapshot ? now - (_lastScrollSnapshot.scrollY ? now : now) : -1; // approximate

  const wasAtTop = isAtTop();
  const wasPulling = lastTM ? lastTM.pullingDownAtTop : false;
  const atTopAndPulling = wasAtTop && wasPulling;

  // Build confidence
  let score = 0;
  const signals: string[] = [];

  // Signal: navType is reload and no JS/HMR cause
  if (boot.navType === "reload" && !hasJsReload && !hasHmrWS && errs === 0) {
    score += 2;
    signals.push("browser-level reload, no JS/HMR/error");
  }

  // Signal: pagehide persisted=false before reload
  if (phPersistedFalse) {
    score += 1;
    signals.push("pagehide(persisted=false)");
  }

  // Signal: recent touch activity (within 1500ms)
  if (lastTM && timeFromTouch < 1500) {
    score += 2;
    signals.push(`last touchmove ${timeFromTouch}ms ago`);
  } else if (lastTM && timeFromTouch < 5000) {
    score += 1;
    signals.push(`last touchmove ${timeFromTouch}ms ago (moderate)`);
  }

  // Signal: user was pulling down at top
  if (atTopAndPulling) {
    score += 3;
    signals.push("pulling down at top of page");
  } else if (wasPulling) {
    score += 2;
    signals.push("was pulling down (not at top anymore)");
  }

  // Signal: downward movement
  if (lastTM && lastTM.direction === "down" && lastTM.deltaY > 10) {
    score += 1;
    signals.push(`downward swipe (deltaY=${Math.round(lastTM.deltaY)})`);
  }

  // Signal: total touch moves > 0 (user was actively touching)
  if (_totalTouchMoves > 0) {
    score += 1;
    signals.push(`${_totalTouchMoves} touch moves recorded`);
  }

  // Signal: no scrolling before reload (user was pulling, not scrolling)
  if (_totalScrolls === 0 && _totalTouchMoves > 0 && atTopAndPulling) {
    score += 1;
    signals.push("touching but no scroll events registered");
  }

  let confidence: string;
  if (score >= 6) confidence = "high";
  else if (score >= 4) confidence = "medium";
  else if (score >= 2) confidence = "low";
  else confidence = "none";

  const likely = score >= 4;

  return {
    likely,
    confidence,
    reason: signals.length > 0 ? signals.join("; ") : "insufficient evidence",
    lastTouchMoveDeltaY: lastTM ? Math.round(lastTM.deltaY) : 0,
    lastTouchMoveDirection: lastTM ? lastTM.direction : "none",
    scrollYBeforePagehide: _lastScrollBeforePagehide?.scrollY ?? Math.round(window.scrollY || 0),
    wasAtTopBeforePagehide: _lastScrollBeforePagehide?.nearTop ?? isAtTop(),
    wasPullingDownBeforePagehide: _lastGestureBeforePagehide?.pullingDownAtTop ?? false,
    timeFromLastTouchMoveToPagehideMs: timeFromTouch,
    timeFromLastScrollToPagehideMs: timeFromScroll,
    visualViewportChangedBeforePagehide: _visualViewportChangedBeforePagehide
  };
}

/* ── Suspect classification ────────────────────────────────────────── */

function classify(e: BBEvent[], boot: BootRecord): string[] {
  const s: string[] = [];
  const types = e.map(x => x.type);
  const details = e.map(x => x.detail);

  // JS reload
  if (types.some(t => t.startsWith("location."))) {
    s.push("⚠️ JS RELOAD: location.reload/assign/replace was called");
  }

  // Errors
  const errs = types.filter(t => t === "error" || t === "unhandledrejection").length;
  if (errs > 0) s.push(`⚠️ ${errs} unhandled error(s) — possible crash before reload`);

  // WebSocket (Vite HMR)
  const wsCloses = e.filter(t => t.type === "websocket-close");
  const wsHasVite = wsCloses.some(c => c.detail.includes("vite") || c.detail.includes("@vite"));
  if (wsCloses.length > 0) {
    s.push(`ℹ️ ${wsCloses.length} WebSocket close(s)${wsHasVite ? " (incl. Vite HMR)" : ""}`);
  }

  // pagehide without persisted
  const pagehides = e.filter(x => x.type === "pagehide");
  for (const ph of pagehides) {
    if (ph.detail.includes('"persisted":false')) {
      s.push("⚠️ pagehide(persisted=false) — page likely discarded by browser");
      break;
    }
  }

  // Navigation type = reload with no JS cause
  if (boot.navType === "reload") {
    const hasJs = types.some(t => t.startsWith("location.") || t === "websocket-close");
    if (!hasJs && errs === 0) {
      s.push("ℹ️ reload from browser-level cause (refresh button, tab discard, address bar)");
    }
  }

  // bfcache
  if (types.some(t => t === "pageshow" && details.some(d => d.includes('"persisted":true')))) {
    s.push("✅ bfcache restore detected (pageshow persisted=true)");
  }

  return s;
}

/* ── Report generation ─────────────────────────────────────────────── */

function generateReport(): Report {
  const boot: BootRecord = safeGet<BootRecord>(`${STORAGE_KEY}_boot`) || {
    ts: _bootTime, url: "", navType: "unknown", referrer: "", ua: "",
    vw: 0, vh: 0, dpr: 1, vis: "unknown", online: true,
    bootCount: _bootCount, sessionId: _sessionId
  };

  const stats = {
    beforeUnloadCount: 0, pageHideCount: 0, errorCount: 0, rejectionCount: 0,
    wsOpenCount: 0, wsCloseCount: 0, locationChangeCount: 0
  };
  for (const e of _events) {
    if (e.type === "beforeunload") stats.beforeUnloadCount++;
    if (e.type === "pagehide") stats.pageHideCount++;
    if (e.type === "error") stats.errorCount++;
    if (e.type === "unhandledrejection") stats.rejectionCount++;
    if (e.type === "websocket-open") stats.wsOpenCount++;
    if (e.type === "websocket-close") stats.wsCloseCount++;
    if (e.type.startsWith("location.")) stats.locationChangeCount++;
  }

  const hasJsReload = _events.some(e => e.type.startsWith("location."));
  const hasHmrWS = _events.some(e =>
    e.type === "websocket-open" &&
    (e.detail.includes("vite") || e.detail.includes("@vite") || e.detail.includes("/ws"))
  );
  const hasPagehideBeforeReload = _events.some(e => e.type === "pagehide" && e.detail.includes('"persisted":false'));

  // ── Gesture analysis ──────────────────────────────────────────────

  const ptrEvidence = detectPullToRefresh(boot, hasJsReload, hasHmrWS);

  // Last 15 gesture events for report
  const gestureTimeline = _gestureEvents.slice(-15).map(g => ({
    rel: g.t - _bootTime,
    type: g.type,
    detail: JSON.stringify({
      x: g.x, y: g.y, dY: g.deltaY, dir: g.direction,
      sY: g.scrollY, nearTop: g.nearTop, pulling: g.pullingDownAtTop,
      target: g.target
    })
  }));

  // Last 15 scroll/viewport events from main event log
  const scrollEvents = _events.filter(e =>
    e.type === "scroll" || e.type === "visualViewport" ||
    e.type === "orientationchange" || e.type === "resize"
  );
  const scrollTimeline = scrollEvents.slice(-15).map(e => ({
    rel: e.t - _bootTime,
    type: e.type,
    detail: e.detail
  }));

  // Last gesture/scroll before pagehide
  const lastGestureBeforeUnload = _lastGestureBeforePagehide ? {
    rel: _lastGestureBeforePagehide.t - _bootTime,
    type: _lastGestureBeforePagehide.type,
    detail: JSON.stringify({
      x: _lastGestureBeforePagehide.x, y: _lastGestureBeforePagehide.y,
      dY: _lastGestureBeforePagehide.deltaY, dir: _lastGestureBeforePagehide.direction,
      sY: _lastGestureBeforePagehide.scrollY,
      nearTop: _lastGestureBeforePagehide.nearTop,
      pulling: _lastGestureBeforePagehide.pullingDownAtTop
    })
  } : null;

  const lastScrollBeforeUnload = _lastScrollBeforePagehide ? {
    rel: _lastScrollBeforePagehide.scrollY, // not time-based, but state
    type: "scroll-snapshot",
    detail: JSON.stringify(_lastScrollBeforePagehide)
  } : null;

  const timeline = _events.map(e => ({
    rel: e.t - _bootTime,
    type: e.type,
    detail: e.detail
  }));

  // Last 30 events (before the last unload/pagehide if any)
  let lastUnloadIdx = -1;
  for (let i = _events.length - 1; i >= 0; i--) {
    if (["beforeunload", "pagehide", "unload"].includes(_events[i].type)) {
      lastUnloadIdx = i;
      break;
    }
  }
  const lastEvents = lastUnloadIdx >= 0
    ? _events.slice(Math.max(0, lastUnloadIdx - 29), lastUnloadIdx + 1)
    : _events.slice(-30);

  const suspects = classify(_events, boot);

  return {
    meta: {
      generatedAt: new Date().toISOString(),
      sessionId: _sessionId,
      bootCount: _bootCount,
      currentUrl: window.location.href
    },
    summary: {
      totalEvents: _events.length,
      ...stats,
      jsReload: hasJsReload,
      hmrWebSocket: hasHmrWS,
      pagehideBeforeReload: hasPagehideBeforeReload,
      errors: stats.errorCount + stats.rejectionCount,
      totalTouchMoves: _totalTouchMoves,
      totalScrolls: _totalScrolls
    },
    suspects,
    pullToRefresh: ptrEvidence,
    timeline,
    lastEvents: lastEvents.map(e => ({
      rel: e.t - _bootTime,
      type: e.type,
      detail: e.detail
    })),
    gestureLastEvents: gestureTimeline,
    scrollLastEvents: scrollTimeline,
    lastGestureBeforeUnload,
    lastScrollBeforeUnload,
    raw: _events.slice(-80)
  };
}

function formatReport(r: Report): string {
  const L = "─".repeat(55);
  const lines: string[] = [];

  lines.push(`┌${L}┐`);
  lines.push(`│  RELOAD BLACKBOX REPORT                          │`);
  lines.push(`└${L}┘`);
  lines.push(` Generated:  ${r.meta.generatedAt}`);
  lines.push(` Session:    ${r.meta.sessionId}`);
  lines.push(` Boot #:     ${r.meta.bootCount}`);
  lines.push(` URL:        ${r.meta.currentUrl}`);
  lines.push("");

  lines.push(`── Summary ──────────────────────────────────────────`);
  const s = r.summary;
  lines.push(`  Reload type:          ${s.jsReload ? "JS-triggered" : s.hmrWebSocket ? "Vite HMR" : "Browser-level"}`);
  lines.push(`  Total events:         ${s.totalEvents}`);
  lines.push(`  beforeunload:         ${s.beforeUnloadCount}`);
  lines.push(`  pagehide:             ${s.pageHideCount}`);
  lines.push(`  Errors:               ${s.errorCount}`);
  lines.push(`  Rejections:           ${s.rejectionCount}`);
  lines.push(`  WebSocket open:       ${s.wsOpenCount}`);
  lines.push(`  WebSocket close:      ${s.wsCloseCount}`);
  lines.push(`  location.* calls:     ${s.locationChangeCount}`);
  lines.push(`  jsReload:             ${s.jsReload}`);
  lines.push(`  hmrWebSocket:         ${s.hmrWebSocket}`);
  lines.push(`  pagehideBeforeReload: ${s.pagehideBeforeReload}`);
  lines.push(`  Touch moves:          ${s.totalTouchMoves}`);
  lines.push(`  Scroll events:        ${s.totalScrolls}`);

  lines.push("");
  lines.push(`── Suspects ──────────────────────────────────────────`);
  if (r.suspects.length === 0) {
    lines.push("  (none — normal navigation)");
  } else {
    for (const x of r.suspects) lines.push(`  ${x}`);
  }

  lines.push("");
  lines.push(`── Pull-to-Refresh Analysis ──────────────────────────`);
  const ptr = r.pullToRefresh;
  if (ptr.likely) {
    lines.push(`  🔴 LIKELY PULL-TO-REFRESH (confidence: ${ptr.confidence})`);
  } else if (ptr.confidence !== "none") {
    lines.push(`  🟡 Possible (confidence: ${ptr.confidence})`);
  } else {
    lines.push(`  🟢 No pull-to-refresh indicators`);
  }
  lines.push(`  Reason:                  ${ptr.reason}`);
  lines.push(`  lastTouchMoveDeltaY:     ${ptr.lastTouchMoveDeltaY}`);
  lines.push(`  lastTouchMoveDirection:  ${ptr.lastTouchMoveDirection}`);
  lines.push(`  scrollYBeforePagehide:   ${ptr.scrollYBeforePagehide}`);
  lines.push(`  wasAtTopBeforePagehide:  ${ptr.wasAtTopBeforePagehide}`);
  lines.push(`  wasPullingDown:          ${ptr.wasPullingDownBeforePagehide}`);
  lines.push(`  timeFromTouch->pagehide: ${ptr.timeFromLastTouchMoveToPagehideMs}ms`);
  lines.push(`  timeFromScroll->pagehide:${ptr.timeFromLastScrollToPagehideMs}ms`);
  lines.push(`  vvChangedBeforePagehide: ${ptr.visualViewportChangedBeforePagehide}`);

  if (r.lastGestureBeforeUnload) {
    lines.push("");
    lines.push(`── Last Gesture Before Unload ────────────────────────`);
    lines.push(`  ${r.lastGestureBeforeUnload.detail}`);
  }

  if (r.lastScrollBeforeUnload) {
    lines.push("");
    lines.push(`── Last Scroll Before Unload ─────────────────────────`);
    lines.push(`  ${r.lastScrollBeforeUnload.detail}`);
  }

  lines.push("");
  lines.push(`── Last 20 Gesture Events ────────────────────────────`);
  const gl = r.gestureLastEvents;
  if (gl.length === 0) {
    lines.push("  (no gesture events recorded)");
  } else {
    for (const g of gl) {
      const rel = g.rel >= 0 ? `+${g.rel}ms` : `${g.rel}ms`;
      const d = g.detail;
      lines.push(`  [${rel}] ${g.type}`);
      if (d && d.length > 4) lines.push(`          ${d.length > 140 ? d.slice(0, 137) + "..." : d}`);
    }
  }

  if (r.scrollLastEvents.length > 0) {
    lines.push("");
    lines.push(`── Last 15 Scroll/Viewport Events ───────────────────`);
    for (const e of r.scrollLastEvents) {
      const rel = e.rel >= 0 ? `+${e.rel}ms` : `${e.rel}ms`;
      lines.push(`  [${rel}] ${e.type}: ${e.detail.length > 120 ? e.detail.slice(0, 117) + "..." : e.detail}`);
    }
  }

  lines.push("");
  lines.push(`── Timeline (last 40) ────────────────────────────────`);
  const tim = r.timeline.slice(-40);
  for (const e of tim) {
    const rel = e.rel >= 0 ? `+${e.rel}ms` : `${e.rel}ms`;
    lines.push(`  [${rel}] ${e.type}`);
    const d = e.detail;
    if (d && d !== "{}" && d.length > 2) {
      lines.push(`          ${d.length > 120 ? d.slice(0, 117) + "..." : d}`);
    }
  }

  lines.push("");
  lines.push(`── Last Events Before Unload ─────────────────────────`);
  if (r.lastEvents.length === 0) {
    lines.push("  (no unload detected)");
  } else {
    for (const e of r.lastEvents.slice(-15)) {
      const rel = e.rel >= 0 ? `+${e.rel}ms` : `${e.rel}ms`;
      lines.push(`  [${rel}] ${e.type}`);
    }
  }

  lines.push("");
  lines.push(`└${L}┘`);
  return lines.join("\n");
}

/* ── Public API ────────────────────────────────────────────────────── */

function report() {
  console.log(formatReport(generateReport()));
}

async function copyReport() {
  const text = formatReport(generateReport());
  // Preferred: Clipboard API
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      console.log("[ReloadBB] Report copied to clipboard");
      return;
    }
  } catch { /* fall through */ }
  // Fallback: textarea (works on iOS HTTP)
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.cssText = "position:fixed;left:-9999px;top:-9999px";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    console.log("[ReloadBB] Report copied (fallback)");
  } catch (e) {
    console.warn("[ReloadBB] Copy failed:", e);
    // Last resort: log the text so user can screenshot
    console.log(text);
  }
}

function clear() {
  _events = [];
  safeRemove(STORAGE_KEY);
  safeRemove(`${STORAGE_KEY}_boot`);
  safeRemove(STORAGE_ENABLED_KEY);
  console.log("[ReloadBB] Cleared all stored events");
}

function status() {
  console.log(`[ReloadBB] State:
  installed:  ${_installed}
  bootCount:  ${_bootCount}
  sessionId:  ${_sessionId}
  events:     ${_events.length}
  storage:    ${STORAGE_KEY}
  enabled:    ${safeGet(STORAGE_ENABLED_KEY) === "1" || "0"}`);
}

function enable() {
  safeSet(STORAGE_ENABLED_KEY, "1");
  console.log("[ReloadBB] Enabled (set localStorage). Reload to activate.");
}

function disable() {
  // Remove all stored data
  safeRemove(STORAGE_KEY);
  safeRemove(`${STORAGE_KEY}_boot`);
  safeRemove(STORAGE_ENABLED_KEY);
  // Remove all listeners
  for (const fn of _disableHandlers) fn();
  _disableHandlers = [];
  _events = [];
  _installed = false;
  console.log("[ReloadBB] Disabled. Remove ?debugReload=1 from URL and reload.");
}

function log(tag: string, msg: string) {
  addEvent("manual-log", { tag, msg });
}

/* ── Installation ──────────────────────────────────────────────────── */

export function installReloadBlackBoxIfEnabled(): void {
  // Check enable condition
  const hasParam = typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).has("debugReload");
  const hasStorage = safeGet<string>(STORAGE_ENABLED_KEY) === "1";

  if (!hasParam && !hasStorage) return;
  if (_installed) return;
  _installed = true;

  _bootTime = Date.now();
  _events = safeGet<BBEvent[]>(STORAGE_KEY) || [];
  _sessionId = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

  const prevBoot = parseInt(safeGet<string>(`${STORAGE_KEY}_bootCount`) || "0", 10);
  _bootCount = prevBoot + 1;
  safeSet(`${STORAGE_KEY}_bootCount`, _bootCount);

  // Ensure enabled flag is set
  safeSet(STORAGE_ENABLED_KEY, "1");

  // ── Phase 1: WebSocket patching (BEFORE anything else) ──────────

  patchWebSocket();

  // ── Phase 2: Record boot ────────────────────────────────────────

  const bootRec: BootRecord = {
    ts: _bootTime,
    url: window.location.href,
    navType: getNavType(),
    referrer: document.referrer,
    ua: navigator.userAgent,
    vw: window.innerWidth,
    vh: window.innerHeight,
    dpr: window.devicePixelRatio || 1,
    vis: document.visibilityState,
    online: navigator.onLine,
    bootCount: _bootCount,
    sessionId: _sessionId,
  };
  safeSet(`${STORAGE_KEY}_boot`, bootRec);
  addEvent("boot", { ...bootRec, navTiming: "see storage" });

  // ── Phase 3: Lifecycle listeners ────────────────────────────────

  function on(type: string, el: EventTarget, cb: (e: Event) => void) {
    el.addEventListener(type, cb);
    _disableHandlers.push(() => el.removeEventListener(type, cb));
  }

  on("beforeunload", window, () => addEvent("beforeunload", { url: window.location.href }));
  on("pagehide", window, (e: Event) => {
    const pe = e as PageTransitionEvent;
    // Capture synchronous state before page goes away
    _lastScrollBeforePagehide = getScrollSnapshot();
    _lastGestureBeforePagehide = _gestureEvents.length > 0
      ? _gestureEvents[_gestureEvents.length - 1]
      : null;
    addEvent("pagehide", {
      persisted: pe.persisted,
      url: window.location.href,
      scrollY: _lastScrollBeforePagehide.scrollY,
      nearTop: _lastScrollBeforePagehide.nearTop,
      "lastTouchMove.deltaY": _lastTouchMove?.deltaY ?? 0,
      "lastTouchMove.direction": _lastTouchMove?.direction ?? "none",
      "lastTouchMove.pullingAtTop": _lastTouchMove?.pullingDownAtTop ?? false,
      "lastTouchMove.msAgo": _lastTouchMove ? Date.now() - _lastTouchMove.t : -1,
      totalTouchMoves: _totalTouchMoves
    });
  });
  on("pageshow", window, (e: Event) => {
    const pe = e as PageTransitionEvent;
    addEvent("pageshow", { persisted: pe.persisted, url: window.location.href });
  });
  on("visibilitychange", document, () => addEvent("visibilitychange", {
    state: document.visibilityState
  }));
  on("freeze", window, () => addEvent("freeze", {}));
  on("resume", window, () => addEvent("resume", {}));
  // NOTE: unload listener intentionally omitted — it blocks bfcache on iOS Safari
  // and contributes to the very page discards we're trying to diagnose.
  // pagehide is sufficient: it fires in both bfcache (persisted=true) and
  // non-bfcache (persisted=false) scenarios.
  on("popstate", window, () => addEvent("popstate", { url: window.location.href }));

  // ── Phase 4: Error tracking ─────────────────────────────────────

  on("error", window, (e: Event) => {
    const ee = e as ErrorEvent;
    addEvent("error", {
      message: ee.message,
      filename: ee.filename,
      lineno: ee.lineno,
      stack: (ee.error as Error)?.stack?.slice(0, 300) || "(no stack)"
    });
  });

  on("unhandledrejection", window, (e: Event) => {
    const pe = e as PromiseRejectionEvent;
    const reason = pe.reason;
    addEvent("unhandledrejection", {
      reason: String(reason),
      stack: (reason instanceof Error ? reason.stack?.slice(0, 300) : undefined) || "(n/a)"
    });
  });

  // ── Phase 5: Location API monkeypatching ────────────────────────

  try {
    const proto = Object.getPrototypeOf(window.location) as Record<string, unknown>;
    const origReload = proto.reload as ((...a: unknown[]) => void);
    const origAssign = proto.assign as ((...a: unknown[]) => void);
    const origReplace = proto.replace as ((...a: unknown[]) => void);

    if (typeof origReload === "function") {
      proto.reload = function (this: Location) {
        addEvent("location.reload", { stack: getStack(4) });
        return origReload.apply(this, arguments as unknown as []);
      } as () => void;
    }
    if (typeof origAssign === "function") {
      proto.assign = function (this: Location, url: string) {
        addEvent("location.assign", { url: String(url), stack: getStack(4) });
        return origAssign.apply(this, [url]);
      } as (url: string) => void;
    }
    if (typeof origReplace === "function") {
      proto.replace = function (this: Location, url: string) {
        addEvent("location.replace", { url: String(url), stack: getStack(4) });
        return origReplace.apply(this, [url]);
      } as (url: string) => void;
    }

    // Also detect location.href set via getter/setter
    // (complex — skip for now, the prototype patches cover the main cases)
  } catch { /* location patching failed — security restriction */ }

  // ── Phase 6: History API ────────────────────────────────────────

  try {
    const origPush = history.pushState.bind(history);
    history.pushState = function (this: History, ...args: unknown[]) {
      addEvent("history.pushState", { url: String(args[2] || ""), stack: getStack(3) });
      return origPush(args[0] as unknown, args[1] as string, args[2] as string | null | undefined);
    };
    const origReplace = history.replaceState.bind(history);
    history.replaceState = function (this: History, ...args: unknown[]) {
      addEvent("history.replaceState", { url: String(args[2] || ""), stack: getStack(3) });
      return origReplace(args[0] as unknown, args[1] as string, args[2] as string | null | undefined);
    };
  } catch { /* history patching failed */ }

  // ── Phase 7: Expose global API ──────────────────────────────────

  (window as any).__galleryReloadBlackBox = {
    install: () => { /* already installed */ },
    log,
    report,
    copyReport,
    clear,
    status,
    enable,
    disable,
  };

  console.log(
    `[ReloadBB] BlackBox active (boot #${_bootCount}, ${_events.length} stored events). ` +
    `Run __galleryReloadBlackBox.report() or copyReport().`
  );

  // ── Phase 8: Floating debug button ─────────────────────────────

  addFloatingUI();

  // ── Phase 9: Gesture/scroll tracking ──────────────────────────

  setupGestureTracking();
}

/* ── Floating debug UI ──────────────────────────────────────────────── */

function addFloatingUI(): void {
  const container = document.createElement("div");
  container.id = "__gallery_reload_bb_ui";
  container.style.cssText = [
    "position: fixed",
    "bottom: 12px",
    "right: 12px",
    "z-index: 999999",
    "display: flex",
    "flex-direction: column",
    "gap: 4px",
    "pointer-events: none",
  ].join(";");

  const btnStyle = [
    "pointer-events: auto",
    "background: rgba(30,30,30,0.7)",
    "backdrop-filter: blur(4px)",
    "color: #fff",
    "border: 1px solid rgba(255,255,255,0.25)",
    "border-radius: 6px",
    "padding: 4px 10px",
    "font: 11px/1.4 -apple-system, system-ui, sans-serif",
    "cursor: pointer",
    "white-space: nowrap",
    "transition: opacity 0.15s",
    "text-shadow: 0 1px 2px rgba(0,0,0,0.5)",
  ].join(";");

  const btnCopy = document.createElement("button");
  btnCopy.textContent = "📋 Copy Reload Report";
  btnCopy.style.cssText = btnStyle;
  btnCopy.addEventListener("click", (e) => {
    e.stopPropagation();
    copyReport();
  });

  const btnClear = document.createElement("button");
  btnClear.textContent = "🗑 Clear Reload Log";
  btnClear.style.cssText = btnStyle;
  btnClear.style.marginBottom = "0";
  btnClear.addEventListener("click", (e) => {
    e.stopPropagation();
    clear();
  });

  container.appendChild(btnCopy);
  container.appendChild(btnClear);
  document.body.appendChild(container);

  _disableHandlers.push(() => {
    const el = document.getElementById("__gallery_reload_bb_ui");
    if (el) el.remove();
  });
}

/* ── Gesture/scroll tracking ─────────────────────────────────────── */

function setupGestureTracking(): void {
  // Capture initial viewport state
  try {
    const vv = (window as any).visualViewport;
    if (vv) {
      _vvInitialHeight = vv.height;
      _vvInitialWidth = vv.width;
    }
  } catch { /* ignore */ }

  let lastScrollTime = 0;
  let lastTouchPos: { x: number; y: number } | null = null;
  let touchStartPos: { x: number; y: number } | null = null;

  function on(type: string, el: EventTarget, cb: EventListenerOrEventListenerObject, opts?: AddEventListenerOptions) {
    el.addEventListener(type, cb, opts || { passive: true });
    _disableHandlers.push(() => el.removeEventListener(type, cb));
  }

  // ── Touch events ───────────────────────────────────────────────

  on("touchstart", document, (e: Event) => {
    const te = e as TouchEvent;
    const touch = te.changedTouches[0];
    if (!touch) return;
    const x = Math.round(touch.clientX);
    const y = Math.round(touch.clientY);
    lastTouchPos = { x, y };
    touchStartPos = { x, y };
    const scrollY = window.scrollY || document.documentElement.scrollTop || 0;
    recordGesture({
      t: Date.now(), type: "touchstart",
      target: getTargetSummary(te.target),
      x, y, deltaY: 0, deltaX: 0, direction: "none",
      scrollY: Math.round(scrollY),
      nearTop: scrollY <= 20,
      pullingDownAtTop: false,
      docScrollTop: Math.round(scrollY),
      docScrollHeight: Math.round(document.documentElement.scrollHeight),
      docClientHeight: Math.round(document.documentElement.clientHeight)
    });
  });

  on("touchmove", document, (e: Event) => {
    const te = e as TouchEvent;
    const touch = te.changedTouches[0];
    if (!touch || !lastTouchPos) return;
    _totalTouchMoves++;
    const x = Math.round(touch.clientX);
    const y = Math.round(touch.clientY);
    const deltaY = y - lastTouchPos.y;
    const deltaX = x - lastTouchPos.x;
    const absDY = Math.abs(deltaY);
    const absDX = Math.abs(deltaX);
    let direction = "none";
    if (absDY > absDX && absDY > 2) direction = deltaY > 0 ? "down" : "up";
    else if (absDX > absDY && absDX > 2) direction = deltaX > 0 ? "right" : "left";
    const scrollY = window.scrollY || document.documentElement.scrollTop || 0;
    const nearTop = scrollY <= 20;
    const pullingDownAtTop = nearTop && deltaY > 5;
    lastTouchPos = { x, y };

    if (_totalTouchMoves % 3 === 0 || pullingDownAtTop) {
      // Only record every 3rd move to reduce noise, but always record pull-down-at-top
      recordGesture({
        t: Date.now(), type: "touchmove",
        target: getTargetSummary(te.target),
        x, y, deltaY: Math.round(deltaY), deltaX: Math.round(deltaX),
        direction, scrollY: Math.round(scrollY),
        nearTop, pullingDownAtTop,
        docScrollTop: Math.round(scrollY),
        docScrollHeight: Math.round(document.documentElement.scrollHeight),
        docClientHeight: Math.round(document.documentElement.clientHeight)
      });
    }
  });

  on("touchend", document, (e: Event) => {
    const te = e as TouchEvent;
    const touch = te.changedTouches[0];
    if (!touch) return;
    const x = Math.round(touch.clientX);
    const y = Math.round(touch.clientY);
    const totalDY = touchStartPos ? y - touchStartPos.y : 0;
    const scrollY = window.scrollY || document.documentElement.scrollTop || 0;
    const nearTop = scrollY <= 20;
    const flickDown = totalDY > 30 && nearTop;
    recordGesture({
      t: Date.now(), type: "touchend",
      target: getTargetSummary(te.target),
      x, y, deltaY: Math.round(totalDY), deltaX: 0,
      direction: totalDY > 0 ? "down" : totalDY < 0 ? "up" : "none",
      scrollY: Math.round(scrollY),
      nearTop, pullingDownAtTop: flickDown,
      docScrollTop: Math.round(scrollY),
      docScrollHeight: Math.round(document.documentElement.scrollHeight),
      docClientHeight: Math.round(document.documentElement.clientHeight)
    });
    lastTouchPos = null;
    touchStartPos = null;
  });

  // ── Scroll event (throttled) ───────────────────────────────────

  on("scroll", document, () => {
    const now = Date.now();
    if (now - lastScrollTime < 100) return; // throttle to ~10fps
    lastScrollTime = now;
    _totalScrolls++;
    const ss = getScrollSnapshot();
    _lastScrollSnapshot = ss;
    addEvent("scroll", {
      scrollY: ss.scrollY,
      nearTop: ss.nearTop,
      nearBottom: ss.nearBottom,
      scrollHeight: ss.scrollHeight,
      clientHeight: ss.clientHeight
    });
  }, { passive: true, capture: true });

  // ── Wheel events (desktop trackpad overscroll) ─────────────────

  on("wheel", document, (e: Event) => {
    const we = e as WheelEvent;
    addEvent("wheel", {
      deltaY: Math.round(we.deltaY),
      deltaX: Math.round(we.deltaX),
      deltaMode: we.deltaMode,
      target: getTargetSummary(we.target),
      scrollY: Math.round(window.scrollY || 0)
    });
  });

  // ── VisualViewport ─────────────────────────────────────────────

  try {
    const vv = (window as any).visualViewport as EventTarget | null;
    if (vv) {
      on("resize", vv, () => {
        const vvObj = (window as any).visualViewport;
        if (!vvObj) return;
        const hChanged = Math.abs(vvObj.height - _vvInitialHeight) > 20;
        const wChanged = Math.abs(vvObj.width - _vvInitialWidth) > 20;
        if (hChanged || wChanged) {
          _visualViewportChangedBeforePagehide = true;
        }
        addEvent("visualViewport", {
          height: Math.round(vvObj.height),
          width: Math.round(vvObj.width),
          offsetTop: Math.round(vvObj.offsetTop),
          offsetLeft: Math.round(vvObj.offsetLeft),
          scale: vvObj.scale
        });
      });
      on("scroll", vv, () => {
        const vvObj = (window as any).visualViewport;
        if (!vvObj) return;
        _visualViewportChangedBeforePagehide = true;
        addEvent("visualViewportScroll", {
          offsetTop: Math.round(vvObj.offsetTop),
          offsetLeft: Math.round(vvObj.offsetLeft)
        });
      });
    }
  } catch { /* visualViewport not supported */ }

  // ── Orientation change ─────────────────────────────────────────

  on("orientationchange", window, () => {
    addEvent("orientationchange", {
      orientation: window.screen?.orientation?.type || screen.orientation?.type || "unknown",
      angle: window.screen?.orientation?.angle ?? -1
    });
  });

  // ── Window resize ──────────────────────────────────────────────

  let lastResizeTime = 0;
  on("resize", window, () => {
    const now = Date.now();
    if (now - lastResizeTime < 300) return;
    lastResizeTime = now;
    addEvent("resize", {
      width: window.innerWidth,
      height: window.innerHeight,
      outerWidth: window.outerWidth,
      outerHeight: window.outerHeight
    });
  });
}

/* ── WebSocket patching (standalone, for early invocation) ─────────── */

function patchWebSocket(): void {
  try {
    const OrigWS = window.WebSocket;

    // 1. Trap constructor — catch all new WebSocket connections
    class BBPatchingWS extends OrigWS {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols);
        const urlStr = String(url);
        const isVite = /@vite|vite|hmr|ws:\/\/|wss:\/\//i.test(urlStr);
        addEvent("websocket-open", { url: urlStr, isViteHmr: isVite });
        this.addEventListener("close", (e: CloseEvent) => {
          addEvent("websocket-close", {
            url: urlStr,
            code: e.code,
            reason: e.reason,
            wasClean: e.wasClean,
            isViteHmr: isVite,
          });
        });
        this.addEventListener("error", () => {
          addEvent("websocket-error", { url: urlStr, isViteHmr: isVite });
        });
        this.addEventListener("message", (msg: MessageEvent) => {
          const text = typeof msg.data === "string" ? msg.data : "";
          // Flag suspicious Vite messages that can trigger reload
          if (isVite && /reload|full-reload|update|prune/i.test(text)) {
            addEvent("websocket-msg-suspect", {
              url: urlStr,
              data: text.slice(0, 200),
            });
          }
        });
      }
    }
    window.WebSocket = BBPatchingWS as unknown as typeof WebSocket;
  } catch (e) {
    addEvent("ws-patch-error", { error: String(e) });
  }
}
