/**
 * Purpose:
 * Verifies IndexStatusPanel copy, status states, popover content, and rebuild actions.
 *
 * Guarantees:
 * * index status counts and labels remain user-facing and stable
 * * rebuild/rescan controls call the expected endpoints and refresh state
 *
 * Run when:
 * * changing IndexStatusPanel, index status API fields, or rebuild controls
 * * touching status copy, tooltips, popovers, or debug-only API traces
 */

import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-index-status-test";
const imagePaths = Array.from(
  { length: 2 },
  (_, i) => `${rootPath}/image_${i + 1}.png`
);
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64"
);

const indexStatusData = {
  enabled: true,
  worker_count: 2,
  active_jobs: 0,
  runtime_queue_depth: 0,
  done: 150,
  running: 0,
  queued: 0,
  failed: 0,
  stale: 0,
  skipped: 0,
  total: 150,
  indexed_photos: 150,
  metadata_records: 150,
  path: rootPath,
  counts: { done: 150 },
  oldest_queued_age_seconds: null,
  last_error: null,
  updated_at: 1000000000,
  coalesced_duplicates: 0,
  staged_path_queue_depth: 0,
  staged_path_coalesced: 0,
  staged_path_failed: 0,
  staged_path_flushes_forced: 0,
  staged_path_worker_count: 1,
  active_scan_requests: 0,
  batch_size: 100,
  staged_path_batch_size: 50,
  stage_max_wait_seconds: 30,
};

async function installStubbedGallery(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());

    if (url.pathname === "/api/scan") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          folders: [],
          images: imagePaths.map((path, i) => ({
            name: `image_${i + 1}.png`,
            path,
            type: "image",
            has_children: false,
            cover_images: [],
            mtime: 1000 + i,
            image_count: 0,
            width: 1600,
            height: 1000,
          })),
          next_cursor: null,
          total_images: imagePaths.length,
          index_source: "direct_scan",
        }),
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
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ status: "ok" }),
      });
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

    if (url.pathname === "/api/index/status") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(indexStatusData),
      });
      return;
    }

    if (url.pathname === "/api/index/rebuild") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          path: url.searchParams.get("path"),
          cleared: {
            file_index_fts: 0,
            file_index: 0,
            image_metadata: 0,
            metadata_index_jobs: 0,
            folder_index_state: 0,
          },
          rebuild_started: true,
        }),
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

async function openStubbedGallery(page: Page, withPath = true) {
  await page.addInitScript((opts) => {
    localStorage.setItem("intro_mode", "disabled");
    if (opts) {
      localStorage.setItem("gallery-root-path", opts);
    }
  }, withPath ? rootPath : "");

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
}

