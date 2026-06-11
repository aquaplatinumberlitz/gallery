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
  };
  suspects: string[];
  timeline: { rel: number; type: string; detail: string }[];
  lastEvents: { rel: number; type: string; detail: string }[];
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
      errors: stats.errorCount + stats.rejectionCount
    },
    suspects,
    timeline,
    lastEvents: lastEvents.map(e => ({
      rel: e.t - _bootTime,
      type: e.type,
      detail: e.detail
    })),
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

  lines.push("");
  lines.push(`── Suspects ──────────────────────────────────────────`);
  if (r.suspects.length === 0) {
    lines.push("  (none — normal navigation)");
  } else {
    for (const x of r.suspects) lines.push(`  ${x}`);
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
    addEvent("pagehide", { persisted: pe.persisted, url: window.location.href });
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
  on("unload", window, () => addEvent("unload", { url: window.location.href }));
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
