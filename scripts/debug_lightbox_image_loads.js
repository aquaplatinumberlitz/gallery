/**
 * Gallery Lightbox Image Load Debugger
 * ====================================
 *
 * Copy-paste this entire script into the browser console on the running gallery
 * site, then use the `__galleryLightboxDebug` global to control it.
 *
 * Quick start:
 *   __galleryLightboxDebug.start()
 *   // open a gallery folder, click an image to open lightbox
 *   // navigate next/previous once
 *   __galleryLightboxDebug.report()
 *   __galleryLightboxDebug.copyReport()
 *
 * Commands:
 *   .start()         – begin tracking resources, fetch/XHR, DOM images, lightbox state
 *   .stop()          – pause tracking (keeps collected data)
 *   .report()        – print the formatted report to console
 *   .copyReport()    – copy the full report JSON to clipboard
 *   .clear()         – clear all collected data (tracking stays on if currently active)
 *   .json()          – return the raw collected data object
 *   .status()        – show brief live status
 *
 * What it tracks:
 *   1. Network resources (PerformanceObserver + performance.getEntriesByType)
 *      for /api/thumbnail, /api/preview, /api/image
 *   2. fetch() and XMLHttpRequest monkeypatches (safe, non-breaking)
 *   3. <img> elements via MutationObserver + load/error events
 *   4. Lightbox open/close via PhotoSwipe DOM classes (.pswp, .pswp--open)
 *   5. Duplicate analysis grouped by normalized image path
 */

