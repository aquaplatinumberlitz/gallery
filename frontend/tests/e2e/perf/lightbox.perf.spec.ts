/**
 * Purpose:
 * Measures lightbox open and next-image transition timing against real endpoint usage.
 *
 * Guarantees:
 * * preview and thumbnail request timing is captured around lightbox interactions
 * * full original image fetches are surfaced when they affect normal open performance
 * * multi-sample (5 iterations) with p95 reporting instead of single measurement
 * * uses performance.now() (monotonic, sub-ms) for all timing — never Date.now()
 * * visual ready (open and next-slide) is timed in the page by an observer armed before the
 *   interaction; it stamps the first animation frame where the active slide's preview image is
 *   complete, decoded and visible, so Playwright's polling does not add to it. The older harness
 *   figure is kept as `harnessObservedReadyMs` / `harnessObservedTransitionMs` (diagnostic only,
 *   not gated) for one release. See docs/testing/PERFORMANCE_TESTING.md.
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
  /** In-page visual ready: click mark to the first frame the active preview is complete, decoded and visible. Gated. */
  visualReadyAfterEventMs: number;
  /** Diagnostic only (not gated): the pre-LB-01 harness figure, read after Playwright's polling. */
  harnessObservedReadyMs: number;
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

type VisualReadyTiming = {
  /** Interaction mark to the readiness frame, in ms. */
  visualReadyAfterInteractionMs: number;
  resourceLoadMs: number;
  /** Response end to the readiness frame, in ms. */
  responseToReadyMs: number;
};

const ACTIVE_LIGHTBOX_PREVIEW_SELECTOR =
  '[data-testid="lightbox"] .pswp__item[aria-hidden="false"] .pswp__img:not(.pswp__img--placeholder)';

/**
 * Arms an in-page visual-ready probe. Runs inside the page before the interaction (click or ArrowRight).
 * It stamps performance.now() in the first animation frame where the active slide's preview <img>:
 * is connected, has src containing /api/preview (and is not `excludeSrc`, the slide that was active
 * before the interaction), is complete with naturalWidth/naturalHeight > 0, has finished img.decode(),
 * and is visible. The stamp is taken in the frame, not when the decode promise resolves. A
 * MutationObserver wakes the frame loop on DOM changes; rAF runs the check.
 */
function armVisualReadyProbe(options: { selector: string; excludeSrc: string | null; timeoutMs: number }): void {
  type ProbeResult = { readyAt: number; src: string; resourceLoadMs: number; responseToReadyMs: number };
  type Probe = { result: ProbeResult | null; error: string | null; stop: () => void };
  const host = window as unknown as { __galleryVisualReadyProbe?: Probe };
  host.__galleryVisualReadyProbe?.stop();

  let frameId = 0;
  let timeoutId = 0;
  let observer: MutationObserver | null = null;
  let decodedSrc: string | null = null;
  let decodingSrc: string | null = null;
  let finished = false;

  const probe: Probe = {
    result: null,
    error: null,
    stop: () => {
      finished = true;
      if (frameId) cancelAnimationFrame(frameId);
      frameId = 0;
      window.clearTimeout(timeoutId);
      observer?.disconnect();
    },
  };
  host.__galleryVisualReadyProbe = probe;

  const isVisible = (img: HTMLImageElement): boolean => {
    const style = getComputedStyle(img);
    const rect = img.getBoundingClientRect();
    return (
      style.display !== "none" &&
      style.visibility !== "hidden" &&
      Number(style.opacity) >= 0.99 &&
      rect.width > 0 &&
      rect.height > 0
    );
  };

  const frame = () => {
    frameId = 0;
    if (finished) return;
    const img = document.querySelector<HTMLImageElement>(options.selector);
    if (
      img &&
      img.src.includes("/api/preview") &&
      img.src !== options.excludeSrc &&
      img.complete &&
      img.naturalWidth > 0 &&
      img.naturalHeight > 0
    ) {
      const src = img.src;
      if (decodedSrc !== src && decodingSrc !== src) {
        decodingSrc = src;
        img.decode().then(
          () => {
            decodedSrc = src;
          },
          () => {
            // Retried on a later frame; the timeout bounds a persistent failure.
            if (decodingSrc === src) decodingSrc = null;
          },
        );
      }
      if (decodedSrc === src && isVisible(img)) {
        // Stamp in this frame, not in the decode promise continuation.
        const readyAt = performance.now();
        const resource = performance.getEntriesByName(img.currentSrc || src, "resource").at(-1) as
          | PerformanceResourceTiming
          | undefined;
        probe.result = {
          readyAt,
          src,
          resourceLoadMs: resource ? resource.responseEnd - resource.startTime : 0,
          responseToReadyMs: resource ? Math.max(0, readyAt - resource.responseEnd) : 0,
        };
        probe.stop();
        return;
      }
    }
    frameId = window.requestAnimationFrame(frame);
  };

  observer = new MutationObserver(() => {
    if (!frameId && !finished) frameId = window.requestAnimationFrame(frame);
  });
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["src", "class", "style", "aria-hidden"],
  });
  timeoutId = window.setTimeout(() => {
    if (!probe.result) probe.error = `visual ready probe timed out after ${options.timeoutMs} ms: ${options.selector}`;
    probe.stop();
  }, options.timeoutMs);
  frameId = window.requestAnimationFrame(frame);
}

