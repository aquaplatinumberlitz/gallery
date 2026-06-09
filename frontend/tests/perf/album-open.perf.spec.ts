import { expect, test } from "@playwright/test";
import { compactStats, installApiNetworkTracker, waitForNetworkQuiet } from "./perf-utils";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const albumName = process.env.GALLERY_PERF_ALBUM_NAME ?? "test mika";
const scanBudgetMs = Number(process.env.GALLERY_PERF_SCAN_BUDGET_MS ?? "500");
const firstThumbBudgetMs = Number(process.env.GALLERY_PERF_FIRST_THUMB_BUDGET_MS ?? "1000");
const thumbP95BudgetMs = Number(process.env.GALLERY_PERF_THUMB_P95_BUDGET_MS ?? "1200");

test("album open performance", async ({ page }) => {
  const clickTime = { value: 0 };
  const tracker = installApiNetworkTracker(page, clickTime);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

  const album = page
    .getByTestId("album-card")
    .filter({ has: page.locator(".album-name", { hasText: albumName }) })
    .first();
  await expect(album).toBeVisible();

  clickTime.value = Date.now();
  await album.click();

  await expect.poll(() => tracker.scanSamples().length, { timeout: 10_000 }).toBeGreaterThan(0);
  await waitForNetworkQuiet(page);

  const scanSamples = tracker.scanSamples();
  const thumbnailSamples = tracker.thumbnailSamples().filter((sample) => typeof sample.durationMs === "number");
  const firstScan = scanSamples[0];
  const firstScanDuration = firstScan?.durationMs ?? 0;
  const firstThumbnailStart = thumbnailSamples.length
    ? Math.min(...thumbnailSamples.map((sample) => sample.startMs))
    : 0;
  const lastThumbnailEnd = thumbnailSamples.length
    ? Math.max(...thumbnailSamples.map((sample) => sample.endMs ?? 0))
    : 0;
  const thumbnailDurations = thumbnailSamples.map((sample) => sample.durationMs ?? 0);
  const thumbnailStats = compactStats(thumbnailDurations);
  const duplicateScanCursor0Count = scanSamples.filter((sample) => {
    const params = new URLSearchParams(sample.search);
    return (params.get("image_cursor") ?? "0") === "0";
  }).length;

  const report = {
    albumName,
    clickTimeEpochMs: clickTime.value,
    scanStartAfterClickMs: Math.round(firstScan?.startMs ?? 0),
    scanDurationMs: Math.round(firstScanDuration),
    scanEndAfterClickMs: Math.round(firstScan?.endMs ?? 0),
    firstThumbnailStartAfterClickMs: Math.round(firstThumbnailStart),
    lastThumbnailEndAfterClickMs: Math.round(lastThumbnailEnd),
    thumbnailCount: thumbnailSamples.length,
    thumbnailP50Ms: thumbnailStats.p50,
    thumbnailP95Ms: thumbnailStats.p95,
    thumbnailMaxMs: thumbnailStats.max,
    duplicateScanCursor0Count,
    budgets: {
      scanMs: scanBudgetMs,
      firstThumbnailStartMs: firstThumbBudgetMs,
      thumbnailP95Ms: thumbP95BudgetMs,
    },
  };
  console.log(JSON.stringify(report, null, 2));

  expect(duplicateScanCursor0Count).toBeLessThanOrEqual(1);
  expect(firstScanDuration).toBeLessThanOrEqual(scanBudgetMs);
  expect(firstThumbnailStart || Number.POSITIVE_INFINITY).toBeLessThanOrEqual(firstThumbBudgetMs);
  expect(thumbnailStats.p95).toBeLessThanOrEqual(thumbP95BudgetMs);
});
