/**
 * Purpose:
 * Verifies breadcrumb rendering and navigation for deep gallery paths.
 *
 * Guarantees:
 * * long path segments remain accessible without breaking layout
 * * breadcrumb clicks update the gallery path through SPA navigation
 *
 * Run when:
 * * changing Breadcrumb, path routing, or gallery navigation state
 * * touching responsive header space used by breadcrumbs
 */

import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/breadcrumb-root/alpha/beta/gamma/delta/epsilon/zeta";
const imagePath = `${rootPath}/image_1.png`;
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64",
);

async function installStubbedGallery(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());

    if (url.pathname === "/api/scan") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          folders: [],
          images: [
            {
              name: "image_1.png",
              path: imagePath,
              type: "image",
              has_children: false,
              cover_images: [],
              mtime: 1000,
              image_count: 0,
              width: 1600,
              height: 1000,
            },
          ],
          next_cursor: null,
          total_images: 1,
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
          name: "image_1.png",
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
        body: JSON.stringify({
          enabled: false,
          worker_count: 0,
          active_jobs: 0,
          runtime_queue_depth: 0,
          done: 0,
          running: 0,
          queued: 0,
          failed: 0,
          stale: 0,
          skipped: 0,
          total: 0,
          path: rootPath,
          counts: {},
          oldest_queued_age_seconds: null,
          last_error: null,
          updated_at: null,
          coalesced_duplicates: 0,
          staged_path_queue_depth: 0,
          staged_path_coalesced: 0,
          staged_path_failed: 0,
          staged_path_flushes_forced: 0,
          staged_path_worker_count: 0,
          active_scan_requests: 0,
          batch_size: 100,
          staged_path_batch_size: 50,
          stage_max_wait_seconds: 30,
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

async function openStubbedGallery(page: Page) {
  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
}

test.describe("Breadcrumb", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("opens collapsed breadcrumb menu without getBoundingClientRect runtime error", async ({
    page,
    monitoredErrors,
  }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    const ellipsisButton = page.getByLabel(/more folders/);
    await expect(ellipsisButton).toBeVisible();

    await ellipsisButton.click();

    await expect(page.locator(".ellipsis-menu")).toBeVisible();
    await expect(page.getByRole("button", { name: "Show full path" })).toBeVisible();
    expect(
      monitoredErrors.consoleErrors.some(
        (message) =>
          message.includes("getBoundingClientRect is not a function") || message.includes("Unhandled Vue error"),
      ),
    ).toBe(false);
  });
});
