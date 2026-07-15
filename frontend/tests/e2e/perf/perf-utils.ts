import type { Page, Request, Response } from "@playwright/test";
import { resolve } from "node:path";
import { perfBudgets } from "./perf-budgets";

export type NetworkSample = {
  url: string;
  pathname: string;
  search: string;
  startMs: number;
  endMs?: number;
  durationMs?: number;
  status?: number;
  failure?: string;
  settled: boolean;
  serverQueueWaitMs?: number;
  serverRenderEncodePersistMs?: number;
};

export type NetworkContractOptions = {
  minimum?: number;
  allowedStatuses?: number[];
};

export function networkContractViolations(samples: NetworkSample[], options: NetworkContractOptions = {}): string[] {
  const minimum = options.minimum ?? 0;
  const allowedStatuses = new Set(options.allowedStatuses ?? [200, 304]);
  const violations: string[] = [];
  if (samples.length < minimum) {
    violations.push(`expected at least ${minimum} tracked requests, observed ${samples.length}`);
  }
  for (const sample of samples) {
    if (sample.failure) {
      violations.push(`${sample.pathname}${sample.search} failed: ${sample.failure}`);
    }
    if (!sample.settled || sample.durationMs === undefined || sample.endMs === undefined) {
      violations.push(`${sample.pathname}${sample.search} did not produce a complete timing sample`);
    }
    if (sample.status === undefined) {
      violations.push(`${sample.pathname}${sample.search} did not produce an HTTP status`);
    } else if (!allowedStatuses.has(sample.status)) {
      violations.push(`${sample.pathname}${sample.search} returned unexpected HTTP ${sample.status}`);
    }
  }
  return violations;
}

