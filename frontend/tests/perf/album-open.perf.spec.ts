import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve, join, dirname as pathDirname } from "node:path";
import { compactStats, installApiNetworkTracker, waitForNetworkQuiet } from "./perf-utils";

const __filename = fileURLToPath(import.meta.url);
const __dirname = pathDirname(__filename);

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const albumName = process.env.GALLERY_PERF_ALBUM_NAME ?? "a1111";
const albumPath = process.env.GALLERY_PERF_ALBUM_PATH ?? "";
const scanBudgetMs = Number(process.env.GALLERY_PERF_SCAN_BUDGET_MS ?? "500");
const firstThumbBudgetMs = Number(process.env.GALLERY_PERF_FIRST_THUMB_BUDGET_MS ?? "1000");
const thumbP95BudgetMs = Number(process.env.GALLERY_PERF_THUMB_P95_BUDGET_MS ?? "1200");

function filterByAlbumPath(sample: { search: string }, path: string): boolean {
  if (!path) return true;
  const params = new URLSearchParams(sample.search);
  const samplePath = params.get("path") ?? "";
  return samplePath.startsWith(path);
}

function scanCursor(sample: { search: string }): string {
  const params = new URLSearchParams(sample.search);
  return params.get("image_cursor") ?? "0";
}

function scanLimit(sample: { search: string }): string {
  const params = new URLSearchParams(sample.search);
  return params.get("image_limit") ?? "";
}

test("album open performance", async ({ page }) => {
  const clickTime = { value: 0 };

  // Set gallery root path so albums appear on page load
  await page.addInitScript(() => {
    localStorage.setItem("gallery-root-path", "/home/ubuntu/gallery-repo/test-images");
    localStorage.setItem("gallery-sort-preference", JSON.stringify({ field: "name", order: "asc" }));
  });

  const tracker = installApiNetworkTracker(page, clickTime);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

  // Dismiss intro screen if visible (desktop shows intro)
  const enterBtn = page.getByRole("button", { name: /enter gallery/i });
  if (await enterBtn.isVisible().catch(() => false)) {
    await enterBtn.click();
    // Wait for gallery to load and render albums
    await page.waitForURL("**/");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
  }

  const album = page.getByText(albumName, { exact: false }).first();
  await expect(album).toBeVisible({ timeout: 15000 });

  tracker.clear();
  clickTime.value = Date.now();
  await album.click();

  await expect.poll(() => tracker.scanSamples().length, { timeout: 10_000 }).toBeGreaterThan(0);
  await waitForNetworkQuiet(page);

  const allScanSamples = tracker.scanSamples();
  const scanSamples = allScanSamples
    .filter((s) => filterByAlbumPath(s, albumPath))
    .sort((a, b) => a.startMs - b.startMs);
  const firstScan = scanSamples[0];

  const allThumbnailSamples = tracker.thumbnailSamples().filter((sample) => typeof sample.durationMs === "number");
  const thumbnailSamples = allThumbnailSamples.filter((s) => filterByAlbumPath(s, albumPath));
  const thumbnailDurations = thumbnailSamples.map((sample) => sample.durationMs ?? 0);
  const thumbnailStats = compactStats(thumbnailDurations);

  const firstThumbnailStart = thumbnailSamples.length
    ? Math.min(...thumbnailSamples.map((sample) => sample.startMs))
    : 0;
  const lastThumbnailEnd = thumbnailSamples.length
    ? Math.max(...thumbnailSamples.map((sample) => sample.endMs ?? 0))
    : 0;

  const duplicateCursor0Count = scanSamples.filter((s) => scanCursor(s) === "0").length;

  expect(firstScan).toBeTruthy();
  expect(firstScan.startMs).toBeGreaterThanOrEqual(0);
  expect(thumbnailSamples.length).toBeGreaterThan(0);
  if (albumPath) {
    const scanPath = new URLSearchParams(firstScan.search).get("path") ?? "";
    expect(scanPath).toBe(albumPath);
  }

  const firstScanDuration = firstScan?.durationMs ?? 0;

  const report = {
    albumName,
    albumPath,
    samplesIgnoredBeforeClick: 0,
    scan: {
      count: scanSamples.length,
      duplicateCursor0Count,
      startAfterClickMs: Math.round(firstScan?.startMs ?? 0),
      durationMs: Math.round(firstScanDuration),
      endAfterClickMs: Math.round(firstScan?.endMs ?? 0),
      path: new URLSearchParams(firstScan?.search ?? "").get("path") ?? "",
      cursor: scanCursor(firstScan!),
      limit: scanLimit(firstScan!),
    },
    thumbnails: {
      count: thumbnailSamples.length,
      firstStartAfterClickMs: Math.round(firstThumbnailStart),
      lastEndAfterClickMs: Math.round(lastThumbnailEnd),
      p50Ms: thumbnailStats.p50,
      p95Ms: thumbnailStats.p95,
      maxMs: thumbnailStats.max,
    },
    budgets: {
      scanBudgetMs,
      firstThumbBudgetMs,
      thumbP95BudgetMs,
    },
    verdict:
      firstScan &&
      firstScanDuration <= scanBudgetMs &&
      firstThumbnailStart <= firstThumbBudgetMs &&
      thumbnailStats.p95 <= thumbP95BudgetMs
        ? "pass"
        : "fail",
  };
  const resultsDir = resolve(__dirname, "../../test-results/perf");
  mkdirSync(resultsDir, { recursive: true });
  writeFileSync(join(resultsDir, "album-open-report.json"), JSON.stringify(report, null, 2));

  expect(duplicateCursor0Count).toBeLessThanOrEqual(1);
  expect(firstScanDuration).toBeLessThanOrEqual(scanBudgetMs);
  expect(firstThumbnailStart || Number.POSITIVE_INFINITY).toBeLessThanOrEqual(firstThumbBudgetMs);
  expect(thumbnailStats.p95).toBeLessThanOrEqual(thumbP95BudgetMs);
});
