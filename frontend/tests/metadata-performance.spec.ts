/**
 * Purpose:
 * Diagnostic performance measurement for the /metadata page.
 * Separates backend API time from frontend render/update time.
 * Measures whether search fires debounced or multiple requests.
 * Measures whether metadata page loads many thumbnails immediately.
 *
 * Guarantees:
 * - Timing separated into: click→URL, click→API request, API duration, API response→render, click→usable
 * - Network tracking for library inspector, thumbnails, index status
 * - Compact JSON report printed to console
 *
 * Run when:
 * - Diagnosing /metadata slowness
 * - Validating metadata page performance before release
 *
 * Run:
 *   cd frontend
 *   pnpm playwright test metadata-performance.spec.ts --headed
 */

import { expect, test } from "./helpers/monitorErrors";
import type { Page, Request } from "@playwright/test";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";

// ---------------------------------------------------------------------------
// Network tracker for metadata-specific endpoints
// ---------------------------------------------------------------------------

type MetadataSample = {
  url: string;
  pathname: string;
  search: string;
  startMs: number;
  endMs?: number;
  durationMs?: number;
  status?: number;
};

function installMetadataTracker(page: Page, clickTimeRef: { value: number }) {
  const samples: MetadataSample[] = [];
  const byRequest = new Map<Request, MetadataSample>();

  const trackedPaths = new Set([
    "/api/library/inspector",
    "/api/thumbnail",
    "/api/library/inspector/metadata",
    "/api/index/status",
  ]);

  page.on("request", (req) => {
    const url = new URL(req.url());
    if (!trackedPaths.has(url.pathname)) return;
    if (clickTimeRef.value <= 0) return;
    const sample: MetadataSample = {
      url: req.url(),
      pathname: url.pathname,
      search: url.search,
      startMs: performance.now() - clickTimeRef.value,
    };
    byRequest.set(req, sample);
    samples.push(sample);
  });

  page.on("response", async (res) => {
    const req = res.request();
    const sample = byRequest.get(req);
    if (!sample) return;
    await res.finished().catch(() => undefined);
    sample.endMs = performance.now() - clickTimeRef.value;
    sample.durationMs = sample.endMs - sample.startMs;
    sample.status = res.status();
  });

  const inspectorSamples = () => samples.filter((s) => s.pathname === "/api/library/inspector");
  const thumbnailSamples = () => samples.filter((s) => s.pathname === "/api/thumbnail");
  const metadataDetailSamples = () =>
    samples.filter((s) => s.pathname === "/api/library/inspector/metadata");
  const indexStatusSamples = () => samples.filter((s) => s.pathname === "/api/index/status");

  const clear = () => {
    samples.length = 0;
    byRequest.clear();
  };

  return { samples, inspectorSamples, thumbnailSamples, metadataDetailSamples, indexStatusSamples, clear };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timestamp() {
  return performance.now();
}

/**
 * Resolves once a table row appears in the tbody.
 * Times out at 15 s.
 */
async function waitForFirstRow(page: Page) {
  await expect(page.locator("tbody > tr").first()).toBeVisible({ timeout: 15_000 });
}

/**
 * Resolves once the table body contains at least `min` rows.
 * Times out at 15 s.
 */
async function waitForRowCount(page: Page, min: number) {
  await expect.poll(
    () => page.locator("tbody > tr").count(),
    { timeout: 15_000 }
  ).toBeGreaterThanOrEqual(min);
}

/**
 * Navigate to gallery root, skip intro if visible, and wait for the gallery
 * grid (main heading) to become visible.
 */
async function openGallery(page: Page) {
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  const enterBtn = page.getByRole("button", { name: /enter gallery/i });
  if (await enterBtn.isVisible().catch(() => false)) {
    await enterBtn.click();
    await page.waitForURL("**/");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
  }
  await expect(page.getByRole("heading", { name: /museum art gallery/i })).toBeVisible({
    timeout: 15_000,
  });
}

// ---------------------------------------------------------------------------
// Scenarios
// ---------------------------------------------------------------------------

test.describe("Metadata performance", () => {
  test.use({ viewport: { width: 1366, height: 900 } });

  test("Gallery → Metadata navigation timing", async ({ page }) => {
    const clickTime = { value: 0 };
    const tracker = installMetadataTracker(page, clickTime);

    await openGallery(page);

    // Clear network samples from gallery load
    tracker.clear();

    const metaButton = page.getByRole("link", { name: /metadata/i });
    await expect(metaButton).toBeVisible();

    clickTime.value = timestamp();
    const clickWallMs = clickTime.value;
    await metaButton.click();

    // ---- measure URL arrival ----
    await page.waitForURL("**/metadata");
    const urlMs = timestamp() - clickWallMs;

    // ---- capture the first inspector request ----
    let firstInspector = tracker.inspectorSamples()[0];
    // If not yet arrived, poll briefly
    if (!firstInspector) {
      await expect
        .poll(() => tracker.inspectorSamples().length, { timeout: 10_000 })
        .toBeGreaterThanOrEqual(1);
      firstInspector = tracker.inspectorSamples()[0];
    }

    // ---- wait for first row (means API returned + Vue rendered) ----
    await waitForFirstRow(page);
    const firstRowMs = timestamp() - clickWallMs;

    // ---- collect remaining samples ----
    // Let lazy thumbnails start loading
    await page.waitForTimeout(500);

    const inspectorSamples = tracker.inspectorSamples();
    const firstApi = inspectorSamples[0];
    const apiDurationMs = firstApi?.durationMs ?? -1;
    const requestStartMs = firstApi?.startMs ?? -1;
    const apiResponseToFirstRowMs = requestStartMs >= 0 ? firstRowMs - (requestStartMs + apiDurationMs) : -1;

    const thumbnailSamples = tracker.thumbnailSamples();
    const rowCount = await page.locator("tbody > tr").count();

    const indexStatusSamples = tracker.indexStatusSamples();
    const metadataDetailSamples = tracker.metadataDetailSamples();

    const report = {
      metadataNavigation: {
        clickToUrlMs: Math.round(urlMs),
        clickToInspectorRequestStartMs: Math.round(requestStartMs),
        apiDurationMs: Math.round(apiDurationMs),
        apiResponseToFirstRowMs: Math.round(apiResponseToFirstRowMs),
        clickToTableReadyMs: Math.round(firstRowMs),
        renderedRows: rowCount,
        thumbnailRequests: thumbnailSamples.length,
        indexStatusRequests: indexStatusSamples.length,
        metadataDetailRequests: metadataDetailSamples.length,
        inspectorRequests: inspectorSamples.length,
        inspectorDetail: firstApi
          ? {
              query: new URLSearchParams(firstApi.search).get("q") ?? "",
              limit: new URLSearchParams(firstApi.search).get("limit") ?? "",
              sort: new URLSearchParams(firstApi.search).get("sort") ?? "",
            }
          : null,
      },
    };

    console.log(JSON.stringify(report, null, 2));

    // Diagnostic assertions only (no budgets)
    expect(urlMs).toBeGreaterThan(0);
    expect(apiDurationMs).toBeGreaterThan(0);
    expect(rowCount).toBeGreaterThan(0);
  });

  test("Metadata sort timing", async ({ page }) => {
    const clickTime = { value: 0 };
    const tracker = installMetadataTracker(page, clickTime);

    // Navigate directly to /metadata
    await page.goto(`${baseUrl}/metadata`, { waitUntil: "domcontentloaded" });
    await waitForFirstRow(page);
    await page.waitForTimeout(200);

    const initialRowCount = await page.locator("tbody > tr").count();
    const firstCellBefore = await page.locator("tbody tr").first().locator("td").first().textContent();

    tracker.clear();
    clickTime.value = timestamp();
    const sortWallMs = clickTime.value;

    // Click the sort dropdown trigger
    const sortBtn = page.getByRole("combobox", { name: /sort metadata table/i });
    await sortBtn.click();
    // Pick "Name A-Z" to toggle sort direction
    const nameAsc = page.getByRole("option", { name: /name.*a[-–]z/i });
    await expect(nameAsc).toBeVisible({ timeout: 3_000 });
    await nameAsc.click();
    const clickDoneMs = timestamp();

    // Wait for inspector API to fire
    await expect
      .poll(() => tracker.inspectorSamples().length, { timeout: 10_000 })
      .toBeGreaterThanOrEqual(1);

    // Wait for the table rows to update (content changes indicate re-render)
    await expect
      .poll(
        () => page.locator("tbody tr").first().locator("td").first().textContent(),
        { timeout: 15_000 }
      )
      .not.toBe(firstCellBefore);

    const tableUpdatedMs = timestamp() - sortWallMs;

    const inspectorSamples = tracker.inspectorSamples();
    const apiSample = inspectorSamples[0];
    const apiDurationMs = apiSample?.durationMs ?? -1;
    const requestStartMs = apiSample?.startMs ?? -1;
    const apiResponseToUpdateMs =
      requestStartMs >= 0 && apiDurationMs >= 0
        ? tableUpdatedMs - (requestStartMs + apiDurationMs)
        : -1;

    const rowCount = await page.locator("tbody > tr").count();

    const report = {
      sort: {
        sortActionMs: Math.round(clickDoneMs - sortWallMs),
        clickToRequestStartMs: Math.round(requestStartMs),
        apiDurationMs: Math.round(apiDurationMs),
        apiResponseToUpdateMs: Math.round(apiResponseToUpdateMs),
        totalMs: Math.round(tableUpdatedMs),
        renderedRows: rowCount,
        previousRowCount: initialRowCount,
        tableClearedDuringLoad: initialRowCount !== rowCount,
      },
    };

    console.log(JSON.stringify(report, null, 2));

    expect(apiDurationMs).toBeGreaterThan(0);
    expect(rowCount).toBeGreaterThan(0);
  });

  test("Metadata search timing", async ({ page }) => {
    const clickTime = { value: 0 };
    const tracker = installMetadataTracker(page, clickTime);

    // Navigate directly to /metadata
    await page.goto(`${baseUrl}/metadata`, { waitUntil: "domcontentloaded" });
    await waitForFirstRow(page);
    const initialRowCount = await page.locator("tbody > tr").count();

    tracker.clear();

    const searchInput = page.getByLabel("Search metadata table");
    await expect(searchInput).toBeVisible();

    clickTime.value = timestamp();
    const searchWallMs = clickTime.value;

    // Simulate typing character by character (this exercises debounce)
    const searchTerm = "blue forest";
    for (const char of searchTerm) {
      await searchInput.press(char);
      // Small delay to mimic human typing (~50ms between chars)
      await page.waitForTimeout(50);
    }
    const typingDoneMs = timestamp();

    // Give time for debounce + API
    await page.waitForTimeout(400);

    // Count all inspector requests fired during typing
    const allRequestsDuringTyping = tracker.inspectorSamples().length;

    // Wait for the table to stabilize (less rows = filtered results)
    await expect
      .poll(() => page.locator("tbody > tr").count(), { timeout: 15_000 })
      .not.toBe(initialRowCount);

    const tableUpdatedMs = timestamp() - searchWallMs;

    const inspectorSamples = tracker.inspectorSamples();
    const lastApi = inspectorSamples.length ? inspectorSamples[inspectorSamples.length - 1] : null;
    const apiDurationMs = lastApi?.durationMs ?? -1;
    const requestStartMs = lastApi?.startMs ?? -1;
    const apiResponseToUpdateMs =
      requestStartMs >= 0 && apiDurationMs >= 0
        ? tableUpdatedMs - (requestStartMs + apiDurationMs)
        : -1;

    const rowCount = await page.locator("tbody > tr").count();
    const queryInLastRequest = lastApi
      ? new URLSearchParams(lastApi.search).get("q") ?? ""
      : "";

    // Determine if backend got the full query (debounced) or intermediate
    const gotFullQuery = queryInLastRequest.trim() === searchTerm;

    const report = {
      search: {
        typingDurationMs: Math.round(typingDoneMs - searchWallMs),
        requestsWhileTyping: allRequestsDuringTyping,
        gotFullQueryInLastRequest: gotFullQuery,
        queryInLastRequest,
        finalApiDurationMs: Math.round(apiDurationMs),
        finalRequestStartMs: Math.round(requestStartMs),
        finalResponseToUpdateMs: Math.round(apiResponseToUpdateMs),
        totalMs: Math.round(tableUpdatedMs),
        renderedRows: rowCount,
        previousRowCount: initialRowCount,
      },
    };

    console.log(JSON.stringify(report, null, 2));

    // Diagnostic: search should fire at most a few requests (debounced)
    // Not asserting a hard count — this is diagnostic output
    expect(apiDurationMs).toBeGreaterThan(0);
    expect(gotFullQuery).toBe(true);
  });

  test("Metadata state restores after gallery round trip", async ({ page }) => {
    await page.goto(`${baseUrl}/metadata`, { waitUntil: "domcontentloaded" });
    await waitForFirstRow(page);

    const sortBtn = page.getByRole("combobox", { name: /sort metadata table/i });
    await sortBtn.click();
    await page.getByRole("option", { name: /name.*a[-–]z/i }).click();
    await expect(sortBtn).toContainText(/Name A[-–]Z/);

    const tableShell = page.locator(".metadata-table-shell");
    await tableShell.evaluate((el) => {
      el.scrollTop = 420;
      el.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    await expect.poll(() => tableShell.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);

    await page.getByRole("link", { name: /^gallery$/i }).click();
    await page.waitForURL("**/");
    await page.getByRole("link", { name: /metadata/i }).click();
    await page.waitForURL("**/metadata");
    await waitForFirstRow(page);

    await expect(page.getByRole("combobox", { name: /sort metadata table/i })).toContainText(/Name A[-–]Z/);
    await expect.poll(() => page.locator(".metadata-table-shell").evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  });
});