export function resolvePerfResultsDir(fallback: string): string {
  return resolve(process.env.GALLERY_PERF_RESULTS_DIR || fallback);
}

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
  album_open: { scan_p95_ms: number; first_thumbnail_ms: number; warm_batch_complete_ms: number };
  lightbox: { open_ms: number; transition_ms: number; visual_ready_ms: number };
  metadata_nav: {
    api_ms: number;
    nav_ms: number;
    render_ms: number;
    rendered_rows_max: number;
    sort_ms: number;
    search_debounce_ms: number;
    search_requests_max: number;
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
      warm_batch_complete_ms: Number(
        env.GALLERY_PERF_THUMB_BATCH_BUDGET_MS ??
          env.GALLERY_PERF_THUMB_P95_BUDGET_MS ??
          albumOpen.warm_batch_complete_ms,
      ),
    },
    lightbox: {
      open_ms: Number(env.GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS ?? lightbox.open_ms),
      transition_ms: Number(env.GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS ?? lightbox.transition_ms),
      visual_ready_ms: Number(
        env.GALLERY_PERF_LIGHTBOX_VISUAL_READY_BUDGET_MS ??
          env.GALLERY_PERF_LIGHTBOX_PREVIEW_BUDGET_MS ??
          lightbox.visual_ready_ms,
      ),
    },
    metadata_nav: {
      api_ms: Number(env.GALLERY_PERF_METADATA_API_BUDGET_MS ?? metadataNav.api_ms),
      nav_ms: Number(
        env.GALLERY_PERF_METADATA_TABLE_READY_BUDGET_MS ??
          env.GALLERY_PERF_METADATA_NAV_BUDGET_MS ??
          metadataNav.nav_ms,
      ),
      render_ms: Number(
        env.GALLERY_PERF_METADATA_RESPONSE_RENDER_BUDGET_MS ??
          env.GALLERY_PERF_METADATA_RENDER_BUDGET_MS ??
          metadataNav.render_ms,
      ),
      rendered_rows_max: Number(env.GALLERY_PERF_METADATA_RENDERED_ROWS_MAX ?? metadataNav.rendered_rows_max),
      sort_ms: Number(env.GALLERY_PERF_METADATA_SORT_TOTAL_BUDGET_MS ?? metadataNav.sort_ms),
      search_debounce_ms: Number(
        env.GALLERY_PERF_METADATA_SEARCH_TOTAL_BUDGET_MS ??
          env.GALLERY_PERF_METADATA_SEARCH_DEBOUNCE_BUDGET_MS ??
          metadataNav.search_debounce_ms,
      ),
      search_requests_max: Number(env.GALLERY_PERF_METADATA_SEARCH_REQUESTS_MAX ?? metadataNav.search_requests_max),
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

  const onRequest = (request: Request) => {
    if (!shouldTrack(request)) return;
    if (clickTimeRef.value <= 0) return; // ignore pre-click network
    const url = new URL(request.url());
    const sample: NetworkSample = {
      url: request.url(),
      pathname: url.pathname,
      search: url.search,
      startMs: nowMs() - clickTimeRef.value,
      settled: false,
    };
    byRequest.set(request, sample);
    samples.push(sample);
  };

  const finish = async (response: Response) => {
    const request = response.request();
    const sample = byRequest.get(request);
    if (!sample) return;
    const finishError = await response.finished().then(
      () => "",
      (error: unknown) => (error instanceof Error ? error.message : String(error)),
    );
    sample.endMs = nowMs() - clickTimeRef.value;
    sample.durationMs = sample.endMs - sample.startMs;
    sample.status = response.status();
    if (finishError) sample.failure = finishError;
    const serverTiming = (await response.headerValue("server-timing").catch(() => null)) ?? "";
    const timingValues = Object.fromEntries(
      serverTiming.split(",").map((entry) => {
        const [name, ...parameters] = entry.trim().split(";");
        const duration = parameters.find((parameter) => parameter.startsWith("dur="))?.slice(4);
        return [name, Number(duration ?? 0)];
      }),
    );
    sample.serverQueueWaitMs = timingValues.queue ?? 0;
    sample.serverRenderEncodePersistMs = timingValues.derivative ?? 0;
    sample.settled = true;
  };

  const onResponse = (response: Response) => {
    void finish(response);
  };
  const onRequestFailed = (request: Request) => {
    const sample = byRequest.get(request);
    if (!sample) return;
    sample.endMs = nowMs() - clickTimeRef.value;
    sample.durationMs = sample.endMs - sample.startMs;
    sample.failure = request.failure()?.errorText ?? "request failed";
    sample.settled = true;
  };

  page.on("request", onRequest);
  page.on("response", onResponse);
  page.on("requestfailed", onRequestFailed);

  return {
    samples,
    scanSamples: () => samples.filter((sample) => sample.pathname === "/api/browse"),
    thumbnailSamples: () => samples.filter((sample) => sample.pathname === "/api/thumbnail"),
    previewSamples: () => samples.filter((sample) => sample.pathname === "/api/preview"),
    imageSamples: () => samples.filter((sample) => sample.pathname === "/api/image"),
    metadataSamples: () => samples.filter((sample) => sample.pathname === "/api/metadata"),
    async waitForSettled(options: { paths?: string[]; minimum?: number; timeoutMs?: number } = {}) {
      const paths = new Set(options.paths ?? []);
      const minimum = options.minimum ?? 0;
      const timeoutMs = options.timeoutMs ?? 15_000;
      const started = nowMs();
      while (nowMs() - started < timeoutMs) {
        const selected = paths.size ? samples.filter((sample) => paths.has(sample.pathname)) : samples;
        if (selected.length >= minimum && selected.every((sample) => sample.settled)) return selected;
        await page.waitForTimeout(25);
      }
      return paths.size ? samples.filter((sample) => paths.has(sample.pathname)) : samples;
    },
    clear() {
      samples.length = 0;
      byRequest.clear();
    },
    dispose() {
      page.off("request", onRequest);
      page.off("response", onResponse);
      page.off("requestfailed", onRequestFailed);
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

  try {
    const started = nowMs();
    while (nowMs() - started < timeoutMs) {
      if (nowMs() - lastActivity >= idleMs) return;
      await page.waitForTimeout(100);
    }
  } finally {
    page.off("request", mark);
    page.off("response", mark);
    page.off("requestfailed", mark);
  }
}
