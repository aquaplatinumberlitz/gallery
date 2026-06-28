/**
 * Purpose:
 * Verifies Catalog Status copy, status states, popover content, and update actions.
 *
 * Guarantees:
 * * catalog status counts and labels remain user-facing and stable
 * * global metadata activity outside the current scope does not drive the primary status
 * * scan/rebuild controls call the library-scoped endpoints and refresh state
 *
 * Run when:
 * * changing IndexStatusPanel, catalog status API fields, or rebuild controls
 * * touching status copy, tooltips, popovers, or debug-only API traces
 */

import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-index-status-test";
const imagePaths = Array.from({ length: 2 }, (_, i) => `${rootPath}/image_${i + 1}.png`);
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64",
);

const stubLibrary = {
  id: 1,
  root_path: rootPath,
  import_paths: [{ id: 10, library_id: 1, path: rootPath, position: 0, created_at: 1, updated_at: 1 }],
  exclusion_patterns: [],
  name: "Test Library",
  state: "ready",
  watch_enabled: 1,
  warm_enabled: 1,
  asset_count: imagePaths.length,
  created_at: 1,
  updated_at: 1,
  last_scan_at: null,
  last_error: null,
};

function mediaRows(width = 1600, height = 1000) {
  return imagePaths.map((path, i) => ({
    name: `image_${i + 1}.png`,
    path,
    type: "image" as const,
    has_children: false,
    cover_images: [],
    mtime: 1000 + i,
    image_count: 0,
    width,
    height,
  }));
}

type StatusFixture = NonNullable<Parameters<typeof statusEnvelope>[0]>;

function defaultStatusFixture(): StatusFixture {
  return {
    libraryId: 1,
    path: rootPath,
    summaryState: "ready",
    totalAssets: 150,
    readyAssets: 150,
    lastScanAt: 1_782_036_040_000,
    lastIndexAt: 1_782_036_050_000,
  };
}

let statusFixture: StatusFixture = defaultStatusFixture();

function currentStatusEnvelope() {
  return statusEnvelope(statusFixture);
}

function scanJob(scopePath: string | null, operation: "scan" | "rebuild" = "scan") {
  return {
    library_id: 1,
    job_id: operation === "scan" ? 501 : 502,
    scope_path: scopePath,
    operation,
    trigger: "manual",
    state: "queued",
    coalesced: false,
  };
}

async function installStubbedGallery(
  page: Page,
  options: { failStatus?: boolean; delayStatus?: Promise<unknown> } = {},
) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();

    if (url.pathname === "/api/libraries") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([stubLibrary]),
      });
      return;
    }

    if (url.pathname === "/api/browse") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          browseResponse({
            libraryId: Number(url.searchParams.get("library_id") ?? 1),
            path: url.searchParams.get("path") ?? rootPath,
            media: mediaRows(),
          }),
        ),
      });
      return;
    }

    if (url.pathname === "/api/libraries/1/status") {
      if (options.failStatus) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: { error: "server_error", message: "Status failed" } }),
        });
        return;
      }
      if (options.delayStatus) await options.delayStatus;
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(currentStatusEnvelope()),
      });
      return;
    }

    if (url.pathname === "/api/libraries/1/scan" && method === "POST") {
      const body = route.request().postDataJSON() as { scope_path?: string } | null;
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify(scanJob(body?.scope_path ?? null, "scan")),
      });
      return;
    }

    if (url.pathname === "/api/metadata") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          tool: "stub",
          prompt: "stub prompt",
          negative_prompt: "",
          params: {},
          width: 1600,
          height: 1000,
          name: url.searchParams.get("path")?.split("/").pop() ?? "image.png",
        }),
      });
      return;
    }

    if (url.pathname === "/api/health") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      return;
    }

    if (url.pathname === "/api/landing-pages") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([]) });
      return;
    }

    if (url.pathname === "/api/search") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ albums: [], photos: [], prompts: [] }),
      });
      return;
    }

    if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
      await route.fulfill({ contentType: "image/png", body: png1x1 });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
}

