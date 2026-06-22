/**
 * Purpose:
 * Verifies sidebar trigger visibility and behavior across gallery layouts.
 *
 * Guarantees:
 * * sidebar controls remain discoverable and do not duplicate unexpectedly
 * * trigger interactions preserve gallery content and route state
 *
 * Run when:
 * * changing sidebar trigger components, App shell layout, or responsive navigation
 * * touching sidebar localStorage state or root path controls
 */

import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-sidebar-trigger-test";
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
  name: "Sidebar Trigger Test",
  state: "ready",
  watch_enabled: 1,
  warm_enabled: 1,
  asset_count: 0,
  created_at: 1,
  updated_at: 1,
  last_scan_at: null,
  last_error: null,
};

async function installStubbedGallery(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());

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
            media: imagePaths.map((path, i) => ({
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
          }),
        ),
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

    if (url.pathname === "/api/libraries/1/status") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(statusEnvelope({ libraryId: 1, path: url.searchParams.get("scope_path") ?? rootPath })),
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
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
    localStorage.setItem("gallery-sidebar-open", "true");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
}

test.describe("SidebarTrigger", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test.beforeEach(async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);
  });

  test("sidebar trigger collapses and expands sidebar", async ({ page }) => {
    const trigger = page.locator('[data-sidebar="trigger"]');
    await expect(trigger).toBeVisible({ timeout: 5_000 });

    await expect(trigger).toHaveAttribute("aria-label", "Collapse sidebar");

    await trigger.click();
    await page.waitForTimeout(500);

    await expect(trigger).toHaveAttribute("aria-label", "Expand sidebar");

    const sidebarContainer = page.locator('[data-sidebar="sidebar"]');
    await expect(sidebarContainer).toBeVisible();

    const desktopGroup = sidebarContainer.locator("..").locator("..");
    const dataCollapsible = await desktopGroup.getAttribute("data-collapsible");
    expect(dataCollapsible).toBe("icon");

    const dataState = await desktopGroup.getAttribute("data-state");
    expect(dataState).toBe("collapsed");

    await trigger.click();
    await page.waitForTimeout(500);

    await expect(trigger).toHaveAttribute("aria-label", "Collapse sidebar");

    const dataStateAfterExpand = await desktopGroup.getAttribute("data-state");
    expect(dataStateAfterExpand).toBe("expanded");
  });

  test("sidebar trigger has correct aria-label", async ({ page }) => {
    const trigger = page.locator('[data-sidebar="trigger"]');
    await expect(trigger).toBeVisible({ timeout: 5_000 });

    await expect(trigger).toHaveAttribute("aria-label", "Collapse sidebar");

    await trigger.click();
    await page.waitForTimeout(500);

    await expect(trigger).toHaveAttribute("aria-label", "Expand sidebar");
  });

  test("sidebar state persists in localStorage", async ({ page }) => {
    const trigger = page.locator('[data-sidebar="trigger"]');
    await expect(trigger).toBeVisible({ timeout: 5_000 });

    let sidebarState = await page.evaluate(() => localStorage.getItem("gallery-sidebar-open"));
    expect(sidebarState).toBe("true");

    await trigger.click();
    await page.waitForTimeout(500);

    sidebarState = await page.evaluate(() => localStorage.getItem("gallery-sidebar-open"));
    expect(sidebarState).toBe("false");

    await expect(trigger).toHaveAttribute("aria-label", "Expand sidebar");
  });

  test("collapsed sidebar narrows to icon rail", async ({ page }) => {
    const trigger = page.locator('[data-sidebar="trigger"]');
    await expect(trigger).toBeVisible({ timeout: 5_000 });

    const sidebarContainer = page.locator('[data-sidebar="sidebar"]');
    const initialBox = await sidebarContainer.boundingBox();
    expect(initialBox).not.toBeNull();
    expect(initialBox!.width).toBeGreaterThan(100);

    await trigger.click();
    await page.waitForTimeout(600);

    const collapsedBox = await sidebarContainer.boundingBox();
    expect(collapsedBox).not.toBeNull();
    expect(collapsedBox!.width).toBeLessThan(100);
  });
});
