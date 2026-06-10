/**
 * Gallery Page Reload Debugger
 * ====================================
 *
 * Standalone copy-paste script for DevTools console.
 * Tracks page reload/navigation events to help identify what causes unexpected reloads.
 *
 * Usage:
 *   Paste this entire script into the browser DevTools console.
 *
 * Commands:
 *   __reloadDebug.start()       - start tracking (auto-started on paste)
 *   __reloadDebug.stop()        - stop tracking (removes listeners)
 *   __reloadDebug.report()      - print formatted report to console
 *   __reloadDebug.copyReport()  - copy report to clipboard
 *   __reloadDebug.mark(label)   - add a manual marker
 *   __reloadDebug.clear()       - clear all collected data
 *   __reloadDebug.status()      - show live status
 *
 * What it tracks:
 *   - beforeunload, pagehide, pageshow, visibilitychange, freeze, resume, unload
 *   - popstate, hashchange, online, offline
 *   - error, unhandledrejection
 *   - click (links/buttons with navigation potential)
 *   - form submit
 *   - keydown (F5, Ctrl+R, Cmd+R)
 *   - location.reload/assign/replace
 *   - history.pushState/replaceState
 *   - window.open
 *   - fetch/XHR to gallery API endpoints
 *   - WebSocket open/close/error
 *   - touchstart/touchend summaries
 *
 * Limitations (standalone script, no localStorage persistence):
 *   - Data is lost on page reload (use ?debugReload=1 for persistence)
 *   - Cannot detect what happened right before a reload that already occurred
 */

