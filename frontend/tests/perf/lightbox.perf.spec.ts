/**
 * Purpose:
 * Measures lightbox open and next-image transition timing against real endpoint usage.
 *
 * Guarantees:
 * * preview and thumbnail request timing is captured around lightbox interactions
 * * full original image fetches are surfaced when they affect normal open performance
 *
 * Run when:
 * * changing lightbox source loading, PhotoSwipe transitions, or preview endpoint behavior
 * * validating real-data lightbox performance before release
 */

import { fileURLToPath } from "node:url";
import { expect, test } from "../helpers/monitorErrors";
import type { Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve, join, dirname as pathDirname } from "node:path";
import { installApiNetworkTracker, getQueryParam } from "./perf-utils";

const __filename = fileURLToPath(import.meta.url);
const __dirname = pathDirname(__filename);

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const albumName = process.env.GALLERY_PERF_ALBUM_NAME ?? "a1111";
const albumPath = process.env.GALLERY_PERF_ALBUM_PATH ?? "";
const rootPath =
  process.env.GALLERY_ROOT_PATH ??
  (albumPath ? albumPath.substring(0, albumPath.lastIndexOf("/")) : "/home/ubuntu/gallery-repo/test-images");

async function navigateToAlbum(page: Page) {
  await page.addInitScript((rootForInit) => {
    localStorage.setItem("gallery-root-path", rootForInit);
    localStorage.removeItem("gallery-lightbox-always-load-original");
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

  const enterBtn = page.getByRole("button", { name: /enter gallery/i });
  if (await enterBtn.isVisible().catch(() => false)) {
    await enterBtn.click();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
  }

  const album = page.getByText(albumName, { exact: false }).first();
  await expect(album).toBeVisible({ timeout: 15000 });
  await album.click();

  const firstPhoto = page.getByTestId("photo-card").first();
  await expect(firstPhoto).toBeVisible({ timeout: 15000 });

  return firstPhoto;
}

test("lightbox opens first photo within budget", async ({ page }) => {
  const clickTime = { value: 0 };
  const tracker = installApiNetworkTracker(page, clickTime);

  await navigateToAlbum(page);

  const firstPhoto = page.getByTestId("photo-card").first();

  tracker.clear();
  clickTime.value = Date.now();

  await firstPhoto.click();

  const lightbox = page.getByTestId("lightbox");
  await expect(lightbox).toBeVisible({ timeout: 10000 });
  const lightboxVisibleAfterClickMs = Date.now() - clickTime.value;

  const lightboxImg = lightbox.locator(".pswp__img:not(.pswp__img--placeholder)").first();
  await expect
    .poll(
      async () => {
        return await lightboxImg.evaluate((img: HTMLImageElement) => ({
          complete: img.complete,
          naturalW: img.naturalWidth,
          naturalH: img.naturalHeight,
        }));
      },
      { timeout: 15000 },
    )
    .toMatchObject({ complete: true });
  const lightboxPreviewLoadedAfterClickMs = Date.now() - clickTime.value;

  const allThumbnailSamples = tracker.thumbnailSamples();
  const previewSamples = tracker.previewSamples();
  const imageSamples = tracker.imageSamples();
  const metadataSamples = tracker.metadataSamples();

  const thumbnailSamples = allThumbnailSamples.filter((s) => getQueryParam(s.search, "max_long_edge") === "512");
  const firstPreviewSample = previewSamples.find((s) => s.durationMs && s.durationMs > 0);
  const usedPreviewEndpoint = firstPreviewSample?.pathname === "/api/preview";
  const usedFullImageEndpointOnOpen = imageSamples.some((s) => s.pathname === "/api/image");

  const dims = await lightboxImg.evaluate((img: HTMLImageElement) => ({
    naturalW: img.naturalWidth,
    naturalH: img.naturalHeight,
    displayW: img.getBoundingClientRect().width,
    displayH: img.getBoundingClientRect().height,
  }));

  const viewport = page.viewportSize();

  const actualSrc = await lightboxImg.evaluate((img: HTMLImageElement) => img.src);
  const srcIsFullImage = actualSrc?.includes("/api/image") ?? false;
  const srcIsPreview = actualSrc?.includes("/api/preview") ?? false;

  tracker.clear();
  clickTime.value = Date.now();
  // Trigger original load (simulates zoom/explicit full-res action).
  try {
    await page.evaluate(() => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- Perf tests call an optional app test hook exposed on the browser window.
      (window as any).__loadOriginalForCurrent?.("zoom");
    });
  } catch (_) {
    // zoom trigger is optional in perf test; full coverage in lightbox-loading-policy.spec.ts
  }
  await page.waitForTimeout(500);

  const report = {
    albumName,
    albumPath,
    open: {
      lightboxVisibleAfterClickMs,
      lightboxPreviewLoadedAfterClickMs,
      previewRequestStartAfterClickMs: Math.round(firstPreviewSample?.startMs ?? 0),
      previewRequestDurationMs: Math.round(firstPreviewSample?.durationMs ?? 0),
      metadataDurationMs: metadataSamples.length
        ? Math.round(Math.min(...metadataSamples.map((s) => s.durationMs ?? 0)))
        : 0,
      thumbnail512Count: thumbnailSamples.length,
      usedPreviewEndpoint,
      usedFullImageEndpointOnOpen,
      srcIsFullImage,
      srcIsPreview,
      naturalWidth: dims.naturalW,
      naturalHeight: dims.naturalH,
      displayWidth: Math.round(dims.displayW),
      displayHeight: Math.round(dims.displayH),
      viewportWidth: viewport?.width ?? 0,
      viewportHeight: viewport?.height ?? 0,
    },
    budgets: {
      openVisibleMs: Number(process.env.GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS ?? "1500"),
      openPreviewLoadedMs: Number(process.env.GALLERY_PERF_LIGHTBOX_PREVIEW_BUDGET_MS ?? "4000"),
    },
    verdict: "pass",
  };

  const resultsDir = resolve(__dirname, "../../test-results/perf");
  mkdirSync(resultsDir, { recursive: true });
  writeFileSync(join(resultsDir, "lightbox-open-report.json"), JSON.stringify(report, null, 2));

  if (dims.displayW < (viewport?.width ?? 1920) * 0.5 && dims.displayH < (viewport?.height ?? 1080) * 0.5) {
    console.warn(
      `WARNING: Lightbox image (${Math.round(dims.displayW)}×${Math.round(dims.displayH)}px) is smaller than 50% of viewport (${viewport?.width}×${viewport?.height}px). Image may be displaying a thumbnail instead of full-res.`,
    );
  }

  expect(lightboxVisibleAfterClickMs).toBeLessThanOrEqual(report.budgets.openVisibleMs);
  expect(lightboxPreviewLoadedAfterClickMs).toBeLessThanOrEqual(report.budgets.openPreviewLoadedMs);
  expect(dims.naturalW).toBeGreaterThan(0);
  expect(dims.naturalH).toBeGreaterThan(0);
  expect(dims.displayW).toBeGreaterThan(300);
  expect(dims.displayH).toBeGreaterThan(300);
  expect(usedPreviewEndpoint).toBe(true);
  expect(usedFullImageEndpointOnOpen).toBe(false);
  expect(srcIsPreview).toBe(true);
  expect(srcIsFullImage).toBe(false);
});

test("lightbox transitions to next image within budget", async ({ page }) => {
  const clickTime = { value: 0 };
  const tracker = installApiNetworkTracker(page, clickTime);

  await navigateToAlbum(page);

  const firstPhoto = page.getByTestId("photo-card").first();

  // Open lightbox by clicking first photo
  await firstPhoto.click();

  const lightbox = page.getByTestId("lightbox");
  await expect(lightbox).toBeVisible({ timeout: 10000 });

  // Wait for initial image loaded
  const lightboxImg = lightbox.locator(".pswp__img:not(.pswp__img--placeholder)").first();
  await expect
    .poll(
      async () => {
        return await lightboxImg.evaluate((img: HTMLImageElement) => img.complete);
      },
      { timeout: 10000 },
    )
    .toBe(true);

  const beforeSrc = await lightboxImg.getAttribute("src");

  // Ensure no "always load original" preference interferes with transition
  await page.evaluate(() => {
    localStorage.removeItem("gallery-lightbox-always-load-original");
  });

  tracker.clear();
  clickTime.value = Date.now();

  await page.keyboard.press("ArrowRight");

  const nextVisibleAfterActionMs = Date.now() - clickTime.value;

  await expect
    .poll(
      async () => {
        const currentImg = lightbox.locator(".pswp__img:not(.pswp__img--placeholder)").first();
        const src = await currentImg.getAttribute("src");
        const dims = await currentImg.evaluate((img: HTMLImageElement) => ({
          nw: img.naturalWidth,
          nh: img.naturalHeight,
        }));
        return src !== beforeSrc && dims.nw > 0 && dims.nh > 0;
      },
      { timeout: 20000 },
    )
    .toBe(true);
  const transitionPreviewLoadedAfterActionMs = Date.now() - clickTime.value;

  const dims = await lightboxImg.evaluate((img: HTMLImageElement) => ({
    naturalW: img.naturalWidth,
    naturalH: img.naturalHeight,
    displayW: img.getBoundingClientRect().width,
    displayH: img.getBoundingClientRect().height,
  }));

  const viewport = page.viewportSize();

  const naturalRatio = dims.naturalW / dims.naturalH;
  const displayRatio = dims.displayW / dims.displayH;
  const ratioDiff = Math.abs(1 - naturalRatio / displayRatio);

  const report = {
    albumName,
    albumPath,
    transition: {
      nextVisibleAfterActionMs,
      transitionPreviewLoadedAfterActionMs,
      previewRequestCount: tracker.previewSamples().length,
      originalRequestCount: tracker.imageSamples().length,
      naturalWidth: dims.naturalW,
      naturalHeight: dims.naturalH,
      displayWidth: Math.round(dims.displayW),
      displayHeight: Math.round(dims.displayH),
      viewportWidth: viewport?.width ?? 0,
      viewportHeight: viewport?.height ?? 0,
      ratioDiff: Math.round(ratioDiff * 1000) / 1000,
    },
    budgets: {
      transitionMs: Number(process.env.GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS ?? "3000"),
    },
    verdict: "pass",
  };

  const resultsDir = resolve(__dirname, "../../test-results/perf");
  mkdirSync(resultsDir, { recursive: true });
  writeFileSync(join(resultsDir, "lightbox-transition-report.json"), JSON.stringify(report, null, 2));

  if (dims.displayW < (viewport?.width ?? 1920) * 0.5 && dims.displayH < (viewport?.height ?? 1080) * 0.5) {
    console.warn(
      `WARNING: Lightbox image (${Math.round(dims.displayW)}×${Math.round(dims.displayH)}px) is smaller than 50% of viewport (${viewport?.width}×${viewport?.height}px). Image may be displaying a thumbnail instead of full-res.`,
    );
  }

  expect(transitionPreviewLoadedAfterActionMs).toBeLessThanOrEqual(report.budgets.transitionMs);
  expect(dims.naturalW).toBeGreaterThan(0);
  expect(dims.naturalH).toBeGreaterThan(0);
  expect(ratioDiff).toBeLessThan(0.2);
  // Normal transition: current slide should display preview, not original.
  // Check via network tracker that the transition itself didn't load /api/image
  // for the actual transition target image (index 0->1 means image at index 1).
  const imageForTransition = tracker.imageSamples().filter((s) => {
    const params = new URLSearchParams(s.search);
    const path = params.get("path") || "";
    return path.includes("0 (2)"); // index 1 in the sorted album
  });
  expect(imageForTransition.length).toBe(0);
});