(function () {
  "use strict";

  if (window.__galleryLightboxDebug) {
    console.warn(
      "[GalleryDebug] Already loaded. Call __galleryLightboxDebug.clear() to reset."
    );
    return;
  }

  // ── Constants ──────────────────────────────────────────────────────────────
  const ENDPOINTS = ["/api/thumbnail", "/api/preview", "/api/image"];
  const ENDPOINT_LABELS = {
    thumbnail: "/api/thumbnail",
    preview: "/api/preview",
    original: "/api/image",
  };

  // PhotoSwipe DOM markers
  const PSWP_SELECTORS = {
    root: ".pswp",
    open: ".pswp--open",
    img: ".pswp__img",
    imgPlaceholder: ".pswp__img--placeholder",
    container: ".pswp__container",
    item: ".pswp__item",
    button: ".pswp__button",
  };

  const GRID_IMG_SELECTOR = ".photo-card img, .thumbnail-img, img[src*='/api/thumbnail']";
  const SUSPICIOUS_ORIGINAL_WINDOW_MS = 3000;

  // ── State ──────────────────────────────────────────────────────────────────
  let trackingActive = false;
  let startTime = 0;
  const resourceRecords = [];
  const fetchRecords = [];
  const xhrRecords = [];
  const domImageRecords = [];
  const lightboxEvents = [];
  let lastLightboxOpenTime = 0;
  let currentLightboxOpenTime = 0;

  // Observers / patches (for cleanup)
  let perfObserver = null;
  let mutationObserver = null;
  let origFetch = null;
  let origXhrOpen = null;
  let origXhrSend = null;

  // ── Helpers ────────────────────────────────────────────────────────────────

  function now() {
    return performance.now();
  }

  function timeSinceStart() {
    return startTime ? now() - startTime : 0;
  }

  function timeSinceLastLightboxOpen() {
    return lastLightboxOpenTime ? now() - lastLightboxOpenTime : -1;
  }

  function classifyEndpoint(url) {
    for (const endpoint of ENDPOINTS) {
      if (url.includes(endpoint)) return endpoint;
    }
    return null;
  }

  function endpointType(endpoint) {
    if (endpoint === "/api/thumbnail") return "thumbnail";
    if (endpoint === "/api/preview") return "preview";
    if (endpoint === "/api/image") return "original";
    return "unknown";
  }

  function extractPathParam(url) {
    try {
      const u = new URL(url, window.location.origin);
      return u.searchParams.get("path") || null;
    } catch {
      const m = url.match(/[?&]path=([^&]+)/);
      return m ? decodeURIComponent(m[1]) : null;
    }
  }

  function extractQueryParams(url) {
    const params = {};
    try {
      const u = new URL(url, window.location.origin);
      for (const [k, v] of u.searchParams.entries()) {
        params[k] = v;
      }
    } catch {
      const qs = url.split("?")[1];
      if (qs) {
        qs.split("&").forEach((pair) => {
          const [k, v] = pair.split("=");
          if (k) params[k] = decodeURIComponent(v || "");
        });
      }
    }
    return params;
  }

  function normalizePath(path) {
    if (!path) return null;
    try {
      return decodeURIComponent(path);
    } catch {
      return path;
    }
  }

  function isCacheHit(transferSize, encodedBodySize) {
    // transferSize === 0 with non-zero encodedBodySize means disk/memory cache hit
    // for same-origin resources. transferSize === 0 and encodedBodySize === 0
    // usually means a 304 or opaque response — treat as unclear.
    if (transferSize === 0 && encodedBodySize > 0) return true;
    if (transferSize === 0 && encodedBodySize === 0) return null; // unclear
    return false;
  }

  function cacheLabel(entry) {
    const hit = isCacheHit(entry.transferSize, entry.encodedBodySize);
    if (hit === true) return "disk/memory cache";
    if (hit === null) return "unclear (zero transfer)";
    return "network (" + (entry.transferSize || "?") + " bytes)";
  }

  function isLightboxOpen() {
    return !!document.querySelector(PSWP_SELECTORS.open) || !!document.querySelector(PSWP_SELECTORS.root);
  }

  function isInsideLightbox(el) {
    if (!el) return false;
    let current = el;
    while (current) {
      if (
        current.classList &&
        (current.classList.contains("pswp") ||
          current.classList.contains("pswp__container") ||
          current.classList.contains("pswp__item") ||
          current.classList.contains("pswp__img--placeholder") ||
          current.classList.contains("lightbox-overlay"))
      ) {
        return true;
      }
      current = current.parentElement;
    }
    return false;
  }

  function isInsideGrid(el) {
    if (!el) return false;
    let current = el;
    while (current) {
      if (
        current.classList &&
        (current.classList.contains("photo-card") || current.classList.contains("grid"))
      ) {
        return true;
      }
      if (current.hasAttribute && current.hasAttribute("data-testid")) {
        if (current.getAttribute("data-testid") === "photo-card") return true;
      }
      current = current.parentElement;
    }
    return false;
  }

  function elementContext(el) {
    if (!el) return "unknown";
    if (isInsideLightbox(el)) return "lightbox";
    if (isInsideGrid(el)) return "grid";
    const closestUseful =
      el.closest?.(".pswp, .pswp__container, .lightbox-overlay, .photo-card, .grid") ||
      el.parentElement?.closest?.(".pswp, .pswp__container, .lightbox-overlay, .photo-card, .grid");
    if (closestUseful) {
      const cls = closestUseful.className?.toString?.() || "";
      if (/pswp/.test(cls)) return "lightbox";
      if (/lightbox-overlay/.test(cls)) return "lightbox";
      if (/photo-card|grid/.test(cls)) return "grid";
    }
    return "unknown";
  }

  function detectOriginalLoadingReason() {
    // Heuristics to guess why an /api/image was loaded.
    // Check for fullscreen, zoom, animated, or always-load-original preference.
    const reasons = [];
    if (document.fullscreenElement) reasons.push("fullscreen");
    try {
      if (localStorage.getItem("gallery-lightbox-always-load-original") === "true") {
        reasons.push("preference");
      }
    } catch (_) {}
    // Check the PhotoSwipe item data if available via the test hook
    const pswp = window.__pswp;
    if (pswp && pswp.currSlide) {
      const idx = pswp.currSlide.index;
      const ds = pswp.options?.dataSource;
      if (Array.isArray(ds) && ds[idx]) {
        const item = ds[idx];
        if (item.originalLoadReason) reasons.push(item.originalLoadReason);
        if (item.isAnimatedAsset) reasons.push("animated");
        if (item.isOriginalLoaded) reasons.push("already-loaded");
      }
    }
    // Zoom heuristic: check if current zoom level exceeds threshold
    if (pswp && pswp.currSlide) {
      try {
        const initialZoom = pswp.currSlide.zoomLevels?.initial || 1;
        const currZoom = pswp.currSlide.currZoomLevel || 1;
        if (currZoom / initialZoom > 1.2) reasons.push("zoom");
      } catch (_) {}
    }
    return reasons.length ? reasons : ["unknown"];
  }

  // ── 1. Performance Observer for resource entries ──────────────────────────

  function handleResourceEntry(entry) {
    const url = entry.name;
    const endpoint = classifyEndpoint(url);
    if (!endpoint) return;

    const pathParam = extractPathParam(url);
    const rec = {
      source: "resource",
      url,
      endpoint,
      endpointType: endpointType(endpoint),
      path: normalizePath(pathParam),
      queryParams: extractQueryParams(url),
      startTime: entry.startTime,
      duration: entry.duration,
      transferSize: entry.transferSize,
      encodedBodySize: entry.encodedBodySize,
      decodedBodySize: entry.decodedBodySize,
      initiatorType: entry.initiatorType,
      cache: cacheLabel(entry),
      isCacheHit: isCacheHit(entry.transferSize, entry.encodedBodySize),
      timestampRel: timeSinceStart(),
      timeSinceLightboxOpen: timeSinceLastLightboxOpen(),
      lightboxWasOpen: isLightboxOpen(),
      recordedAt: now(),
    };

    resourceRecords.push(rec);
  }

  function startPerformanceObserver() {
    // Capture already-completed entries
    try {
      performance
        .getEntriesByType("resource")
        .filter((e) => ENDPOINTS.some((ep) => e.name.includes(ep)))
        .forEach(handleResourceEntry);
    } catch (_) {}

    // Observe new ones
    try {
      perfObserver = new PerformanceObserver((list) => {
        list.getEntries().forEach(handleResourceEntry);
      });
      perfObserver.observe({ type: "resource", buffered: true });
    } catch (e) {
      console.warn("[GalleryDebug] PerformanceObserver failed:", e);
    }
  }

  function stopPerformanceObserver() {
    if (perfObserver) {
      try {
        perfObserver.disconnect();
      } catch (_) {}
      perfObserver = null;
    }
  }

  // ── 2. fetch() monkeypatch ─────────────────────────────────────────────────

  function patchFetch() {
    if (origFetch) return; // already patched
    origFetch = window.fetch;

    window.fetch = function (input, init) {
      const url = typeof input === "string" ? input : input?.url || "";
      const endpoint = classifyEndpoint(url);

      if (endpoint) {
        const rec = {
          source: "fetch",
          url,
          endpoint,
          endpointType: endpointType(endpoint),
          path: normalizePath(extractPathParam(url)),
          queryParams: extractQueryParams(url),
          timestampRel: timeSinceStart(),
          timeSinceLightboxOpen: timeSinceLastLightboxOpen(),
          lightboxWasOpen: isLightboxOpen(),
          recordedAt: now(),
          status: null,
          ok: null,
        };

        const promise = origFetch.call(window, input, init);
        // Attach response info without breaking the promise chain
        promise
          .then((resp) => {
            rec.status = resp.status;
            rec.ok = resp.ok;
            rec.responseTimestampRel = timeSinceStart();
          })
          .catch(() => {
            rec.status = 0;
            rec.ok = false;
          });

        fetchRecords.push(rec);

        // Return a wrapped promise that still resolves/rejects normally
        return promise.then(
          (r) => r,
          (e) => Promise.reject(e)
        );
      }

      return origFetch.call(window, input, init);
    };
  }

  function unpatchFetch() {
    if (origFetch) {
      window.fetch = origFetch;
      origFetch = null;
    }
  }

  // ── 3. XMLHttpRequest monkeypatch ──────────────────────────────────────────

  function patchXHR() {
    if (origXhrOpen) return;
    origXhrOpen = XMLHttpRequest.prototype.open;
    origXhrSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url) {
      this.__galleryDebug_url = url;
      this.__galleryDebug_method = method;
      return origXhrOpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function () {
      const url = this.__galleryDebug_url;
      const endpoint = classifyEndpoint(url);

      if (endpoint) {
        const rec = {
          source: "xhr",
          url,
          endpoint,
          endpointType: endpointType(endpoint),
          path: normalizePath(extractPathParam(url)),
          queryParams: extractQueryParams(url),
          timestampRel: timeSinceStart(),
          timeSinceLightboxOpen: timeSinceLastLightboxOpen(),
          lightboxWasOpen: isLightboxOpen(),
          recordedAt: now(),
          status: null,
        };

        this.addEventListener("loadend", function () {
          rec.status = this.status;
          rec.timestampEndRel = timeSinceStart();
        });

        xhrRecords.push(rec);
      }

      return origXhrSend.apply(this, arguments);
    };
  }

  function unpatchXHR() {
    if (origXhrOpen) {
      XMLHttpRequest.prototype.open = origXhrOpen;
      XMLHttpRequest.prototype.send = origXhrSend;
      origXhrOpen = null;
      origXhrSend = null;
    }
  }

  // ── 4. DOM image tracking ──────────────────────────────────────────────────

  function recordDomImage(img, reason) {
    const src = img.src || img.currentSrc || "";
    const endpoint = classifyEndpoint(src);
    if (!endpoint) return;

    const rec = {
      source: "dom-img",
      reason,
      src,
      currentSrc: img.currentSrc || "",
      endpoint,
      endpointType: endpointType(endpoint),
      path: normalizePath(extractPathParam(src)),
      queryParams: extractQueryParams(src),
      naturalWidth: img.naturalWidth || 0,
      naturalHeight: img.naturalHeight || 0,
      renderedWidth: Math.round(img.getBoundingClientRect?.().width || 0),
      renderedHeight: Math.round(img.getBoundingClientRect?.().height || 0),
      classes: img.className?.toString?.() || "",
      context: elementContext(img),
      complete: img.complete,
      timestampRel: timeSinceStart(),
      timeSinceLightboxOpen: timeSinceLastLightboxOpen(),
      lightboxWasOpen: isLightboxOpen(),
      recordedAt: now(),
    };

    domImageRecords.push(rec);
  }

  function setupDOMObserver() {
    // Scan existing images
    document.querySelectorAll("img").forEach((img) => {
      recordDomImage(img, "initial-scan");
    });

    // Observe new images
    mutationObserver = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node.nodeName === "IMG") {
            recordDomImage(node, "mutation-add");
            // Also listen for load/error
            node.addEventListener("load", () => recordDomImage(node, "load-event"), { once: true });
            node.addEventListener(
              "error",
              () => recordDomImage(node, "error-event"),
              { once: true }
            );
          }
          if (node.querySelectorAll) {
            node.querySelectorAll("img").forEach((img) => {
              recordDomImage(img, "mutation-add-child");
              img.addEventListener("load", () => recordDomImage(img, "load-event"), { once: true });
              img.addEventListener("error", () => recordDomImage(img, "error-event"), { once: true });
            });
          }
        }
        // Track src changes on existing images
        if (
          mutation.type === "attributes" &&
          (mutation.attributeName === "src" || mutation.attributeName === "srcset") &&
          mutation.target.nodeName === "IMG"
        ) {
          recordDomImage(mutation.target, "src-change");
        }
      }
    });

    mutationObserver.observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["src", "srcset"],
    });

    // Listen for load events globally via capture
    document.addEventListener(
      "load",
      (e) => {
        if (e.target.nodeName === "IMG") {
          recordDomImage(e.target, "global-load-capture");
        }
      },
      true
    );
  }

  function stopDOMObserver() {
    if (mutationObserver) {
      try {
        mutationObserver.disconnect();
      } catch (_) {}
      mutationObserver = null;
    }
  }

  // ── 5. Lightbox state detection ────────────────────────────────────────────

  function checkLightboxState(reason) {
    const wasOpen = currentLightboxOpenTime > 0;
    const isOpen = isLightboxOpen();

    if (isOpen && !wasOpen) {
      currentLightboxOpenTime = now();
      lastLightboxOpenTime = currentLightboxOpenTime;
      const event = {
        type: "open",
        reason,
        timestamp: now(),
        timestampRel: timeSinceStart(),
        pswpAvailable: !!window.__pswp,
      };

      // Capture active slide image URLs if possible
      const pswp = window.__pswp;
      if (pswp && pswp.currSlide) {
        const idx = pswp.currSlide.index;
        const ds = pswp.options?.dataSource;
        if (Array.isArray(ds) && ds[idx]) {
          event.activeItem = {
            src: ds[idx].src,
            previewSrc: ds[idx].previewSrc,
            msrc: ds[idx].msrc,
            path: ds[idx].path,
          };
        }
      }

      lightboxEvents.push(event);

      // Schedule a check for early original requests
      setTimeout(() => {
        const suspicious = resourceRecords.filter(
          (r) =>
            r.endpointType === "original" &&
            r.timestampRel > event.timestampRel &&
            r.timestampRel < event.timestampRel + SUSPICIOUS_ORIGINAL_WINDOW_MS &&
            r.isCacheHit !== true
        );
        if (suspicious.length > 0) {
          lightboxEvents.push({
            type: "suspicious-original-detected",
            openTimestamp: event.timestamp,
            count: suspicious.length,
            records: suspicious.map((r) => ({
              url: r.url,
              path: r.path,
              timingAfterOpen: Math.round(r.timestampRel - event.timestampRel),
              cache: r.cache,
            })),
            timestamp: now(),
          });
        }
      }, SUSPICIOUS_ORIGINAL_WINDOW_MS + 500);
    } else if (!isOpen && wasOpen) {
      lightboxEvents.push({
        type: "close",
        reason,
        timestamp: now(),
        timestampRel: timeSinceStart(),
        duration: now() - currentLightboxOpenTime,
      });
      currentLightboxOpenTime = 0;
    }
  }

  function setupLightboxObserver() {
    // Poll-based state detection as fallback
    let wasOpen = false;
    const pollInterval = setInterval(() => {
      if (!trackingActive) {
        clearInterval(pollInterval);
        return;
      }
      const isOpen = isLightboxOpen();
      if (isOpen !== wasOpen) {
        wasOpen = isOpen;
        checkLightboxState("poll");
      }
    }, 250);

    // Mutation-based detection for .pswp--open class
    const pswpObserver = new MutationObserver(() => {
      checkLightboxState("mutation");
    });

    const targetNode = document.querySelector(PSWP_SELECTORS.root) || document.body;
    pswpObserver.observe(targetNode, {
      attributes: true,
      attributeFilter: ["class"],
      subtree: true,
    });

    // Initial check
    checkLightboxState("initial");

    // Store for cleanup
    return () => {
      clearInterval(pollInterval);
      pswpObserver.disconnect();
    };
  }

  let lightboxCleanup = null;

  // ── Analysis ───────────────────────────────────────────────────────────────

  function allResourceRecords() {
    return [...resourceRecords].sort((a, b) => a.timestampRel - b.timestampRel);
  }

  function allFetchRecords() {
    return [...fetchRecords].sort((a, b) => a.timestampRel - b.timestampRel);
  }

  function allXhrRecords() {
    return [...xhrRecords].sort((a, b) => a.timestampRel - b.timestampRel);
  }

  function allNetworkRecords() {
    // Merge resource + fetch + xhr, deduplicate by URL+time proximity
    const all = [...resourceRecords, ...fetchRecords, ...xhrRecords];
    const seen = new Set();
    const deduped = [];

    all.sort((a, b) => a.timestampRel - b.timestampRel);

    for (const rec of all) {
      const key = rec.url + "|" + Math.round(rec.timestampRel / 50); // 50ms window
      if (!seen.has(key)) {
        seen.add(key);
        deduped.push(rec);
      }
    }

    return deduped;
  }

  function imagePaths() {
    const paths = new Set();
    for (const rec of allNetworkRecords()) {
      if (rec.path) paths.add(rec.path);
    }
    for (const rec of domImageRecords) {
      if (rec.path) paths.add(rec.path);
    }
    return [...paths].sort();
  }

  function groupByPath() {
    const groups = {};
    const networkRecs = allNetworkRecords();

    for (const rec of networkRecs) {
      const key = rec.path || "__unknown__";
      if (!groups[key]) {
        groups[key] = {
          path: rec.path,
          endpoints: new Set(),
          records: [],
          urls: new Set(),
          firstSeen: Infinity,
          lastSeen: -Infinity,
          realNetworkTransfers: 0,
          cacheHits: 0,
          transferSizes: [],
        };
      }
      const g = groups[key];
      g.endpoints.add(rec.endpointType);
      g.records.push(rec);
      g.urls.add(rec.url);
      g.firstSeen = Math.min(g.firstSeen, rec.timestampRel);
      g.lastSeen = Math.max(g.lastSeen, rec.timestampRel);
      if (rec.isCacheHit === false) {
        g.realNetworkTransfers++;
        if (rec.transferSize > 0) g.transferSizes.push(rec.transferSize);
      } else if (rec.isCacheHit === true) {
        g.cacheHits++;
      }
    }

    return groups;
  }

  function analyze() {
    const networkRecs = allNetworkRecords();
    const groups = groupByPath();

    // Counts
    const thumbnails = networkRecs.filter((r) => r.endpointType === "thumbnail");
    const previews = networkRecs.filter((r) => r.endpointType === "preview");
    const originals = networkRecs.filter((r) => r.endpointType === "original");
    const uniquePaths = imagePaths();

    // Suspicious originals: original requests within 3s of lightbox open
    const lightboxOpens = lightboxEvents.filter((e) => e.type === "open");
    const suspiciousOriginals = [];
    for (const rec of originals) {
      for (const openEvent of lightboxOpens) {
        const relTime = rec.timestampRel - openEvent.timestampRel;
        if (relTime >= 0 && relTime < SUSPICIOUS_ORIGINAL_WINDOW_MS) {
          const reasons = detectOriginalLoadingReason();
          const hasLegitimateReason = reasons.some((r) =>
            ["zoom", "preference", "fullscreen", "animated", "fallback"].includes(r)
          );
          if (!hasLegitimateReason || rec.isCacheHit !== true) {
            suspiciousOriginals.push({
              ...rec,
              relativeTimeMs: Math.round(relTime),
              detectedReasons: reasons,
              hasLegitimateReason,
            });
            break;
          }
        }
      }
    }

    // Duplicate real-network requests (same URL, multiple network transfers)
    const urlCounts = {};
    for (const rec of networkRecs) {
      if (rec.isCacheHit === false) {
        if (!urlCounts[rec.url]) urlCounts[rec.url] = [];
        urlCounts[rec.url].push(rec);
      }
    }
    const duplicateRealTransfers = Object.entries(urlCounts)
      .filter(([, recs]) => recs.length > 1)
      .map(([url, recs]) => ({
        url,
        count: recs.length,
        totalTransferSize: recs.reduce((s, r) => s + (r.transferSize || 0), 0),
        records: recs,
      }));

    // Per-image verdicts
    const imageVerdicts = {};
    for (const [key, g] of Object.entries(groups)) {
      const endpoints = g.endpoints;
      const hasOriginal = endpoints.has("original");
      const hasThumbnail = endpoints.has("thumbnail");
      const hasPreview = endpoints.has("preview");
      const allThree = hasOriginal && hasThumbnail && hasPreview;
      const originalIsRealNetwork = g.records.some(
        (r) => r.endpointType === "original" && r.isCacheHit === false
      );
      const originalNearOpen = g.records.some((r) => {
        if (r.endpointType !== "original" || r.isCacheHit === true) return false;
        for (const openEvent of lightboxOpens) {
          const rel = r.timestampRel - openEvent.timestampRel;
          if (rel >= 0 && rel < SUSPICIOUS_ORIGINAL_WINDOW_MS) return true;
        }
        return false;
      });

      // Determine if this image was a neighbor
      let isNeighbor = false;
      for (const openEvent of lightboxOpens) {
        if (openEvent.activeItem && openEvent.activeItem.path !== g.path) {
          isNeighbor = true;
          break;
        }
      }

      let verdict = "OK";
      const flags = [];

      if (hasOriginal && originalIsRealNetwork) {
        if (originalNearOpen && !isNeighbor) {
          verdict = "BAD";
          flags.push("original requested on normal lightbox open");
        } else if (isNeighbor && originalIsRealNetwork) {
          verdict = "BAD";
          flags.push("neighbor preload requested original /api/image");
        } else if (allThree && originalIsRealNetwork) {
          verdict = "WARN";
          flags.push("thumbnail + preview + original all loaded");
        }
      }

      if (hasThumbnail && hasPreview && hasOriginal && !originalIsRealNetwork && originalNearOpen) {
        verdict = "WARN";
        flags.push("original attempted near open but possibly cached");
      }

      // Check for duplicate previews of different sizes
      const previewSizes = g.records
        .filter((r) => r.endpointType === "preview")
        .map((r) => r.queryParams?.max_long_edge)
        .filter(Boolean);
      const uniquePreviewSizes = new Set(previewSizes);
      if (uniquePreviewSizes.size > 1) {
        if (verdict === "OK") verdict = "WARN";
        flags.push("multiple preview sizes: " + [...uniquePreviewSizes].join(", "));
      }

      // Check for duplicate requests with real transfers
      const dupUrls = g.records
        .filter((r) => r.isCacheHit === false)
        .map((r) => r.url);
      if (new Set(dupUrls).size < dupUrls.length) {
        if (verdict === "OK") verdict = "WARN";
        flags.push("duplicate real-network requests for same URL");
      }

      if (flags.length === 0) {
        if (hasOriginal && !originalIsRealNetwork && originalNearOpen) {
          flags.push("original cached — unlikely an issue");
        }
      }

      if (flags.length === 0) {
        flags.push("normal");
      }

      imageVerdicts[key] = {
        path: g.path,
        endpoints: [...endpoints].sort(),
        totalRequests: g.records.length,
        realNetworkTransfers: g.realNetworkTransfers,
        cacheHits: g.cacheHits,
        totalTransferBytes: g.transferSizes.reduce((a, b) => a + b, 0),
        firstSeenMs: Math.round(g.firstSeen),
        lastSeenMs: Math.round(g.lastSeen),
        urls: [...g.urls],
        verdict,
        flags,
        isNeighbor,
      };
    }

    // DOM image summary
    const currentPSWPImages = domImageRecords.filter(
      (r) => r.context === "lightbox" && r.reason !== "initial-scan"
    );
    const gridImages = domImageRecords.filter((r) => r.context === "grid");
    const originalImgElements = domImageRecords.filter((r) => r.endpointType === "original");

    return {
      summary: {
        totalThumbnailRequests: thumbnails.length,
        totalPreviewRequests: previews.length,
        totalOriginalRequests: originals.length,
        uniqueImagePaths: uniquePaths.length,
        suspiciousOriginalOnOpenCount: suspiciousOriginals.length,
        duplicateRealNetworkRequestCount: duplicateRealTransfers.length,
        duplicateRealNetworkTotalWasteBytes: duplicateRealTransfers.reduce(
          (s, d) => s + d.totalTransferSize,
          0
        ),
        lightboxOpenCount: lightboxOpens.length,
        lightboxCloseCount: lightboxEvents.filter((e) => e.type === "close").length,
        trackingDurationMs: Math.round(timeSinceStart()),
      },
      timeline: networkRecs.map((r) => ({
        timeMs: Math.round(r.timestampRel),
        endpoint: r.endpointType,
        path: r.path,
        cacheStatus: r.cache,
        transferSize: r.transferSize,
        initiator: r.initiatorType || r.source,
        lightboxContext: r.lightboxWasOpen ? "open" : "closed",
      })),
      byImage: imageVerdicts,
      suspiciousOriginals,
      duplicateRealTransfers,
      lightboxEvents,
      domSummary: {
        currentPhotoSwipeImages: currentPSWPImages.map((img) => ({
          src: img.src,
          endpointType: img.endpointType,
          naturalSize: `${img.naturalWidth}x${img.naturalHeight}`,
          renderedSize: `${img.renderedWidth}x${img.renderedHeight}`,
          path: img.path,
          classes: img.classes,
        })),
        gridImagesSummary: {
          count: gridImages.length,
          endpointTypes: [...new Set(gridImages.map((r) => r.endpointType))],
        },
        originalImageElements: originalImgElements.map((img) => ({
          src: img.src,
          path: img.path,
          naturalSize: `${img.naturalWidth}x${img.naturalHeight}`,
          context: img.context,
          classes: img.classes,
        })),
      },
      raw: {
        resourceRecords,
        fetchRecords,
        xhrRecords,
        domImageRecords,
        lightboxEvents,
      },
    };
  }

  // ── Report formatting ──────────────────────────────────────────────────────

  function formatReport() {
    const data = analyze();
    const { summary, timeline, byImage, suspiciousOriginals, duplicateRealTransfers, domSummary } = data;

    const lines = [];

    lines.push("");
    lines.push("═".repeat(80));
    lines.push("  GALLERY LIGHTBOX IMAGE LOAD DEBUG REPORT");
    lines.push("═".repeat(80));
    lines.push("");
    lines.push("Tracking duration: " + (summary.trackingDurationMs / 1000).toFixed(1) + "s");
    lines.push("");
    lines.push("── Summary ──");
    lines.push(`  Thumbnail (/api/thumbnail) requests:  ${summary.totalThumbnailRequests}`);
    lines.push(`  Preview   (/api/preview)   requests:  ${summary.totalPreviewRequests}`);
    lines.push(`  Original  (/api/image)     requests:  ${summary.totalOriginalRequests}`);
    lines.push(`  Unique image paths:                   ${summary.uniqueImagePaths}`);
    lines.push(`  Lightbox opens:                       ${summary.lightboxOpenCount}`);
    lines.push(`  Lightbox closes:                      ${summary.lightboxCloseCount}`);
    lines.push("");

    if (suspiciousOriginals.length > 0) {
      lines.push(`  ⚠  Suspicious /api/image on open:  ${summary.suspiciousOriginalOnOpenCount}`);
    } else {
      lines.push(`  ✓  Suspicious /api/image on open:  0`);
    }

    if (duplicateRealTransfers.length > 0) {
      lines.push(
        `  ⚠  Duplicate real-network requests:  ${summary.duplicateRealNetworkRequestCount} (wasted ~${formatBytes(summary.duplicateRealNetworkTotalWasteBytes)})`
      );
    } else {
      lines.push(`  ✓  Duplicate real-network requests:  0`);
    }

    lines.push("");
    lines.push("── Per-Image Analysis ──");
    const verdictOrder = { BAD: 0, WARN: 1, OK: 2 };
    const sortedImages = Object.values(byImage).sort(
      (a, b) => (verdictOrder[a.verdict] ?? 99) - (verdictOrder[b.verdict] ?? 99)
    );

    for (const img of sortedImages) {
      const verdictIcon = img.verdict === "BAD" ? "✗" : img.verdict === "WARN" ? "⚠" : "✓";
      const displayPath = img.path || "(unknown)";
      const shortPath = displayPath.length > 60 ? "..." + displayPath.slice(-57) : displayPath;

      lines.push(`  ${verdictIcon} [${img.verdict}] ${shortPath}`);
      lines.push(`      Endpoints: ${img.endpoints.join(", ")}`);
      lines.push(`      Requests: ${img.totalRequests} (${img.realNetworkTransfers} real network, ${img.cacheHits} cache hits)`);
      if (img.totalTransferBytes > 0) {
        lines.push(`      Data transferred: ${formatBytes(img.totalTransferBytes)}`);
      }
      for (const flag of img.flags) {
        lines.push(`      → ${flag}`);
      }
      lines.push("");
    }

    if (suspiciousOriginals.length > 0) {
      lines.push("── Suspicious /api/image Requests Near Lightbox Open ──");
      for (const rec of suspiciousOriginals) {
        const reasons = rec.detectedReasons?.join(", ") || "none detected";
        lines.push(`  ${rec.path || "unknown"}`);
        lines.push(`    Timing: +${rec.relativeTimeMs}ms after open`);
        lines.push(`    Cache:  ${rec.cache}`);
        lines.push(`    Legitimate reasons found: ${rec.hasLegitimateReason ? reasons : "NONE"}`);
        if (!rec.hasLegitimateReason) {
          lines.push(`    ⚠  No zoom/fullscreen/animated/fallback/preference reason detected`);
        }
      }
      lines.push("");
    }

    if (duplicateRealTransfers.length > 0) {
      lines.push("── Duplicate Real-Network Transfers ──");
      for (const dup of duplicateRealTransfers) {
        lines.push(`  ${dup.url}`);
        lines.push(`    Count: ${dup.count}, Waste: ${formatBytes(dup.totalTransferSize)}`);
      }
      lines.push("");
    }

    lines.push("── Timeline (sorted by time) ──");
    lines.push("  Time(ms) | Endpoint   | Path (short) | Cache/Transfer | Context");
    lines.push("  " + "─".repeat(74));
    for (const t of timeline) {
      const shortPath = (t.path || "").split("/").pop() || t.path || "?";
      const truncated = shortPath.length > 25 ? shortPath.slice(0, 22) + "..." : shortPath;
      const cacheStr = t.cacheStatus.padEnd(28).slice(0, 28);
      const ctx = t.lightboxContext === "open" ? "LB-OPEN" : "grid";
      lines.push(
        `  ${String(t.timeMs).padStart(8)} | ${t.endpoint.padEnd(10)} | ${truncated.padEnd(27)} | ${cacheStr} | ${ctx}`
      );
    }
    lines.push("");

    lines.push("── DOM Image Summary ──");
    lines.push(`  Grid images tracked:     ${domSummary.gridImagesSummary.count}`);
    lines.push(`  Grid endpoint types:     ${domSummary.gridImagesSummary.endpointTypes.join(", ")}`);
    lines.push(`  PhotoSwipe <img> (live): ${domSummary.currentPhotoSwipeImages.length}`);
    for (const img of domSummary.currentPhotoSwipeImages) {
      lines.push(`    src=${img.endpointType.padEnd(10)} ${img.naturalSize.padEnd(12)} rendered=${img.renderedSize}`);
    }
    lines.push(`  <img> using /api/image:  ${domSummary.originalImageElements.length}`);
    for (const img of domSummary.originalImageElements) {
      lines.push(`    context=${img.context.padEnd(10)} path=${img.path || "?"}`);
    }
    lines.push("");

    lines.push("── Expected Architecture ──");
    lines.push("  Grid:              /api/thumbnail = OK");
    lines.push("  Normal lightbox:   /api/preview   = OK");
    lines.push("                     /api/thumbnail as msrc/placeholder = OK");
    lines.push("                     /api/image     = suspicious unless zoom/fullscreen/");
    lines.push("                                       download/animated/fallback");
    lines.push("  Neighbor preload:  /api/thumbnail = OK");
    lines.push("                     /api/preview   = OK");
    lines.push("                     /api/image     = BAD");
    lines.push("");
    lines.push("═".repeat(80));
    lines.push("  END OF REPORT — use __galleryLightboxDebug.copyReport() to copy JSON");
    lines.push("═".repeat(80));

    // Attach data for clipboard
    lines._reportData = data;

    return lines.join("\n");
  }

  function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    if (!bytes) return "? B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  function copyToClipboard(text) {
    // Try modern clipboard API first
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      navigator.clipboard
        .writeText(text)
        .then(() => {
          console.log("[GalleryDebug] Copied debug report to clipboard");
        })
        .catch(() => {
          fallbackCopy(text);
        });
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    try {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      textarea.style.top = "-9999px";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      console.log("[GalleryDebug] Copied debug report to clipboard (fallback)");
    } catch (e) {
      console.error("[GalleryDebug] Failed to copy to clipboard:", e);
      console.log("[GalleryDebug] Report data available as __galleryLightboxDebug.json()");
    }
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  const api = {
    start() {
      if (trackingActive) {
        console.warn("[GalleryDebug] Already tracking. Call .stop() first or .clear() to reset.");
        return;
      }

      startTime = performance.now();
      trackingActive = true;
      lastLightboxOpenTime = 0;
      currentLightboxOpenTime = 0;

      startPerformanceObserver();
      patchFetch();
      patchXHR();
      setupDOMObserver();
      lightboxCleanup = setupLightboxObserver();

      // Initial scan
      document.querySelectorAll("img").forEach((img) => recordDomImage(img, "start-scan"));

      console.log(
        "[GalleryDebug] Tracking started at t=0ms. Open a lightbox and navigate to collect data."
      );
      console.log("[GalleryDebug] Commands: .report() .copyReport() .stop() .clear() .status()");
    },

    stop() {
      if (!trackingActive) {
        console.warn("[GalleryDebug] Not currently tracking.");
        return;
      }

      stopPerformanceObserver();
      unpatchFetch();
      unpatchXHR();
      stopDOMObserver();
      if (lightboxCleanup) {
        lightboxCleanup();
        lightboxCleanup = null;
      }
      trackingActive = false;
      console.log("[GalleryDebug] Tracking stopped. Data preserved. Use .report() to view.");
    },

    clear() {
      const wasActive = trackingActive;
      if (wasActive) {
        this.stop();
      }

      resourceRecords.length = 0;
      fetchRecords.length = 0;
      xhrRecords.length = 0;
      domImageRecords.length = 0;
      lightboxEvents.length = 0;
      lastLightboxOpenTime = 0;
      currentLightboxOpenTime = 0;
      startTime = 0;

      console.log("[GalleryDebug] All data cleared.");

      if (wasActive) {
        this.start();
      }
    },

    report() {
      if (resourceRecords.length === 0 && fetchRecords.length === 0 && domImageRecords.length === 0) {
        console.log("[GalleryDebug] No data collected yet. Call .start() and interact with the lightbox.");
        return null;
      }

      const report = formatReport();
      console.log(report);
      return report._reportData;
    },

    copyReport() {
      const data = this.report();
      if (!data) return;
      const json = JSON.stringify(data, null, 2);
      copyToClipboard(json);
    },

    json() {
      return analyze();
    },

    status() {
      const isOpen = isLightboxOpen();
      console.log("── Gallery Lightbox Debug Status ──");
      console.log(`  Tracking:    ${trackingActive ? "ACTIVE" : "STOPPED"}`);
      console.log(`  Elapsed:     ${(timeSinceStart() / 1000).toFixed(1)}s`);
      console.log(`  Lightbox:    ${isOpen ? "OPEN" : "closed"}`);
      console.log(`  Resources:   ${resourceRecords.length}`);
      console.log(`  Fetch calls: ${fetchRecords.length}`);
      console.log(`  XHR calls:   ${xhrRecords.length}`);
      console.log(`  DOM images:  ${domImageRecords.length}`);
      console.log(`  LB events:   ${lightboxEvents.length}`);
      if (isOpen) {
        const pswp = window.__pswp;
        if (pswp) {
          const idx = pswp.currIndex;
          const ds = pswp.options?.dataSource;
          if (Array.isArray(ds) && ds[idx]) {
            console.log(`  Active slide: #${idx} — ${ds[idx].path || "?"}`);
            console.log(`    src=${ds[idx].src}`);
          }
        }
      }
    },
  };

  // Export
  window.__galleryLightboxDebug = api;
  console.log(
    "[GalleryDebug] Lightbox image load debugger ready. Call __galleryLightboxDebug.start() to begin tracking."
  );
})();
