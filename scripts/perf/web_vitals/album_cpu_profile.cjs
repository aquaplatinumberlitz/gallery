#!/usr/bin/env node
// CPU attribution of the album-open click and the lightbox click (Track M1).
//
// Purpose:
// Record one Chromium trace (timeline + the V8 sampling CPU profiler) around a real click and attribute the main-thread
// time of the long task(s) it caused to functions and to categories (JSON parse, TanStack Query, Vue, virtualizer,
// PhotoCard, PhotoSwipe, metadata panel, layout/style/paint). It answers "what is inside the 123 ms long task and the
// 128-160 ms click INP" so a change can be justified by evidence.
//
// Guarantees:
// * the trace is started after the page settled and stopped 1.5 s after the target (first photo card / lightbox) appears
// * network and CPU throttling match album_open_profile.cjs (4g = 85 ms, 9 Mbps, 4x CPU)
// * attribution is by self time of the sampled stack; categories are matched on function name and file name, so run it
//   against an UNMINIFIED build (`vite build --minify false --outDir DIR`) for readable names
// * output is one JSON object on stdout (tasks, categories, top functions, event timing); progress goes to stderr
//
// Usage:
//   BASE=https://127.0.0.1:8443 PROFILE=4g TARGET=album|lightbox ALBUM=real [MIN_TASK=45] [TOP=25] \
//     node scripts/perf/web_vitals/album_cpu_profile.cjs
// Env: BASE, PROFILE = 4g (default) | slow4g | desktop, TARGET = album (default) | lightbox, ALBUM (default real),
// MIN_TASK = shortest RunTask (ms) that is analysed (default 45), TOP = rows per table (default 25), OUT = write the raw
// trace events to this file.
//
// Run when:
// * before and after changing album-open or lightbox-open work (Track M)

const fs = require("fs");
const { loadChromium } = require("./lib.cjs");

const BASE = process.env.BASE || "http://127.0.0.1:8080";
const PROFILE = process.env.PROFILE || "4g";
const TARGET = process.env.TARGET || "album";
const ALBUM = process.env.ALBUM || "real";
const MIN_TASK = Number(process.env.MIN_TASK || 45) * 1000;
const TOP = Number(process.env.TOP || 25);
const NETS = { slow4g: { latency: 150, down: 1.6 }, "4g": { latency: 85, down: 9 }, desktop: null };
if (!(PROFILE in NETS)) throw new Error(`unknown PROFILE=${PROFILE} (4g|slow4g|desktop)`);
if (!["album", "lightbox"].includes(TARGET)) throw new Error(`unknown TARGET=${TARGET} (album|lightbox)`);
const mobile = PROFILE !== "desktop";

