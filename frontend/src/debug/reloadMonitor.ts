/**
 * Debug-only reload monitor.
 *
 * Enable: ?debugReload=1 or localStorage.setItem("GALLERY_DEBUG_RELOAD", "1") + reload
 * Disable: __galleryReloadDebug.disable()
 *
 * DO NOT ship enabled in production. Guarded by explicit opt-in only.
 */

const STORAGE_KEY_LOGS = "GALLERY_RELOAD_DEBUG_LOGS";
const STORAGE_KEY_SESSION = "GALLERY_RELOAD_DEBUG_SESSION_ID";
const STORAGE_KEY_BOOT_COUNT = "GALLERY_RELOAD_DEBUG_BOOT_COUNT";
const STORAGE_KEY_ENABLED = "GALLERY_DEBUG_RELOAD";
const MAX_EVENTS = 500;

interface ReloadLogEvent {
  t: number; // timestamp
  type: string;
  detail: string; // JSON-serialized detail
}

interface BootRecord {
  sessionId: string;
  bootCount: number;
  bootTime: number;
  url: string;
  navigationType: string;
  navigationTiming: Record<string, number>;
  referrer: string;
  wasDiscarded: boolean | undefined;
  userAgent: string;
  viewportWidth: number;
  viewportHeight: number;
  devicePixelRatio: number;
  visibilityState: string;
  online: boolean;
}

interface InFlightRequest {
  url: string;
  method: string;
  startTime: number;
}

interface ReloadReport {
  summary: {
    bootCount: number;
    currentUrl: string;
    lastNavigationType: string;
    totalEvents: number;
    beforeUnloadCount: number;
    pageHideCount: number;
    errorCount: number;
    rejectionCount: number;
    fullNavSuspects: number;
    wsCloseCount: number;
    apiInFlightBeforeUnload: number;
    lastReloadTimestamp: number | null;
  };
  timeline: Array<{
    rel: number; // ms from boot
    type: string;
    detail: string;
    stack?: string;
  }>;
  suspects: string[];
  lastEventsBeforeUnload: Array<{
    rel: number;
    type: string;
    detail: string;
    stack?: string;
  }>;
  inFlightAtUnload: string[];
  events: ReloadLogEvent[];
}

function safeGetItem(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSetItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage full or private browsing — silently ignore
  }
}

