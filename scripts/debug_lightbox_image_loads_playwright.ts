/**
 * Playwright debug script for Gallery Lightbox Image Load Analysis
 * ==================================================================
 *
 * Opens a gallery URL, clicks the first image to open the lightbox,
 * navigates next/previous, and collects all network requests to
 * /api/thumbnail, /api/preview, and /api/image.
 *
 * Usage:
 *   corepack pnpm exec playwright test scripts/debug_lightbox_image_loads_playwright.ts \
 *     --project=chromium
 *
 *   # Custom URL:
 *   GALLERY_BASE_URL=https://150.230.56.153 \
 *   GALLERY_DEBUG_ALBUM=my-album \
 *   GALLERY_ROOT_PATH=/path/to/images \
 *   corepack pnpm exec playwright test scripts/debug_lightbox_image_loads_playwright.ts \
 *     --project=chromium
 *
 * Output:
 *   - Console output with grouped analysis
 *   - debug-lightbox-image-loads.json in the working directory
 */

import { test, expect, type Page, type Request, type Response } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

// ── Config (overridable via env) ────────────────────────────────────────────

const BASE_URL = process.env.GALLERY_BASE_URL ?? "https://150.230.56.153";
const ALBUM_NAME = process.env.GALLERY_DEBUG_ALBUM ?? "";
const ALBUM_PATH = process.env.GALLERY_DEBUG_ALBUM_PATH ?? "";
const ROOT_PATH =
  process.env.GALLERY_ROOT_PATH ??
  (ALBUM_PATH ? ALBUM_PATH.substring(0, ALBUM_PATH.lastIndexOf("/")) : "/home/ubuntu/gallery-repo/test-images");
const LIGHTBOX_WAIT_MS = Number(process.env.GALLERY_DEBUG_LIGHTBOX_WAIT_MS ?? "4000");
const OUTPUT_FILE = process.env.GALLERY_DEBUG_OUTPUT ?? resolve(process.cwd(), "debug-lightbox-image-loads.json");

// ── Types ───────────────────────────────────────────────────────────────────

interface RequestRecord {
  url: string;
  endpoint: "thumbnail" | "preview" | "original";
  path: string; // decoded path param
  queryParams: Record<string, string>;
  startMs: number; // relative to click time
  endMs?: number;
  durationMs?: number;
  status?: number;
  transferSize?: number;
  encodedBodySize?: number;
}

interface ImageGroup {
  path: string;
  endpoints: string[];
  records: RequestRecord[];
  firstSeenMs: number;
  lastSeenMs: number;
}

type Verdict = "OK" | "WARN" | "BAD";

// ── Helpers ─────────────────────────────────────────────────────────────────

function classifyEndpoint(url: string): RequestRecord["endpoint"] | null {
  if (url.includes("/api/thumbnail")) return "thumbnail";
  if (url.includes("/api/preview")) return "preview";
  if (url.includes("/api/image")) return "original";
  return null;
}

function extractQueryParams(url: string): Record<string, string> {
  const params: Record<string, string> = {};
  try {
    const u = new URL(url);
    for (const [k, v] of u.searchParams.entries()) {
      params[k] = v;
    }
  } catch {
    const qs = url.split("?")[1];
    if (qs) {
      qs.split("&").forEach((pair) => {
        const [k, v] = pair.split("=");
        if (k) params[k] = decodeURIComponent(v || "");
      });
    }
  }
  return params;
}

function isCacheHit(transferSize?: number, encodedBodySize?: number): boolean | null {
  if (transferSize === 0 && (encodedBodySize ?? 0) > 0) return true;
  if (transferSize === 0 && (encodedBodySize ?? 0) === 0) return null;
  return false;
}

function cacheLabel(transferSize?: number, encodedBodySize?: number): string {
  const hit = isCacheHit(transferSize, encodedBodySize);
  if (hit === true) return "disk/memory cache";
  if (hit === null) return "unclear";
  return `network (${transferSize ?? "?"} B)`;
}