// First matching rule wins. Matched against "<functionName> <file>" of the sampled frame, innermost frame first, then
// outward through the callers, so a helper called from JSON-heavy code is still charged to the right bucket.
const CATEGORIES = [
  ["json-parse", /\bJSON\.parse\b|\bparse\b.*\(native\)|readAsJson|\.json\b|^\(?json\b/i],
  ["query-structural-sharing", /replaceData|replaceEqualDeep|structuralSharing|isPlainArray|isPlainObject/],
  ["query-other", /query-core|vue-query|QueryObserver|QueryClient|Mutation|notifyManager|infiniteQueryBehavior|fetchPage|hydrate|useBaseQuery|useInfiniteQuery|useQuery/],
  ["virtualizer", /virtual-core|vue-virtual|Virtualizer|getVirtualItems|measureElement|calculateRange|useVirtualizer|useVirtualGrid/],
  ["photo-swipe", /photoswipe|PhotoSwipe|\bPswp|pswp|usePhotoSwipe|lightbox/i],
  ["metadata-panel", /Metadata|metadata|LightboxMobileSheet|LightboxDesktopPanel|LightboxTabletPanel|VueSpringBottomSheet|bottom-sheet/],
  ["photo-card", /PhotoCard|useVisibleLoadGate|useRenderedWidth|useImageRetry|thumbnailSizes|ResizeObserver|IntersectionObserver/],
  ["gallery-grid", /GalleryGrid|useColumnResize|useVirtualGridMetrics|sortItems|compareNatural|natural/],
  ["vue-reactivity", /\bref\b|reactive|computed|ReactiveEffect|trigger|track|watch|effect|flushJobs|queueJob|flushPostFlushCbs|proxy|Dep\b|\bdep\b/],
  ["vue-render", /runtime-core|runtime-dom|\bpatch|mount|render|setupComponent|setupStatefulComponent|createVNode|h\(|diff|unmount|updateComponent|patchProp|patchElement|processElement|processComponent|resolveComponent|callWithErrorHandling|createApp/],
  ["router", /router|navigat|history/i],
  ["pinia-store", /pinia|defineStore|useGalleryStore|useLightboxStore/],
];

function categorize(stack) {
  // stack: array of "name file" strings from the sampled frame outward
  for (const frame of stack) {
    for (const [cat, re] of CATEGORIES) if (re.test(frame)) return cat;
  }
  return "other-js";
}

// Event Timing reports one entry per target for pointerenter/over; keep one row per (name, startTime).
function dedupeEvents(events) {
  const seen = new Map();
  for (const e of events) {
    const key = `${e.name}@${Math.round(e.start)}`;
    if (!seen.has(key)) seen.set(key, { ...e, startMs: Math.round(e.start), durMs: e.dur, inputDelayMs: +(e.procStart - e.start).toFixed(1), processingMs: +(e.procEnd - e.procStart).toFixed(1), presentationMs: +(e.start + e.dur - e.procEnd).toFixed(1) });
  }
  return [...seen.values()].map(({ name, startMs, durMs, inputDelayMs, processingMs, presentationMs, iid }) => ({ name, startMs, durMs, inputDelayMs, processingMs, presentationMs, iid }));
}

const short = (u) => (u ? u.split("/").pop().replace(/-[A-Za-z0-9_-]{8}\.js/, ".js") : "");

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
    window.__ev = [];
    window.__lt = [];
    new PerformanceObserver((l) => {
      for (const e of l.getEntries())
        window.__ev.push({
          name: e.name,
          start: e.startTime,
          dur: e.duration,
          procStart: e.processingStart,
          procEnd: e.processingEnd,
          iid: e.interactionId,
        });
    }).observe({ type: "event", buffered: true, durationThreshold: 16 });
    new PerformanceObserver((l) => {
      for (const e of l.getEntries()) window.__lt.push([e.startTime, e.duration]);
    }).observe({ type: "longtask", buffered: true });
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
  const albumCard = p.locator(`[data-testid="album-card"][data-album-name="${ALBUM}"]`).first();
  await albumCard.waitFor();
  await p.waitForTimeout(4000);
  if (TARGET === "lightbox") {
    await albumCard.click();
    await p.getByTestId("photo-card").first().waitFor();
    await p.waitForFunction(
      () => {
        const imgs = [...document.querySelectorAll('[data-testid="photo-card"] img')].filter((i) => {
          const r = i.getBoundingClientRect();
          return r.bottom > 40 && r.top < innerHeight - 40 && r.width > 0;
        });
        return imgs.length > 0 && imgs.every((i) => i.complete && i.naturalWidth > 0);
      },
      null,
      { timeout: 60000, polling: 50 },
    );
    await p.waitForTimeout(4000); // lazy lightbox chunk + idle warm-ups settle
  }
  await p.evaluate(() => {
    window.__ev.length = 0;
    window.__lt.length = 0;
  });

  const traceEvents = [];
  cdp.on("Tracing.dataCollected", (e) => traceEvents.push(...e.value));
  const done = new Promise((res) => cdp.once("Tracing.tracingComplete", res));
  await cdp.send("Tracing.start", {
    traceConfig: {
      recordMode: "recordContinuously",
      includedCategories: [
        "devtools.timeline",
        "disabled-by-default-devtools.timeline",
        "v8.execute",
        "disabled-by-default-v8.cpu_profiler",
      ],
      enableSampling: true,
    },
  });
  const c0 = await p.evaluate(() => performance.now());
  if (TARGET === "album") {
    await albumCard.click();
    await p.getByTestId("photo-card").first().waitFor();
  } else {
    await p.getByTestId("photo-card").nth(1).click();
    await p.getByTestId("lightbox").waitFor({ timeout: 30000 });
  }
  await p.waitForTimeout(1800);
  await cdp.send("Tracing.end");
  await done;
  const page = await p.evaluate(() => ({ ev: window.__ev, lt: window.__lt, now: performance.now() }));
  await b.close();
  if (process.env.OUT) fs.writeFileSync(process.env.OUT, JSON.stringify(traceEvents));

  // --- find the renderer main thread
  const meta = traceEvents.filter((e) => e.ph === "M" && e.name === "thread_name");
  const mainTids = meta.filter((e) => e.args.name === "CrRendererMain").map((e) => `${e.pid}:${e.tid}`);
  const onMain = (e) => mainTids.includes(`${e.pid}:${e.tid}`);
  const pickPid = (() => {
    // the page renderer is the one that produced the CPU profile
    const prof = traceEvents.find((e) => e.name === "Profile" && onMain(e));
    return prof ? `${prof.pid}:${prof.tid}` : mainTids[0];
  })();
  const mine = (e) => `${e.pid}:${e.tid}` === pickPid;
  const rendererPid = Number(pickPid.split(":")[0]);

  // --- CPU profile: nodes, samples, absolute times (us)
  const nodes = new Map();
  const samples = [];
  const pstart = {};
  for (const e of traceEvents) {
    if (e.name === "Profile" && e.pid === rendererPid) pstart[e.id] = e.args.data.startTime;
  }
  const chunks = traceEvents.filter((e) => e.name === "ProfileChunk" && e.pid === rendererPid);
  const clock = {};
  for (const ch of chunks) {
    const d = ch.args.data;
    const prof = d.cpuProfile || {};
    for (const nd of prof.nodes || []) nodes.set(nd.id, { ...nd, parentId: nd.parent });
    const sm = prof.samples || [];
    const td = d.timeDeltas || [];
    let t = clock[ch.id] ?? pstart[ch.id] ?? 0;
    for (let i = 0; i < sm.length; i++) {
      t += td[i] || 0;
      samples.push({ id: sm[i], t, dt: 0 });
    }
    clock[ch.id] = t;
  }
  for (const nd of nodes.values()) {
    if (nd.parentId !== undefined) nd.parentId = nd.parentId;
  }
  // parent links may be given as children lists
  for (const nd of nodes.values()) for (const c of nd.children || []) if (nodes.has(c)) nodes.get(c).parentId = nd.id;
  samples.sort((a, c) => a.t - c.t);
  for (let i = 0; i < samples.length - 1; i++) samples[i].dt = samples[i + 1].t - samples[i].t;

  const frameName = (nd) => {
    const cf = nd.callFrame || {};
    return `${cf.functionName || "(anonymous)"} ${short(cf.url)}:${cf.lineNumber ?? ""}`;
  };
  const stackOf = (id) => {
    const out = [];
    let nd = nodes.get(id);
    let guard = 0;
    while (nd && guard++ < 200) {
      out.push(frameName(nd));
      nd = nodes.get(nd.parentId);
    }
    return out; // innermost first
  };

  // --- tasks
  const tasks = traceEvents
    .filter((e) => e.name === "RunTask" && e.ph === "X" && mine(e) && e.dur >= MIN_TASK)
    .sort((a, c) => a.ts - c.ts);
  const report = { profile: PROFILE, target: TARGET, eventTiming: dedupeEvents(page.ev), longtasks: page.lt, tasks: [] };

  // Events (trace X events) nested inside a task, self time per name
  const xEvents = traceEvents.filter((e) => e.ph === "X" && mine(e) && e.name !== "RunTask");
  const timelineNames = new Set([
    "UpdateLayoutTree",
    "Layout",
    "PrePaint",
    "Paint",
    "Layerize",
    "Commit",
    "UpdateLayer",
    "HitTest",
    "MinorGC",
    "MajorGC",
    "V8.GC_MC_BACKGROUND_MARKING",
    "ParseHTML",
    "EvaluateScript",
    "v8.compile",
    "v8.run",
    "FunctionCall",
    "EventDispatch",
    "TimerFire",
    "FireAnimationFrame",
    "RunMicrotasks",
    "FireIdleCallback",
    "ResourceReceiveResponse",
    "ResourceFinish",
    "ImageDecodeTask",
    "XHRReadyStateChange",
    "ResourceSendRequest",
    "IntersectionObserverController::computeIntersections",
    "ResizeObserverController::deliverObservations",
    "UpdateLayoutTree.SelectorStats",
  ]);

  for (const task of tasks) {
    const t0 = task.ts;
    const t1 = task.ts + task.dur;
    const inWin = samples.filter((s) => s.t >= t0 && s.t < t1);
    const sumDt = inWin.reduce((a, s) => a + s.dt, 0);
    // trace events in window, self-time by name using an interval stack
    const evs = xEvents
      .filter((e) => e.ts >= t0 && e.ts + e.dur <= t1 + 50 && timelineNames.has(e.name))
      .sort((a, c) => a.ts - c.ts || c.dur - a.dur);
    const selfBy = {};
    const stack = [];
    for (const e of evs) {
      while (stack.length && stack[stack.length - 1].end <= e.ts) stack.pop();
      const parent = stack[stack.length - 1];
      selfBy[e.name] = (selfBy[e.name] || 0) + e.dur;
      if (parent) selfBy[parent.name] -= Math.min(parent.end, e.ts + e.dur) - e.ts;
      stack.push({ name: e.name, end: e.ts + e.dur });
    }
    const timeline = Object.entries(selfBy)
      .map(([name, us]) => [name, +(us / 1000).toFixed(1)])
      .filter(([, ms]) => ms > 0.4)
      .sort((a, c) => c[1] - a[1]);
    // JS self time per function and per category
    const selfFn = new Map();
    const cat = new Map();
    const incl = new Map();
    let jsUs = 0;
    for (const s of inWin) {
      const nd = nodes.get(s.id);
      if (!nd) continue;
      const fn = nd.callFrame.functionName;
      if (fn === "(idle)") continue;
      const stk = stackOf(s.id);
      const key = stk[0];
      selfFn.set(key, (selfFn.get(key) || 0) + s.dt);
      const isNative = fn === "(program)" || fn === "(garbage collector)" || fn === "(root)";
      const c = fn === "(garbage collector)" ? "gc" : fn === "(program)" ? "native-nonjs(layout/style/paint/parse)" : categorize(stk);
      cat.set(c, (cat.get(c) || 0) + s.dt);
      if (!isNative) jsUs += s.dt;
      for (const f of new Set(stk)) incl.set(f, (incl.get(f) || 0) + s.dt);
    }
    const toRows = (m, k = TOP) =>
      [...m.entries()]
        .sort((a, c) => c[1] - a[1])
        .slice(0, k)
        .map(([name, us]) => [name, +(us / 1000).toFixed(1)]);
    report.tasks.push({
      startMsAfterTraceClick: null,
      durMs: +(task.dur / 1000).toFixed(1),
      sampledMs: +(sumDt / 1000).toFixed(1),
      jsMs: +(jsUs / 1000).toFixed(1),
      timeline,
      categories: toRows(cat, 30),
      selfTop: toRows(selfFn),
      inclusiveTop: toRows(incl, TOP + 15),
      tsAbsUs: t0,
    });
  }
  const traceStart = tasks.length ? tasks[0].ts : 0;
  report.tasks.forEach((t) => (t.startMsAfterFirstTask = +((t.tsAbsUs - traceStart) / 1000).toFixed(1)));
  report.clickAtMs = +c0.toFixed(1);
  console.log(JSON.stringify(report, null, 1));
})().catch((e) => {
  console.error("ERR", e.message);
  process.exit(1);
});
