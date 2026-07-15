/**
 * Purpose:
 * Measures lightbox open and next-image transition timing against real endpoint usage.
 *
 * Guarantees:
 * * preview and thumbnail request timing is captured around lightbox interactions
 * * full original image fetches are surfaced when they affect normal open performance
 * * multi-sample (5 iterations) with p95 reporting instead of single measurement
 * * uses performance.now() (monotonic, sub-ms) for all timing — never Date.now()
 *
 * Run when:
 * * changing lightbox source loading, PhotoSwipe transitions, or preview endpoint behavior
 * * validating real-data lightbox performance before release
 */

import { fileURLToPath } from "node:url";
import { expect, test } from "../helpers/monitorErrors";
import type { Locator, Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve, join, dirname as pathDirname } from "node:path";
import { LIGHTBOX_PERF_MARKS } from "../../../src/utils/lightboxPerformance";
import {
  compactStats,
  installApiNetworkTracker,
  loadBudgets,
  networkContractViolations,
  nowMs,
  resolvePerfResultsDir,
  waitForNetworkQuiet,
} from "./perf-utils";

const __filename = fileURLToPath(import.meta.url);
const __dirname = pathDirname(__filename);

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const albumName = process.env.GALLERY_PERF_ALBUM_NAME ?? "a1111";
const albumPath = process.env.GALLERY_PERF_ALBUM_PATH ?? "";

const SAMPLE_COUNT = Number(process.env.GALLERY_PERF_LIGHTBOX_SAMPLES ?? "5");
const budgets = loadBudgets();
const perfE2EEnabled =
  process.env.GALLERY_PERF_E2E === "1" ||
  process.env.GALLERY_PERF_USE_FIXTURE === "1" ||
  Boolean(process.env.GALLERY_PERF_ALBUM_PATH);

test.skip(
  !perfE2EEnabled,
  "Set GALLERY_PERF_E2E=1 with a real gallery backend or fixture to run lightbox performance diagnostics.",
);

if (perfE2EEnabled && (!Number.isInteger(SAMPLE_COUNT) || SAMPLE_COUNT < 2)) {
  throw new Error("GALLERY_PERF_LIGHTBOX_SAMPLES must be an integer >= 2 so warm-cache p95 is meaningful.");
}

async function navigateToAlbum(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
    localStorage.removeItem("gallery-lightbox-always-load-original");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

  const enterBtn = page.getByRole("button", { name: /enter gallery/i });
  const album = page.getByText(albumName, { exact: false }).first();
  await expect
    .poll(async () => (await enterBtn.isVisible().catch(() => false)) || (await album.isVisible().catch(() => false)), {
      timeout: 15000,
    })
    .toBe(true);

  if (await enterBtn.isVisible().catch(() => false)) {
    await enterBtn.click();
    await expect(album).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(1000);
  }

  await expect(album).toBeVisible({ timeout: 15000 });
  await album.click();

  const firstPhoto = page.getByTestId("photo-card").first();
  await expect(firstPhoto).toBeVisible({ timeout: 15000 });

  return firstPhoto;
}

type OpenIteration = {
  eventToOverlayMs: number;
  derivativeQueueWaitMs: number;
  renderEncodePersistMs: number;
  networkResponseMs: number;
  browserResourceLoadMs: number;
  browserDecodeVisualReadyMs: number;
  visualReadyAfterEventMs: number;
  previewRequestDurationMs: number;
  metadataDurationMs: number;
  usedPreviewEndpoint: boolean;
  usedFullImageEndpointOnOpen: boolean;
  srcIsFullImage: boolean;
  srcIsPreview: boolean;
  naturalWidth: number;
  naturalHeight: number;
  displayWidth: number;
  displayHeight: number;
  viewportWidth: number;
  viewportHeight: number;
  networkContractViolations: string[];
};

type BrowserVisualTiming = {
  visualReadyAfterInteractionMs: number;
  resourceLoadMs: number;
  responseToDecodedMs: number;
};

