/*
Purpose:
Cover active registered-library selection, legacy raw-path migration, and empty
library states across desktop/mobile shells.

Guarantees:
The gallery persists registered library/import-path IDs, removes legacy raw
root paths, and avoids arbitrary path entry when no library exists.

Run when:
Changing active library selection, legacy migration, library selector UI, or
no-library onboarding.
*/

import { expect, test, type Page } from "@playwright/test";
import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";

const rootPath = "/registered/photos";
const nestedPath = `${rootPath}/events`;
const baseUrl = process.env.GALLERY_BASE_URL ?? "http://127.0.0.1:5173";
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64",
);
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
const immichLibrary = {
  id: 8,
  root_path: "/registered/immich",
  import_paths: [{ id: 80, library_id: 8, path: "/registered/immich", position: 0, created_at: 1, updated_at: 1 }],
  exclusion_patterns: [],
  name: "Immich",
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
    if (url.pathname === "/api/browse") {
      await route.fulfill({
        json: browseResponse({
          libraryId: Number(url.searchParams.get("library_id") ?? library.id),
          path: url.searchParams.get("path") ?? rootPath,
        }),
      });
      return;
    }
    if (url.pathname === "/api/search") {
      await route.fulfill({
        json: { query: "", scope: "current", root: rootPath, albums: [], photos: [], prompt: [] },
      });
      return;
    }
    if (/^\/api\/libraries\/\d+\/status$/.test(url.pathname)) {
      await route.fulfill({
        json: statusEnvelope({
          libraryId: Number(url.pathname.match(/^\/api\/libraries\/(\d+)\/status$/)?.[1] ?? library.id),
          path: url.searchParams.get("scope_path") ?? rootPath,
        }),
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

test("desktop library switch can return to a cached active library", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const libraryId = Number(url.searchParams.get("library_id") ?? library.id);
    const path = url.searchParams.get("path") ?? (libraryId === immichLibrary.id ? immichLibrary.root_path : rootPath);
    const activeRoot = libraryId === immichLibrary.id ? immichLibrary.root_path : rootPath;

    if (url.pathname === "/api/libraries") {
      await route.fulfill({ json: [library, immichLibrary] });
      return;
    }
    if (url.pathname === "/api/browse") {
      await route.fulfill({
        json: browseResponse({
          libraryId,
          path,
          media: [
            {
              name: libraryId === immichLibrary.id ? "immich.png" : "gallery-repo.png",
              path: `${activeRoot}/${libraryId === immichLibrary.id ? "immich.png" : "gallery-repo.png"}`,
              type: "image",
              has_children: false,
              cover_images: [],
              mtime: 1000,
              image_count: 0,
              width: 1600,
              height: 1000,
            },
          ],
        }),
      });
      return;
    }
    if (url.pathname === "/api/search") {
      await route.fulfill({
        json: { query: "", scope: "current", root: activeRoot, albums: [], photos: [], videos: [], prompt: [] },
      });
      return;
    }
    if (/^\/api\/libraries\/\d+\/status$/.test(url.pathname)) {
      const statusLibraryId = Number(url.pathname.match(/^\/api\/libraries\/(\d+)\/status$/)?.[1] ?? library.id);
      await route.fulfill({
        json: statusEnvelope({
          libraryId: statusLibraryId,
          path:
            url.searchParams.get("scope_path") ??
            (statusLibraryId === immichLibrary.id ? immichLibrary.root_path : rootPath),
          totalAssets: 1,
        }),
      });
      return;
    }
    if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
      await route.fulfill({ contentType: "image/png", body: png1x1 });
      return;
    }
    await route.fulfill({ json: [] });
  });
  await disableIntro(page);
  await page.addInitScript(() => {
    localStorage.setItem("gallery-active-library-id", "7");
    localStorage.setItem("gallery-active-import-path-id", "70");
  });

  await page.goto(baseUrl);
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByAltText("gallery-repo.png").first()).toBeVisible();

  await page.getByLabel("Active library").click();
  await page.getByRole("option", { name: "Immich" }).click();
  await expect(page.getByAltText("immich.png").first()).toBeVisible({ timeout: 15_000 });

  await page.getByLabel("Active library").click();
  await page.getByRole("option", { name: "Photos" }).click();
  await expect(page.getByAltText("gallery-repo.png").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("photo-card").first()).toBeVisible();
});