// ── Network Tracker ─────────────────────────────────────────────────────────

function installTracker(page: Page, clickTimeRef: { value: number }) {
  const records: RequestRecord[] = [];
  const byRequest = new Map<Request, RequestRecord>();

  const shouldTrack = (request: Request) => {
    const url = request.url();
    return classifyEndpoint(url) !== null;
  };

  page.on("request", (request) => {
    if (!shouldTrack(request)) return;
    if (clickTimeRef.value <= 0) return; // ignore pre-click network

    const url = request.url();
    const endpoint = classifyEndpoint(url)!;
    const params = extractQueryParams(url);

    const rec: RequestRecord = {
      url,
      endpoint,
      path: params.path ? decodeURIComponent(params.path) : "",
      queryParams: params,
      startMs: Date.now() - clickTimeRef.value,
    };

    byRequest.set(request, rec);
    records.push(rec);
  });

  page.on("response", async (response: Response) => {
    const request = response.request();
    const rec = byRequest.get(request);
    if (!rec) return;

    rec.endMs = Date.now() - clickTimeRef.value;
    rec.durationMs = rec.endMs - rec.startMs;
    rec.status = response.status();

    // Try to extract transferSize from the response if possible
    try {
      const timing = request.timing();
      // transferSize is only available in Chromium via response.allHeaders() or similar
      // We'll try to get it from the raw response if headers expose it
    } catch (_) {}
  });

  return {
    records,
    thumbnails: () => records.filter((r) => r.endpoint === "thumbnail"),
    previews: () => records.filter((r) => r.endpoint === "preview"),
    originals: () => records.filter((r) => r.endpoint === "original"),
    clear: () => {
      records.length = 0;
      byRequest.clear();
    },
  };
}

// ── Analysis ────────────────────────────────────────────────────────────────

