import { expect, test, type Page } from "@playwright/test";
import { installApiNetworkTracker, getQueryParam } from "./perf-utils";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const albumName = process.env.GALLERY_PERF_ALBUM_NAME ?? "test mika";
const albumPath = process.env.GALLERY_PERF_ALBUM_PATH ?? "";

async function navigateToAlbum(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("gallery-root-path", "/home/ubuntu/gallery-repo");
  });

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

  const lightboxImg = lightbox.locator(".pswp__img").first();
  await expect.poll(async () => {
    return await lightboxImg.evaluate((img: HTMLImageElement) => ({
      complete: img.complete,
      naturalW: img.naturalWidth,
      naturalH: img.naturalHeight,
    }));
  }, { timeout: 10000 }).toMatchObject({ complete: true });
  const mainImageLoadedAfterClickMs = Date.now() - clickTime.value;

  const allThumbnailSamples = tracker.thumbnailSamples();
  const imageSamples = tracker.imageSamples();
  const metadataSamples = tracker.metadataSamples();

  const highResThumbnailSamples = allThumbnailSamples.filter(s => {
    const maxSize = getQueryParam(s.search, "max_size");
    return maxSize && Number(maxSize) >= 800;
  });
  const firstThumbSample = highResThumbnailSamples.find(s => s.durationMs && s.durationMs > 0);
  const firstImageSample = imageSamples.find(s => s.durationMs && s.durationMs > 0);
  const usedImageEndpoint = (firstImageSample?.pathname === "/api/image" || firstThumbSample?.pathname === "/api/thumbnail");

  const dims = await lightboxImg.evaluate((img: HTMLImageElement) => ({
    naturalW: img.naturalWidth,
    naturalH: img.naturalHeight,
    displayW: img.getBoundingClientRect().width,
    displayH: img.getBoundingClientRect().height,
  }));

  const report = {
    albumName,
    albumPath,
    open: {
      lightboxVisibleAfterClickMs,
      mainImageLoadedAfterClickMs,
      mainImageRequestStartAfterClickMs: Math.round((firstImageSample ?? firstThumbSample)?.startMs ?? 0),
      mainImageRequestDurationMs: Math.round((firstImageSample ?? firstThumbSample)?.durationMs ?? 0),
      metadataDurationMs: metadataSamples.length ? Math.round(Math.min(...metadataSamples.map(s => s.durationMs ?? 0))) : 0,
      usedImageEndpoint,
      naturalWidth: dims.naturalW,
      naturalHeight: dims.naturalH,
      displayWidth: Math.round(dims.displayW),
      displayHeight: Math.round(dims.displayH),
    },
    budgets: {
      openVisibleMs: Number(process.env.GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS ?? "1500"),
      openImageLoadedMs: Number(process.env.GALLERY_PERF_LIGHTBOX_IMAGE_BUDGET_MS ?? "4000"),
    },
    verdict: "pass",
  };

  console.log(JSON.stringify(report, null, 2));

  expect(lightboxVisibleAfterClickMs).toBeLessThanOrEqual(report.budgets.openVisibleMs);
  expect(mainImageLoadedAfterClickMs).toBeLessThanOrEqual(report.budgets.openImageLoadedMs);
  expect(dims.naturalW).toBeGreaterThan(0);
  expect(dims.naturalH).toBeGreaterThan(0);
  expect(dims.displayW).toBeGreaterThan(300);
  expect(dims.displayH).toBeGreaterThan(300);
  expect(usedImageEndpoint).toBe(true);
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
  const lightboxImg = lightbox.locator(".pswp__img").first();
  await expect.poll(async () => {
    return await lightboxImg.evaluate((img: HTMLImageElement) => img.complete);
  }, { timeout: 10000 }).toBe(true);

  const beforeSrc = await lightboxImg.getAttribute("src");

  tracker.clear();
  clickTime.value = Date.now();

  await page.keyboard.press("ArrowRight");

  await expect.poll(async () => {
    const src = await lightboxImg.getAttribute("src");
    return src !== beforeSrc;
  }, { timeout: 5000 }).toBe(true);
  const nextVisibleAfterActionMs = Date.now() - clickTime.value;

  await expect.poll(async () => {
    return await lightboxImg.evaluate((img: HTMLImageElement) => img.complete);
  }, { timeout: 10000 }).toBe(true);
  const nextImageLoadedAfterActionMs = Date.now() - clickTime.value;

  const dims = await lightboxImg.evaluate((img: HTMLImageElement) => ({
    naturalW: img.naturalWidth,
    naturalH: img.naturalHeight,
    displayW: img.getBoundingClientRect().width,
    displayH: img.getBoundingClientRect().height,
  }));

  const naturalRatio = dims.naturalW / dims.naturalH;
  const displayRatio = dims.displayW / dims.displayH;
  const ratioDiff = Math.abs(1 - naturalRatio / displayRatio);

  const report = {
    albumName,
    albumPath,
    transition: {
      nextVisibleAfterActionMs,
      nextImageLoadedAfterActionMs,
      naturalWidth: dims.naturalW,
      naturalHeight: dims.naturalH,
      displayWidth: Math.round(dims.displayW),
      displayHeight: Math.round(dims.displayH),
      ratioDiff: Math.round(ratioDiff * 1000) / 1000,
    },
    budgets: {
      transitionMs: Number(process.env.GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS ?? "3000"),
    },
    verdict: "pass",
  };

  console.log(JSON.stringify(report, null, 2));

  expect(nextImageLoadedAfterActionMs)
    .toBeLessThanOrEqual(report.budgets.transitionMs);
  expect(dims.naturalW).toBeGreaterThan(0);
  expect(dims.naturalH).toBeGreaterThan(0);
  expect(ratioDiff).toBeLessThan(0.2);
});
