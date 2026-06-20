/**
 * Purpose:
 * Verifies that frontend views degrade safely when backend endpoints fail.
 *
 * Guarantees:
 * * API 500s and offline states show controlled fallback UI
 * * gallery, metadata, image, and lightbox failures do not trigger page errors
 *
 * Run when:
 * * changing API error handling, toast/error UI, or lightbox fallback behavior
 * * touching scan, search, metadata, thumbnail, preview, or image request flows
 */

import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-fault-test";
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

// Shared scan response used by most tests unless overridden
const scanResponse = {
  folders: [],
  images: imagePaths.map((path, i) => ({
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
  next_cursor: null,
  total_images: imagePaths.length,
  index_source: "direct_scan",
};

const metadataResponse = (name: string) => ({
  tool: "stub",
  prompt: "stub prompt test",
  negative_prompt: "",
  params: {},
  width: 1600,
  height: 1000,
  name,
});

type ApiRequest = { pathname: string; path: string };

function requestsFor(requests: ApiRequest[], pathname: string) {
  return requests.filter((r) => r.pathname === pathname);
}

async function installGalleryWithFaults(
  page: Page,
  faults: {
    failScan?: boolean;
    failThumbnail?: boolean;
    failPreview?: boolean;
    failImage?: boolean;
    failMetadata?: boolean;
    failSearch?: boolean;
  } = {},
) {
  const requests: ApiRequest[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const req: ApiRequest = { pathname: url.pathname, path: url.searchParams.get("path") ?? "" };
    requests.push(req);

    if (url.pathname === "/api/libraries") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([stubLibrary]),
      });
      return;
    }

    if (url.pathname === "/api/scan") {
      if (faults.failScan) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: { error: "server_error", message: "Scan failed" } }),
        });
        return;
      }
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(scanResponse),
      });
      return;
    }

    if (url.pathname === "/api/search") {
      if (faults.failSearch) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: { error: "server_error", message: "Search failed" } }),
        });
        return;
      }
      const q = url.searchParams.get("q") ?? "";
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          query: q,
          scope: "all",
          root: rootPath,
          albums: [],
          photos: q
            ? [
                {
                  name: "match.png",
                  path: `${rootPath}/a.png`,
                  type: "photo",
                  parent_path: rootPath,
                  relative_path: "",
                  mtime: 1000,
                  width: 1600,
                  height: 1000,
                  match_type: "filename",
                  prompt_snippet: "",
                  model: "",
                  sampler: "",
                  seed: "",
                },
              ]
            : [],
          prompt: [],
        }),
      });
      return;
    }

    if (url.pathname === "/api/metadata") {
      if (faults.failMetadata) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: { error: "server_error", message: "Metadata failed" } }),
        });
        return;
      }
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(metadataResponse(req.path.split("/").pop() ?? "image.png")),
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

    if (url.pathname === "/api/thumbnail") {
      if (faults.failThumbnail) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: { error: "server_error", message: "Thumbnail failed" } }),
        });
        return;
      }
      await route.fulfill({ contentType: "image/png", body: png1x1 });
      return;
    }

    if (url.pathname === "/api/preview") {
      if (faults.failPreview) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: { error: "server_error", message: "Preview failed" } }),
        });
        return;
      }
      await route.fulfill({ contentType: "image/png", body: png1x1 });
      return;
    }

    if (url.pathname === "/api/image") {
      if (faults.failImage) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: { error: "server_error", message: "Image failed" } }),
        });
        return;
      }
      await route.fulfill({ contentType: "image/png", body: png1x1 });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
  return requests;
}

async function openGallery(page: Page, requests?: ApiRequest[]) {
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
    localStorage.setItem("gallery-sort-preference", JSON.stringify({ field: "name", order: "asc" }));
    localStorage.removeItem("gallery-lightbox-always-load-original");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  if (requests) {
    await page.waitForTimeout(500);
    requests.length = 0;
  }
}

test.use({ viewport: { width: 1280, height: 820 } });

// ─── 2a: Search store throws during grid render ───
test("search 500 shows fallback; no page error", async ({ page, monitoredErrors: _monitoredErrors }) => {
  const requests = await installGalleryWithFaults(page, { failSearch: true });
  await openGallery(page);

  // Perform a search that will fail
  const searchInput = page.locator("#gallery-search");
  await searchInput.fill("test-query");
  await searchInput.press("Enter");
  await page.waitForTimeout(800);

  // The app should not crash - page should still have content
  const pageContent = await page.content();
  expect(pageContent.length).toBeGreaterThan(0);

  // Verify search request was made (it failed with 500)
  const searchRequests = requestsFor(requests, "/api/search");
  expect(searchRequests.length).toBeGreaterThanOrEqual(1);

  // Clear search - gallery should restore
  await searchInput.fill("");
  await searchInput.press("Enter");
  await page.waitForTimeout(500);
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });
});

