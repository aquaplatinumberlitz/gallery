import type { Page, Request, Response } from "@playwright/test";
import { perfBudgets } from "./perf-budgets";

export type NetworkSample = {
  url: string;
  pathname: string;
  search: string;
  startMs: number;
  endMs?: number;
  durationMs?: number;
  status?: number;
  serverQueueWaitMs?: number;
  serverRenderEncodePersistMs?: number;
};

export function percentile(values: number[], pct: number): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  if (sorted.length === 1) return sorted[0];
  // Linear-interpolation percentile, matches scripts/perf_lib.percentile.
  const k = (pct / 100) * (sorted.length - 1);
  const floor = Math.floor(k);
  const ceil = Math.ceil(k);
  if (floor === ceil) return sorted[k];
  const lower = sorted[floor] * (ceil - k);
  const upper = sorted[ceil] * (k - floor);
  return lower + upper;
}

export function compactStats(values: number[]) {
  return {
    p50: Math.round(percentile(values, 50)),
    p95: Math.round(percentile(values, 95)),
    max: Math.round(values.length ? Math.max(...values) : 0),
  };
}

/**
 * Monotonic clock helper. `performance.now()` is sub-millisecond and is not
 * affected by system-clock adjustments (NTP, manual changes), which makes it
 * strictly better than `Date.now()` for perf timing. We fall back to
 * `Date.now()` only in jsdom unit-test environments where `performance.now()`
 * may not be polyfilled identically.
 */
export function nowMs(): number {
  return typeof performance !== "undefined" && typeof performance.now === "function" ? performance.now() : Date.now();
}

export type BudgetSource = {
  album_open: { scan_p95_ms: number; first_thumbnail_ms: number; thumbnail_p95_ms: number };
  lightbox: { open_ms: number; transition_ms: number; preview_check_ms: number };
  metadata_nav: {
    nav_ms: number;
    render_ms: number;
    search_debounce_ms: number;
    state_restore_ms: number;
  };
};

/**
 * Read the shared perf budgets. Defaults come from `perf-budgets.json` (which
 * mirrors `scripts/perf_budgets.toml`). Env vars still win so CI matrices can
 * override a single budget without editing the JSON.
 */
export function loadBudgets(env: NodeJS.ProcessEnv = process.env): BudgetSource {
  const albumOpen = perfBudgets.album_open;
  const lightbox = perfBudgets.lightbox;
  const metadataNav = perfBudgets.metadata_nav;
  return {
    album_open: {
      scan_p95_ms: Number(env.GALLERY_PERF_SCAN_BUDGET_MS ?? albumOpen.scan_p95_ms),
      first_thumbnail_ms: Number(env.GALLERY_PERF_FIRST_THUMB_BUDGET_MS ?? albumOpen.first_thumbnail_ms),
      thumbnail_p95_ms: Number(env.GALLERY_PERF_THUMB_P95_BUDGET_MS ?? albumOpen.thumbnail_p95_ms),
    },
    lightbox: {
      open_ms: Number(env.GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS ?? lightbox.open_ms),
      transition_ms: Number(env.GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS ?? lightbox.transition_ms),
      preview_check_ms: Number(env.GALLERY_PERF_LIGHTBOX_PREVIEW_BUDGET_MS ?? lightbox.preview_check_ms),
    },
    metadata_nav: {
      nav_ms: Number(env.GALLERY_PERF_METADATA_NAV_BUDGET_MS ?? metadataNav.nav_ms),
      render_ms: Number(env.GALLERY_PERF_METADATA_RENDER_BUDGET_MS ?? metadataNav.render_ms),
      search_debounce_ms: Number(env.GALLERY_PERF_METADATA_SEARCH_DEBOUNCE_BUDGET_MS ?? metadataNav.search_debounce_ms),
      state_restore_ms: Number(env.GALLERY_PERF_METADATA_STATE_RESTORE_BUDGET_MS ?? metadataNav.state_restore_ms),
    },
  };
}

export function installApiNetworkTracker(page: Page, clickTimeRef: { value: number }) {
  const samples: NetworkSample[] = [];
  const byRequest = new Map<Request, NetworkSample>();

  const shouldTrack = (request: Request) => {
    const url = new URL(request.url());
    return (
      url.pathname === "/api/browse" ||
      url.pathname === "/api/thumbnail" ||
      url.pathname === "/api/preview" ||
      url.pathname === "/api/image" ||
      url.pathname === "/api/metadata"
    );
  };

  page.on("request", (request) => {
    if (!shouldTrack(request)) return;
    if (clickTimeRef.value <= 0) return; // ignore pre-click network
    const url = new URL(request.url());
    const sample: NetworkSample = {
      url: request.url(),
      pathname: url.pathname,
      search: url.search,
      startMs: nowMs() - clickTimeRef.value,
    };
    byRequest.set(request, sample);
    samples.push(sample);
  });

  const finish = async (response: Response) => {
    const request = response.request();
    const sample = byRequest.get(request);
    if (!sample) return;
    await response.finished().catch(() => undefined);
    sample.endMs = nowMs() - clickTimeRef.value;
    sample.durationMs = sample.endMs - sample.startMs;
    sample.status = response.status();
    const serverTiming = (await response.headerValue("server-timing")) ?? "";
    const timingValues = Object.fromEntries(
      serverTiming.split(",").map((entry) => {
        const [name, ...parameters] = entry.trim().split(";");
        const duration = parameters.find((parameter) => parameter.startsWith("dur="))?.slice(4);
        return [name, Number(duration ?? 0)];
      }),
    );
    sample.serverQueueWaitMs = timingValues.queue ?? 0;
    sample.serverRenderEncodePersistMs = timingValues.derivative ?? 0;
  };

  page.on("response", (response) => {
    void finish(response);
  });

  return {
    samples,
    scanSamples: () => samples.filter((sample) => sample.pathname === "/api/browse"),
    thumbnailSamples: () => samples.filter((sample) => sample.pathname === "/api/thumbnail"),
    previewSamples: () => samples.filter((sample) => sample.pathname === "/api/preview"),
    imageSamples: () => samples.filter((sample) => sample.pathname === "/api/image"),
    metadataSamples: () => samples.filter((sample) => sample.pathname === "/api/metadata"),
    clear() {
      samples.length = 0;
      byRequest.clear();
    },
  };
}

export function getQueryParam(search: string, name: string): string {
  return new URLSearchParams(search).get(name) ?? "";
}

export async function waitForNetworkQuiet(page: Page, idleMs = 750, timeoutMs = 15_000) {
  let lastActivity = nowMs();
  const mark = () => {
    lastActivity = nowMs();
  };

  page.on("request", mark);
  page.on("response", mark);
  page.on("requestfailed", mark);

  const started = nowMs();
  while (nowMs() - started < timeoutMs) {
    if (nowMs() - lastActivity >= idleMs) return;
    await page.waitForTimeout(100);
  }
}