function analyze(records: RequestRecord[], lightboxOpens: number[]) {
  const thumbnails = records.filter((r) => r.endpoint === "thumbnail");
  const previews = records.filter((r) => r.endpoint === "preview");
  const originals = records.filter((r) => r.endpoint === "original");

  const groups = new Map<string, ImageGroup>();
  for (const rec of records) {
    const key = rec.path || "__unknown__";
    if (!groups.has(key)) {
      groups.set(key, {
        path: rec.path,
        endpoints: [],
        records: [],
        firstSeenMs: Infinity,
        lastSeenMs: -Infinity,
      });
    }
    const g = groups.get(key)!;
    if (!g.endpoints.includes(rec.endpoint)) g.endpoints.push(rec.endpoint);
    g.records.push(rec);
    g.firstSeenMs = Math.min(g.firstSeenMs, rec.startMs);
    g.lastSeenMs = Math.max(g.lastSeenMs, rec.startMs);
  }

  // Determine active image (first image clicked)
  const firstOpen = lightboxOpens[0] ?? 0;
  const activeImagePath =
    records.find((r) => r.startMs >= firstOpen && r.endpoint === "preview")?.path || "";

  // Suspicious originals within 3s of lightbox open
  const SUSPICIOUS_WINDOW = 3000;
  const suspiciousOriginals: RequestRecord[] = [];
  for (const rec of originals) {
    for (const openTime of lightboxOpens) {
      const rel = rec.startMs - openTime;
      if (rel >= 0 && rel < SUSPICIOUS_WINDOW) {
        suspiciousOriginals.push(rec);
        break;
      }
    }
  }

  // Per-image verdicts
  const imageVerdicts: Record<
    string,
    {
      path: string;
      endpoints: string[];
      numRequests: number;
      firstSeenMs: number;
      lastSeenMs: number;
      verdict: Verdict;
      flags: string[];
    }
  > = {};

  for (const [key, g] of groups.entries()) {
    const flags: string[] = [];
    let verdict: Verdict = "OK";

    const isActiveImage = g.path === activeImagePath;
    const endpoints = g.endpoints;
    const hasOriginal = endpoints.includes("original");
    const hasPreview = endpoints.includes("preview");
    const hasThumbnail = endpoints.includes("thumbnail");
    const allThree = hasOriginal && hasPreview && hasThumbnail;

    const originalReqs = g.records.filter((r) => r.endpoint === "original");
    const originalNearOpen = originalReqs.some((r) => {
      for (const openTime of lightboxOpens) {
        const rel = r.startMs - openTime;
        if (rel >= 0 && rel < SUSPICIOUS_WINDOW) return true;
      }
      return false;
    });

    if (hasOriginal && originalNearOpen && isActiveImage && !allThree) {
      verdict = "BAD";
      flags.push("/api/image requested on normal lightbox open");
    }

    if (hasOriginal && !isActiveImage) {
      verdict = "BAD";
      flags.push("neighbor preload requested /api/image");
    }

    if (allThree && hasOriginal && isActiveImage) {
      verdict = "WARN";
      flags.push("thumbnail + preview + original all loaded for same image");
    }

    // Check multiple preview requests for same image
    const previewReqs = g.records.filter((r) => r.endpoint === "preview");
    if (previewReqs.length > 1) {
      if (verdict === "OK") verdict = "WARN";
      flags.push(`multiple preview requests (${previewReqs.length})`);
    }

    if (flags.length === 0) {
      flags.push("normal");
    }

    imageVerdicts[key] = {
      path: g.path,
      endpoints: g.endpoints.sort(),
      numRequests: g.records.length,
      firstSeenMs: g.firstSeenMs,
      lastSeenMs: g.lastSeenMs,
      verdict,
      flags,
    };
  }

  return {
    summary: {
      thumbnailCount: thumbnails.length,
      previewCount: previews.length,
      originalCount: originals.length,
      uniquePaths: groups.size,
      suspiciousOriginalOnOpenCount: suspiciousOriginals.length,
      activeImagePath,
      lightboxOpens: lightboxOpens.length,
    },
    perImage: imageVerdicts,
    suspiciousOriginals: suspiciousOriginals.map((r) => ({
      url: r.url,
      path: r.path,
      endpoint: r.endpoint,
      startMs: r.startMs,
      durationMs: r.durationMs,
      status: r.status,
    })),
    timeline: records
      .sort((a, b) => a.startMs - b.startMs)
      .map((r) => ({
        timeMs: r.startMs,
        endpoint: r.endpoint,
        path: r.path,
        durationMs: r.durationMs,
        status: r.status,
        queryParams: r.queryParams,
      })),
  };
}

// ── Navigation Helpers ──────────────────────────────────────────────────────

async function navigateToAlbum(page: Page) {
  await page.addInitScript(
    (rootForInit) => {
      localStorage.setItem("gallery-root-path", rootForInit);
      localStorage.removeItem("gallery-lightbox-always-load-original");
    },
    ROOT_PATH
  );

  console.log(`[Debug] Navigating to ${BASE_URL}`);
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 30000 });

  // Handle landpage if present
  const enterBtn = page.getByRole("button", { name: /enter gallery/i });
  if (await enterBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    console.log("[Debug] Clicking 'Enter Gallery'");
    await enterBtn.click();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
  }

  if (ALBUM_NAME) {
    const album = page.getByText(ALBUM_NAME, { exact: false }).first();
    await expect(album).toBeVisible({ timeout: 15000 });
    console.log(`[Debug] Clicking album: ${ALBUM_NAME}`);
    await album.click();
  }

  // Wait for thumbnails to appear
  const firstPhoto = page.getByTestId("photo-card").first();
  await expect(firstPhoto).toBeVisible({ timeout: 30000 });
  console.log("[Debug] Grid thumbnails loaded");

  return firstPhoto;
}

// ── Test ────────────────────────────────────────────────────────────────────

