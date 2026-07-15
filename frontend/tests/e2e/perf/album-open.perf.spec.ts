/**
 * Purpose:
 * Measures album open scan and thumbnail timing against configurable performance budgets.
 *
 * Guarantees:
 * * album navigation records scan and thumbnail timing after the user click
 * * JSON perf output is written for budget comparison and trend review
 * * multi-sample (5 iterations) with p95 reporting instead of single measurement
 * * uses performance.now() (monotonic, sub-ms) for all timing — never Date.now()
 *
 * Run when:
 * * changing scan pagination, album navigation, thumbnail loading, or performance budgets
 * * validating real-data album open performance before release
 */

import { fileURLToPath } from "node:url";
import { expect, test } from "../helpers/monitorErrors";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve, join, dirname as pathDirname } from "node:path";
import {
  compactStats,
  installApiNetworkTracker,
  loadBudgets,
  networkContractViolations,
  nowMs,
  resolvePerfResultsDir,
  waitForNetworkQuiet,
} from "./perf-utils";

const __filename = fileURLToPath(import.meta.url);
const __dirname = pathDirname(__filename);

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const albumName = process.env.GALLERY_PERF_ALBUM_NAME ?? "a1111";
const albumPath = process.env.GALLERY_PERF_ALBUM_PATH ?? "";

const SAMPLE_COUNT = Number(process.env.GALLERY_PERF_ALBUM_SAMPLES ?? "5");
const budgets = loadBudgets();
const perfE2EEnabled =
  process.env.GALLERY_PERF_E2E === "1" ||
  process.env.GALLERY_PERF_USE_FIXTURE === "1" ||
  Boolean(process.env.GALLERY_PERF_ALBUM_PATH);

test.skip(
  !perfE2EEnabled,
  "Set GALLERY_PERF_E2E=1 with a real gallery backend or fixture to run album-open performance diagnostics.",
);

function filterByAlbumPath(sample: { search: string }, path: string): boolean {
  if (!path) return true;
  const params = new URLSearchParams(sample.search);
  const samplePath = params.get("path") ?? "";
  return samplePath.startsWith(path);
}

function scanCursor(sample: { search: string }): string {
  const params = new URLSearchParams(sample.search);
  return params.get("cursor") ?? "0";
}

function scanLimit(sample: { search: string }): string {
  const params = new URLSearchParams(sample.search);
  return params.get("limit") ?? "";
}

type IterationResult = {
  scanDurationMs: number;
  scanStartMs: number;
  firstThumbnailStartMs: number;
  lastThumbnailEndMs: number;
  thumbnailCount: number;
  thumbnailP95Ms: number;
  thumbnailP50Ms: number;
  thumbnailMaxMs: number;
  duplicateCursor0Count: number;
  scanPath: string;
  scanCursor: string;
  scanLimit: string;
  networkContractViolations: string[];
};

async function runOneIteration(page: import("@playwright/test").Page): Promise<IterationResult> {
  const clickTime = { value: 0 };

  await page.addInitScript(() => {
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
    localStorage.setItem("gallery-sort-preference", JSON.stringify({ field: "name", order: "asc" }));
  });

  const tracker = installApiNetworkTracker(page, clickTime);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

  const enterBtn = page.getByRole("button", { name: /enter gallery/i });
  const album = page.getByText(albumName, { exact: false }).first();
  await expect
    .poll(async () => (await enterBtn.isVisible().catch(() => false)) || (await album.isVisible().catch(() => false)), {
      timeout: 15000,
    })
    .toBe(true);

  if (await enterBtn.isVisible().catch(() => false)) {
    await enterBtn.click();
    await expect(album).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(1000);
  }

  await expect(album).toBeVisible({ timeout: 15000 });

  tracker.clear();
  clickTime.value = nowMs();
  await album.click();

  await expect.poll(() => tracker.scanSamples().length, { timeout: 10_000 }).toBeGreaterThan(0);
  await waitForNetworkQuiet(page);
  await tracker.waitForSettled({ paths: ["/api/browse", "/api/thumbnail"], minimum: 2 });

  const allScanSamples = tracker.scanSamples();
  const scanSamples = allScanSamples
    .filter((s) => filterByAlbumPath(s, albumPath))
    .sort((a, b) => a.startMs - b.startMs);
  const firstScan = scanSamples[0];

  const allThumbnailSamples = tracker.thumbnailSamples();
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

  const contractViolations = [
    ...networkContractViolations(scanSamples, { minimum: 1, allowedStatuses: [200] }),
    ...networkContractViolations(thumbnailSamples, { minimum: 1, allowedStatuses: [200, 304] }),
  ];
  tracker.dispose();

  return {
    scanDurationMs: Math.round(firstScan?.durationMs ?? 0),
    scanStartMs: Math.round(firstScan?.startMs ?? 0),
    firstThumbnailStartMs: Math.round(firstThumbnailStart),
    lastThumbnailEndMs: Math.round(lastThumbnailEnd),
    thumbnailCount: thumbnailSamples.length,
    thumbnailP50Ms: thumbnailStats.p50,
    thumbnailP95Ms: thumbnailStats.p95,
    thumbnailMaxMs: thumbnailStats.max,
    duplicateCursor0Count,
    scanPath: new URLSearchParams(firstScan?.search ?? "").get("path") ?? "",
    scanCursor: scanCursor(firstScan!),
    scanLimit: scanLimit(firstScan!),
    networkContractViolations: contractViolations,
  };
}