async function waitForPreviewDecoded(lightboxImg: Locator, interactionMark: string): Promise<BrowserVisualTiming> {
  return lightboxImg.evaluate(async (img: HTMLImageElement, markName) => {
    const isPreviewReady = () =>
      img.src.includes("/api/preview") && img.complete && img.naturalWidth > 0 && img.naturalHeight > 0;

    if (!isPreviewReady()) {
      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(() => {
          cleanup();
          reject(new Error(`Timed out waiting for decoded preview image; current src=${img.src}`));
        }, 15_000);
        const observer = new MutationObserver(() => {
          if (isPreviewReady()) {
            cleanup();
            resolve();
          }
        });
        const onLoad = () => {
          if (isPreviewReady()) {
            cleanup();
            resolve();
          }
        };
        const onError = () => {
          cleanup();
          reject(new Error(`Preview image failed to load; current src=${img.src}`));
        };
        const cleanup = () => {
          window.clearTimeout(timeout);
          observer.disconnect();
          img.removeEventListener("load", onLoad);
          img.removeEventListener("error", onError);
        };

        observer.observe(img, { attributes: true, attributeFilter: ["src", "srcset"] });
        img.addEventListener("load", onLoad);
        img.addEventListener("error", onError);
        onLoad();
      });
    }

    await img.decode();
    const readyAt = performance.now();
    const interactionStart = performance.getEntriesByName(markName, "mark").at(-1)?.startTime;
    if (interactionStart === undefined) {
      throw new Error(`Missing browser performance mark ${markName}`);
    }
    const resource = performance.getEntriesByName(img.currentSrc || img.src, "resource").at(-1) as
      | PerformanceResourceTiming
      | undefined;
    return {
      visualReadyAfterInteractionMs: readyAt - interactionStart,
      resourceLoadMs: resource ? resource.responseEnd - resource.startTime : 0,
      responseToDecodedMs: resource ? Math.max(0, readyAt - resource.responseEnd) : 0,
    };
  }, interactionMark);
}

async function browserMarkDuration(page: Page, startMark: string, endMark: string): Promise<number> {
  return page.evaluate(
    ({ startMark, endMark }) => {
      const start = performance.getEntriesByName(startMark, "mark").at(-1)?.startTime;
      const end = performance.getEntriesByName(endMark, "mark").at(-1)?.startTime;
      return start === undefined || end === undefined ? 0 : end - start;
    },
    { startMark, endMark },
  );
}

async function armClickPerformanceMark(target: Locator, markName: string): Promise<void> {
  await target.evaluate(
    (element: HTMLElement, marks) => {
      performance.clearMarks(marks.start);
      performance.clearMarks(marks.overlay);
      element.addEventListener(
        "click",
        () => {
          performance.mark(marks.start);
        },
        { capture: true, once: true },
      );
    },
    { start: markName, overlay: LIGHTBOX_PERF_MARKS.overlayPainted },
  );
}

function activeLightboxImage(lightbox: Locator): Locator {
  return lightbox.locator('.pswp__item[aria-hidden="false"] .pswp__img:not(.pswp__img--placeholder)').first();
}