test("debug lightbox image loads", async ({ page }) => {
  const clickTime = { value: 0 };
  const tracker = installTracker(page, clickTime);

  console.log("═══════════════════════════════════════════════════════════");
  console.log("  GALLERY LIGHTBOX IMAGE LOAD DEBUG (Playwright)");
  console.log("═══════════════════════════════════════════════════════════");
  console.log(`  Base URL:   ${BASE_URL}`);
  console.log(`  Album:      ${ALBUM_NAME || "(root directory)"}`);
  console.log(`  Root path:  ${ROOT_PATH}`);
  console.log("═══════════════════════════════════════════════════════════");

  // Navigate and wait for grid
  const firstPhoto = await navigateToAlbum(page);

  // Start tracking
  tracker.clear();
  const lightboxOpens: number[] = [];
  clickTime.value = Date.now();

  // Click first image to open lightbox
  console.log("[Debug] Clicking first image to open lightbox...");
  await firstPhoto.click();
  lightboxOpens.push(Date.now() - clickTime.value);

  // Wait for lightbox to be visible
  const lightbox = page.getByTestId("lightbox");
  await expect(lightbox).toBeVisible({ timeout: 10000 });
  console.log("[Debug] Lightbox visible");

  // Wait for preview image to load
  const lightboxImg = lightbox.locator(".pswp__img:not(.pswp__img--placeholder)").first();
  await expect
    .poll(async () => {
      return await lightboxImg.evaluate((img: HTMLImageElement) => ({
        complete: img.complete,
        naturalW: img.naturalWidth,
        naturalH: img.naturalHeight,
      }));
    }, { timeout: 15000 })
    .toMatchObject({ complete: true });
  console.log("[Debug] Preview image loaded");

  // Log current slide info
  const currentSrc = await lightboxImg.evaluate((img: HTMLImageElement) => img.src);
  const naturalDims = await lightboxImg.evaluate((img: HTMLImageElement) => ({
    w: img.naturalWidth,
    h: img.naturalHeight,
  }));
  console.log(`[Debug] Current slide: ${naturalDims.w}x${naturalDims.h}`);
  console.log(`[Debug] Current src:   ${currentSrc}`);
  console.log(`[Debug] Is /api/image:  ${currentSrc.includes("/api/image")}`);
  console.log(`[Debug] Is /api/preview: ${currentSrc.includes("/api/preview")}`);

  // Wait for neighbor preload + PhotoSwipe internal preload to fire
  console.log(`[Debug] Waiting ${LIGHTBOX_WAIT_MS}ms for preloads...`);
  await page.waitForTimeout(LIGHTBOX_WAIT_MS);

  // Navigate to next image
  console.log("[Debug] Navigating to next image...");
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(1500);

  // Navigate to previous image
  console.log("[Debug] Navigating to previous image...");
  await page.keyboard.press("ArrowLeft");
  await page.waitForTimeout(1500);

  // Final settle
  await page.waitForTimeout(500);

  // Close lightbox
  console.log("[Debug] Closing lightbox...");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(500);

  // ── Collect and analyze ──────────────────────────────────────────────────

  const allRecords = tracker.records.sort((a, b) => a.startMs - b.startMs);
  const analysis = analyze(allRecords, lightboxOpens);

  // ── Print report ─────────────────────────────────────────────────────────

  console.log("");
  console.log("═══════════════════════════════════════════════════════════");
  console.log("  RESULTS");
  console.log("═══════════════════════════════════════════════════════════");
  console.log("");
  console.log("── Summary ──");
  console.log(`  /api/thumbnail: ${analysis.summary.thumbnailCount}`);
  console.log(`  /api/preview:   ${analysis.summary.previewCount}`);
  console.log(`  /api/image:     ${analysis.summary.originalCount}`);
  console.log(`  Unique paths:   ${analysis.summary.uniquePaths}`);
  console.log(`  Suspicious /api/image near open: ${analysis.summary.suspiciousOriginalOnOpenCount}`);
  console.log(`  Active image:   ${analysis.summary.activeImagePath || "(unknown)"}`);
  console.log("");

  console.log("── Per-Image Analysis ──");
  for (const [key, img] of Object.entries(analysis.perImage)) {
    const icon = img.verdict === "BAD" ? "✗" : img.verdict === "WARN" ? "⚠" : "✓";
    const shortPath = (img.path || key).length > 60 ? "..." + (img.path || key).slice(-57) : img.path || key;
    console.log(`  ${icon} [${img.verdict}] ${shortPath}`);
    console.log(`      Endpoints: ${img.endpoints.join(", ")}`);
    console.log(`      Requests: ${img.numRequests}`);
    console.log(`      Timing: +${img.firstSeenMs}ms to +${img.lastSeenMs}ms`);
    for (const flag of img.flags) {
      console.log(`      → ${flag}`);
    }
  }
  console.log("");

  console.log("── Timeline ──");
  console.log("  Time | Endpoint  | Path");
  console.log("  " + "─".repeat(60));
  for (const t of analysis.timeline) {
    const shortPath = (t.path || "").split("/").pop() || t.path || "?";
    console.log(`  +${String(t.timeMs).padStart(5)}ms | ${t.endpoint.padEnd(10)} | ${shortPath}`);
  }
  console.log("");

  if (analysis.suspiciousOriginals.length > 0) {
    console.log("── ⚠  Suspicious /api/image Requests ──");
    for (const rec of analysis.suspiciousOriginals) {
      console.log(`  +${rec.startMs}ms | ${rec.path || "?"} | ${rec.url}`);
      console.log(`    duration: ${rec.durationMs ?? "?"}ms, status: ${rec.status ?? "?"}`);
    }
    console.log("");
  }

  // ── Verdicts ─────────────────────────────────────────────────────────────

  const badCount = Object.values(analysis.perImage).filter((i) => i.verdict === "BAD").length;
  const warnCount = Object.values(analysis.perImage).filter((i) => i.verdict === "WARN").length;

  console.log("── Verdicts ──");
  console.log(`  BAD:  ${badCount}`);
  console.log(`  WARN: ${warnCount}`);
  console.log("");

  console.log("── Expected Architecture ──");
  console.log("  Grid:              /api/thumbnail = OK");
  console.log("  Normal lightbox:   /api/preview   = OK");
  console.log("                     /api/thumbnail as msrc/placeholder = OK");
  console.log("                     /api/image     = suspicious");
  console.log("  Neighbor preload:  /api/thumbnail = OK, /api/preview = OK");
  console.log("                     /api/image     = BAD");
  console.log("");

  // ── Write output ─────────────────────────────────────────────────────────

  const output = {
    config: {
      baseUrl: BASE_URL,
      albumName: ALBUM_NAME || "(root)",
      rootPath: ROOT_PATH,
      lightboxWaitMs: LIGHTBOX_WAIT_MS,
      timestamp: new Date().toISOString(),
    },
    analysis,
    rawRecords: allRecords,
  };

  writeFileSync(OUTPUT_FILE, JSON.stringify(output, null, 2));
  console.log(`[Debug] Full report written to: ${OUTPUT_FILE}`);
  console.log("═══════════════════════════════════════════════════════════");

  // ── Assertions ────────────────────────────────────────────────────────────

  // Core assertions: no /api/image on normal open (for the active image)
  const activeImageAnalysis = analysis.perImage[analysis.summary.activeImagePath];
  if (activeImageAnalysis) {
    const hasOriginalRequest = activeImageAnalysis.endpoints.includes("original");
    if (hasOriginalRequest) {
      console.warn(
        `WARNING: Active image loaded /api/image. This is suspicious unless ` +
          `zoom/fullscreen/download/animated/fallback was detected.`
      );
    }
  }

  // Check: was the lightbox src a preview URL?
  expect(currentSrc.includes("/api/preview"), "Lightbox image src should use /api/preview, not /api/image").toBe(true);
  expect(currentSrc.includes("/api/image"), "Lightbox image src should NOT be /api/image").toBe(false);
});
