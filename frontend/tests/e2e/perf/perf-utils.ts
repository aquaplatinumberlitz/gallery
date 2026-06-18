import type { Page, Request, Response } from "@playwright/test";

export type NetworkSample = {
  url: string;
  pathname: string;
  search: string;
  startMs: number;
  endMs?: number;
  durationMs?: number;
  status?: number;
};

export function percentile(values: number[], pct: number): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.max(0, Math.min(sorted.length - 1, Math.ceil((pct / 100) * sorted.length) - 1));
  return sorted[index];
}

export function compactStats(values: number[]) {
  return {
    p50: Math.round(percentile(values, 50)),
    p95: Math.round(percentile(values, 95)),
    max: Math.round(values.length ? Math.max(...values) : 0),
  };
}

export function installApiNetworkTracker(page: Page, clickTimeRef: { value: number }) {
  const samples: NetworkSample[] = [];
  const byRequest = new Map<Request, NetworkSample>();

  const shouldTrack = (request: Request) => {
    const url = new URL(request.url());
    return (
      url.pathname === "/api/scan" ||
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
      startMs: Date.now() - clickTimeRef.value,
    };
    byRequest.set(request, sample);
    samples.push(sample);
  });

  const finish = async (response: Response) => {
    const request = response.request();
    const sample = byRequest.get(request);
    if (!sample) return;
    await response.finished().catch(() => undefined);
    sample.endMs = Date.now() - clickTimeRef.value;
    sample.durationMs = sample.endMs - sample.startMs;
    sample.status = response.status();
  };

  page.on("response", (response) => {
    void finish(response);
  });

  return {
    samples,
    scanSamples: () => samples.filter((sample) => sample.pathname === "/api/scan"),
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
  let lastActivity = Date.now();
  const mark = () => {
    lastActivity = Date.now();
  };

  page.on("request", mark);
  page.on("response", mark);
  page.on("requestfailed", mark);

  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (Date.now() - lastActivity >= idleMs) return;
    await page.waitForTimeout(100);
  }
}