async function runOpenIteration(page: Page): Promise<OpenIteration> {
  const clickTime = { value: 0 };
  const tracker = installApiNetworkTracker(page, clickTime);

  await navigateToAlbum(page);

  const firstPhoto = page.getByTestId("photo-card").first();

  tracker.clear();
  clickTime.value = nowMs();
  await armClickPerformanceMark(firstPhoto, LIGHTBOX_PERF_MARKS.openStart);

  await firstPhoto.click();

  const lightbox = page.getByTestId("lightbox");
  await expect(lightbox).toBeVisible({ timeout: 10000 });
  await expect
    .poll(() => browserMarkDuration(page, LIGHTBOX_PERF_MARKS.openStart, LIGHTBOX_PERF_MARKS.overlayPainted), {
      timeout: 5000,
      message: "wait for browser-native lightbox overlay paint marks",
    })
    .toBeGreaterThan(0);
  const eventToOverlayMs = Math.round(
    await browserMarkDuration(page, LIGHTBOX_PERF_MARKS.openStart, LIGHTBOX_PERF_MARKS.overlayPainted),
  );

  const lightboxImg = activeLightboxImage(lightbox);
  const visualTiming = await waitForPreviewDecoded(lightboxImg, LIGHTBOX_PERF_MARKS.openStart);

  const actualSrc = await lightboxImg.evaluate((img: HTMLImageElement) => img.src);
  await expect
    .poll(() => tracker.previewSamples().find((sample) => sample.url === actualSrc)?.durationMs ?? 0, {
      timeout: 5000,
      message: `wait for completed preview timing sample: ${actualSrc}`,
    })
    .toBeGreaterThan(0);

  await tracker.waitForSettled({ paths: ["/api/preview", "/api/image", "/api/metadata"], minimum: 1 });
  const previewSamples = tracker.previewSamples();
  const imageSamples = tracker.imageSamples();
  const metadataSamples = tracker.metadataSamples();

  const firstPreviewSample = previewSamples.find((sample) => sample.url === actualSrc);
  const usedPreviewEndpoint = firstPreviewSample?.pathname === "/api/preview";
  const usedFullImageEndpointOnOpen = imageSamples.some((s) => s.pathname === "/api/image");

  const dims = await lightboxImg.evaluate((img: HTMLImageElement) => ({
    naturalW: img.naturalWidth,
    naturalH: img.naturalHeight,
    displayW: img.getBoundingClientRect().width,
    displayH: img.getBoundingClientRect().height,
  }));

  const viewport = page.viewportSize();

  const srcIsFullImage = actualSrc?.includes("/api/image") ?? false;
  const srcIsPreview = actualSrc?.includes("/api/preview") ?? false;
  const contractViolations = [
    ...networkContractViolations(previewSamples, { minimum: 1, allowedStatuses: [200, 304] }),
    ...networkContractViolations(imageSamples, { allowedStatuses: [200, 304] }),
    ...networkContractViolations(metadataSamples, { allowedStatuses: [200, 304] }),
  ];
  tracker.dispose();

  return {
    eventToOverlayMs,
    derivativeQueueWaitMs: Math.round(firstPreviewSample?.serverQueueWaitMs ?? 0),
    renderEncodePersistMs: Math.round(firstPreviewSample?.serverRenderEncodePersistMs ?? 0),
    networkResponseMs: Math.round(
      Math.max(
        0,
        (firstPreviewSample?.durationMs ?? 0) -
          (firstPreviewSample?.serverQueueWaitMs ?? 0) -
          (firstPreviewSample?.serverRenderEncodePersistMs ?? 0),
      ),
    ),
    browserResourceLoadMs: Math.round(visualTiming.resourceLoadMs),
    browserDecodeVisualReadyMs: Math.round(visualTiming.responseToDecodedMs),
    visualReadyAfterEventMs: Math.round(visualTiming.visualReadyAfterInteractionMs),
    previewRequestDurationMs: Math.round(firstPreviewSample?.durationMs ?? 0),
    metadataDurationMs: metadataSamples.length
      ? Math.round(Math.min(...metadataSamples.map((s) => s.durationMs ?? 0)))
      : 0,
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
    networkContractViolations: contractViolations,
  };
}