function safeRemoveItem(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

function generateSessionId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function loadEvents(): ReloadLogEvent[] {
  const raw = safeGetItem(STORAGE_KEY_LOGS);
  if (!raw) return [];
  try {
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

function saveEvents(events: ReloadLogEvent[]): void {
  const trimmed = events.length > MAX_EVENTS ? events.slice(-MAX_EVENTS) : events;
  safeSetItem(STORAGE_KEY_LOGS, JSON.stringify(trimmed));
}

function getNavigationType(): string {
  try {
    const entries = performance.getEntriesByType("navigation") as PerformanceNavigationTiming[];
    if (entries.length > 0) {
      return entries[0].type || "unknown";
    }
  } catch {
    // ignore
  }
  return "unknown";
}

function getNavigationTiming(): Record<string, number> {
  try {
    const entries = performance.getEntriesByType("navigation") as PerformanceNavigationTiming[];
    if (entries.length > 0) {
      const t = entries[0];
      return {
        dns: t.domainLookupEnd - t.domainLookupStart,
        tcp: t.connectEnd - t.connectStart,
        ssl: t.secureConnectionStart > 0 ? t.connectEnd - t.secureConnectionStart : 0,
        request: t.responseStart - t.requestStart,
        response: t.responseEnd - t.responseStart,
        dom: t.domContentLoadedEventEnd - t.domContentLoadedEventStart,
        load: t.loadEventEnd - t.loadEventStart,
        ttfb: t.responseStart - t.requestStart,
        total: t.loadEventEnd - t.fetchStart,
      };
    }
  } catch {
    // ignore
  }
  return {};
}

function isGalleryApiUrl(url: string): boolean {
  const apiPatterns = [
    "/api/scan",
    "/api/thumbnail",
    "/api/preview",
    "/api/image",
    "/api/metadata",
    "/api/search",
    "/api/index/status",
    "/api/folders",
    "/api/landing-pages",
  ];
  return apiPatterns.some((p) => url.includes(p));
}

function isViteWebSocketUrl(url: string): boolean {
  return /@vite|vite|ws:\/\/|wss:\/\//i.test(url);
}

function getNearestElementInfo(el: Element | null): string {
  if (!el) return "unknown";
  const tag = el.tagName.toLowerCase();
  const cls = typeof el.className === "string" ? el.className.replace(/\s+/g, " ").trim().slice(0, 80) : "";
  const id = el.id || "";
  const parts: string[] = [tag];
  if (id) parts.push(`#${id}`);
  if (cls) parts.push(`.${cls.split(" ").slice(0, 3).join(".")}`);
  return parts.join("");
}

function classifySuspect(events: ReloadLogEvent[], boot: BootRecord): string[] {
  const suspects: string[] = [];
  const eventTypes = events.map((e) => e.type);

  // Check for location.reload/assign/replace
  if (eventTypes.some((t) => t.startsWith("location."))) {
    suspects.push("BAD: location.reload/assign/replace called");
  }

  // Check for anchor/form full navigation
  const clickEvents = events.filter((e) => e.type === "click");
  for (const ce of clickEvents) {
    try {
      const d = JSON.parse(ce.detail);
      if (d.fullNavSuspect && d.sameOrigin) {
        suspects.push("BAD: anchor/form caused full navigation — " + d.href || d.action);
        break;
      }
    } catch { /* ignore */ }
  }
  const submitEvents = events.filter((e) => e.type === "submit");
  if (submitEvents.length > 0) {
    suspects.push("BAD: form submitted — possible full navigation");
  }

  // Check for unhandled errors
  const errors = events.filter((e) => e.type === "error");
  if (errors.length > 0) {
    suspects.push(`BAD: ${errors.length} unhandled error(s) happened`);
  }
  const rejections = events.filter((e) => e.type === "unhandledrejection");
  if (rejections.length > 0) {
    suspects.push(`BAD: ${rejections.length} unhandled rejection(s) happened`);
  }

  // Check for Vite/HMR WebSocket close before reload
  const wsCloses = events.filter((e) => e.type === "websocket-close");
  if (wsCloses.length > 0) {
    suspects.push(`WARN: ${wsCloses.length} WebSocket close(s) — possible HMR reconnect`);
  }

  // Check for pagehide without persisted
  const pagehides = events.filter((e) => e.type === "pagehide");
  for (const ph of pagehides) {
    try {
      const d = JSON.parse(ph.detail);
      if (d.persisted === false) {
        suspects.push("WARN: pagehide without persisted — possible discard");
        break;
      }
    } catch { /* ignore */ }
  }

  // Check for wasDiscarded
  if (boot.wasDiscarded) {
    suspects.push("WARN: document.wasDiscarded true — browser discarded page");
  }

  // Check for reload navigation type with no JS cause
  if (boot.navigationType === "reload") {
    const hasJsCause = eventTypes.some(
      (t) => t.startsWith("location.") || t === "websocket-close"
    );
    if (!hasJsCause) {
      suspects.push("WARN: reload navigation type with no JS cause detected — user pressed refresh or browser reloaded");
    }
  }

  // Check for bfcache restore
  const pageshows = events.filter((e) => e.type === "pageshow");
  for (const ps of pageshows) {
    try {
      const d = JSON.parse(ps.detail);
      if (d.persisted === true) {
        suspects.push("OK: bfcache pageshow (persisted=true) — page restored from cache");
      }
    } catch { /* ignore */ }
  }

  // Check for SPA navigation only
  const spaNavs = events.filter(
    (e) => e.type === "history.pushState" || e.type === "history.replaceState"
  );
  const fullNavs = eventTypes.filter(
    (t) =>
      t.startsWith("location.") ||
      t === "beforeunload" ||
      t === "pagehide" ||
      t === "unload"
  );
  if (spaNavs.length > 0 && fullNavs.length === 0) {
    suspects.push("OK: SPA route pushState/replaceState only — no real reload");
  }

  return suspects;
}

export function startReloadMonitor(): void {
  if ((window as any).__galleryReloadDebug?._active) return;

  const sessionId = generateSessionId();
  safeSetItem(STORAGE_KEY_SESSION, sessionId);
  safeSetItem(STORAGE_KEY_ENABLED, "1");

  const prevBootCount = parseInt(safeGetItem(STORAGE_KEY_BOOT_COUNT) || "0", 10) || 0;
  const bootCount = prevBootCount + 1;
  safeSetItem(STORAGE_KEY_BOOT_COUNT, String(bootCount));

  const events: ReloadLogEvent[] = loadEvents();
  const bootTime = Date.now();
  const inFlightRequests: InFlightRequest[] = [];
  let touchStartCount = 0;
  let touchEndCount = 0;

  const bootRecord: BootRecord = {
    sessionId,
    bootCount,
    bootTime,
    url: window.location.href,
    navigationType: getNavigationType(),
    navigationTiming: getNavigationTiming(),
    referrer: document.referrer,
    wasDiscarded: (document as any).wasDiscarded,
    userAgent: navigator.userAgent,
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
    devicePixelRatio: window.devicePixelRatio || 1,
    visibilityState: document.visibilityState,
    online: navigator.onLine,
  };

  function addEvent(type: string, detail: Record<string, unknown>): void {
    const entry: ReloadLogEvent = {
      t: Date.now(),
      type,
      detail: JSON.stringify(detail),
    };
    events.push(entry);
    if (events.length > MAX_EVENTS) {
      events.splice(0, events.length - MAX_EVENTS);
    }
    saveEvents(events);
  }

  // Record boot
  addEvent("boot", {
    ...bootRecord,
    navigationTiming: JSON.stringify(bootRecord.navigationTiming),
  });

  function markAction(label: string): void {
    addEvent("mark", { label, url: window.location.href });
  }

  // ── Browser lifecycle events ────────────────────────────────────────

  window.addEventListener("beforeunload", () => {
    const infly = inFlightRequests.map((r) => `${r.method} ${r.url}`);
    addEvent("beforeunload", {
      url: window.location.href,
      inFlight: infly,
    });
  });

  window.addEventListener("pagehide", (e: PageTransitionEvent) => {
    const infly = inFlightRequests.map((r) => `${r.method} ${r.url}`);
    addEvent("pagehide", {
      persisted: e.persisted,
      url: window.location.href,
      inFlight: infly,
    });
  });

  window.addEventListener("pageshow", (e: PageTransitionEvent) => {
    addEvent("pageshow", {
      persisted: e.persisted,
      url: window.location.href,
    });
  });

  document.addEventListener("visibilitychange", () => {
    addEvent("visibilitychange", {
      state: document.visibilityState,
      url: window.location.href,
    });
  });

  window.addEventListener("freeze", () => {
    addEvent("freeze", { url: window.location.href });
  });

  window.addEventListener("resume", () => {
    addEvent("resume", { url: window.location.href });
  });

  // NOTE: unload listener intentionally omitted — it blocks bfcache on iOS Safari
  // and contributes to the very page discards we're trying to diagnose.
  // pagehide is sufficient: it fires in both bfcache (persisted=true) and
  // non-bfcache (persisted=false) scenarios.

  window.addEventListener("popstate", (e: PopStateEvent) => {
    addEvent("popstate", {
      url: window.location.href,
      state: e.state ? "(state present)" : "(no state)",
    });
  });

  window.addEventListener("hashchange", () => {
    addEvent("hashchange", { url: window.location.href });
  });

  window.addEventListener("online", () => {
    addEvent("online", { url: window.location.href });
  });

  window.addEventListener("offline", () => {
    addEvent("offline", { url: window.location.href });
  });

  // ── Error tracking ──────────────────────────────────────────────────

  window.addEventListener("error", (e: ErrorEvent) => {
    addEvent("error", {
      message: e.message,
      filename: e.filename,
      lineno: e.lineno,
      colno: e.colno,
      stack: (e.error as Error)?.stack || "(no stack)",
    });
  });

  window.addEventListener("unhandledrejection", (e: PromiseRejectionEvent) => {
    const reason = e.reason;
    const detail: Record<string, unknown> = {
      reason: String(reason),
    };
    if (reason instanceof Error) {
      detail.message = reason.message;
      detail.stack = reason.stack || "(no stack)";
    }
    addEvent("unhandledrejection", detail);
  });

  // ── Click capture ───────────────────────────────────────────────────

  document.addEventListener(
    "click",
    (e: MouseEvent) => {
      const target = e.target as Element;
      if (!target) return;
      const tag = target.tagName.toLowerCase();
      if (tag !== "a" && tag !== "button" && !target.closest("a") && !target.closest("button"))
        return;

      const anchor = tag === "a" ? (target as HTMLAnchorElement) : target.closest("a") as HTMLAnchorElement | null;
      const btn = tag === "button" ? target : target.closest("button");

      const info = getNearestElementInfo(target);

      if (anchor) {
        const sameOrigin = (() => {
          try {
            const u = new URL(anchor.href, window.location.origin);
            return u.origin === window.location.origin;
          } catch {
            return false;
          }
        })();

        const fullNavSuspect =
          !anchor.target &&
          !e.defaultPrevented &&
          sameOrigin &&
          !anchor.href.startsWith("javascript:") &&
          !anchor.href.startsWith("#") &&
          anchor.href !== window.location.href;

        addEvent("click", {
          tag: "a",
          href: anchor.href,
          target: anchor.target || "_self",
          ctrlKey: e.ctrlKey,
          metaKey: e.metaKey,
          shiftKey: e.shiftKey,
          defaultPrevented: e.defaultPrevented,
          sameOrigin,
          fullNavSuspect,
          element: info,
        });
      } else if (btn) {
        addEvent("click", {
          tag: "button",
          type: (btn as HTMLButtonElement).type || "button",
          element: info,
          defaultPrevented: e.defaultPrevented,
        });
      }
    },
    true // capture phase
  );

  // ── Submit capture ──────────────────────────────────────────────────

  document.addEventListener(
    "submit",
    (e: SubmitEvent) => {
      const form = e.target as HTMLFormElement;
      if (!form) return;
      addEvent("submit", {
        action: form.action,
        method: form.method,
        element: getNearestElementInfo(form),
        defaultPrevented: e.defaultPrevented,
      });
    },
    true
  );

  // ── Keydown capture ─────────────────────────────────────────────────

  document.addEventListener(
    "keydown",
    (e: KeyboardEvent) => {
      if (e.key === "F5" || (e.key === "r" && (e.ctrlKey || e.metaKey))) {
        addEvent("keydown", {
          key: e.key,
          ctrlKey: e.ctrlKey,
          metaKey: e.metaKey,
          shiftKey: e.shiftKey,
          element: getNearestElementInfo(e.target as Element),
        });
      }
    },
    true
  );

  // ── Touch event summaries ───────────────────────────────────────────

  document.addEventListener(
    "touchstart",
    () => {
      touchStartCount++;
      if (touchStartCount % 20 === 0) {
        addEvent("touchstart-summary", { count: touchStartCount });
      }
    },
    { passive: true, capture: true }
  );

  document.addEventListener(
    "touchend",
    () => {
      touchEndCount++;
      if (touchEndCount % 20 === 0) {
        addEvent("touchend-summary", { count: touchEndCount });
      }
    },
    { passive: true, capture: true }
  );

  // ── Monkeypatch navigation APIs ─────────────────────────────────────

  function getStackTrace(): string {
    try {
      const err = new Error();
      const stack = err.stack || "";
      const lines = stack.split("\n").slice(2, 7);
      return lines.join("\n");
    } catch {
      return "(stack unavailable)";
    }
  }

  // history.pushState
  try {
    const origPushState = history.pushState.bind(history);
    history.pushState = function (state: any, title: string, url?: string | null) {
      addEvent("history.pushState", {
        url: url || "(none)",
        state: state ? "(state present)" : "(no state)",
        stack: getStackTrace(),
      });
      return origPushState(state, title, url);
    };
  } catch (e) {
    addEvent("monkeypatch-error", { api: "history.pushState", error: String(e) });
  }

  // history.replaceState
  try {
    const origReplaceState = history.replaceState.bind(history);
    history.replaceState = function (state: any, title: string, url?: string | null) {
      addEvent("history.replaceState", {
        url: url || "(none)",
        state: state ? "(state present)" : "(no state)",
        stack: getStackTrace(),
      });
      return origReplaceState(state, title, url);
    };
  } catch (e) {
    addEvent("monkeypatch-error", { api: "history.replaceState", error: String(e) });
  }

  // window.open
  try {
    const origOpen = window.open.bind(window);
    window.open = function (...args: any[]) {
      addEvent("window.open", {
        url: String(args[0] || ""),
        target: String(args[1] || ""),
        stack: getStackTrace(),
      });
      return origOpen(...args);
    };
  } catch (e) {
    addEvent("monkeypatch-error", { api: "window.open", error: String(e) });
  }

  // location.reload — may throw on some browsers
  try {
    const loc = window.location as any;
    const origReload = loc.reload?.bind?.(loc);
    if (typeof origReload === "function") {
      Object.defineProperty(window, "location", {
        get() {
          return loc;
        },
        set(val: string) {
          addEvent("location.href-set", {
            value: String(val),
            stack: getStackTrace(),
          });
          // Can't actually set window.location from getter — this is just logging
        },
      });
    }
  } catch {
    // Some browsers don't allow patching location at all
    addEvent("monkeypatch-error", {
      api: "location.reload/assign/replace",
      error: "Browser prevented patching location APIs",
    });
  }

  // Proxy location.assign and location.replace via overriding the prototype
  // This is the most reliable cross-browser approach
  try {
    const locProto = Object.getPrototypeOf(window.location);
    if (locProto) {
      const origAssign = (locProto as any).assign;
      const origReplace = (locProto as any).replace;
      const origReload = (locProto as any).reload;

      if (typeof origAssign === "function") {
        (locProto as any).assign = function (url: string) {
          addEvent("location.assign", {
            url: String(url),
            stack: getStackTrace(),
          });
          return origAssign.call(window.location, url);
        };
      }
      if (typeof origReplace === "function") {
        (locProto as any).replace = function (url: string) {
          addEvent("location.replace", {
            url: String(url),
            stack: getStackTrace(),
          });
          return origReplace.call(window.location, url);
        };
      }
      if (typeof origReload === "function") {
        (locProto as any).reload = function () {
          addEvent("location.reload", {
            url: window.location.href,
            stack: getStackTrace(),
          });
          return origReload.call(window.location);
        };
      }
    }
  } catch (e) {
    addEvent("monkeypatch-error", { api: "location", error: String(e) });
  }

  // ── Network instrumentation ─────────────────────────────────────────

  // fetch
  const origFetch = window.fetch.bind(window);
  window.fetch = function (input: RequestInfo | URL, init?: RequestInit) {
    const url = typeof input === "string" ? input : input instanceof Request ? input.url : String(input);
    const method = (init?.method || "GET").toUpperCase();
    const startTime = Date.now();

    if (isGalleryApiUrl(url)) {
      const req: InFlightRequest = { url, method, startTime };
      inFlightRequests.push(req);

      addEvent("fetch-start", { url, method });

      return origFetch(input, init).then(
        (response) => {
          const idx = inFlightRequests.indexOf(req);
          if (idx >= 0) inFlightRequests.splice(idx, 1);
          addEvent("fetch-end", {
            url,
            method,
            status: response.status,
            duration: Date.now() - startTime,
          });
          return response;
        },
        (error) => {
          const idx = inFlightRequests.indexOf(req);
          if (idx >= 0) inFlightRequests.splice(idx, 1);
          addEvent("fetch-error", {
            url,
            method,
            duration: Date.now() - startTime,
            error: String(error),
          });
          throw error;
        }
      );
    }

    return origFetch(input, init);
  };

  // XMLHttpRequest
  try {
    const OrigXHR = window.XMLHttpRequest;
    class InstrumentedXHR extends OrigXHR {
      private _url = "";
      private _method = "GET";
      private _startTime = 0;
      private _req: InFlightRequest | null = null;
      private _galleryApi = false;

      open(method: string, url: string | URL, ...rest: any[]) {
        const urlStr = String(url);
        this._url = urlStr;
        this._method = method.toUpperCase();
        this._startTime = Date.now();
        this._galleryApi = isGalleryApiUrl(urlStr);
        if (this._galleryApi) {
          this._req = { url: urlStr, method: this._method, startTime: this._startTime };
          inFlightRequests.push(this._req);
          addEvent("xhr-start", { url: urlStr, method: this._method });
        }
        const openFn = super.open as (...args: any[]) => void;
        return openFn.apply(this, [method, url as string, ...rest]);
      }

      // Override event listeners to track completion
      addEventListener(type: string, listener: any, ...rest: any[]) {
        if (this._galleryApi && (type === "load" || type === "loadend" || type === "error")) {
          const origListener = listener;
          const self = this;
          const wrapped = function (event: Event) {
            const duration = Date.now() - self._startTime;
            if (self._req) {
              const idx = inFlightRequests.indexOf(self._req);
              if (idx >= 0) inFlightRequests.splice(idx, 1);
            }
            if (type === "load" || type === "loadend") {
              addEvent("xhr-end", {
                url: self._url,
                method: self._method,
                status: self.status,
                duration,
              });
            } else if (type === "error") {
              addEvent("xhr-error", {
                url: self._url,
                method: self._method,
                duration,
              });
            }
            return typeof origListener === "function"
              ? origListener.call(self, event)
              : (origListener as EventListenerObject).handleEvent.call(self, event);
          };
          const addEvtFn = super.addEventListener as (...args: any[]) => void;
          return addEvtFn.apply(this, [type, wrapped].concat(rest));
        }
        const addEvtFn = super.addEventListener as (...args: any[]) => void;
        return addEvtFn.apply(this, [type, listener].concat(rest));
      }
    }
    window.XMLHttpRequest = InstrumentedXHR as typeof XMLHttpRequest;
  } catch (e) {
    addEvent("monkeypatch-error", { api: "XMLHttpRequest", error: String(e) });
  }

  // ── WebSocket instrumentation ───────────────────────────────────────

  try {
    const OrigWebSocket = window.WebSocket;
    class InstrumentedWS extends OrigWebSocket {
      private _messageCount = 0;

      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols);
        const urlStr = String(url);
        const isVite = isViteWebSocketUrl(urlStr);

        addEvent("websocket-open", {
          url: urlStr,
          isViteHmr: isVite,
        });

        this.addEventListener("close", (e: CloseEvent) => {
          addEvent("websocket-close", {
            url: urlStr,
            code: e.code,
            reason: e.reason,
            wasClean: e.wasClean,
            isViteHmr: isVite,
            messageCount: this._messageCount,
          });
        });

        this.addEventListener("error", () => {
          addEvent("websocket-error", {
            url: urlStr,
            isViteHmr: isVite,
            messageCount: this._messageCount,
          });
        });

        this.addEventListener("message", () => {
          this._messageCount++;
        });
      }
    }
    window.WebSocket = InstrumentedWS as typeof WebSocket;
  } catch (e) {
    addEvent("monkeypatch-error", { api: "WebSocket", error: String(e) });
  }

  // ── Report generation ───────────────────────────────────────────────

  function generateReport(): ReloadReport {
    const allEvents = events;

    // Stats
    let beforeUnloadCount = 0;
    let pageHideCount = 0;
    let errorCount = 0;
    let rejectionCount = 0;
    let fullNavSuspects = 0;
    let wsCloseCount = 0;
    let apiInFlightBeforeUnload = 0;
    let lastReloadTimestamp: number | null = null;

    for (const e of allEvents) {
      if (e.type === "beforeunload") beforeUnloadCount++;
      if (e.type === "pagehide") {
        pageHideCount++;
        try {
          const d = JSON.parse(e.detail);
          if (d.inFlight && Array.isArray(d.inFlight)) {
            apiInFlightBeforeUnload = Math.max(apiInFlightBeforeUnload, d.inFlight.length);
          }
        } catch { /* ignore */ }
      }
      if (e.type === "error") errorCount++;
      if (e.type === "unhandledrejection") rejectionCount++;
      if (e.type.startsWith("location.")) fullNavSuspects++;
      if (e.type === "click") {
        try {
          const d = JSON.parse(e.detail);
          if (d.fullNavSuspect) fullNavSuspects++;
        } catch { /* ignore */ }
      }
      if (e.type === "websocket-close") wsCloseCount++;
      if (e.type === "location.reload") lastReloadTimestamp = e.t;
    }

    // Timeline with relative time from this boot
    const timeline: ReloadReport["timeline"] = [];
    for (const e of allEvents) {
      if (!lastReloadTimestamp) lastReloadTimestamp = bootTime;
      const detail = e.detail.length > 200 ? e.detail.slice(0, 200) + "..." : e.detail;
      const entry: ReloadReport["timeline"][0] = {
        rel: e.t - bootTime,
        type: e.type,
        detail,
      };
      if (
        e.type === "error" ||
        e.type === "unhandledrejection" ||
        e.type.startsWith("location.") ||
        e.type === "history.pushState" ||
        e.type === "history.replaceState"
      ) {
        try {
          const d = JSON.parse(e.detail);
          if (d.stack) entry.stack = d.stack;
        } catch { /* ignore */ }
      }
      timeline.push(entry);
    }

    // Last 20 events before unload/pagehide
    let lastUnloadIdx = -1;
    for (let i = allEvents.length - 1; i >= 0; i--) {
      if (
        allEvents[i].type === "beforeunload" ||
        allEvents[i].type === "pagehide" ||
        allEvents[i].type === "unload"
      ) {
        lastUnloadIdx = i;
        break;
      }
    }

    const lastEventsBeforeUnload: ReloadReport["lastEventsBeforeUnload"] = [];
    if (lastUnloadIdx >= 0) {
      const startIdx = Math.max(0, lastUnloadIdx - 19);
      for (let i = startIdx; i <= lastUnloadIdx; i++) {
        const e = allEvents[i];
        const detail = e.detail.length > 200 ? e.detail.slice(0, 200) + "..." : e.detail;
        const entry: ReloadReport["lastEventsBeforeUnload"][0] = {
          rel: e.t - bootTime,
          type: e.type,
          detail,
        };
        if (e.type === "error" || e.type === "unhandledrejection" || e.type.startsWith("location.")) {
          try {
            const d = JSON.parse(e.detail);
            if (d.stack) entry.stack = d.stack;
          } catch { /* ignore */ }
        }
        lastEventsBeforeUnload.push(entry);
      }
    }

    // In-flight requests at last unload
    const inFlightAtUnload: string[] = [];
    if (lastUnloadIdx >= 0) {
      try {
        const d = JSON.parse(allEvents[lastUnloadIdx].detail);
        if (d.inFlight && Array.isArray(d.inFlight)) {
          inFlightAtUnload.push(...d.inFlight);
        }
      } catch { /* ignore */ }
    }

    const suspects = classifySuspect(allEvents, bootRecord);

    return {
      summary: {
        bootCount,
        currentUrl: window.location.href,
        lastNavigationType: getNavigationType(),
        totalEvents: allEvents.length,
        beforeUnloadCount,
        pageHideCount,
        errorCount,
        rejectionCount,
        fullNavSuspects,
        wsCloseCount,
        apiInFlightBeforeUnload,
        lastReloadTimestamp,
      },
      timeline,
      suspects,
      lastEventsBeforeUnload,
      inFlightAtUnload,
      events: allEvents,
    };
  }

  function formatReport(report: ReloadReport): string {
    const lines: string[] = [];
    const s = report.summary;

    lines.push("═══════════════════════════════════════════════════════");
    lines.push("  GALLERY RELOAD DEBUG REPORT");
    lines.push("═══════════════════════════════════════════════════════");
    lines.push("");
    lines.push("── Summary ────────────────────────────────────────────");
    lines.push(`  Boot count:              ${s.bootCount}`);
    lines.push(`  Current URL:             ${s.currentUrl}`);
    lines.push(`  Last navigation type:    ${s.lastNavigationType}`);
    lines.push(`  Total events recorded:   ${s.totalEvents}`);
    lines.push(`  beforeunload events:     ${s.beforeUnloadCount}`);
    lines.push(`  pagehide events:         ${s.pageHideCount}`);
    lines.push(`  Errors:                  ${s.errorCount}`);
    lines.push(`  Rejections:              ${s.rejectionCount}`);
    lines.push(`  Full-nav suspects:       ${s.fullNavSuspects}`);
    lines.push(`  WebSocket closes:        ${s.wsCloseCount}`);
    lines.push(`  API in flight at unload: ${s.apiInFlightBeforeUnload}`);
    lines.push(`  Last reload timestamp:   ${s.lastReloadTimestamp ? new Date(s.lastReloadTimestamp).toISOString() : "none"}`);
    lines.push("");
    lines.push("── Suspect Analysis ───────────────────────────────────");
    if (report.suspects.length === 0) {
      lines.push("  (no suspects identified)");
    } else {
      for (const suspect of report.suspects) {
        lines.push(`  ${suspect}`);
      }
    }
    lines.push("");
    lines.push("── Timeline ───────────────────────────────────────────");
    if (report.timeline.length === 0) {
      lines.push("  (no events)");
    } else {
      for (const e of report.timeline) {
        const relStr = e.rel >= 0 ? `+${e.rel}ms` : `${e.rel}ms`;
        lines.push(`  [${relStr}] ${e.type}`);
        if (e.detail && e.detail !== "{}") {
          lines.push(`    ${e.detail}`);
        }
        if (e.stack) {
          lines.push(`    stack: ${e.stack.split("\n").join("\n    ")}`);
        }
      }
    }
    lines.push("");
    lines.push("── Last 20 Events Before Unload ───────────────────────");
    if (report.lastEventsBeforeUnload.length === 0) {
      lines.push("  (no unload detected yet)");
    } else {
      for (const e of report.lastEventsBeforeUnload) {
        const relStr = e.rel >= 0 ? `+${e.rel}ms` : `${e.rel}ms`;
        lines.push(`  [${relStr}] ${e.type}`);
        if (e.detail && e.detail !== "{}") {
          lines.push(`    ${e.detail}`);
        }
        if (e.stack) {
          lines.push(`    stack: ${e.stack.split("\n").join("\n    ")}`);
        }
      }
    }
    lines.push("");
    lines.push("── In-Flight API Requests at Unload ───────────────────");
    if (report.inFlightAtUnload.length === 0) {
      lines.push("  (none)");
    } else {
      for (const r of report.inFlightAtUnload) {
        lines.push(`  ${r}`);
      }
    }
    lines.push("");
    lines.push("── Raw Events (last 50) ───────────────────────────────");
    const last50 = report.events.slice(-50);
    for (const e of last50) {
      const rel = bootTime ? e.t - bootTime : 0;
      const relStr = rel >= 0 ? `+${rel}ms` : `${rel}ms`;
      lines.push(`  [${relStr}] ${e.type}: ${e.detail}`);
    }
    lines.push("");
    lines.push("───────────────────────────────────────────────────────");
    lines.push(`  Report generated: ${new Date().toISOString()}`);
    lines.push("═══════════════════════════════════════════════════════");

    return lines.join("\n");
  }

  function report(): void {
    const r = generateReport();
    console.log(formatReport(r));
  }

  async function copyReport(): Promise<void> {
    const r = generateReport();
    const text = formatReport(r);
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        console.log("Copied reload debug report to clipboard");
        return;
      }
    } catch {
      // Fallback
    }
    // Fallback: temporary textarea
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      ta.style.top = "-9999px";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      console.log("Copied reload debug report to clipboard (fallback)");
    } catch (e: unknown) {
      console.error("Failed to copy report:", e);
    }
  }

  function clear(): void {
    events.length = 0;
    safeRemoveItem(STORAGE_KEY_LOGS);
    safeRemoveItem(STORAGE_KEY_SESSION);
    safeRemoveItem(STORAGE_KEY_BOOT_COUNT);
    addEvent("clear", {});
    console.log("Reload debug logs cleared");
  }

  function disable(): void {
    safeRemoveItem(STORAGE_KEY_ENABLED);
    safeRemoveItem(STORAGE_KEY_LOGS);
    safeRemoveItem(STORAGE_KEY_SESSION);
    safeRemoveItem(STORAGE_KEY_BOOT_COUNT);
    console.log(
      "Reload debug monitor disabled. Remove ?debugReload=1 from URL and reload. " +
        "Or run: location.reload()"
    );
  }

  function isActive(): boolean {
    return true;
  }

  // ── Expose global API ───────────────────────────────────────────────

  (window as any).__galleryReloadDebug = {
    _active: true,
    start: () => console.log("Reload debug monitor already running"),
    stop: disable,
    mark: markAction,
    report,
    copyReport,
    clear,
    disable,
    isActive,
  };

  console.log(
    `[ReloadDebug] Monitor started (boot #${bootCount}, session ${sessionId}). ` +
      `Run __galleryReloadDebug.report() to view logs, __galleryReloadDebug.disable() to stop.`
  );
}