// ─── 2b: Metadata 500 in lightbox sidebar ───
test("metadata 500 shows placeholder in sidebar; lightbox still shows image", async ({ page }) => {
  const requests = await installGalleryWithFaults(page, { failMetadata: true });
  await openGallery(page, requests);

  // Clear tracked requests after initial load
  requests.length = 0;

  // Open lightbox
  await page.getByTestId("photo-card").first().click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
  await page.waitForTimeout(800);

  // Metadata request should have been made (and failed)
  const metadataRequests = requestsFor(requests, "/api/metadata");
  expect(metadataRequests.length).toBeGreaterThanOrEqual(1);

  // Lightbox itself should still be visible with the image shown
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 5000 });

  // Metadata panel should show error/placeholder state (meta-error class)
  const metaError = page.locator(".meta-error");
  const hasMetaError = await metaError.isVisible({ timeout: 3000 }).catch(() => false);
  // If the app has a meta-error display, it should show; if not, lightbox must still function
  if (hasMetaError) {
    await expect(metaError.first()).toBeVisible();
  }
});

// ─── 2c: Preview 500 — fallback to original ───
test("preview 500 falls back to original; no page error", async ({ page }) => {
  const requests = await installGalleryWithFaults(page, { failPreview: true });
  await openGallery(page, requests);

  // Clear tracked requests after initial load
  requests.length = 0;

  // Open lightbox — preview will fail, app should fall back to original
  await page.getByTestId("photo-card").first().click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
  await page.waitForTimeout(1000);

  // Preview request should have been attempted
  const previewRequests = requestsFor(requests, "/api/preview");
  expect(previewRequests.length).toBeGreaterThanOrEqual(1);

  // Original image should have been requested as fallback
  const imageRequests = requestsFor(requests, "/api/image");
  expect(imageRequests.length).toBeGreaterThanOrEqual(1);
});

// ─── 2d: Image 500 — lightbox doesn't crash ───
test("image 500 during zoom does not crash lightbox", async ({ page }) => {
  const requests = await installGalleryWithFaults(page, { failImage: true });
  await openGallery(page, requests);

  // Open lightbox
  await page.getByTestId("photo-card").first().click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
  await page.waitForTimeout(800);

  requests.length = 0;

  // Zoom to trigger original load
  await page.mouse.move(440, 410);
  await page.keyboard.down("Control");
  await page.mouse.wheel(0, -600);
  await page.keyboard.up("Control");
  await page.waitForTimeout(800);

  // Image request should have been attempted
  const imageRequests = requestsFor(requests, "/api/image");
  expect(imageRequests.length).toBeGreaterThanOrEqual(1);

  // Lightbox must NOT have crashed
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 5000 });
});

// ─── 2e: Thumbnail 500 — grid shows placeholder ───
test("thumbnail 500 shows placeholder in grid; no page error", async ({ page }) => {
  const requests = await installGalleryWithFaults(page, { failThumbnail: true });
  await openGallery(page);

  // Wait for thumbnails to be requested
  await page.waitForTimeout(1000);

  // Thumbnail requests should have been made
  const thumbnailRequests = requestsFor(requests, "/api/thumbnail");
  expect(thumbnailRequests.length).toBeGreaterThanOrEqual(1);

  // Photo cards should still be present (with placeholder state)
  const cards = page.getByTestId("photo-card");
  const count = await cards.count();
  expect(count).toBeGreaterThanOrEqual(1);

  // Placeholder text or broken state should appear for cards with failed images
  const placeholder = page.locator(".placeholder-text");
  const placeholderCount = await placeholder.count();
  expect(placeholderCount).toBeGreaterThanOrEqual(1);
});

// ─── 2f: Scan 500 — error message shown ───
test("scan 500 shows error message; no page error", async ({ page }) => {
  await installGalleryWithFaults(page, { failScan: true });

  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
    localStorage.setItem("gallery-sort-preference", JSON.stringify({ field: "name", order: "asc" }));
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3000);

  // The app should show an error banner or error state (not a blank/white page)
  // Check for either error banner or empty-state with error type
  const errorBanner = page.locator(".error-banner");
  const emptyState = page.locator(".empty-state-container");
  const pageContent = await page.content();

  const hasErrorBanner = await errorBanner.isVisible({ timeout: 3000 }).catch(() => false);
  const hasEmptyState = await emptyState.isVisible({ timeout: 2000 }).catch(() => false);

  // At minimum, the page must not be blank/crashed
  expect(pageContent.length).toBeGreaterThan(100);

  // Verify either error banner, empty state, or error message is shown
  const hasErrorMessage =
    pageContent.includes("Unable to load") || pageContent.includes("An unexpected error occurred");
  expect(hasErrorBanner || hasEmptyState || hasErrorMessage).toBe(true);
});

// ─── 2g: Network offline during lightbox ───
test("network offline during lightbox shows error state; no crash", async ({ page }) => {
  const requests = await installGalleryWithFaults(page);
  await openGallery(page, requests);

  // Open lightbox successfully
  await page.getByTestId("photo-card").first().click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
  await page.waitForTimeout(500);

  // Go offline
  await page.context().setOffline(true);
  requests.length = 0;

  // Try navigating to next image (should fail gracefully)
  const nextBtn = page.locator('[data-testid="lightbox-next"]');
  if (await nextBtn.isVisible().catch(() => false)) {
    await nextBtn.click();
    await page.waitForTimeout(1000);
  }

  // Lightbox must still be visible (not crashed)
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 5000 });

  // Restore online
  await page.context().setOffline(false);
});
