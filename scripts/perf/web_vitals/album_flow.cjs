#!/usr/bin/env node
// Album open -> visible thumbnails, two fast scrolls, lightbox open and three next-image steps.
// Port of the scratch album.cjs.
//
// Purpose:
// Measure the in-app flow against the Nielsen limits in docs/testing/PERFORMANCE_TESTING.md: album open until the
// visible thumbnails load (ST-3), click INP on album and lightbox open (ST-5), fast-scroll settle time, lightbox
// first image and preview, and next-image timing.
//
// Guarantees:
// * the album is opened by its card (data-album-name = ALBUM); the run waits for every visible thumbnail to load
// * network and CPU throttling match the profile: slow4g (150 ms, 1.6 Mbps, 4x CPU), 4g (85 ms, 9 Mbps, 4x CPU),
//   desktop (unthrottled, 1440x900, DPR 1)
// * output is one JSON object on stdout; progress and errors go to stderr via the ERR line
//
// Usage:
//   BASE=http://127.0.0.1:8080 PROFILE=4g ALBUM=real node scripts/perf/web_vitals/album_flow.cjs label
// Env: BASE (default http://127.0.0.1:8080), PROFILE = slow4g (default) | 4g | desktop, ALBUM (default real).
// Output keys: album {firstCardMs, visibleThumbsMs, visible, net, clickINP}, scroll1/scroll2 {frames, p50, p95,
// over50, settleMs, longtasks, net}, lightbox {visibleMs, firstImageMs, previewMs, clickINP, net, previewReqTimes},
// next[] {slideMs, previewMs, thumb/preview/original counts}, longtasksTotal.
//
// Run when:
// * changing album open, virtualised grid rendering, thumbnail loading or the lightbox (Tracks M and H)
// * comparing a branch with main in the same run

const { loadChromium } = require("./lib.cjs");

