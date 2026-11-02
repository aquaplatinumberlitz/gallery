#!/usr/bin/env node
// Long tasks and API timings during album open. Port of the scratch openprof.cjs.
//
// Purpose:
// Attribute the album-open main-thread time (Track M, ST-4): every long task (>= 50 ms) from the click, and the
// backend API requests that ran during the open (excluding thumbnails, which the flow script counts separately).
//
// Guarantees:
// * long tasks come from a buffered PerformanceObserver installed before any page script runs
// * times in the output are relative to the click, in milliseconds (rounded)
// * the profile is 4g by default (85 ms, 9 Mbps, 4x CPU), slow4g is 150 ms / 1.6 Mbps, desktop is unthrottled
//
// Usage:
//   BASE=http://127.0.0.1:8080 PROFILE=4g ALBUM=real node scripts/perf/web_vitals/album_open_profile.cjs
// Env: BASE (default http://127.0.0.1:8080), PROFILE = 4g (default) | slow4g | desktop, ALBUM (default real).
// Output: one JSON object: firstCard (ms from click to the first photo card), lt ([start, duration] of long tasks
// relative to the click), api ([pathname, start, duration, transferSize] of non-thumbnail /api requests),
// cards (photo cards rendered), dom (element count).
//
// Run when:
// * profiling the album open long task or the click INP before changing it
// * checking that an album-open change moved work out of the click (Track M1 attribution)

const { loadChromium } = require("./lib.cjs");

const BASE = process.env.BASE || "http://127.0.0.1:8080";
const PROFILE = process.env.PROFILE || "4g";
const ALBUM = process.env.ALBUM || "real";
const NETS = { slow4g: { latency: 150, down: 1.6 }, "4g": { latency: 85, down: 9 }, desktop: null };
if (!(PROFILE in NETS)) throw new Error(`unknown PROFILE=${PROFILE} (4g|slow4g|desktop)`);
const mobile = PROFILE !== "desktop";

(async () => {
  const chromium = loadChromium();
  const b = await chromium.launch();
  const ctx = await b.newContext({
    ignoreHTTPSErrors: true,
    viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    isMobile: mobile,
    hasTouch: mobile,
    deviceScaleFactor: mobile ? 2 : 1,
  });
  await ctx.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    window.__lt = [];
    new PerformanceObserver((l) => {
      for (const e of l.getEntries()) window.__lt.push([Math.round(e.startTime), Math.round(e.duration)]);
    }).observe({ type: "longtask", buffered: true });
    performance.setResourceTimingBufferSize(10000);
  });
  const p = await ctx.newPage();
  const cdp = await ctx.newCDPSession(p);
  const n = NETS[PROFILE];
  if (n) {
    await cdp.send("Network.enable");
    await cdp.send("Network.emulateNetworkConditions", {
      offline: false,
      latency: n.latency,
      downloadThroughput: (n.down * 1024 * 1024) / 8,
      uploadThroughput: 1e6 / 8,
    });
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  }
  await p.goto(BASE, { waitUntil: "load" });
  const card = p.locator(`[data-testid="album-card"][data-album-name="${ALBUM}"]`).first();
  await card.waitFor();
  await p.waitForTimeout(4000);
  const c0 = await p.evaluate(() => {
    window.__lt.length = 0;
    return performance.now();
  });
  await card.click();
  await p.getByTestId("photo-card").first().waitFor();
  const c1 = await p.evaluate(() => performance.now());
  await p.waitForTimeout(1500);
  const r = await p.evaluate(
    (c0) => ({
      lt: window.__lt.filter(([s]) => s >= c0).map(([s, d]) => [s - Math.round(c0), d]),
      api: performance
        .getEntriesByType("resource")
        .filter((e) => e.startTime >= c0 && e.name.includes("/api/") && !e.name.includes("thumbnail"))
        .map((e) => [new URL(e.name).pathname, Math.round(e.startTime - c0), Math.round(e.duration), e.transferSize]),
      cards: document.querySelectorAll('[data-testid="photo-card"]').length,
      dom: document.getElementsByTagName("*").length,
    }),
    c0,
  );
  console.log(JSON.stringify({ firstCard: Math.round(c1 - c0), ...r }));
  await b.close();
})().catch((e) => {
  console.error("ERR", e.message);
  process.exit(1);
});
