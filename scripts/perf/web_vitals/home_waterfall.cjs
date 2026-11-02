#!/usr/bin/env node
// Home page cold + repeat load with a request waterfall. Port of the scratch waterfall.cjs.
//
// Purpose:
// Measure home LCP, FCP and transferred bytes for a cold load and a repeat visit, and list the requests that
// made up the LCP chain (LIST=1).
//
// Guarantees:
// * mobile profiles use a 390x844 viewport at DPR 2 with 4x CPU throttling; desktop uses 1440x900 at DPR 1
//   with no throttling
// * the LCP element and its time are read from a PerformanceObserver installed before any page script runs
// * the intro is disabled through localStorage so the measurement starts at the home page
//
// Usage:
//   BASE=http://127.0.0.1:8080 NET=slow4g node scripts/perf/web_vitals/home_waterfall.cjs
//   BASE=... NET=4g LIST=1 node ...        # typical 4G, print the request timeline
//   BASE=... NET=desktop node ...          # unthrottled desktop
// Env: BASE (default http://127.0.0.1:8080), NET = slow4g (default) | 4g | desktop, LIST = 1 to print the waterfall.
// Run from frontend/ (or set NODE_PATH) so Playwright resolves; set PLAYWRIGHT_BROWSERS_PATH for Chromium.
//
// Output: one line per run, "== cold: fcp <ms> lcp <ms> (<element>) requests <n> bytes <n>", then, with LIST=1,
// one line per request: start -> end (ms), encoded bytes, status, cache flag, content-encoding, URL.
//
// Run when:
// * changing home load order, the root browse request, cover images or font loading (Track L)
// * checking home LCP/FCP against the user-facing standard in docs/testing/PERFORMANCE_TESTING.md

const { loadChromium } = require("./lib.cjs");

const BASE = process.env.BASE || "http://127.0.0.1:8080";
const NET = process.env.NET || "slow4g";
const NET_PROFILES = {
  slow4g: { latency: 150, download: (1.6 * 1024 * 1024) / 8, upload: (750 * 1024) / 8 },
  "4g": { latency: 85, download: (9 * 1024 * 1024) / 8, upload: (1.5 * 1024 * 1024) / 8 },
  desktop: null,
};
if (!(NET in NET_PROFILES)) throw new Error(`unknown NET=${NET} (slow4g|4g|desktop)`);
const mobile = NET !== "desktop";

(async () => {
  const chromium = loadChromium();
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    ignoreHTTPSErrors: true,
    viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    isMobile: mobile,
    hasTouch: mobile,
    deviceScaleFactor: mobile ? 2 : 1,
  });
  await ctx.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    window.__lcp = 0;
    new PerformanceObserver((l) => {
      for (const e of l.getEntries()) {
        window.__lcp = e.startTime;
        window.__lcpEl = (e.element && (e.element.tagName + "." + (e.element.className || "").toString().slice(0, 60))) || e.url;
      }
    }).observe({ type: "largest-contentful-paint", buffered: true });
  });
  const run = async (label) => {
    const page = await ctx.newPage();
    const cdp = await ctx.newCDPSession(page);
    await cdp.send("Network.enable");
    const net = NET_PROFILES[NET];
    if (net) {
      await cdp.send("Network.emulateNetworkConditions", {
        offline: false,
        latency: net.latency,
        downloadThroughput: net.download,
        uploadThroughput: net.upload,
      });
      await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
    }
    const reqs = {};
    let t0 = null;
    cdp.on("Network.requestWillBeSent", (e) => {
      if (t0 === null) t0 = e.timestamp;
      reqs[e.requestId] = { url: e.request.url.replace(BASE, "/").slice(0, 90), start: e.timestamp };
    });
    cdp.on("Network.responseReceived", (e) => {
      const r = reqs[e.requestId];
      if (r) {
        r.status = e.response.status;
        r.fromCache = e.response.fromDiskCache || e.response.fromMemoryCache;
        r.enc = e.response.headers["content-encoding"] || e.response.headers["Content-Encoding"] || "";
      }
    });
    cdp.on("Network.loadingFinished", (e) => {
      const r = reqs[e.requestId];
      if (r) {
        r.end = e.timestamp;
        r.bytes = e.encodedDataLength;
      }
    });
    await page.goto(BASE, { waitUntil: "load" });
    await page.getByTestId("album-card").first().waitFor({ timeout: 60000 });
    await page.waitForTimeout(2500);
    const v = await page.evaluate(() => ({
      fcp: performance.getEntriesByName("first-contentful-paint")[0]?.startTime,
      lcp: window.__lcp,
      lcpEl: window.__lcpEl,
    }));
    const list = Object.values(reqs)
      .filter((r) => r.end)
      .sort((a, b) => a.start - b.start);
    const total = list.reduce((a, r) => a + (r.bytes || 0), 0);
    console.log(
      `== ${label}: fcp ${Math.round(v.fcp)} lcp ${Math.round(v.lcp)} (${v.lcpEl}) requests ${list.length} bytes ${total}`,
    );
    if (process.env.LIST) {
      for (const r of list) {
        console.log(
          `${Math.round((r.start - t0) * 1000).toString().padStart(6)} → ${Math.round((r.end - t0) * 1000).toString().padStart(6)} ms ${String(r.bytes).padStart(8)}B ${r.status}${r.fromCache ? " cache" : ""} ${r.enc} ${r.url}`,
        );
      }
    }
    await page.close();
  };
  await run("cold");
  await run("repeat");
  await browser.close();
})().catch((e) => {
  console.error("ERR", e.message);
  process.exit(1);
});
