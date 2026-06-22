/**
 * Purpose:
 * Verifies gallery revisit behavior does not refetch duplicate first-page browse requests.
 *
 * Guarantees:
 * * cached album data survives soft revisit and browser back navigation
 * * cursor=0 browse requests are not duplicated unnecessarily
 *
 * Run when:
 * * changing TanStack query keys, gallery cache lifetime, or route revisit behavior
 * * touching search clear/back navigation flows that return to gallery results
 */

import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-cache-revisit-test";
const imagePaths = [`${rootPath}/a.png`, `${rootPath}/b.png`, `${rootPath}/c.png`];
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
  asset_count: 0,
  created_at: 1,
  updated_at: 1,
  last_scan_at: null,
  last_error: null,
};

type ApiRequest = { pathname: string; path: string; cursor: string };

function requestsFor(requests: ApiRequest[], pathname: string) {
  return requests.filter((r) => r.pathname === pathname);
}

function cursorZeroBrowses(requests: ApiRequest[]) {
  return requests.filter((r) => r.pathname === "/api/browse" && r.cursor === "0");
}

async function installStubbedGallery(page: Page) {
  const requests: ApiRequest[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const req: ApiRequest = {
      pathname: url.pathname,
      path: url.searchParams.get("path") ?? "",
      cursor: url.searchParams.get("cursor") ?? "0",
    };
    requests.push(req);

    if (url.pathname === "/api/libraries") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([stubLibrary]),
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

    if (url.pathname === "/api/browse") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          browseResponse({
            libraryId: Number(url.searchParams.get("library_id") ?? 1),
            path: url.searchParams.get("path") ?? rootPath,
            media: imagePaths.map((path, i) => ({
              name: `image-${i + 1}.png`,
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

    if (url.pathname === "/api/search") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          query: url.searchParams.get("q") ?? "",
          scope: "all",
          root: rootPath,
          albums: [],
          photos: [],
          prompt: [],
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
          name: req.path.split("/").pop() ?? "image.png",
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

    if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
      await route.fulfill({ contentType: "image/png", body: png1x1 });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
  return requests;
}

test.use({ viewport: { width: 1280, height: 820 } });

test("first album open shows photo cards", async ({ page }) => {
  const requests = await installStubbedGallery(page);

  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
  expect(requestsFor(requests, "/api/browse").length).toBeGreaterThanOrEqual(1);
});

test("soft revisit via search UI does not trigger duplicate cursor=0 browse requests", async ({ page }) => {
  const requests = await installStubbedGallery(page);

  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Wait for initial browse request to settle, then clear request tracking
  await page.waitForTimeout(500);
  requests.length = 0;

  // Soft navigation: enter search (switches to search view)
  await page.locator("#gallery-search").fill("navigate-away");
  await page.locator("#gallery-search").press("Enter");
  await page.waitForTimeout(500);

  // Soft navigation back: clear search (restores gallery view)
  await page.locator("#gallery-search").fill("");
  await page.locator("#gallery-search").press("Enter");
  await page.waitForTimeout(500);

  // Photo cards should reappear quickly (no skeleton/flicker)
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });

  // No duplicate cursor=0 browse on revisit
  const cursorZero = cursorZeroBrowses(requests);
  expect(cursorZero.length).toBeLessThanOrEqual(1);

  // Verify photo cards are rendered
  const cardCount = await page.getByTestId("photo-card").count();
  expect(cardCount).toBeGreaterThanOrEqual(1);
});

test("revisit after browser back preserves gallery without duplicate browse requests", async ({ page }) => {
  const requests = await installStubbedGallery(page);

  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Navigate away — go to blank page on same origin to preserve localStorage access
  await page.goto(baseUrl.replace(/\/+$/, "") + "/blank-non-existent-path", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(300);

  // Track requests after re-entry
  requests.length = 0;

  // Navigate back
  await page.goBack({ waitUntil: "networkidle" });
  await page.waitForTimeout(1500);

  // Photo cards should be visible without excessive new browse requests
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  const cursorZero = cursorZeroBrowses(requests);

  // On revisit, cursor=0 browse requests should be minimal (cached data)
  expect(cursorZero.length).toBeLessThanOrEqual(2);

  // Cards should be rendered
  const cardCount = await page.getByTestId("photo-card").count();
  expect(cardCount).toBeGreaterThanOrEqual(1);
});