const BASE = process.env.BASE || "http://127.0.0.1:8080";
const PROFILE = process.env.PROFILE || "slow4g";
const ALBUM = process.env.ALBUM || "real";
const label = process.argv[2] || "";
const NETS = { slow4g: { latency: 150, down: 1.6, up: 0.75 }, "4g": { latency: 85, down: 9, up: 1.5 }, desktop: null };
if (!(PROFILE in NETS)) throw new Error(`unknown PROFILE=${PROFILE} (slow4g|4g|desktop)`);
const mobile = PROFILE !== "desktop";
const OBS = () => {
  window.__ev = [];
  window.__lt = [];
  performance.setResourceTimingBufferSize(10000);
  new PerformanceObserver((l) => {
    for (const e of l.getEntries()) if (e.interactionId) window.__ev.push([e.name, e.duration, e.startTime]);
  }).observe({ type: "event", buffered: true, durationThreshold: 16 });
  new PerformanceObserver((l) => {
    for (const e of l.getEntries()) window.__lt.push([e.startTime, e.duration]);
  }).observe({ type: "longtask", buffered: true });
};
const scrollerJs = `(() => { const c = [...document.querySelectorAll("*")].filter((e) => e.scrollHeight > e.clientHeight + 1500 && /(auto|scroll)/.test(getComputedStyle(e).overflowY)); return c.sort((a,b)=>b.scrollHeight-a.scrollHeight)[0] || document.scrollingElement; })()`;
const visibleLoaded = `(() => { const imgs = [...document.querySelectorAll('[data-testid="photo-card"] img')].filter((i) => { const r = i.getBoundingClientRect(); return r.bottom > 40 && r.top < innerHeight - 40 && r.width > 0; }); return { n: imgs.length, done: imgs.filter((i) => i.complete && i.naturalWidth > 0).length }; })()`;
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
  });
  await ctx.addInitScript(OBS);
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await cdp.send("Network.enable");
  if (NETS[PROFILE]) {
    const n = NETS[PROFILE];
    await cdp.send("Network.emulateNetworkConditions", {
      offline: false,
      latency: n.latency,
      downloadThroughput: (n.down * 1024 * 1024) / 8,
      uploadThroughput: (n.up * 1024 * 1024) / 8,
    });
  }
  if (mobile) await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  const reqs = new Map();
  cdp.on("Network.requestWillBeSent", (e) => {
    const u = e.request.url;
    const k = u.includes("/api/thumbnail")
      ? "thumb"
      : u.includes("/api/preview")
        ? "preview"
        : u.includes("/api/image")
          ? "original"
          : null;
    if (k) reqs.set(e.requestId, { k, t0: e.timestamp, url: u });
  });
  cdp.on("Network.responseReceived", (e) => {
    const r = reqs.get(e.requestId);
    if (r) r.status = e.response.status;
  });
  cdp.on("Network.loadingFinished", (e) => {
    const r = reqs.get(e.requestId);
    if (r) {
      r.t1 = e.timestamp;
      r.bytes = e.encodedDataLength;
    }
  });
  cdp.on("Network.loadingFailed", (e) => {
    const r = reqs.get(e.requestId);
    if (r) {
      r.failed = e.errorText;
      r.canceled = e.canceled;
    }
  });
  const snap = () => {
    const a = [...reqs.values()];
    const by = (k) => a.filter((r) => r.k === k);
    return {
      thumbs: by("thumb").length,
      thumbsDone: by("thumb").filter((r) => r.t1).length,
      thumbsCanceled: by("thumb").filter((r) => r.failed).length,
      thumbKB: Math.round(by("thumb").reduce((s, r) => s + (r.bytes || 0), 0) / 1024),
      previews: by("preview").length,
      originals: by("original").length,
      s304: a.filter((r) => r.status === 304).length,
    };
  };
  const out = { label, profile: PROFILE };
  await page.goto(BASE, { waitUntil: "load" });
  const card = page.locator(`[data-testid="album-card"][data-album-name="${ALBUM}"]`).first();
  await card.waitFor({ timeout: 60000 });
  await page.waitForTimeout(4000); // let idle warm-ups finish
  reqs.clear();
  await page.evaluate(() => {
    window.__ev.length = 0;
    window.__lt.length = 0;
  });
  // 1. open album
  let t = Date.now();
  await card.click();
  await page.getByTestId("photo-card").first().waitFor({ timeout: 60000 });
  out.album = { firstCardMs: Date.now() - t };
  await page.waitForFunction(
    `(() => { const v = ${visibleLoaded}; return v.n > 0 && v.done === v.n; })()`,
    null,
    { timeout: 120000, polling: 50 },
  );
  out.album.visibleThumbsMs = Date.now() - t;
  out.album.visible = (await page.evaluate(visibleLoaded)).n;
  out.album.net = snap();
  out.album.clickINP = await page.evaluate(() => Math.max(0, ...window.__ev.map((e) => e[1])));
  await page.waitForTimeout(1500);
  // 2. fast scroll (fling-like: 1 viewport per 80 ms, 8 viewports), then settle
  for (const round of ["scroll1", "scroll2"]) {
    reqs.clear();
    await page.evaluate(() => {
      window.__lt.length = 0;
    });
    const fr = await page.evaluate(async (js) => {
      const sc = eval(js);
      const frames = [];
      let last = performance.now(),
        run = true;
      const tick = (x) => {
        frames.push(x - last);
        last = x;
        if (run) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
      for (let i = 0; i < 8; i++) {
        sc.scrollBy(0, innerHeight);
        await new Promise((r) => setTimeout(r, 80));
      }
      run = false;
      frames.sort((a, b) => a - b);
      return {
        frames: frames.length,
        p50: Math.round(frames[frames.length >> 1]),
        p95: Math.round(frames[Math.floor(frames.length * 0.95)]),
        over50: frames.filter((f) => f > 50).length,
        scrollTop: Math.round(sc.scrollTop),
        dom: document.getElementsByTagName("*").length,
      };
    }, scrollerJs);
    t = Date.now();
    let settled = true;
    try {
      await page.waitForFunction(
        `(() => { const v = ${visibleLoaded}; return v.n > 0 && v.done === v.n; })()`,
        null,
        { timeout: 60000, polling: 50 },
      );
    } catch {
      settled = false;
    }
    out[round] = {
      ...fr,
      settleMs: settled ? Date.now() - t : "timeout",
      longtasks: await page.evaluate(() => window.__lt.length),
      net: snap(),
    };
    await page.waitForTimeout(1500);
  }
  // 3. lightbox open + next x3
  await page.evaluate((js) => {
    eval(js).scrollTop = 0;
    window.scrollTo(0, 0);
  }, scrollerJs);
  await page.waitForTimeout(2000);
  reqs.clear();
  await page.evaluate(() => {
    window.__ev.length = 0;
  });
  const clickAt = await page.evaluate(() => performance.now());
  t = Date.now();
  await page.getByTestId("photo-card").nth(1).click();
  await page.getByTestId("lightbox").waitFor({ timeout: 30000 });
  const lb = { visibleMs: Date.now() - t };
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll(".pswp__img")].some(
        (i) => i.complete && i.naturalWidth > 0 && i.getBoundingClientRect().width > 100,
      ),
    null,
    { timeout: 60000, polling: 30 },
  );
  lb.firstImageMs = Date.now() - t;
  await page
    .waitForFunction(
      () =>
        [...document.querySelectorAll(".pswp__item:not([aria-hidden='true']) .pswp__img, .pswp__img")].some(
          (i) => /\/api\/preview/.test(i.currentSrc || i.src) && i.complete && i.naturalWidth > 0,
        ),
      null,
      { timeout: 60000, polling: 30 },
    )
    .catch(() => {});
  lb.previewMs = Date.now() - t;
  lb.clickINP = await page.evaluate(() => Math.max(0, ...window.__ev.map((e) => e[1])));
  lb.net = snap();
  lb.previewReqTimes = await page.evaluate(
    (c) =>
      performance
        .getEntriesByType("resource")
        .filter((e) => e.name.includes("/api/preview") && e.startTime > c)
        .map((e) => [
          Math.round(e.startTime - c),
          Math.round(e.duration),
          new URL(e.name).searchParams.get("path").split("/").pop(),
        ]),
    clickAt,
  );
  out.lightbox = lb;
  await page.waitForTimeout(2500);
  const nexts = [];
  const centered = () =>
    page.evaluate(() => {
      const imgs = [...document.querySelectorAll(".pswp__img")].filter((i) => {
        const r = i.getBoundingClientRect();
        return r.left < innerWidth / 2 && r.right > innerWidth / 2 && r.width > 100;
      });
      const i = imgs[imgs.length - 1];
      if (!i) return null;
      const u = new URL(i.currentSrc || i.src, location.href);
      return { path: u.searchParams.get("path"), kind: u.pathname, done: i.complete && i.naturalWidth > 0 };
    });
  for (let i = 0; i < 3; i++) {
    const before = (await centered())?.path;
    reqs.clear();
    t = Date.now();
    await page.keyboard.press("ArrowRight");
    let slideMs = null,
      previewMs = null;
    while (Date.now() - t < 20000) {
      const c = await centered();
      if (c && c.path !== before && c.done && slideMs === null) slideMs = Date.now() - t;
      if (c && c.path !== before && c.done && /preview/.test(c.kind)) {
        previewMs = Date.now() - t;
        break;
      }
      await page.waitForTimeout(15);
    }
    nexts.push({ slideMs, previewMs, ...snap() });
    await page.waitForTimeout(1500);
  }
  out.previewReqs = [...reqs.values()]
    .filter((r) => r.k === "preview")
    .map((r) => Math.round(((r.t1 || 0) - r.t0) * 1000));
  out.next = nexts;
  out.longtasksTotal = await page.evaluate(() => window.__lt.length);
  console.log(JSON.stringify(out));
  await browser.close();
})().catch((e) => {
  console.error("ERR", e.message);
  process.exit(1);
});
