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

  test("shows Disabled badge when no root path is set", async ({ page }) => {
    await installStubbedGallery(page);

    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
    });
    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByLabel("Index Status")).toBeVisible({ timeout: 10_000 });

    const statusButton = page.getByLabel("Index Status");
    await expect(statusButton).toBeVisible();

    const badge = statusButton.locator(".inline-flex");
    await expect(badge).toContainText("Disabled");
  });

  test("shows index status details when path is set", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Index Status");
    await expect(statusButton).toBeVisible();

    const badge = statusButton.locator(".inline-flex");
    await expect(badge).toContainText("Idle");

    await statusButton.click();
    const popover = page.getByRole("dialog", { name: "Index Status" });
    await expect(popover).toBeVisible({ timeout: 5_000 });

    // Summary fields visible by default
    await expect(popover).toContainText("indexed");
    await expect(popover).toContainText("150");

    // Click Details to reveal technical metrics
    await popover.getByText("Details").click();
    await expect(popover).toContainText("Workers");
    await expect(popover).toContainText("2");
    await expect(popover).toContainText("Processing");
  });

  test("popover content is not empty when opened", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page, true);

    const statusButton = page.getByLabel("Index Status");
    await expect(statusButton).toBeVisible();
    await statusButton.click();

    const popover = page.getByRole("dialog", { name: "Index Status" });
    await expect(popover).toBeVisible({ timeout: 5_000 });

    // Expand Details so screenshot shows technical metrics too
    await popover.getByText("Details").click();
    await page.waitForTimeout(300);

    const textContent = await popover.textContent();
    expect(textContent.trim().length).toBeGreaterThan(0);

    const isVisible = await popover.isVisible();
    expect(isVisible).toBe(true);

    const boundingBox = await popover.boundingBox();
    expect(boundingBox).not.toBeNull();
    expect(boundingBox!.width).toBeGreaterThan(0);
    expect(boundingBox!.height).toBeGreaterThan(0);

    await expect(popover).toHaveScreenshot("index-status-popover.png");
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

    await expect(page.getByRole("dialog", { name: "Index Status" })).toContainText("indexed", { timeout: 5_000 });
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
    await expect(popover).toContainText(/Failed to load status|Unavailable|Something went wrong/);
  });
});