test.describe("IndexStatusPanel", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("desktop load does not throw SidebarContext injection errors", async ({ page, monitoredErrors }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });
    expect(
      monitoredErrors.consoleErrors.some((message) =>
        message.includes("SidebarContext") || message.includes("Injection `Symbol(SidebarContext)` not found")
      )
    ).toBe(false);
  });

  test("shows Unknown status when no root path is set", async ({ page }) => {
    await installStubbedGallery(page);

    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
    });
    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByLabel("Index Status")).toBeVisible({ timeout: 10_000 });

    const statusButton = page.getByLabel("Index Status");
    await expect(statusButton).toBeVisible();

    await expect(statusButton).toContainText("Unknown");
  });

  test("shows index status details when path is set", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Index Status");
    await expect(statusButton).toBeVisible();

    await expect(statusButton).toContainText("Ready");
    await expect(statusButton).toContainText("150 photos ready");
    await expect(statusButton).toContainText("Details");

    await statusButton.click();
    const popover = page.getByRole("dialog", { name: "Index Status" });
    await expect(popover).toBeVisible({ timeout: 5_000 });

    // Summary fields visible by default
    await expect(popover).toContainText("Status");
    await expect(popover).toContainText("Ready");
    await expect(popover).toContainText("Photo details ready");
    await expect(popover).toContainText("150");
    await expect(popover).toContainText("Folder");
    await expect(popover).toContainText(rootPath);
    await expect(popover).toContainText("Including subfolders");
    await expect(popover).toContainText("Yes");
    await expect(popover.getByRole("button", { name: "Rescan" })).toBeVisible();
    await expect(popover.getByRole("button", { name: "Rebuild" })).toBeVisible();
    await expect(popover).toContainText("Rebuild clears this folder's index and extracted metadata cache before indexing again. Source image files are not deleted.");
    await expect(popover).not.toContainText("Clear cache");
    await expect(popover).not.toContainText("Clear DB");
    await expect(popover).not.toContainText("Clear index");
    await expect(popover).not.toContainText("Reset DB");
    await expect(popover).not.toContainText("Reset");
  });

  test("popover content is not empty when opened", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Index Status");
    await expect(statusButton).toBeVisible();
    await statusButton.click();

    const popover = page.getByRole("dialog", { name: "Index Status" });
    await expect(popover).toBeVisible({ timeout: 5_000 });

    await page.waitForTimeout(300);

    const textContent = await popover.textContent();
    expect(textContent.trim().length).toBeGreaterThan(0);

    const isVisible = await popover.isVisible();
    expect(isVisible).toBe(true);

    const boundingBox = await popover.boundingBox();
    expect(boundingBox).not.toBeNull();
    expect(boundingBox!.width).toBeGreaterThan(0);
    expect(boundingBox!.height).toBeGreaterThan(0);
  });

  test("index status shows loading state initially", async ({ page }) => {
    let resolveStatus: (value: unknown) => void;
    const statusPromise = new Promise<unknown>((resolve) => {
      resolveStatus = resolve;
    });

    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());

      if (url.pathname === "/api/index/status") {
        await statusPromise.then(() =>
          route.fulfill({
            contentType: "application/json",
            body: JSON.stringify(indexStatusData),
          })
        );
        return;
      }

      if (url.pathname === "/api/scan") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            folders: [],
            images: imagePaths.map((path, i) => ({
              name: `image_${i + 1}.png`,
              path,
              type: "image",
              has_children: false,
              cover_images: [],
              mtime: 1000 + i,
              image_count: 0,
              width: 1600,
              height: 1000,
            })),
            next_cursor: null,
            total_images: imagePaths.length,
            index_source: "direct_scan",
          }),
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
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({ status: "ok" }),
        });
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

    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Index Status");
    await statusButton.click();

    await expect(page.getByRole("dialog", { name: "Index Status" })).toBeVisible({ timeout: 5_000 });
    await expect(page.getByRole("dialog", { name: "Index Status" })).toContainText("Loading index status");

    resolveStatus!(null);
    await page.waitForTimeout(500);

    await expect(page.getByRole("dialog", { name: "Index Status" })).toContainText("Photo details ready", { timeout: 5_000 });
  });

  test("index status shows error state when API fails", async ({ page }) => {
    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());

      if (url.pathname === "/api/index/status") {
        await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "Internal Server Error" }) });
        return;
      }

      if (url.pathname === "/api/scan") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            folders: [],
            images: imagePaths.map((path, i) => ({
              name: `image_${i + 1}.png`,
              path,
              type: "image",
              has_children: false,
              cover_images: [],
              mtime: 1000 + i,
              image_count: 0,
              width: 1600,
              height: 1000,
            })),
            next_cursor: null,
            total_images: imagePaths.length,
            index_source: "direct_scan",
          }),
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
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({ status: "ok" }),
        });
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

    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Index Status");
    await statusButton.click();

    const popover = page.getByRole("dialog", { name: "Index Status" });
    await expect(popover).toBeVisible({ timeout: 5_000 });
    await expect(popover).toContainText(/Failed to load status|Error|Something went wrong/);
  });

  test("Rescan calls /api/scan", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Index Status");
    await statusButton.click();
    const popover = page.getByRole("dialog", { name: "Index Status" });
    await expect(popover).toBeVisible({ timeout: 5_000 });

    const scanPromise = page.waitForRequest(
      (req) => new URL(req.url()).pathname === "/api/scan",
      { timeout: 5_000 }
    );
    await popover.getByRole("button", { name: "Rescan" }).click();
    const scanReq = await scanPromise;
    expect(scanReq.method()).toBe("GET");
  });

  test("Rebuild index shows confirmation dialog and calls /api/index/rebuild after confirm", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Index Status");
    await statusButton.click();
    const popover = page.getByRole("dialog", { name: "Index Status" });
    await expect(popover).toBeVisible({ timeout: 5_000 });

    const rebuildButton = popover.getByRole("button", { name: "Rebuild" });

    // Opening the dialog should not call the API yet.
    await rebuildButton.click();
    const dialog = page.getByRole("dialog", { name: "Rebuild?" });
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    await expect(dialog).toContainText("Rebuild?");
    await expect(dialog).toContainText(
      "Rebuild clears this folder's index and extracted metadata cache before indexing again. Source image files are not deleted."
    );

    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).not.toBeVisible();

    // Confirming should issue the rebuild request.
    await rebuildButton.click();
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    const rebuildPromise = page.waitForRequest(
      (req) => new URL(req.url()).pathname === "/api/index/rebuild",
      { timeout: 5_000 }
    );
    await dialog.getByRole("button", { name: "Rebuild" }).click();
    const rebuildReq = await rebuildPromise;
    expect(rebuildReq.method()).toBe("POST");
    const rebuildUrl = new URL(rebuildReq.url());
    expect(rebuildUrl.searchParams.get("confirm")).toBe("true");
  });

  test("card variant shows Database icon near Index title", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const dbIcon = page.locator(".index-status-card .index-status-card__title .lucide-database");
    await expect(dbIcon).toBeVisible({ timeout: 5_000 });
    await expect(dbIcon).toHaveClass(/lucide-database/);
  });

  test("collapsed desktop sidebar shows compact status button with dot", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const trigger = page.locator('[data-sidebar="trigger"]');
    await expect(trigger).toBeVisible({ timeout: 5_000 });
    await trigger.click();
    await expect(trigger).toHaveAttribute("aria-label", "Expand sidebar");

    const sidebarContainer = page.locator('[data-sidebar="sidebar"]');
    const statusButton = page.getByLabel("Index Status");
    await expect(statusButton).toBeVisible({ timeout: 10_000 });
    await expect(statusButton.locator(".lucide-database")).toBeVisible();

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

    const footer = page.locator('[data-sidebar="footer"]');
    await expect(footer).toBeVisible();
    const sidebarBox = await sidebarContainer.boundingBox();
    const footerBox = await footer.boundingBox();
    expect(sidebarBox).not.toBeNull();
    expect(footerBox).not.toBeNull();
    expect(footerBox!.width).toBeLessThanOrEqual(sidebarBox!.width + 1);
  });

  test("collapsed desktop index button opens details popover", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const trigger = page.locator('[data-sidebar="trigger"]');
    await expect(trigger).toBeVisible({ timeout: 5_000 });
    await trigger.click();
    await expect(trigger).toHaveAttribute("aria-label", "Expand sidebar");

    const statusButton = page.getByLabel("Index Status");
    await expect(statusButton).toBeVisible({ timeout: 10_000 });
    await statusButton.click();

    const popover = page.getByRole("dialog", { name: "Index Status" });
    await expect(popover).toBeVisible({ timeout: 5_000 });
    await expect(popover).toContainText("150 photos ready");
  });

  test("details popover does not overflow with long root path", async ({ page }) => {
    const longRootPath = "/home/ubuntu/gallery-repo/test-images/comfyui/some/very/long/path/that/should/overflow";
    const prev = { ...indexStatusData };

    try {
      Object.assign(indexStatusData, { path: longRootPath });

      await installStubbedGallery(page);
      await openStubbedGallery(page, true);

      const statusButton = page.getByLabel("Index Status");
      await statusButton.click();

      const popover = page.getByRole("dialog", { name: "Index Status" });
      await expect(popover).toBeVisible({ timeout: 5_000 });
      await expect(popover).toContainText("Folder");

      const rootValue = popover.locator("strong[title]");
      await expect(rootValue).toHaveAttribute("title", longRootPath);

      const box = await popover.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x + box!.width).toBeLessThanOrEqual(1280);
      expect(box!.y + box!.height).toBeLessThanOrEqual(900);
    } finally {
      Object.assign(indexStatusData, prev);
    }
  });

  test("mobile viewport preserves button variant", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });

    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Index Status");
    await expect(statusButton).toBeVisible({ timeout: 10_000 });
    await statusButton.click();

    const popover = page.getByRole("dialog", { name: "Index Status" });
    await expect(popover).toBeVisible({ timeout: 5_000 });
    await expect(popover).toContainText("150 photos ready");
  });

  test("collapsed Ready popover shows clean count without fraction when all records ready", async ({ page }) => {
    const prev = { ...indexStatusData };

    try {
      Object.assign(indexStatusData, {
        indexed_photos: 205,
        metadata_records: 205,
        done: 205,
        total: 205,
        stale: 0,
        failed: 0,
        staged_path_failed: 0,
      });

      await installStubbedGallery(page);
      await openStubbedGallery(page, true);

      const trigger = page.locator('[data-sidebar="trigger"]');
      await trigger.click();
      await expect(trigger).toHaveAttribute("aria-label", "Expand sidebar");

      const statusButton = page.getByLabel("Index Status");
      await statusButton.click();
      const popover = page.getByRole("dialog", { name: "Index Status" });
      await expect(popover).toBeVisible({ timeout: 5_000 });

      await expect(popover).toContainText("205 photos ready");
      await expect(popover).not.toContainText("205 / 205 photos ready");
      await expect(popover).not.toContainText("Processing");

      await expect(popover.locator(".index-progress-bar")).not.toBeVisible();
    } finally {
      Object.assign(indexStatusData, prev);
    }
  });

  test("collapsed Needs update popover shows X photos need update when stale > 0", async ({ page }) => {
    const prev = { ...indexStatusData };

    try {
      Object.assign(indexStatusData, {
        indexed_photos: 205,
        metadata_records: 200,
        done: 200,
        total: 205,
        stale: 5,
      });

      await installStubbedGallery(page);
      await openStubbedGallery(page, true);

      const trigger = page.locator('[data-sidebar="trigger"]');
      await trigger.click();
      await expect(trigger).toHaveAttribute("aria-label", "Expand sidebar");

      const statusButton = page.getByLabel("Index Status");
      await statusButton.click();
      const popover = page.getByRole("dialog", { name: "Index Status" });
      await expect(popover).toBeVisible({ timeout: 5_000 });

      await expect(popover).toContainText("5 photos need update");
      await expect(popover).not.toContainText("200 / 205 photos ready");
    } finally {
      Object.assign(indexStatusData, prev);
    }
  });

  test("collapsed Updating popover shows compact header with one progress bar in Processing", async ({ page }) => {
    const prev = { ...indexStatusData };

    try {
      Object.assign(indexStatusData, {
        indexed_photos: 522,
        metadata_records: 200,
        done: 256,
        total: 522,
        queued: 50,
        running: 1,
        stale: 0,
        failed: 0,
      });

      await installStubbedGallery(page);
      await openStubbedGallery(page, true);

      const trigger = page.locator('[data-sidebar="trigger"]');
      await trigger.click();
      await expect(trigger).toHaveAttribute("aria-label", "Expand sidebar");

      const statusButton = page.getByLabel("Index Status");
      await statusButton.click();
      const popover = page.getByRole("dialog", { name: "Index Status" });
      await expect(popover).toBeVisible({ timeout: 5_000 });

      await expect(popover).toContainText("Updating");
      await expect(popover).toContainText("Updating photo details");

      await popover.getByRole("button", { name: "Details" }).click();

      await expect(popover).toContainText("Processing");
      await expect(popover).toContainText("256 / 522 details processed");

      const barCount = await popover.locator(".index-progress-bar").count();
      expect(barCount).toBe(1);
    } finally {
      Object.assign(indexStatusData, prev);
    }
  });

  test("stale badge label shows Needs update not Stale", async ({ page }) => {
    const prev = { ...indexStatusData };

    try {
      Object.assign(indexStatusData, {
        indexed_photos: 205,
        metadata_records: 200,
        stale: 5,
        done: 200,
        total: 205,
      });

      await installStubbedGallery(page);
      await openStubbedGallery(page, true);

      const statusButton = page.getByLabel("Index Status");
      await expect(statusButton).toBeVisible({ timeout: 10_000 });
      await expect(statusButton).toContainText("Needs update");
      await expect(statusButton).not.toContainText("Stale");
    } finally {
      Object.assign(indexStatusData, prev);
    }
  });

  test("error state with zero issues shows Index needs attention fallback", async ({ page }) => {
    const prev = { ...indexStatusData };

    try {
      Object.assign(indexStatusData, {
        failed: 0,
        staged_path_failed: 0,
        last_error: {
          message: "Connection refused",
          updated_at: 1000000000,
        },
      });

      await installStubbedGallery(page);
      await openStubbedGallery(page, true);

      const trigger = page.locator('[data-sidebar="trigger"]');
      await trigger.click();
      await expect(trigger).toHaveAttribute("aria-label", "Expand sidebar");

      const statusButton = page.getByLabel("Index Status");
      await statusButton.click();
      const popover = page.getByRole("dialog", { name: "Index Status" });
      await expect(popover).toBeVisible({ timeout: 5_000 });

      await expect(popover).toContainText("Index needs attention");
      await expect(popover).not.toContainText("0 items need attention");
    } finally {
      Object.assign(indexStatusData, prev);
    }
  });

  test("unavailable state badge shows Unavailable not Warning", async ({ page }) => {
    const prev = { ...indexStatusData };

    try {
      Object.assign(indexStatusData, {
        enabled: false,
        stale: 0,
        failed: 0,
        last_error: null,
      });

      await installStubbedGallery(page);
      await openStubbedGallery(page, true);

      const statusButton = page.getByLabel("Index Status");
      await expect(statusButton).toBeVisible({ timeout: 10_000 });
      await expect(statusButton).toContainText("Unavailable");
      await expect(statusButton).not.toContainText("Warning");
    } finally {
      Object.assign(indexStatusData, prev);
    }
  });

  test("partial Ready (no stale, metadata < indexed) shows fraction summary", async ({ page }) => {
    const prev = { ...indexStatusData };

    try {
      Object.assign(indexStatusData, {
        indexed_photos: 205,
        metadata_records: 200,
        done: 200,
        total: 205,
        stale: 0,
        failed: 0,
      });

      await installStubbedGallery(page);
      await openStubbedGallery(page, true);

      const trigger = page.locator('[data-sidebar="trigger"]');
      await trigger.click();
      await expect(trigger).toHaveAttribute("aria-label", "Expand sidebar");

      const statusButton = page.getByLabel("Index Status");
      await statusButton.click();
      const popover = page.getByRole("dialog", { name: "Index Status" });
      await expect(popover).toBeVisible({ timeout: 5_000 });

      await expect(popover).toContainText("200 / 205 photos ready");
    } finally {
      Object.assign(indexStatusData, prev);
    }
  });

  test("collapsed Updating progress bar uses shared index-progress-bar", async ({ page }) => {
    const prev = { ...indexStatusData };

    try {
      Object.assign(indexStatusData, {
        indexed_photos: 522,
        metadata_records: 200,
        done: 256,
        total: 522,
        queued: 50,
        running: 1,
        stale: 0,
        failed: 0,
      });

      await installStubbedGallery(page);
      await openStubbedGallery(page, true);

      const trigger = page.locator('[data-sidebar="trigger"]');
      await trigger.click();
      await expect(trigger).toHaveAttribute("aria-label", "Expand sidebar");

      const statusButton = page.getByLabel("Index Status");
      await statusButton.click();
      const popover = page.getByRole("dialog", { name: "Index Status" });
      await expect(popover).toBeVisible({ timeout: 5_000 });

      await popover.getByRole("button", { name: "Details" }).click();
      await expect(popover).toContainText("Processing");

      const bar = popover.locator(".index-progress-bar");
      await expect(bar).toBeVisible();
      const fill = bar.locator(".index-progress-bar__fill");
      await expect(fill).toBeVisible();
    } finally {
      Object.assign(indexStatusData, prev);
    }
  });

  test("expanded card Updating progress bar uses shared index-progress-bar", async ({ page }) => {
    const prev = { ...indexStatusData };

    try {
      Object.assign(indexStatusData, {
        indexed_photos: 522,
        metadata_records: 200,
        done: 256,
        total: 522,
        queued: 50,
        running: 1,
        stale: 0,
        failed: 0,
      });

      await installStubbedGallery(page);
      await openStubbedGallery(page, true);

      const card = page.locator(".index-status-card");
      await expect(card).toBeVisible({ timeout: 10_000 });

      const bar = card.locator(".index-progress-bar");
      await expect(bar).toBeVisible();
      const fill = bar.locator(".index-progress-bar__fill");
      await expect(fill).toBeVisible();

      await card.click();
      const popover = page.getByRole("dialog", { name: "Index Status" });
      await expect(popover).toBeVisible({ timeout: 5_000 });

      const popoverBar = popover.locator(".index-progress-bar");
      await expect(popoverBar).toBeVisible();
      const popoverFill = popoverBar.locator(".index-progress-bar__fill");
      await expect(popoverFill).toBeVisible();
    } finally {
      Object.assign(indexStatusData, prev);
    }
  });

  test("debug fields are hidden by default in collapsed popover", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const trigger = page.locator('[data-sidebar="trigger"]');
    await trigger.click();
    await expect(trigger).toHaveAttribute("aria-label", "Expand sidebar");

    const statusButton = page.getByLabel("Index Status");
    await statusButton.click();
    const popover = page.getByRole("dialog", { name: "Index Status" });
    await expect(popover).toBeVisible({ timeout: 5_000 });

    await expect(popover).not.toContainText("Workers");
    await expect(popover).not.toContainText("Active jobs");
    await expect(popover).not.toContainText("Queue depth");
  });
});