(function () {
  if (window.__reloadDebug && window.__reloadDebug._active) {
    console.log("[ReloadDebug] Already running. Use __reloadDebug.report() to view logs.");
    return;
  }

  var events = [];
  var inFlight = [];
  var active = true;
  var bootTime = Date.now();
  var touchStartCount = 0;
  var touchEndCount = 0;

  function addEvent(type, detail) {
    if (!active) return;
    events.push({
      t: Date.now(),
      type: type,
      detail: typeof detail === "string" ? detail : JSON.stringify(detail)
    });
  }

  function mark(label) {
    addEvent("mark", { label: label, url: window.location.href });
  }

  function getElInfo(el) {
    if (!el) return "unknown";
    var tag = el.tagName.toLowerCase();
    var cls = typeof el.className === "string" ? el.className.replace(/\s+/g, " ").trim().slice(0, 60) : "";
    var id = el.id || "";
    var parts = [tag];
    if (id) parts.push("#" + id);
    if (cls) parts.push("." + cls.split(" ").slice(0, 2).join("."));
    return parts.join("");
  }

  function isGalleryApi(url) {
    return /\/api\/(scan|thumbnail|preview|image|metadata|search|index\/status|folders|landing-pages)/i.test(url);
  }

  function getStack() {
    try {
      var e = new Error();
      return (e.stack || "").split("\n").slice(2, 6).join("\n");
    } catch (err) {
      return "(unavailable)";
    }
  }

  // ── Browser lifecycle listeners ─────────────────────────────────────

  function onBeforeunload() {
    addEvent("beforeunload", {
      url: location.href,
      inFlight: inFlight.map(function (r) { return r.method + " " + r.url; })
    });
  }

  function onPagehide(e) {
    addEvent("pagehide", {
      persisted: e.persisted,
      url: location.href,
      inFlight: inFlight.map(function (r) { return r.method + " " + r.url; })
    });
  }

  function onPageshow(e) {
    addEvent("pageshow", { persisted: e.persisted, url: location.href });
  }

  function onVisibilitychange() {
    addEvent("visibilitychange", { state: document.visibilityState, url: location.href });
  }

  function onFreeze() {
    addEvent("freeze", { url: location.href });
  }

  function onResume() {
    addEvent("resume", { url: location.href });
  }

  function onUnload() {
    addEvent("unload", {
      url: location.href,
      inFlight: inFlight.map(function (r) { return r.method + " " + r.url; })
    });
  }

  function onPopstate() {
    addEvent("popstate", { url: location.href });
  }

  function onHashchange() {
    addEvent("hashchange", { url: location.href });
  }

  function onOnline() {
    addEvent("online", { url: location.href });
  }

  function onOffline() {
    addEvent("offline", { url: location.href });
  }

  function onError(e) {
    addEvent("error", {
      message: e.message,
      filename: e.filename,
      lineno: e.lineno,
      colno: e.colno
    });
  }

  function onRejection(e) {
    var reason = e.reason;
    if (reason instanceof Error) {
      addEvent("unhandledrejection", { message: reason.message, stack: reason.stack });
    } else {
      addEvent("unhandledrejection", { reason: String(reason) });
    }
  }

  function onClick(e) {
    var target = e.target;
    if (!target) return;
    var anchor = target.tagName === "A" ? target : target.closest("a");
    var btn = target.tagName === "BUTTON" ? target : target.closest("button");

    if (anchor) {
      var sameOrigin = false;
      try {
        sameOrigin = new URL(anchor.href, location.origin).origin === location.origin;
      } catch (err) { /* ignore */ }
      var fullNavSuspect = !anchor.target &&
        !e.defaultPrevented &&
        sameOrigin &&
        !anchor.href.startsWith("javascript:") &&
        !anchor.href.startsWith("#") &&
        anchor.href !== location.href;
      addEvent("click", {
        tag: "a",
        href: anchor.href,
        target: anchor.target || "_self",
        ctrl: e.ctrlKey,
        meta: e.metaKey,
        shift: e.shiftKey,
        defaultPrevented: e.defaultPrevented,
        sameOrigin: sameOrigin,
        fullNavSuspect: fullNavSuspect,
        element: getElInfo(target)
      });
    } else if (btn) {
      addEvent("click", {
        tag: "button",
        type: btn.type || "button",
        element: getElInfo(target),
        defaultPrevented: e.defaultPrevented
      });
    }
  }

  function onSubmit(e) {
    var form = e.target;
    if (!form || form.tagName !== "FORM") return;
    addEvent("submit", {
      action: form.action,
      method: form.method,
      element: getElInfo(form),
      defaultPrevented: e.defaultPrevented
    });
  }

  function onKeydown(e) {
    if (e.key === "F5" || (e.key === "r" && (e.ctrlKey || e.metaKey))) {
      addEvent("keydown", {
        key: e.key,
        ctrl: e.ctrlKey,
        meta: e.metaKey,
        element: getElInfo(e.target)
      });
    }
  }

  function onTouchStart() {
    touchStartCount++;
    if (touchStartCount % 20 === 0) {
      addEvent("touchstart-summary", { count: touchStartCount });
    }
  }

  function onTouchEnd() {
    touchEndCount++;
    if (touchEndCount % 20 === 0) {
      addEvent("touchend-summary", { count: touchEndCount });
    }
  }

  window.addEventListener("beforeunload", onBeforeunload);
  window.addEventListener("pagehide", onPagehide);
  window.addEventListener("pageshow", onPageshow);
  document.addEventListener("visibilitychange", onVisibilitychange);
  window.addEventListener("freeze", onFreeze);
  window.addEventListener("resume", onResume);
  window.addEventListener("unload", onUnload);
  window.addEventListener("popstate", onPopstate);
  window.addEventListener("hashchange", onHashchange);
  window.addEventListener("online", onOnline);
  window.addEventListener("offline", onOffline);
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
  document.addEventListener("click", onClick, true);
  document.addEventListener("submit", onSubmit, true);
  document.addEventListener("keydown", onKeydown, true);
  document.addEventListener("touchstart", onTouchStart, { passive: true, capture: true });
  document.addEventListener("touchend", onTouchEnd, { passive: true, capture: true });

  // ── Monkeypatch location ────────────────────────────────────────────

  try {
    var locProto = Object.getPrototypeOf(window.location);
    if (locProto) {
      var origReload = locProto.reload;
      var origAssign = locProto.assign;
      var origReplace = locProto.replace;
      if (typeof origReload === "function") {
        locProto.reload = function () {
          addEvent("location.reload", { url: location.href, stack: getStack() });
          return origReload.call(location);
        };
      }
      if (typeof origAssign === "function") {
        locProto.assign = function (url) {
          addEvent("location.assign", { url: url, stack: getStack() });
          return origAssign.call(location, url);
        };
      }
      if (typeof origReplace === "function") {
        locProto.replace = function (url) {
          addEvent("location.replace", { url: url, stack: getStack() });
          return origReplace.call(location, url);
        };
      }
    }
  } catch (e) {
    addEvent("monkeypatch-error", { api: "location", error: String(e) });
  }

  // ── Monkeypatch history ─────────────────────────────────────────────

  try {
    var origPush = history.pushState.bind(history);
    var origReplace = history.replaceState.bind(history);
    history.pushState = function (s, t, u) {
      addEvent("history.pushState", { url: u || "(none)", stack: getStack() });
      return origPush(s, t, u);
    };
    history.replaceState = function (s, t, u) {
      addEvent("history.replaceState", { url: u || "(none)", stack: getStack() });
      return origReplace(s, t, u);
    };
  } catch (e) {
    addEvent("monkeypatch-error", { api: "history", error: String(e) });
  }

  // ── Monkeypatch window.open ────────────────────────────────────────

  try {
    var origOpen = window.open.bind(window);
    window.open = function () {
      addEvent("window.open", {
        url: String(arguments[0] || ""),
        target: String(arguments[1] || ""),
        stack: getStack()
      });
      return origOpen.apply(window, arguments);
    };
  } catch (e) {
    /* ignore */
  }

  // ── fetch instrumentation ──────────────────────────────────────────

  var origFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : input instanceof Request ? input.url : String(input);
    var method = (init && init.method || "GET").toUpperCase();
    if (!isGalleryApi(url)) return origFetch(input, init);
    var start = Date.now();
    var req = { url: url, method: method, startTime: start };
    inFlight.push(req);
    addEvent("fetch-start", { url: url, method: method });
    return origFetch(input, init).then(
      function (res) {
        var idx = inFlight.indexOf(req);
        if (idx >= 0) inFlight.splice(idx, 1);
        addEvent("fetch-end", { url: url, method: method, status: res.status, duration: Date.now() - start });
        return res;
      },
      function (err) {
        var idx = inFlight.indexOf(req);
        if (idx >= 0) inFlight.splice(idx, 1);
        addEvent("fetch-error", { url: url, method: method, duration: Date.now() - start, error: String(err) });
        throw err;
      }
    );
  };

  // ── XHR instrumentation ────────────────────────────────────────────

  try {
    var OrigXHR = window.XMLHttpRequest;
    var IXHR = function () {
      var xhr = new OrigXHR();
      var self = { _url: "", _method: "GET", _start: 0, _req: null, _isGallery: false };
      var origOpen = xhr.open;
      var origAddEvt = xhr.addEventListener;

      xhr.open = function (method, url) {
        var urlStr = String(url);
        self._url = urlStr;
        self._method = method.toUpperCase();
        self._start = Date.now();
        self._isGallery = isGalleryApi(urlStr);
        if (self._isGallery) {
          self._req = { url: urlStr, method: self._method, startTime: self._start };
          inFlight.push(self._req);
          addEvent("xhr-start", { url: urlStr, method: self._method });
        }
        var rest = Array.prototype.slice.call(arguments, 2);
        return origOpen.apply(xhr, [method, url].concat(rest));
      };

      xhr.addEventListener = function (type, listener) {
        if (self._isGallery && (type === "load" || type === "loadend" || type === "error")) {
          var rest = Array.prototype.slice.call(arguments, 2);
          return origAddEvt.call(xhr, type, function (event) {
            if (self._req) {
              var idx = inFlight.indexOf(self._req);
              if (idx >= 0) inFlight.splice(idx, 1);
              self._req = null;
            }
            var dur = Date.now() - self._start;
            if (type === "load" || type === "loadend") {
              addEvent("xhr-end", { url: self._url, method: self._method, status: xhr.status, duration: dur });
            } else if (type === "error") {
              addEvent("xhr-error", { url: self._url, method: self._method, duration: dur });
            }
            if (typeof listener === "function") {
              return listener.call(this, event);
            } else if (listener && listener.handleEvent) {
              return listener.handleEvent(event);
            }
          }.bind(xhr), rest[0], rest[1]);
        }
        return origAddEvt.apply(xhr, arguments);
      };

      return xhr;
    };
    IXHR.prototype = OrigXHR.prototype;
    IXHR.UNSENT = OrigXHR.UNSENT;
    IXHR.OPENED = OrigXHR.OPENED;
    IXHR.HEADERS_RECEIVED = OrigXHR.HEADERS_RECEIVED;
    IXHR.LOADING = OrigXHR.LOADING;
    IXHR.DONE = OrigXHR.DONE;
    window.XMLHttpRequest = IXHR;
  } catch (e) {
    addEvent("monkeypatch-error", { api: "XMLHttpRequest", error: String(e) });
  }

  // ── WebSocket instrumentation ──────────────────────────────────────

  try {
    var OrigWS = window.WebSocket;
    var IWS = function (url, protocols) {
      var inst = new OrigWS(url, protocols);
      var u = String(url);
      var isVite = /@vite|vite|ws:\/\/|wss:\/\//i.test(u);
      var msgCount = 0;

      addEvent("websocket-open", { url: u, isViteHmr: isVite });

      inst.addEventListener("close", function (e) {
        addEvent("websocket-close", {
          url: u,
          code: e.code,
          reason: e.reason,
          wasClean: e.wasClean,
          isViteHmr: isVite,
          msgCount: msgCount
        });
      });

      inst.addEventListener("error", function () {
        addEvent("websocket-error", { url: u, isViteHmr: isVite, msgCount: msgCount });
      });

      inst.addEventListener("message", function () {
        msgCount++;
      });

      return inst;
    };
    IWS.prototype = OrigWS.prototype;
    IWS.CONNECTING = OrigWS.CONNECTING;
    IWS.OPEN = OrigWS.OPEN;
    IWS.CLOSING = OrigWS.CLOSING;
    IWS.CLOSED = OrigWS.CLOSED;
    window.WebSocket = IWS;
  } catch (e) {
    addEvent("monkeypatch-error", { api: "WebSocket", error: String(e) });
  }

  // ── Boot event ─────────────────────────────────────────────────────

  var navType = "unknown";
  try {
    var navEntries = performance.getEntriesByType("navigation");
    if (navEntries && navEntries.length > 0) {
      navType = navEntries[0].type || "unknown";
    }
  } catch (e) {
    // ignore
  }

  addEvent("boot", {
    url: location.href,
    navType: navType,
    referrer: document.referrer,
    wasDiscarded: document.wasDiscarded,
    ua: navigator.userAgent,
    viewport: window.innerWidth + "x" + window.innerHeight,
    dpr: window.devicePixelRatio,
    visibility: document.visibilityState,
    online: navigator.onLine
  });

  // ── Report generation ──────────────────────────────────────────────

  function status() {
    console.log("[ReloadDebug] active=" + active + " events=" + events.length + " inFlight=" + inFlight.length);
  }

  function report() {
    var lines = [];
    lines.push("═══ RELOAD DEBUG REPORT ═══");
    lines.push("Events: " + events.length + " | Active: " + active);
    lines.push("");

    var beforeUnload = 0, pageHide = 0, errors = 0, rejections = 0, suspects = 0, wsClose = 0;
    for (var i = 0; i < events.length; i++) {
      var e = events[i];
      if (e.type === "beforeunload") beforeUnload++;
      if (e.type === "pagehide") pageHide++;
      if (e.type === "error") errors++;
      if (e.type === "unhandledrejection") rejections++;
      if (e.type.indexOf("location.") === 0) suspects++;
      if (e.type === "click") {
        try { if (JSON.parse(e.detail).fullNavSuspect) suspects++; } catch (err) { /* ignore */ }
      }
      if (e.type === "websocket-close") wsClose++;
    }

    lines.push("── Summary ──");
    lines.push("  beforeunload: " + beforeUnload + "  pagehide: " + pageHide + "  errors: " + errors + "  rejections: " + rejections);
    lines.push("  full-nav suspects: " + suspects + "  WebSocket closes: " + wsClose);
    lines.push("");

    lines.push("── Timeline ──");
    for (var j = 0; j < events.length; j++) {
      var ev = events[j];
      var rel = ev.t - bootTime;
      var relStr = rel >= 0 ? "+" + rel + "ms" : rel + "ms";
      var detail = typeof ev.detail === "string" ? ev.detail : JSON.stringify(ev.detail);
      if (detail.length > 150) detail = detail.slice(0, 150) + "...";
      lines.push("  [" + relStr + "] " + ev.type + ": " + detail);
    }
    lines.push("");

    lines.push("── Full-Nav Suspects ──");
    var suspectTypes = ["location.reload", "location.assign", "location.replace", "websocket-close", "error", "unhandledrejection"];
    var suspectEvents = events.filter(function (e) {
      return suspectTypes.indexOf(e.type) >= 0;
    });
    if (suspectEvents.length === 0) {
      lines.push("  (none)");
    } else {
      for (var k = 0; k < suspectEvents.length; k++) {
        var se = suspectEvents[k];
        var d = typeof se.detail === "string" ? se.detail.slice(0, 200) : JSON.stringify(se.detail).slice(0, 200);
        lines.push("  [" + (se.t - bootTime) + "ms] " + se.type + ": " + d);
      }
    }
    lines.push("");

    lines.push("═══ END ═══");
    console.log(lines.join("\n"));
  }

  function copyReport() {
    var lines = [];
    lines.push("GALLERY RELOAD DEBUG REPORT");
    lines.push("Generated: " + new Date().toISOString());
    lines.push("");
    for (var i = 0; i < events.length; i++) {
      var e = events[i];
      var detail = typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail);
      lines.push("[" + (e.t - bootTime) + "ms] " + e.type + ": " + detail);
    }
    var text = lines.join("\n");
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          console.log("Copied report to clipboard");
        });
        return;
      }
    } catch (err) { /* ignore */ }
    try {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      console.log("Copied report to clipboard (fallback)");
    } catch (err2) {
      console.error("Copy failed:", err2);
    }
  }

  function clear() {
    events.length = 0;
    inFlight.length = 0;
    console.log("[ReloadDebug] Cleared all data");
  }

  function stop() {
    if (!active) return;
    active = false;
    window.removeEventListener("beforeunload", onBeforeunload);
    window.removeEventListener("pagehide", onPagehide);
    window.removeEventListener("pageshow", onPageshow);
    document.removeEventListener("visibilitychange", onVisibilitychange);
    window.removeEventListener("freeze", onFreeze);
    window.removeEventListener("resume", onResume);
    window.removeEventListener("unload", onUnload);
    window.removeEventListener("popstate", onPopstate);
    window.removeEventListener("hashchange", onHashchange);
    window.removeEventListener("online", onOnline);
    window.removeEventListener("offline", onOffline);
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
    document.removeEventListener("click", onClick, true);
    document.removeEventListener("submit", onSubmit, true);
    document.removeEventListener("keydown", onKeydown, true);
    document.removeEventListener("touchstart", onTouchStart, true);
    document.removeEventListener("touchend", onTouchEnd, true);
    console.log("[ReloadDebug] Stopped (listeners removed, " + events.length + " events retained)");
  }

  function startFn() {
    if (active) { console.log("[ReloadDebug] Already running"); return; }
    active = true;
    window.addEventListener("beforeunload", onBeforeunload);
    window.addEventListener("pagehide", onPagehide);
    window.addEventListener("pageshow", onPageshow);
    document.addEventListener("visibilitychange", onVisibilitychange);
    window.addEventListener("freeze", onFreeze);
    window.addEventListener("resume", onResume);
    window.addEventListener("unload", onUnload);
    window.addEventListener("popstate", onPopstate);
    window.addEventListener("hashchange", onHashchange);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    document.addEventListener("click", onClick, true);
    document.addEventListener("submit", onSubmit, true);
    document.addEventListener("keydown", onKeydown, true);
    document.addEventListener("touchstart", onTouchStart, { passive: true, capture: true });
    document.addEventListener("touchend", onTouchEnd, { passive: true, capture: true });
    console.log("[ReloadDebug] Started");
  }

  window.__reloadDebug = {
    _active: true,
    start: startFn,
    stop: stop,
    report: report,
    copyReport: copyReport,
    mark: mark,
    clear: clear,
    status: status
  };

  console.log(
    "[ReloadDebug] Ready. Commands: .report() .copyReport() .mark('note') .clear() .stop() .status()\n" +
    "  For persistent logs across reloads, reload the page with ?debugReload=1 in the URL."
  );
})();
