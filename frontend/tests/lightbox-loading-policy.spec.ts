/**
 * Purpose:
 * Verifies the lightbox source-loading policy from grid thumbnails through preview/original escalation.
 *
 * Guarantees:
 * * normal open uses thumbnail and preview endpoints without original image fetches
 * * zoom, fullscreen, preview failure, and neighbor preload use the expected endpoints
 *
 * Run when:
 * * changing PhotoSwipe integration, lightbox source selection, or image endpoint policy
 * * touching gallery-lightbox-always-load-original or preview fallback behavior
 */

import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-policy-test";
const imagePaths = [`${rootPath}/a.png`, `${rootPath}/b.png`, `${rootPath}/c.png`];
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64",
);
const svgImage = (width: number, height: number) =>
  Buffer.from(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#456"/></svg>`,
  );

type ApiRequest = {
  pathname: string;
  path: string;
  maxLongEdge: string;
};

function requestsFor(requests: ApiRequest[], pathname: string) {
  return requests.filter((request) => request.pathname === pathname);
}

function requestedPath(requests: ApiRequest[], pathname: string, path: string) {
  return requests.some((request) => request.pathname === pathname && request.path === path);
}

async function installStubbedGallery(
  page: Page,
  options: {
    failPreviewFor?: string;
    includeScanDimensions?: boolean;
    metadataDimensions?: { width: number; height: number } | null;
    previewNaturalSize?: { width: number; height: number };
  } = {},
) {
  const requests: ApiRequest[] = [];
  const includeScanDimensions = options.includeScanDimensions ?? true;
  const metadataDimensions =
    options.metadataDimensions === undefined ? { width: 1600, height: 1000 } : options.metadataDimensions;

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const request = {
      pathname: url.pathname,
      path: url.searchParams.get("path") ?? "",
      maxLongEdge: url.searchParams.get("max_long_edge") ?? "",
    };
    requests.push(request);

    if (url.pathname === "/api/scan") {
      await route.fulfill({
        contentType: "application/json",
        headers: { "Cache-Control": "no-store" },
        body: JSON.stringify({
          folders: [],
          images: imagePaths.map((path, index) => ({
            name: `image-${index + 1}.png`,
            path,
            type: "image",
            mtime: 1000 + index,
            width: includeScanDimensions ? 1600 : null,
            height: includeScanDimensions ? 1000 : null,
          })),
          next_cursor: null,
          total_images: imagePaths.length,
        }),
      });
      return;
    }

    if (url.pathname === "/api/metadata") {
      await route.fulfill({
        contentType: "application/json",
        headers: { "Cache-Control": "no-store" },
        body: JSON.stringify({
          tool: "stub",
          prompt: "stub prompt",
          negative_prompt: "",
          params: {},
          date: "",
          generation_time: "",
          width: metadataDimensions?.width ?? null,
          height: metadataDimensions?.height ?? null,
          name: request.path.split("/").pop() ?? "image.png",
        }),
      });
      return;
    }

    if (url.pathname === "/api/landing-pages") {
      await route.fulfill({
        contentType: "application/json",
        headers: { "Cache-Control": "no-store" },
        body: JSON.stringify([]),
      });
      return;
    }

    if (url.pathname === "/api/preview" && request.path === options.failPreviewFor) {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        headers: { "Cache-Control": "no-store" },
        body: JSON.stringify({
          detail: {
            error: "server_error",
            message: "Unable to generate preview",
          },
        }),
      });
      return;
    }

    if (url.pathname === "/api/preview" && options.previewNaturalSize) {
      await route.fulfill({
        contentType: "image/svg+xml",
        headers: { "Cache-Control": "no-store" },
        body: svgImage(options.previewNaturalSize.width, options.previewNaturalSize.height),
      });
      return;
    }

    if (url.pathname === "/api/thumbnail" || url.pathname === "/api/preview" || url.pathname === "/api/image") {
      await route.fulfill({
        contentType: "image/png",
        headers: { "Cache-Control": "no-store" },
        body: png1x1,
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });

  return requests;
}

async function openStubbedGallery(page: Page, requests: ApiRequest[]) {
  await page.addInitScript((rootForInit) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", rootForInit);
    localStorage.setItem("gallery-sort-preference", JSON.stringify({ field: "name", order: "asc" }));
    localStorage.removeItem("gallery-lightbox-always-load-original");
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
  await expect.poll(() => requestsFor(requests, "/api/thumbnail").length).toBeGreaterThanOrEqual(3);
}

async function openLightbox(page: Page, requests: ApiRequest[], index = 0) {
  requests.length = 0;
  await page.getByTestId("photo-card").nth(index).click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
  await expect.poll(() => requestsFor(requests, "/api/preview").length).toBeGreaterThan(0);
}

test.use({ viewport: { width: 1280, height: 820 } });

test("grid requests 512 thumbnails only", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await openStubbedGallery(page, requests);
  await page.waitForTimeout(300);

  const thumbnailRequests = requestsFor(requests, "/api/thumbnail");
  expect(thumbnailRequests.length).toBeGreaterThanOrEqual(3);
  expect(thumbnailRequests.every((request) => request.maxLongEdge === "512")).toBe(true);
  expect(requestsFor(requests, "/api/preview")).toHaveLength(0);
  expect(requestsFor(requests, "/api/image")).toHaveLength(0);
});

test("normal lightbox open uses thumbnail and preview without original", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await openStubbedGallery(page, requests);
  await openLightbox(page, requests);
  await expect.poll(() => requestsFor(requests, "/api/thumbnail").length).toBeGreaterThan(0);
  await page.waitForTimeout(500);

  expect(requestsFor(requests, "/api/preview").length).toBeGreaterThan(0);
  expect(requestsFor(requests, "/api/thumbnail").every((request) => request.maxLongEdge === "512")).toBe(true);
  expect(requestsFor(requests, "/api/preview").every((request) => request.maxLongEdge === "1440")).toBe(true);
  expect(requestsFor(requests, "/api/image")).toHaveLength(0);
});

