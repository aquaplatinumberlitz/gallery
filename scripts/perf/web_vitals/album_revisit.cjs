#!/usr/bin/env node
// Album open on a first visit and on a revisit in a new page, counting thumbnail responses. Port of the scratch
// revisit.cjs.
//
// Purpose:
// Confirm the revisit path: after the first open, thumbnails come from the immutable HTTP cache (0 thumbnail
// network responses), and the revisit's time to visible thumbnails.
//
// Guarantees:
// * each visit is a fresh page in the same browser context, so the HTTP cache is shared between visits
// * the response tally uses fromDiskCache/fromMemoryCache to report "cache", otherwise the HTTP status
// * the album is opened by its card (data-album-name = ALBUM) and the run waits for every visible thumbnail
// * profiles: 4g (85 ms, 9 Mbps, 4x CPU), slow4g (150 ms, 1.6 Mbps, 4x CPU), desktop (unthrottled, 1440x900)
//
// Usage:
//   BASE=http://127.0.0.1:8080 PROFILE=4g ALBUM=real node scripts/perf/web_vitals/album_revisit.cjs
// Env: BASE (default http://127.0.0.1:8080), PROFILE = 4g (default) | slow4g | desktop, ALBUM (default real).
// Output: one line per visit, "<profile> <first|revisit> visibleThumbsMs <ms> thumbnail responses {...}".
//
// Run when:
// * changing thumbnail URLs, cache headers, or album open order (revisit must stay at 0 thumbnail requests)
// * checking the "Album revisit" row in docs/testing/PERFORMANCE_TESTING.md

const { loadChromium } = require("./lib.cjs");

const BASE = process.env.BASE || "http://127.0.0.1:8080";
const PROFILE = process.env.PROFILE || "4g";
const ALBUM = process.env.ALBUM || "real";
const NETS = { slow4g: { latency: 150, down: 1.6 }, "4g": { latency: 85, down: 9 }, desktop: null };
if (!(PROFILE in NETS)) throw new Error(`unknown PROFILE=${PROFILE} (4g|slow4g|desktop)`);
const mobile = PROFILE !== "desktop";
const visibleLoaded = `(() => { const imgs = [...document.querySelectorAll('[data-testid="photo-card"] img')].filter((i) => { const r = i.getBoundingClientRect(); return r.bottom > 40 && r.top < innerHeight - 40 && r.width > 0; }); return imgs.length > 0 && imgs.every((i) => i.complete && i.naturalWidth > 0); })()`;
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
  await ctx.addInitScript(() => localStorage.setItem("intro_mode", "disabled"));
  for (const visit of ["first", "revisit"]) {
    const page = await ctx.newPage();
    const cdp = await ctx.newCDPSession(page);
    await cdp.send("Network.enable");
    const n = NETS[PROFILE];
    if (n) {
      await cdp.send("Network.emulateNetworkConditions", {
        offline: false,
        latency: n.latency,
        downloadThroughput: (n.down * 1024 * 1024) / 8,
        uploadThroughput: 1e6 / 8,
      });
      await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
    }
    const st = {};
    cdp.on("Network.responseReceived", (e) => {
      if (e.response.url.includes("/api/thumbnail")) {
        const k = e.response.fromDiskCache || e.response.fromMemoryCache ? "cache" : String(e.response.status);
        st[k] = (st[k] || 0) + 1;
      }
    });
    await page.goto(BASE, { waitUntil: "load" });
    const card = page.locator(`[data-testid="album-card"][data-album-name="${ALBUM}"]`).first();
    await card.waitFor();
    await page.waitForTimeout(3000);
    const t = Date.now();
    await card.click();
    await page.waitForFunction(visibleLoaded, null, { timeout: 60000, polling: 50 });
    const ms = Date.now() - t;
    await page.waitForTimeout(1500);
    console.log(PROFILE, visit, "visibleThumbsMs", ms, "thumbnail responses", JSON.stringify(st));
    await page.close();
  }
  await browser.close();
})().catch((e) => {
  console.error("ERR", e.message);
  process.exit(1);
});