test("lightbox opens first photo within budget", async ({ page }) => {
  const iterations: OpenIteration[] = [];
  for (let i = 0; i < SAMPLE_COUNT; i++) {
    if (i > 0) {
      await page.context().clearCookies();
    }
    const result = await runOpenIteration(page);
    iterations.push(result);
    if (i < SAMPLE_COUNT - 1) {
      await page.waitForTimeout(500);
    }
  }

  const visibleDurations = iterations.map((r) => r.eventToOverlayMs);
  const previewRequestDurations = iterations.map((r) => r.previewRequestDurationMs);
  const warmPreviewRequestDurations = iterations.slice(1).map((r) => r.previewRequestDurationMs);
  const visualReadyDurations = iterations.map((r) => r.visualReadyAfterEventMs);
  const browserDecodeDurations = iterations.map((r) => r.browserDecodeVisualReadyMs);

  const visibleP95 = Math.round(compactStats(visibleDurations).p95);
  const previewRequestP95 = Math.round(compactStats(previewRequestDurations).p95);
  const warmPreviewRequestP95 = Math.round(compactStats(warmPreviewRequestDurations).p95);
  const visualReadyP95 = Math.round(compactStats(visualReadyDurations).p95);
  const browserDecodeP95 = Math.round(compactStats(browserDecodeDurations).p95);
  const contractViolations = iterations.flatMap((iteration, index) =>
    iteration.networkContractViolations.map((violation) => `iteration ${index + 1}: ${violation}`),
  );

  // Use the last iteration's image-quality assertions as representative — these
  // are binary invariants (preview endpoint used, no full-image on open, image
  // not too small) that don't benefit from p95 aggregation.
  const last = iterations[iterations.length - 1];

  const report = {
    albumName,
    albumPath,
    sampleCount: iterations.length,
    iterations,
    samples: {
      cold: iterations.slice(0, 1),
      warm: iterations.slice(1),
    },
    aggregate: {
      visibleP95Ms: visibleP95,
      previewRequestP95Ms: previewRequestP95,
      warmPreviewRequestP95Ms: warmPreviewRequestP95,
      initialPreviewRequestMs: iterations[0].previewRequestDurationMs,
      visualReadyP95Ms: visualReadyP95,
      browserDecodeVisualReadyP95Ms: browserDecodeP95,
      networkContractViolations: contractViolations,
    },
    budgets: budgets.lightbox,
    budgetSource: "frontend/tests/e2e/perf/perf-budgets.json[lightbox]",
    verdict:
      visibleP95 <= budgets.lightbox.open_ms &&
      visualReadyP95 <= budgets.lightbox.visual_ready_ms &&
      contractViolations.length === 0
        ? "pass"
        : "fail",
  };

  const resultsDir = resolvePerfResultsDir(resolve(__dirname, "../../../test-results/perf"));
  mkdirSync(resultsDir, { recursive: true });
  writeFileSync(join(resultsDir, "lightbox-open-report.json"), JSON.stringify(report, null, 2));

  if (
    last.displayWidth < (last.viewportWidth || 1920) * 0.5 &&
    last.displayHeight < (last.viewportHeight || 1080) * 0.5
  ) {
    console.warn(
      `WARNING: Lightbox image (${last.displayWidth}×${last.displayHeight}px) is smaller than 50% of viewport (${last.viewportWidth}×${last.viewportHeight}px). Image may be displaying a thumbnail instead of full-res.`,
    );
  }

  expect(visibleP95).toBeLessThanOrEqual(budgets.lightbox.open_ms);
  expect(visualReadyP95).toBeLessThanOrEqual(budgets.lightbox.visual_ready_ms);
  expect(contractViolations).toEqual([]);
  // Binary invariants checked on every iteration — if any iteration violated
  // them, the lightbox-loading-policy.spec.ts covers it; here we assert the
  // representative last sample plus a pass-rate check across iterations.
  const passRate = iterations.filter((r) => r.usedPreviewEndpoint && !r.usedFullImageEndpointOnOpen).length;
  expect(passRate).toBe(iterations.length);
  expect(last.naturalWidth).toBeGreaterThan(0);
  expect(last.naturalHeight).toBeGreaterThan(0);
  expect(last.displayWidth).toBeGreaterThan(300);
  expect(last.displayHeight).toBeGreaterThan(300);
  expect(last.srcIsPreview).toBe(true);
  expect(last.srcIsFullImage).toBe(false);
});

type TransitionIteration = {
  nextVisibleAfterActionMs: number;
  transitionPreviewLoadedAfterActionMs: number;
  previewRequestCount: number;
  originalRequestCount: number;
  naturalWidth: number;
  naturalHeight: number;
  displayWidth: number;
  displayHeight: number;
  viewportWidth: number;
  viewportHeight: number;
  ratioDiff: number;
  currentSrc: string;
  networkContractViolations: string[];
};