test("album open performance", async ({ page }) => {
  const results: IterationResult[] = [];
  for (let i = 0; i < SAMPLE_COUNT; i++) {
    // Fresh page context per iteration so each measurement is independent.
    if (i > 0) {
      await page.context().clearCookies();
    }
    const result = await runOneIteration(page);
    results.push(result);
    if (i < SAMPLE_COUNT - 1) {
      // Brief cooldown between iterations to let backend settle.
      await page.waitForTimeout(500);
    }
  }

  const scanDurations = results.map((r) => r.scanDurationMs);
  const firstThumbStarts = results.map((r) => r.firstThumbnailStartMs);
  const coldThumbnailP95 = results[0]?.thumbnailP95Ms ?? 0;
  const warmResults = results.length > 1 ? results.slice(1) : results;
  const warmBatchDurations = warmResults.map((result) =>
    Math.max(0, result.lastThumbnailEndMs - result.firstThumbnailStartMs),
  );
  const duplicateCursor0Counts = results.map((r) => r.duplicateCursor0Count);

  // p95 across iterations (single measurement per iteration => p95 ≈ max for
  // small N, but we keep the percentile call so the formula scales with SAMPLE_COUNT).
  const scanP95 = Math.round(compactStats(scanDurations).p95);
  const firstThumbP95 = Math.round(compactStats(firstThumbStarts).p95);
  const warmBatchCompleteP95 = Math.round(compactStats(warmBatchDurations).p95);
  const maxDuplicateCursor0 = Math.max(...duplicateCursor0Counts);
  const contractViolations = results.flatMap((result, index) =>
    result.networkContractViolations.map((violation) => `iteration ${index + 1}: ${violation}`),
  );

  const report = {
    albumName,
    albumPath,
    sampleCount: results.length,
    iterations: results,
    aggregate: {
      scanP95Ms: scanP95,
      firstThumbnailStartP95Ms: firstThumbP95,
      coldThumbnailP95Ms: coldThumbnailP95,
      warmThumbnailBatchCompleteP95Ms: warmBatchCompleteP95,
      maxDuplicateCursor0Count: maxDuplicateCursor0,
      networkContractViolations: contractViolations,
    },
    budgets: budgets.album_open,
    budgetSource: "frontend/tests/e2e/perf/perf-budgets.json[album_open]",
    verdict:
      scanP95 <= budgets.album_open.scan_p95_ms &&
      firstThumbP95 <= budgets.album_open.first_thumbnail_ms &&
      warmBatchCompleteP95 <= budgets.album_open.warm_batch_complete_ms &&
      maxDuplicateCursor0 <= 1 &&
      contractViolations.length === 0
        ? "pass"
        : "fail",
  };
  const resultsDir = resolvePerfResultsDir(resolve(__dirname, "../../../test-results/perf"));
  mkdirSync(resultsDir, { recursive: true });
  writeFileSync(join(resultsDir, "album-open-report.json"), JSON.stringify(report, null, 2));

  expect(maxDuplicateCursor0).toBeLessThanOrEqual(1);
  expect(contractViolations).toEqual([]);
  expect(scanP95).toBeLessThanOrEqual(budgets.album_open.scan_p95_ms);
  expect(firstThumbP95 || Number.POSITIVE_INFINITY).toBeLessThanOrEqual(budgets.album_open.first_thumbnail_ms);
  expect(warmBatchCompleteP95).toBeLessThanOrEqual(budgets.album_open.warm_batch_complete_ms);
});