/** Waits for the armed probe to stamp, then reports it against the named interaction mark. */
async function readVisualReadyProbe(page: Page, interactionMark: string): Promise<VisualReadyTiming> {
  const readState = () =>
    page.evaluate((markName) => {
      const host = window as unknown as {
        __galleryVisualReadyProbe?: {
          result: { readyAt: number; src: string; resourceLoadMs: number; responseToReadyMs: number } | null;
          error: string | null;
        };
      };
      const probe = host.__galleryVisualReadyProbe;
      return {
        result: probe?.result ?? null,
        error: probe?.error ?? null,
        markStart: performance.getEntriesByName(markName, "mark").at(-1)?.startTime ?? null,
      };
    }, interactionMark);

  let state = await readState();
  await expect
    .poll(
      async () => {
        state = await readState();
        return state.result !== null || state.error !== null;
      },
      { timeout: 15000, message: `wait for in-page visual ready probe after ${interactionMark}` },
    )
    .toBe(true);
  if (state.error) throw new Error(state.error);
  if (!state.result || state.markStart === null) {
    throw new Error(`Visual ready probe has no result or missing interaction mark ${interactionMark}`);
  }
  return {
    visualReadyAfterInteractionMs: state.result.readyAt - state.markStart,
    resourceLoadMs: state.result.resourceLoadMs,
    responseToReadyMs: state.result.responseToReadyMs,
  };
}

/**
 * Harness wait kept for the image-quality checks and as the diagnostic `harnessObservedReadyMs`.
 * It starts only after Playwright's visibility and polling steps, so it overstates the ready time
 * (LB-01). Gated numbers come from `armVisualReadyProbe`.
 */
async function waitForPreviewDecoded(lightboxImg: Locator, interactionMark: string): Promise<number> {
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
    return readyAt - interactionStart;
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
  await page.evaluate(armVisualReadyProbe, {
    selector: ACTIVE_LIGHTBOX_PREVIEW_SELECTOR,
    excludeSrc: null,
    timeoutMs: 15000,
  });

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
  const harnessObservedReadyMs = await waitForPreviewDecoded(lightboxImg, LIGHTBOX_PERF_MARKS.openStart);
  const visualTiming = await readVisualReadyProbe(page, LIGHTBOX_PERF_MARKS.openStart);

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
    browserDecodeVisualReadyMs: Math.round(visualTiming.responseToReadyMs),
    visualReadyAfterEventMs: Math.round(visualTiming.visualReadyAfterInteractionMs),
    harnessObservedReadyMs: Math.round(harnessObservedReadyMs),
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
  const harnessObservedReadyDurations = iterations.map((r) => r.harnessObservedReadyMs);

  const visibleP95 = Math.round(compactStats(visibleDurations).p95);
  const previewRequestP95 = Math.round(compactStats(previewRequestDurations).p95);
  const warmPreviewRequestP95 = Math.round(compactStats(warmPreviewRequestDurations).p95);
  const visualReadyP95 = Math.round(compactStats(visualReadyDurations).p95);
  const browserDecodeP95 = Math.round(compactStats(browserDecodeDurations).p95);
  const harnessObservedReadyP95 = Math.round(compactStats(harnessObservedReadyDurations).p95);
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
      visualReadySource: "in-page-probe (LB-01): first frame where the active preview is complete, decoded and visible",
      browserDecodeVisualReadyP95Ms: browserDecodeP95,
      // Diagnostic only, not gated: the pre-LB-01 harness figure, kept for one release.
      harnessObservedReadyP95Ms: harnessObservedReadyP95,
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
  /** In-page visual ready: ArrowRight keydown mark to the next active slide's decoded, visible preview. Gated. */
  transitionPreviewLoadedAfterActionMs: number;
  /** Diagnostic only (not gated): the pre-LB-01 harness figure, kept for one release. */
  harnessObservedTransitionMs: number;
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
  const beforeAbsoluteSrc = await lightboxImg.evaluate((img: HTMLImageElement) => img.src);

  await page.evaluate(() => {
    localStorage.removeItem("gallery-lightbox-always-load-original");
  });

  tracker.clear();
  clickTime.value = nowMs();

  // Armed before the keypress so the first frame where the next slide is ready is caught.
  // The slide that was active before ArrowRight is excluded.
  await page.evaluate(armVisualReadyProbe, {
    selector: ACTIVE_LIGHTBOX_PREVIEW_SELECTOR,
    excludeSrc: beforeAbsoluteSrc,
    timeoutMs: 20000,
  });

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
  const harnessObservedTransitionMs = Math.round(
    await waitForPreviewDecoded(currentImg, LIGHTBOX_PERF_MARKS.transitionStart),
  );
  const transitionVisualTiming = await readVisualReadyProbe(page, LIGHTBOX_PERF_MARKS.transitionStart);
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
    harnessObservedTransitionMs,
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
  const harnessObservedTransitionP95 = Math.round(
    compactStats(iterations.map((r) => r.harnessObservedTransitionMs)).p95,
  );
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
      transitionSource:
        "in-page-probe (LB-01): first frame where the next active preview is complete, decoded and visible",
      // Diagnostic only, not gated: the pre-LB-01 harness figure, kept for one release.
      harnessObservedTransitionP95Ms: harnessObservedTransitionP95,
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