test("lightbox does not size the first open from grid thumbnail dimensions", async ({ page }) => {
  const requests = await installStubbedGallery(page, {
    includeScanDimensions: false,
    metadataDimensions: null,
    previewNaturalSize: { width: 824, height: 1024 },
  });
  await openStubbedGallery(page, requests);
  await openLightbox(page, requests);

  await expect.poll(async () => page.evaluate(() => Boolean(document.querySelector(".pswp__img")))).toBe(true);

  const imageRect = await page.evaluate(() => {
    const img = document.querySelector(".pswp__img") as HTMLElement | null;
    if (!img) return null;
    const rect = img.getBoundingClientRect();
    return { width: rect.width, height: rect.height };
  });

  expect(imageRect, "PhotoSwipe image should exist").not.toBeNull();
  expect(imageRect!.width, "first open must not use the 1px stub thumbnail width").toBeGreaterThan(300);
  expect(imageRect!.height, "first open must not use the 1px stub thumbnail height").toBeGreaterThan(300);
});

test("cold-cache lightbox uses preview dimensions for the opening slide aspect ratio", async ({ page }) => {
  const previewNaturalSize = { width: 824, height: 1024 };
  const expectedRatio = previewNaturalSize.width / previewNaturalSize.height;
  const requests = await installStubbedGallery(page, {
    includeScanDimensions: false,
    metadataDimensions: null,
    previewNaturalSize,
  });
  await openStubbedGallery(page, requests);
  await openLightbox(page, requests);

  await expect
    .poll(async () =>
      page.evaluate(() => {
        const img = document.querySelector<HTMLImageElement>(".pswp__img[alt='image-1.png']");
        if (!img || !img.currentSrc.includes("/api/preview")) return 0;
        const rect = img.getBoundingClientRect();
        return rect.height > 0 ? rect.width / rect.height : 0;
      }),
    )
    .toBeCloseTo(expectedRatio, 1);

  const activeImage = await page.evaluate(() => {
    const img = document.querySelector<HTMLImageElement>(".pswp__img[alt='image-1.png']");
    if (!img || !img.currentSrc.includes("/api/preview")) return null;
    const rect = img.getBoundingClientRect();
    return {
      currentSrc: img.currentSrc,
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
      rectWidth: rect.width,
      rectHeight: rect.height,
    };
  });

  expect(activeImage, "PhotoSwipe preview image should exist").not.toBeNull();
  expect(activeImage!.currentSrc).toContain("/api/preview");
  expect(activeImage!.currentSrc).not.toContain("/api/thumbnail");
  expect(activeImage!.naturalWidth).toBe(previewNaturalSize.width);
  expect(activeImage!.naturalHeight).toBe(previewNaturalSize.height);
  expect(activeImage!.rectWidth / activeImage!.rectHeight).toBeCloseTo(expectedRatio, 1);
});

test("zoom beyond threshold requests original for the current image", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await openStubbedGallery(page, requests);
  await openLightbox(page, requests);

  requests.length = 0;
  await page.mouse.move(440, 410);
  await page.keyboard.down("Control");
  await page.mouse.wheel(0, -600);
  await page.keyboard.up("Control");

  await expect.poll(() => requestedPath(requests, "/api/image", imagePaths[0])).toBe(true);
  expect(requestsFor(requests, "/api/image").every((request) => request.path === imagePaths[0])).toBe(true);
});

test("explicit fullscreen action requests original for the current image", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await openStubbedGallery(page, requests);
  await openLightbox(page, requests);
  await expect(page.getByLabel("Toggle fullscreen")).toBeVisible();

  requests.length = 0;
  await page.getByLabel("Toggle fullscreen").click();

  await expect.poll(() => requestedPath(requests, "/api/image", imagePaths[0])).toBe(true);
  expect(requestsFor(requests, "/api/image").every((request) => request.path === imagePaths[0])).toBe(true);
});

test("preview failure falls back to original for the current image", async ({ page }) => {
  const requests = await installStubbedGallery(page, { failPreviewFor: imagePaths[0] });
  await openStubbedGallery(page, requests);

  requests.length = 0;
  await page.getByTestId("photo-card").first().click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });

  await expect.poll(() => requestedPath(requests, "/api/preview", imagePaths[0])).toBe(true);
  await expect.poll(() => requestedPath(requests, "/api/image", imagePaths[0])).toBe(true);
});

test("next and previous preload thumbnail plus preview only", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await openStubbedGallery(page, requests);
  await openLightbox(page, requests, 1);
  await expect.poll(() => requestedPath(requests, "/api/preview", imagePaths[0])).toBe(true);
  await expect.poll(() => requestedPath(requests, "/api/preview", imagePaths[2])).toBe(true);
  await expect.poll(() => requestedPath(requests, "/api/thumbnail", imagePaths[0])).toBe(true);
  await expect.poll(() => requestedPath(requests, "/api/thumbnail", imagePaths[2])).toBe(true);
  await page.waitForTimeout(500);

  expect(requestsFor(requests, "/api/image")).toHaveLength(0);
});

test("metadata panel still loads asynchronously", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await openStubbedGallery(page, requests);
  await openLightbox(page, requests);

  await expect.poll(() => requestedPath(requests, "/api/metadata", imagePaths[0])).toBe(true);
  await expect(page.getByText("stub prompt")).toBeVisible();
});