async function runTransitionIteration(page: Page): Promise<TransitionIteration> {
  const clickTime = { value: 0 };
  const tracker = installApiNetworkTracker(page, clickTime);

  await navigateToAlbum(page);

  const firstPhoto = page.getByTestId("photo-card").first();

  await armClickPerformanceMark(firstPhoto, LIGHTBOX_PERF_MARKS.openStart);
  await firstPhoto.click();

  const lightbox = page.getByTestId("lightbox");
  await expect(lightbox).toBeVisible({ timeout: 10000 });

  const lightboxImg = activeLightboxImage(lightbox);
  await expect
    .poll(
      async () => {
        return await lightboxImg.evaluate((img: HTMLImageElement) => img.complete);
      },
      { timeout: 10000 },
    )
    .toBe(true);
  await waitForPreviewDecoded(lightboxImg, LIGHTBOX_PERF_MARKS.openStart);

  const beforeSrc = await lightboxImg.getAttribute("src");

  await page.evaluate(() => {
    localStorage.removeItem("gallery-lightbox-always-load-original");
  });

  tracker.clear();
  clickTime.value = nowMs();

  await page.keyboard.press("ArrowRight");

  const nextVisibleAfterActionMs = Math.round(nowMs() - clickTime.value);

  await expect
    .poll(
      async () => {
        const currentImg = activeLightboxImage(lightbox);
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
  const currentImg = activeLightboxImage(lightbox);
  const transitionVisualTiming = await waitForPreviewDecoded(currentImg, LIGHTBOX_PERF_MARKS.transitionStart);
  const transitionPreviewLoadedAfterActionMs = Math.round(transitionVisualTiming.visualReadyAfterInteractionMs);
  const currentSrc = await currentImg.evaluate((img: HTMLImageElement) => img.src);
  await waitForNetworkQuiet(page, 250, 3000);
  await tracker.waitForSettled({ paths: ["/api/preview", "/api/image"], minimum: 0 });
  const dims = await currentImg.evaluate((img: HTMLImageElement) => ({
    naturalW: img.naturalWidth,
    naturalH: img.naturalHeight,
    displayW: img.getBoundingClientRect().width,
    displayH: img.getBoundingClientRect().height,
  }));

  const viewport = page.viewportSize();

  const naturalRatio = dims.naturalW / dims.naturalH;
  const displayRatio = dims.displayW / dims.displayH;
  const ratioDiff = Math.abs(1 - naturalRatio / displayRatio);

  const previewSamples = tracker.previewSamples();
  const imageSamples = tracker.imageSamples();
  const contractViolations = [
    ...networkContractViolations(previewSamples, { allowedStatuses: [200, 304] }),
    ...networkContractViolations(imageSamples, { allowedStatuses: [200, 304] }),
  ];
  tracker.dispose();

  return {
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
    currentSrc,
    networkContractViolations: contractViolations,
  };
}

test("lightbox transitions to next image within budget", async ({ page }) => {
  const iterations: TransitionIteration[] = [];
  for (let i = 0; i < SAMPLE_COUNT; i++) {
    if (i > 0) {
      await page.context().clearCookies();
    }
    const result = await runTransitionIteration(page);
    iterations.push(result);
    if (i < SAMPLE_COUNT - 1) {
      await page.waitForTimeout(500);
    }
  }

  const transitionDurations = iterations.map((r) => r.transitionPreviewLoadedAfterActionMs);
  const transitionP95 = Math.round(compactStats(transitionDurations).p95);
  const contractViolations = iterations.flatMap((iteration, index) =>
    iteration.networkContractViolations.map((violation) => `iteration ${index + 1}: ${violation}`),
  );
  const originalRequestCount = iterations.reduce((total, iteration) => total + iteration.originalRequestCount, 0);

  const last = iterations[iterations.length - 1];

  const report = {
    albumName,
    albumPath,
    sampleCount: iterations.length,
    iterations,
    aggregate: {
      transitionPreviewLoadedP95Ms: transitionP95,
      originalRequestCount,
      networkContractViolations: contractViolations,
    },
    budgets: { transitionMs: budgets.lightbox.transition_ms },
    budgetSource: "frontend/tests/e2e/perf/perf-budgets.json[lightbox].transition_ms",
    verdict:
      transitionP95 <= budgets.lightbox.transition_ms && originalRequestCount === 0 && contractViolations.length === 0
        ? "pass"
        : "fail",
  };

  const resultsDir = resolvePerfResultsDir(resolve(__dirname, "../../../test-results/perf"));
  mkdirSync(resultsDir, { recursive: true });
  writeFileSync(join(resultsDir, "lightbox-transition-report.json"), JSON.stringify(report, null, 2));

  if (
    last.displayWidth < (last.viewportWidth || 1920) * 0.5 &&
    last.displayHeight < (last.viewportHeight || 1080) * 0.5
  ) {
    console.warn(
      `WARNING: Lightbox image (${last.displayWidth}×${last.displayHeight}px) is smaller than 50% of viewport (${last.viewportWidth}×${last.viewportHeight}px). Image may be displaying a thumbnail instead of full-res.`,
    );
  }

  expect(transitionP95).toBeLessThanOrEqual(budgets.lightbox.transition_ms);
  expect(originalRequestCount).toBe(0);
  expect(contractViolations).toEqual([]);
  // Every iteration must keep natural dims > 0 and stay within aspect ratio.
  for (const it of iterations) {
    expect(it.naturalWidth).toBeGreaterThan(0);
    expect(it.naturalHeight).toBeGreaterThan(0);
    expect(it.ratioDiff).toBeLessThan(0.2);
    expect(it.originalRequestCount).toBe(0);
  }
});