async function openStubbedGallery(page: Page, withLibrary = true) {
  await page.addInitScript((enabled) => {
    localStorage.setItem("intro_mode", "disabled");
    if (enabled) {
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    }
  }, withLibrary);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  if (withLibrary) {
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
  }
}

async function openStatusPopover(page: Page) {
  const statusButton = page.getByLabel("Catalog Status");
  await expect(statusButton).toBeVisible({ timeout: 10_000 });
  await statusButton.click();
  const popover = page.getByRole("dialog").filter({ hasText: "Catalog" });
  await expect(popover).toBeVisible({ timeout: 5_000 });
  return popover;
}

test.describe("Catalog Status panel", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test.beforeEach(() => {
    statusFixture = defaultStatusFixture();
  });

  test("desktop load does not throw SidebarContext injection errors", async ({ page, monitoredErrors }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });
    expect(
      monitoredErrors.consoleErrors.some(
        (message) =>
          message.includes("SidebarContext") || message.includes("Injection `Symbol(SidebarContext)` not found"),
      ),
    ).toBe(false);
  });

  test("shows Unknown status when no library is selected", async ({ page }) => {
    await installStubbedGallery(page);
    await page.route("**/api/libraries**", async (route) => {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([]) });
    });

    await openStubbedGallery(page, false);
    const statusButton = page.getByLabel("Catalog Status");
    await expect(statusButton).toBeVisible({ timeout: 10_000 });
    await expect(statusButton).toContainText("Unknown");
  });

  test("shows catalog status details when path is set", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Catalog Status");
    await expect(statusButton).toContainText("Ready");
    await expect(statusButton).toContainText("150 photo details ready");
    await expect(statusButton).toContainText("Details");

    const popover = await openStatusPopover(page);
    await expect(popover).toContainText("Ready");
    await expect(popover).toContainText("Photo details ready");
    await expect(popover).toContainText("150");
    await expect(popover).toContainText("Location");
    await expect(popover).toContainText(rootPath);
    await expect(popover).toContainText("Including subfolders");
    await expect(popover).toContainText("Yes");
    await expect(popover.getByRole("button", { name: "Update current folder" })).toBeVisible();
    await expect(popover.getByRole("button", { name: "Scan" })).toHaveCount(0);
    await expect(popover.getByRole("button", { name: "Rebuild" })).toHaveCount(0);
  });

  test("catalog status shows loading state initially", async ({ page }) => {
    let resolveStatus: (value: unknown) => void = () => undefined;
    const delayedStatus = new Promise<unknown>((resolve) => {
      resolveStatus = resolve;
    });

    await installStubbedGallery(page, { delayStatus: delayedStatus });
    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Catalog Status");
    await statusButton.click();
    await expect(page.getByRole("dialog")).toContainText("Loading catalog status", { timeout: 5_000 });

    resolveStatus(null);
    await expect(page.getByRole("dialog")).toContainText("Photo details ready", { timeout: 5_000 });
  });

  test("catalog status shows error state when API fails", async ({ page }) => {
    await installStubbedGallery(page, { failStatus: true });
    await openStubbedGallery(page, true);

    const popover = await openStatusPopover(page);
    await expect(popover).toContainText(/Failed to load status|Status failed|Something went wrong/);
  });

  test("Update current folder calls the library scan endpoint", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const popover = await openStatusPopover(page);
    const scanPromise = page.waitForRequest((req) => new URL(req.url()).pathname === "/api/libraries/1/scan", {
      timeout: 5_000,
    });
    await popover.getByRole("button", { name: "Update current folder" }).click();
    const scanReq = await scanPromise;
    expect(scanReq.method()).toBe("POST");
    expect(scanReq.postDataJSON()).toMatchObject({ scope_path: rootPath });
  });

  test("collapsed desktop sidebar shows compact status button with dot", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const trigger = page.locator('[data-sidebar="trigger"]');
    await expect(trigger).toBeVisible({ timeout: 5_000 });
    await trigger.click();
    await expect(trigger).toHaveAttribute("aria-label", "Expand sidebar");

    const statusButton = page.getByLabel("Catalog Status");
    await expect(statusButton).toBeVisible({ timeout: 10_000 });
    await expect(statusButton.getByTestId("catalog-database-icon")).toBeVisible();

    const buttonBox = await statusButton.boundingBox();
    expect(buttonBox).not.toBeNull();
    expect(buttonBox!.width).toBeLessThanOrEqual(40);
    expect(buttonBox!.height).toBeLessThanOrEqual(40);

    const dot = statusButton.locator("span.relative span.absolute");
    await expect(dot).toBeAttached();
    await expect(dot).toHaveAttribute("aria-hidden", "true");
    await expect(dot).toHaveClass(/size-1\.5/);
    await expect(dot).toHaveClass(/rounded-full/);
    await expect(dot).toHaveClass(/(bg-green-500|bg-amber-500|bg-red-500|bg-gray-400)/);
  });

  test("global activity outside scope does not force current scope Updating", async ({ page }) => {
    Object.assign(statusFixture, {
      globalActiveOutsideScope: true,
      runtime: { metadata_active_jobs: 2, metadata_queue_depth: 3 },
    });

    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Catalog Status");
    await expect(statusButton).toContainText("Ready");
    await expect(statusButton).toContainText("Indexer working in another folder");
    await expect(statusButton).not.toContainText("Updating");

    const popover = await openStatusPopover(page);
    await expect(popover).toContainText("Indexer working in another folder");
    await expect(popover.getByTestId("index-progress-bar")).not.toBeVisible();
  });

  test("Needs update popover shows pending photo details", async ({ page }) => {
    Object.assign(statusFixture, {
      summaryState: "needs_update",
      totalAssets: 205,
      readyAssets: 200,
      staleAssets: 5,
      metadataState: "needs_update",
    });

    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Catalog Status");
    await expect(statusButton).toContainText("Needs update");
    await expect(statusButton).toContainText("5 photo details need updating");

    const popover = await openStatusPopover(page);
    await expect(popover).toContainText("Photos found");
    await expect(popover).toContainText("205");
    await expect(popover).toContainText("Photo details ready");
    await expect(popover).toContainText("200");
    await expect(popover).not.toContainText("200 / 205 photo details ready");
  });

  test("Updating popover shows compact progress", async ({ page }) => {
    Object.assign(statusFixture, {
      summaryState: "indexing",
      totalAssets: 522,
      readyAssets: 256,
      queuedAssets: 50,
      runningAssets: 1,
      metadataState: "indexing",
    });

    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Catalog Status");
    await expect(statusButton).toContainText("Updating");
    await expect(statusButton).toContainText("256 / 522 photo details ready");

    const popover = await openStatusPopover(page);
    await expect(popover).toContainText("Updating");
    await expect(popover).toContainText("Processing");
    await expect(popover).toContainText("49% details processed");
    await expect(popover.getByTestId("index-progress-bar")).toHaveCount(1);
  });

  test("error state with zero issue count shows catalog attention fallback", async ({ page }) => {
    Object.assign(statusFixture, {
      summaryState: "error",
      failedAssets: 0,
      issueCount: 0,
      latestIssue: { source: "scan", path: rootPath, message: "Connection refused", updated_at: 1_782_036_060_000 },
    });

    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Catalog Status");
    await expect(statusButton).toContainText("Catalog needs attention");

    const popover = await openStatusPopover(page);
    await expect(popover).toContainText("Error");
    await expect(popover).toContainText("Connection refused");
    await expect(popover).not.toContainText("0 items need attention");
  });

  test("offline state badge shows Offline not Warning", async ({ page }) => {
    Object.assign(statusFixture, {
      summaryState: "offline",
      availabilityState: "unavailable",
      availablePaths: 0,
      totalPaths: 1,
    });

    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Catalog Status");
    await expect(statusButton).toContainText("Offline");
    await expect(statusButton).not.toContainText("Warning");

    const badge = statusButton.getByTestId("index-status-badge");
    await expect(badge).toHaveClass(/index-status-badge--gray/);
    await expect(badge).not.toHaveClass(/index-status-badge--yellow/);
  });
});
