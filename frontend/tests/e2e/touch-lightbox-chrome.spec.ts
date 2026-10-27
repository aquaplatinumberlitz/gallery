/**
 * Purpose:
 * Verifies phone and tablet lightbox chrome: reachable controls, a single counter, and readable panel meta.
 *
 * Guarantees:
 * * no floating dev overlay (TanStack Query Devtools) covers the lightbox Info button in a dev server session
 * * the phone and tablet lightboxes render exactly one visible image counter
 * * tablet metadata panel meta tags (size/date) keep readable contrast on the dark panel in light theme
 *
 * Run when:
 * * changing MobilePhotoSwipe, TabletPhotoSwipe, Lightbox counters, or tablet panel styles
 * * changing how Query Devtools or other debug overlays are enabled
 */

import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-touch-lightbox-test";
const imagePaths = Array.from({ length: 6 }, (_, i) => `${rootPath}/image_${i + 1}.png`);
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
  asset_count: imagePaths.length,
  created_at: 1,
  updated_at: 1,
  last_scan_at: null,
  last_error: null,
};

async function installStubbedGallery(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());

    if (url.pathname === "/api/libraries") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([stubLibrary]) });
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
            libraryId: 1,
            path: url.searchParams.get("path") ?? rootPath,
            media: imagePaths.map((path, i) => ({
              name: path.split("/").pop()!,
              path,
              type: "image",
              mtime: 1000 + i,
              width: 832,
              height: 1216,
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
          tool: "A1111",
          prompt: "masterpiece, 1girl, cherry blossoms",
          negative_prompt: "low quality",
          params: { Seed: "12345", Steps: "30", Sampler: "Euler a" },
          width: 832,
          height: 1216,
          name: "image.png",
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
}

async function openLightbox(page: Page) {
  await installStubbedGallery(page);
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
    localStorage.setItem("gallery-theme", "light");
  });
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.getByTestId("photo-card").nth(2).click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
}

/** Texts of visible elements whose whole content is an "N / M" counter. */
async function visibleCounters(page: Page) {
  return page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>("body *")]
      .filter((el) => {
        if (el.children.length > 0 || !/^\s*\d+\s*\/\s*\d+\s*$/.test(el.textContent ?? "")) return false;
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && Number(style.opacity) > 0;
      })
      .map((el) => el.textContent!.trim()),
  );
}

/** Element hit at the center of a locator; proves the control is not covered by an overlay. */
async function hitTargetLabel(page: Page, label: string) {
  const box = await page.getByRole("button", { name: label }).boundingBox();
  expect(box).not.toBeNull();
  return page.evaluate(
    ([x, y]) => document.elementFromPoint(x, y)?.closest("button")?.getAttribute("aria-label") ?? null,
    [box!.x + box!.width / 2, box!.y + box!.height / 2],
  );
}

function relativeLuminance(rgb: number[]) {
  const [r, g, b] = rgb.map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

test.describe("phone lightbox chrome", () => {
  test.use({ viewport: { width: 375, height: 667 }, hasTouch: true, isMobile: true });

  test("Info button is the hit target and only one counter is visible", async ({ page }) => {
    await openLightbox(page);
    const info = page.getByRole("button", { name: "View image info" });
    await expect(info).toBeVisible();
    await page.waitForTimeout(800); // let lazy dev overlays mount if they are going to
    expect(await hitTargetLabel(page, "View image info")).toBe("View image info");
    await expect(page.getByRole("button", { name: /tanstack query devtools/i })).toHaveCount(0);
    expect(await visibleCounters(page)).toEqual(["3 / 6"]);

    await info.click();
    await expect(page.getByRole("dialog", { name: "Image metadata" })).toBeVisible();
  });
});

test.describe("tablet lightbox chrome", () => {
  test.use({ viewport: { width: 768, height: 1024 }, hasTouch: true, isMobile: true });

  test("one counter and readable meta tags on the dark metadata panel", async ({ page }) => {
    await openLightbox(page);
    await expect(page.getByRole("button", { name: "View image info" })).toBeVisible();
    expect(await visibleCounters(page)).toEqual(["3 / 6"]);

    await page.getByRole("button", { name: "View image info" }).click();
    const sizeTag = page.locator(".tablet-header .meta-tag").first();
    await expect(sizeTag).toContainText("832");

    const colors = await sizeTag.evaluate((el) => {
      const ctx = document.createElement("canvas").getContext("2d")!;
      const toRgba = (value: string) => {
        ctx.clearRect(0, 0, 1, 1);
        ctx.fillStyle = value;
        ctx.fillRect(0, 0, 1, 1);
        const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
        return [r, g, b, a / 255];
      };
      // Collect translucent background layers up to the first opaque one, then composite them.
      const layers: number[][] = [];
      for (let node: HTMLElement | null = el; node; node = node.parentElement) {
        const layer = toRgba(getComputedStyle(node).backgroundColor);
        if (layer[3] > 0) layers.push(layer);
        if (layer[3] >= 1) break;
      }
      let background = [255, 255, 255];
      for (const [r, g, b, a] of layers.reverse()) {
        background = [
          r * a + background[0] * (1 - a),
          g * a + background[1] * (1 - a),
          b * a + background[2] * (1 - a),
        ];
      }
      const [tr, tg, tb, ta] = toRgba(getComputedStyle(el).color);
      const text = [
        tr * ta + background[0] * (1 - ta),
        tg * ta + background[1] * (1 - ta),
        tb * ta + background[2] * (1 - ta),
      ];
      return { text, background };
    });
    // The panel is always dark; text must be light enough for WCAG AA small text (>= 4.5:1).
    const [light, dark] = [relativeLuminance(colors.text), relativeLuminance(colors.background)].sort((a, b) => b - a);
    expect((light + 0.05) / (dark + 0.05)).toBeGreaterThanOrEqual(4.5);
  });
});
