import { expect, test, type Page } from "@playwright/test";

const rootPath = "/registered/photos";
const nestedPath = `${rootPath}/events`;
const baseUrl = process.env.GALLERY_BASE_URL ?? "http://127.0.0.1:5173";
const library = {
  id: 7,
  root_path: rootPath,
  import_paths: [
    { id: 70, library_id: 7, path: rootPath, position: 0, created_at: 1, updated_at: 1 },
    { id: 71, library_id: 7, path: "/registered/archive", position: 1, created_at: 1, updated_at: 1 },
  ],
  exclusion_patterns: [],
  name: "Photos",
  state: "ready",
  watch_enabled: 1,
  warm_enabled: 1,
  asset_count: 0,
  created_at: 1,
  updated_at: 1,
  last_scan_at: null,
  last_error: null,
};

async function mockGallery(page: Page, libraries = [library]) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/libraries") {
      await route.fulfill({ json: libraries });
      return;
    }
    if (url.pathname === "/api/scan") {
      await route.fulfill({
        json: {
          folders: [],
          images: [],
          next_cursor: null,
          total_images: 0,
          request_path: url.searchParams.get("path"),
        },
      });
      return;
    }
    if (url.pathname === "/api/search") {
      await route.fulfill({
        json: { query: "", scope: "current", root: rootPath, albums: [], photos: [], prompt: [] },
      });
      return;
    }
    if (url.pathname === "/api/index/status") {
      await route.fulfill({
        json: {
          path: url.searchParams.get("path") ?? "",
          total: 0,
          indexed_photos: 0,
          metadata_records: 0,
          counts: {},
          queued: 0,
          running: 0,
          done: 0,
          failed: 0,
          stale: 0,
          skipped: 0,
          oldest_queued_age_seconds: null,
          last_error: null,
          updated_at: null,
          enabled: true,
          worker_count: 0,
          active_jobs: 0,
          runtime_queue_depth: 0,
          coalesced_duplicates: 0,
          staged_path_queue_depth: 0,
          staged_path_coalesced: 0,
          staged_path_failed: 0,
          staged_path_flushes_forced: 0,
          staged_path_worker_count: 0,
          active_scan_requests: 0,
          batch_size: 0,
          staged_path_batch_size: 0,
          stage_max_wait_seconds: 0,
        },
      });
      return;
    }
    await route.fulfill({ json: [] });
  });
}

async function disableIntro(page: Page) {
  await page.addInitScript(() => localStorage.setItem("intro_mode", "disabled"));
}

test("migrates a legacy subfolder to registered IDs and removes the raw path source", async ({ page }) => {
  await mockGallery(page);
  await disableIntro(page);
  await page.addInitScript((path) => localStorage.setItem("gallery-root-path", path), nestedPath);
  await page.goto(baseUrl);

  await expect.poll(() => page.evaluate(() => localStorage.getItem("gallery-active-library-id"))).toBe("7");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("gallery-active-import-path-id"))).toBe("70");
  expect(await page.evaluate(() => localStorage.getItem("gallery-root-path"))).toBeNull();
  await expect(page.getByText("Photos", { exact: true }).first()).toBeVisible();
  await expect(page.getByPlaceholder("Enter folder path...")).toHaveCount(0);
  await expect(page.locator("textarea")).toHaveCount(0);
});

test("mobile selector changes import path and persists the registered selection", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockGallery(page);
  await disableIntro(page);
  await page.goto(baseUrl);
  await page.getByRole("button", { name: /Photos/ }).click();
  await page.getByRole("button", { name: /registered\/archive/ }).click();

  await expect.poll(() => page.evaluate(() => localStorage.getItem("gallery-active-import-path-id"))).toBe("71");
  await expect(page.locator("textarea")).toHaveCount(0);
});

test("no-library state provides a management CTA without arbitrary path entry", async ({ page }) => {
  await mockGallery(page, []);
  await disableIntro(page);
  await page.goto(baseUrl);

  await expect(page.getByText("No library selected")).toBeVisible();
  await expect(
    page
      .getByRole("link", { name: "Manage Libraries" })
      .or(page.getByRole("button", { name: "Manage Libraries" }))
      .first(),
  ).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveCount(0);
});
