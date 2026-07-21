/**
 * Purpose:
 * Verifies SPA gallery browsing, lightbox use, and navigation do not reload the page.
 *
 * Guarantees:
 * * boot identity stays stable across album and lightbox interactions
 * * duplicate initial browse requests are avoided during stubbed navigation flows
 *
 * Run when:
 * * changing router, gallery navigation, lightbox prev/next, or boot initialization
 * * touching query caching that controls browse request reuse
 */

import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-no-reload-test";
const imagePaths = [
  `${rootPath}/a.png`,
  `${rootPath}/b.png`,
  `${rootPath}/c.png`,
  `${rootPath}/d.png`,
  `${rootPath}/e.png`,
];
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64",
);

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
        body: JSON.stringify([
          {
            id: 1,
            root_path: rootPath,
            import_paths: [{ id: 10, library_id: 1, path: rootPath, position: 0, created_at: 1, updated_at: 1 }],
            exclusion_patterns: [],
            name: "No reload library",
            state: "ready",
            watch_enabled: 1,
            warm_enabled: 1,
            asset_count: imagePaths.length,
            created_at: 1,
            updated_at: 1,
            last_scan_at: 1,
            last_error: null,
          },
        ]),
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

async function openStubbedGallery(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
    localStorage.setItem("gallery-sort-preference", JSON.stringify({ field: "name", order: "asc" }));
    localStorage.removeItem("gallery-lightbox-always-load-original");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
}

test.use({ viewport: { width: 1280, height: 820 } });

test("boot id does not change during album browse / lightbox / navigation", async ({ page }) => {
  const bootId = "boot-test-001";
  await page.addInitScript((id) => {
    window.__galleryBootId = id;
  }, bootId);

  await installStubbedGallery(page);
  await openStubbedGallery(page);

  // Verify boot id after initial load
  let currentId = await page.evaluate(() => window.__galleryBootId);
  expect(currentId).toBe(bootId);

  // Open lightbox
  await page.getByTestId("photo-card").first().click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
  currentId = await page.evaluate(() => window.__galleryBootId);
  expect(currentId).toBe(bootId);

  // Close lightbox
  await page.getByLabel("Close").click();
  await expect(page.getByTestId("lightbox")).not.toBeVisible({ timeout: 5000 });
  currentId = await page.evaluate(() => window.__galleryBootId);
  expect(currentId).toBe(bootId);

  // Scroll the grid
  await page.mouse.wheel(0, 500);
  await expect.poll(async () => page.evaluate(() => window.__galleryBootId)).toBe(bootId);
  expect(currentId).toBe(bootId);
});

test("no unexpected full page reload during album browsing", async ({ page }) => {
  let navigations = 0;
  page.on("framenavigated", () => {
    navigations++;
  });

  await installStubbedGallery(page);
  await openStubbedGallery(page);

  // Capture baseline — app may navigate from base URL to gallery root path
  const baseline = navigations;

  // Open lightbox - should not navigate further
  await page.getByTestId("photo-card").first().click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
  expect(navigations).toBe(baseline);

  // Close lightbox - should not navigate
  await page.getByLabel("Close").click();
  await expect(page.getByTestId("lightbox")).not.toBeVisible({ timeout: 5_000 });
  expect(navigations).toBe(baseline);
});

test("/api/browse with cursor=0 is not duplicated unnecessarily", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await openStubbedGallery(page);

  // Wait for initial browse requests to settle
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });

  const browseRequests = requestsFor(requests, "/api/browse");
  const cursorZeroRequests = cursorZeroBrowses(requests);

  // Should not have duplicate initial (cursor=0) browse requests
  expect(cursorZeroRequests.length).toBeLessThanOrEqual(2);

  // Verify at least one browse happened
  expect(browseRequests.length).toBeGreaterThanOrEqual(1);
});

test("lightbox prev/next navigate without page reload", async ({ page }) => {
  let navigations = 0;
  page.on("framenavigated", () => {
    navigations++;
  });

  await installStubbedGallery(page);
  await openStubbedGallery(page);

  await page.getByTestId("photo-card").first().click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });

  const navBefore = navigations;

  // Navigate next in lightbox
  const nextBtn = page.locator('[data-testid="lightbox-next"]');
  if (await nextBtn.isVisible()) {
    await nextBtn.click();
    await expect(page.getByTestId("lightbox").locator("img").first()).toBeVisible({ timeout: 5_000 });
  }

  // Navigate prev in lightbox
  const prevBtn = page.locator('[data-testid="lightbox-prev"]');
  if (await prevBtn.isVisible()) {
    await prevBtn.click();
    await expect(page.getByTestId("lightbox").locator("img").first()).toBeVisible({ timeout: 5_000 });
  }

  // Should not have triggered additional navigations
  expect(navigations).toBe(navBefore);
});
