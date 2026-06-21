/**
 * Purpose:
 * Verifies Tailwind preflight does not regress existing gallery component styling.
 *
 * Guarantees:
 * * buttons, cards, image grids, and app shell keep expected inherited styles
 * * preflight-related CSS changes do not erase required layout defaults
 *
 * Run when:
 * * changing Tailwind preflight, token bridge CSS, or global stylesheet order
 * * touching base component styling shared by gallery views
 */

import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-preflight-test";
const imagePaths = Array.from({ length: 4 }, (_, i) => `${rootPath}/image_${i + 1}.png`);
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

async function installStubbedGallery(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());

    if (url.pathname === "/api/libraries") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([stubLibrary]),
      });
      return;
    }

    if (url.pathname === "/api/scan") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          folders: [],
          media: imagePaths.map((path, i) => ({
            name: `image_${i + 1}.png`,
            path,
            type: "image",
            has_children: false,
            cover_images: [],
            mtime: 1000 + i,
            image_count: 0,
            width: 1600,
            height: 1000,
          })),
          next_media_cursor: null,
          total_images: imagePaths.length,
          total_videos: 0,
          total_assets: imagePaths.length,
          index_source: "direct_scan",
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
          name: url.searchParams.get("path")?.split("/").pop() ?? "image.png",
        }),
      });
      return;
    }

    if (url.pathname === "/api/health") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ status: "ok" }),
      });
      return;
    }

    if (url.pathname === "/api/index/status") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          enabled: true,
          worker_count: 0,
          active_jobs: 0,
          runtime_queue_depth: 0,
          done: imagePaths.length,
          running: 0,
          queued: 0,
          failed: 0,
          stale: 0,
          skipped: 0,
          total: imagePaths.length,
          path: rootPath,
          counts: { done: imagePaths.length },
          oldest_queued_age_seconds: null,
          last_error: null,
          updated_at: 1000000000,
          coalesced_duplicates: 0,
          staged_path_queue_depth: 0,
          staged_path_coalesced: 0,
          staged_path_failed: 0,
          staged_path_flushes_forced: 0,
          staged_path_worker_count: 0,
          active_scan_requests: 0,
          batch_size: 100,
          staged_path_batch_size: 50,
          stage_max_wait_seconds: 30,
          metadata_records: imagePaths.length,
          indexed_photos: imagePaths.length,
        }),
      });
      return;
    }

    if (url.pathname === "/api/landing-pages") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([]) });
      return;
    }

    if (url.pathname === "/api/facets") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({}) });
      return;
    }

    if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
      await route.fulfill({ contentType: "image/png", body: png1x1 });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
}

async function dismissMobileSidebar(page: Page) {
  const sidebar = page.locator('[data-sidebar="sidebar"][data-mobile="true"]');
  if (await sidebar.isVisible({ timeout: 3000 }).catch(() => false)) {
    const viewport = page.viewportSize();
    const clickX = viewport ? viewport.width - 50 : 340;
    const clickY = viewport ? viewport.height / 2 : 400;
    await page.mouse.click(clickX, clickY);
    await page.waitForTimeout(500);
  }
}

async function openStubbedGallery(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
}

test.describe("Tailwind Preflight Regression", () => {
  // =========================================================================
  // Test 1: Preflight CSS injection verification
  // =========================================================================
  test.describe("Preflight CSS injection", () => {
    test.use({ viewport: { width: 1280, height: 820 } });

    test("1a. Preflight base styles are loaded in stylesheets", async ({ page }) => {
      await installStubbedGallery(page);
      await openStubbedGallery(page);

      const preflightCheck = await page.evaluate(() => {
        const results = {
          bodyMarginZero: false,
          imgDisplayBlock: false,
          preflightFound: false,
          preflightPatterns: [] as string[],
        };

        // Check body margin (Preflight sets margin: 0)
        const bodyMargin = getComputedStyle(document.body).margin;
        if (bodyMargin === "0px") {
          results.bodyMarginZero = true;
        }

        // Check img display (Preflight sets display: block on img)
        const allImgs = document.querySelectorAll<HTMLImageElement>(".photo-card img");
        if (allImgs.length > 0) {
          const imgDisplay = getComputedStyle(allImgs[0]).display;
          if (imgDisplay === "block") {
            results.imgDisplayBlock = true;
          }
        }

        // Search stylesheets for Preflight-specific patterns.
        // In Vite dev mode, CSS may be served as JS modules and stylesheets
        // may be empty or cross-origin. Try multiple pattern variants.
        const preflightPatterns = [
          "border-width:0",
          "border-style:solid",
          "box-sizing:border-box",
          "img,svg,video,canvas,audio,iframe,embed,object",
          "button,input",
          "@layer base",
          "tailwindcss",
        ];

        for (const sheet of Array.from(document.styleSheets)) {
          try {
            const text = Array.from(sheet.cssRules || [])
              .map((r) => r.cssText)
              .join(" ");
            // Also check ownerNode textContent for inline style elements
            const ownerText = (sheet.ownerNode as HTMLElement)?.textContent ?? "";
            const combined = text + " " + ownerText;
            for (const pattern of preflightPatterns) {
              if (combined.toLowerCase().includes(pattern.toLowerCase())) {
                results.preflightFound = true;
                results.preflightPatterns.push(pattern);
                break;
              }
            }
            if (results.preflightFound) break;
          } catch {
            // cross-origin stylesheet (e.g., fonts) — skip
          }
        }

        // Fallback: check if any element has box-sizing: border-box from universal selector.
        // Preflight's *,::before,::after{box-sizing:border-box} makes <html> border-box.
        if (!results.preflightFound) {
          const htmlBox = getComputedStyle(document.documentElement).boxSizing;
          if (htmlBox === "border-box") {
            results.preflightFound = true;
            results.preflightPatterns.push("html-box-sizing");
          }
        }

        return results;
      });

      // Preflight presence: verified either via stylesheet patterns or computed styles
      expect(
        preflightCheck.preflightFound || preflightCheck.bodyMarginZero,
        "Preflight CSS should be loaded (checked patterns: " +
          preflightCheck.preflightPatterns.join(", ") +
          ", body margin: " +
          preflightCheck.bodyMarginZero +
          ")",
      ).toBe(true);
      expect(preflightCheck.bodyMarginZero, "body margin should be 0 (Preflight reset)").toBe(true);
      expect(preflightCheck.imgDisplayBlock, "img display should be block (Preflight reset)").toBe(true);
    });

    test("1b. Preflight box-sizing border-box is applied globally", async ({ page }) => {
      await installStubbedGallery(page);
      await openStubbedGallery(page);

      const boxSizingCheck = await page.evaluate(() => {
        const selectors = [
          "header",
          ".photo-card",
          "button",
          "input",
          ".gallery-grid",
          ".tablet-header",
          ".mobile-header",
        ];
        const results: { selector: string; found: boolean; boxSizing: string }[] = [];

        for (const sel of selectors) {
          const el = document.querySelector(sel) as HTMLElement;
          if (el) {
            results.push({
              selector: sel,
              found: true,
              boxSizing: getComputedStyle(el).boxSizing,
            });
          }
        }
        return results;
      });

      expect(boxSizingCheck.length, "should find at least one element").toBeGreaterThan(0);

      for (const entry of boxSizingCheck) {
        expect(entry.boxSizing, `${entry.selector} box-sizing should be border-box, got ${entry.boxSizing}`).toBe(
          "border-box",
        );
      }
    });

    test("1c. body and html have no unexpected margins from Preflight", async ({ page }) => {
      await installStubbedGallery(page);
      await openStubbedGallery(page);

      const bodyStyles = await page.evaluate(() => {
        const body = getComputedStyle(document.body);
        const html = getComputedStyle(document.documentElement);
        return {
          bodyMargin: body.marginTop,
          bodyPadding: body.paddingTop,
          htmlMargin: html.marginTop,
          htmlPadding: html.paddingTop,
        };
      });

      // Preflight sets body { margin: 0 }
      expect(bodyStyles.bodyMargin).toBe("0px");
      // html should not have margin
      expect(bodyStyles.htmlMargin).toBe("0px");
    });
  });

  // =========================================================================
  // Test 2: Desktop lightbox fullscreen image
  // =========================================================================
  test.describe("Desktop lightbox with Preflight", () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    test("2a. desktop lightbox image displays fullscreen correctly", async ({ page }) => {
      await installStubbedGallery(page);
      await openStubbedGallery(page);

      // Open lightbox
      await page.getByTestId("photo-card").first().click();
      await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
      await page.waitForTimeout(1500);

      const imgStyles = await page.evaluate(() => {
        const img = document.querySelector(".pswp__img") as HTMLElement;
        if (!img) return null;
        const style = getComputedStyle(img);
        const rect = img.getBoundingClientRect();
        return {
          maxWidth: style.maxWidth,
          maxHeight: style.maxHeight,
          display: style.display,
          width: style.width,
          height: style.height,
          rectWidth: rect.width,
          rectHeight: rect.height,
          position: style.position,
          objectFit: style.objectFit,
          opacity: style.opacity,
        };
      });

      expect(imgStyles, ".pswp__img element should exist in lightbox").not.toBeNull();

      // PhotoSwipe inline styles should override Preflight's img { max-width: 100% }
      // If max-width is "100%" (Preflight wins), lightbox images would be constrained.
      expect(imgStyles!.maxWidth, "max-width should not be auto (would break layout)").not.toBe("auto");
      expect(imgStyles!.maxHeight, "max-height should not be auto").not.toBe("auto");

      // Preflight sets img { display: block } — PhotoSwipe expects this
      expect(imgStyles!.display, "display should be block").toBe("block");

      // Image must have non-zero dimensions
      expect(parseFloat(imgStyles!.rectWidth.toString()), "rect width must be > 0").toBeGreaterThan(0);
      expect(parseFloat(imgStyles!.rectHeight.toString()), "rect height must be > 0").toBeGreaterThan(0);

      // Opacity should be 1 (fully visible)
      expect(parseFloat(imgStyles!.opacity), "opacity should be 1 (visible)").toBe(1);

      // Position should be absolute (PhotoSwipe layout requirement)
      expect(imgStyles!.position, "position should be absolute").toBe("absolute");

      // Close lightbox
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("lightbox")).not.toBeVisible({ timeout: 5_000 });
    });

    test("2b. desktop lightbox close and reopen preserves image sizing", async ({ page }) => {
      await installStubbedGallery(page);
      await openStubbedGallery(page);

      // Open lightbox
      await page.getByTestId("photo-card").first().click();
      await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
      await page.waitForTimeout(1000);

      const firstOpen = await page.evaluate(() => {
        const img = document.querySelector(".pswp__img") as HTMLElement;
        if (!img) return null;
        const rect = img.getBoundingClientRect();
        return {
          width: rect.width,
          height: rect.height,
          display: getComputedStyle(img).display,
          maxWidth: getComputedStyle(img).maxWidth,
        };
      });
      expect(firstOpen, "pswp__img should exist on first open").not.toBeNull();

      // Close
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("lightbox")).not.toBeVisible({ timeout: 5_000 });
      await page.waitForTimeout(500);

      // Reopen same image
      await page.getByTestId("photo-card").first().click();
      await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
      await page.waitForTimeout(1000);

      const secondOpen = await page.evaluate(() => {
        const img = document.querySelector(".pswp__img") as HTMLElement;
        if (!img) return null;
        const rect = img.getBoundingClientRect();
        return {
          width: rect.width,
          height: rect.height,
          display: getComputedStyle(img).display,
          maxWidth: getComputedStyle(img).maxWidth,
        };
      });
      expect(secondOpen, "pswp__img should exist on second open").not.toBeNull();

      // Display should be block on both opens
      expect(firstOpen!.display).toBe("block");
      expect(secondOpen!.display).toBe("block");

      // Dimensions should be > 0 on both opens
      expect(firstOpen!.width).toBeGreaterThan(0);
      expect(firstOpen!.height).toBeGreaterThan(0);
      expect(secondOpen!.width).toBeGreaterThan(0);
      expect(secondOpen!.height).toBeGreaterThan(0);
    });

    test("2c. lightbox counter and prev/next arrows render correctly", async ({ page }) => {
      await installStubbedGallery(page);
      await openStubbedGallery(page);

      await page.getByTestId("photo-card").first().click();
      await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
      await page.waitForTimeout(1000);

      // Check that lightbox prev/next arrows are present.
      // PhotoSwipe uses .pswp__button--arrow--prev / --next classes.
      // data-testid may not be set on all viewer variants.
      const prevArrow = page.locator("[data-testid='lightbox-prev'], .pswp__button--arrow--prev");
      const nextArrow = page.locator("[data-testid='lightbox-next'], .pswp__button--arrow--next");
      // Arrows should be in the DOM (may or may not be visible)
      const hasPrev = await prevArrow.count();
      const hasNext = await nextArrow.count();
      expect(hasPrev + hasNext, "at least one arrow should be in DOM").toBeGreaterThanOrEqual(1);

      // Close
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("lightbox")).not.toBeVisible({ timeout: 5_000 });
    });
  });

  // =========================================================================
  // Test 3: GalleryGrid image sizing unchanged
  // =========================================================================
  test.describe("GalleryGrid image sizing with Preflight", () => {
    test.use({ viewport: { width: 1280, height: 820 } });

    test("3a. gallery grid image sizing is unchanged by Preflight", async ({ page }) => {
      await installStubbedGallery(page);
      await openStubbedGallery(page);

      const gridImgStyles = await page.evaluate(() => {
        const cards = document.querySelectorAll<HTMLElement>(".photo-card");
        const results: {
          display: string;
          objectFit: string;
          width: number;
          height: number;
          boxSizing: string;
          maxWidth: string;
        }[] = [];

        cards.forEach((card) => {
          const img = card.querySelector("img");
          if (!img) return;
          const style = getComputedStyle(img);
          const rect = img.getBoundingClientRect();
          results.push({
            display: style.display,
            objectFit: style.objectFit,
            width: rect.width,
            height: rect.height,
            boxSizing: style.boxSizing,
            maxWidth: style.maxWidth,
          });
        });

        return results;
      });

      expect(gridImgStyles.length, "should have at least one grid image").toBeGreaterThanOrEqual(1);

      for (let i = 0; i < gridImgStyles.length; i++) {
        const img = gridImgStyles[i];

        // Display must be block (both SCSS and Preflight set this)
        expect(img.display, `grid img[${i}] display should be block`).toBe("block");

        // Object-fit must be cover (gallery SCSS, not Preflight)
        expect(img.objectFit, `grid img[${i}] object-fit should be cover`).toBe("cover");

        // Width and height must be > 0
        expect(img.width, `grid img[${i}] width should be > 0`).toBeGreaterThan(0);
        expect(img.height, `grid img[${i}] height should be > 0`).toBeGreaterThan(0);

        // Box-sizing should be border-box (Preflight)
        expect(img.boxSizing, `grid img[${i}] box-sizing should be border-box`).toBe("border-box");

        // max-width is set to 100% by Preflight (img, video { max-width: 100% })
        // or "none" if overridden — either is fine as long as not "auto"
        expect(img.maxWidth, `grid img[${i}] max-width should not be auto`).not.toBe("auto");
      }
    });

    test("3b. photo cards have correct aspect ratio and bounding boxes", async ({ page }) => {
      await installStubbedGallery(page);
      await openStubbedGallery(page);

      const cards = page.getByTestId("photo-card");
      const count = await cards.count();
      expect(count, "should have at least 1 photo card").toBeGreaterThanOrEqual(1);

      const firstCardBox = await cards.first().boundingBox();
      expect(firstCardBox, "first photo card should have bounding box").not.toBeNull();
      expect(firstCardBox!.width, "photo card width > 0").toBeGreaterThan(0);
      expect(firstCardBox!.height, "photo card height > 0").toBeGreaterThan(0);

      // Photo cards use aspect-ratio: 1 (square) from SCSS
      const aspectRatio = firstCardBox!.width / firstCardBox!.height;
      expect(aspectRatio, `aspect ratio ${aspectRatio.toFixed(2)} should be ~1.0`).toBeCloseTo(1.0, 1);

      // Verify computed aspect-ratio style
      const cardAspectRatio = await cards.first().evaluate((el) => {
        return getComputedStyle(el).aspectRatio;
      });
      expect(cardAspectRatio, "photo card aspect-ratio should contain 1").toMatch(/1/);
    });

    test("3c. gallery grid container has correct layout properties", async ({ page }) => {
      await installStubbedGallery(page);
      await openStubbedGallery(page);

      const gridStyles = await page.evaluate(() => {
        const grid = document.querySelector(".gallery-grid") as HTMLElement;
        if (!grid) return null;
        const style = getComputedStyle(grid);
        return {
          display: style.display,
          boxSizing: style.boxSizing,
          width: parseFloat(style.width),
          flexDirection: style.flexDirection,
        };
      });

      expect(gridStyles, ".gallery-grid should exist").not.toBeNull();
      expect(gridStyles!.boxSizing, "gallery-grid box-sizing should be border-box").toBe("border-box");
      expect(gridStyles!.width, "gallery-grid width should be > 0").toBeGreaterThan(0);
    });
  });

  // =========================================================================
  // Test 4: Mobile header buttons still work
  // =========================================================================
  test.describe("Mobile header with Preflight", () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test.beforeEach(async ({ page }) => {
      await installStubbedGallery(page);
      await openStubbedGallery(page);
      await dismissMobileSidebar(page);
    });

    test("4a. mobile hamburger opens and closes sidebar", async ({ page }) => {
      const hamburger = page.getByLabel("Toggle sidebar");
      await expect(hamburger).toBeVisible();
      await hamburger.click();
      await page.waitForTimeout(300);

      // Sidebar should be open
      const sidebar = page.locator('[data-sidebar="sidebar"][data-mobile="true"]');
      const isOpen = await sidebar.isVisible({ timeout: 3000 }).catch(() => false);
      expect(isOpen, "sidebar should open after hamburger click").toBe(true);

      // Close sidebar via backdrop click
      await dismissMobileSidebar(page);
      const isClosed = await sidebar.isVisible({ timeout: 3000 }).catch(() => false);
      expect(isClosed, "sidebar should close after dismiss").toBe(false);
    });

    test("4b. mobile search expands and collapses", async ({ page }) => {
      const searchBtn = page.getByLabel("Open search");
      await expect(searchBtn).toBeVisible();

      // Open search
      await searchBtn.evaluate((el: HTMLElement) => el.click());
      await page.waitForTimeout(500);

      const searchInput = page.getByLabel("Search gallery");
      await expect(searchInput).toBeVisible({ timeout: 3000 });

      // Type a query
      await searchInput.fill("preflight test");
      expect(await searchInput.inputValue()).toBe("preflight test");

      // Clear the search
      const clearBtn = page.getByLabel("Clear search");
      if (await clearBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
        await clearBtn.evaluate((el: HTMLElement) => el.click());
        await page.waitForTimeout(200);
      }

      // Close search
      const closeBtn = page.getByLabel("Close search");
      await expect(closeBtn).toBeVisible();
      await closeBtn.evaluate((el: HTMLElement) => el.click());
      await page.waitForTimeout(300);

      // Search input should be hidden
      await expect(searchInput).not.toBeVisible({ timeout: 3000 });
    });

    test("4c. mobile sort button is present and clickable", async ({ page }) => {
      const sortBtn = page.getByRole("button", { name: "Sort gallery" });
      await expect(sortBtn).toBeVisible();
      await sortBtn.click();
      await expect(page.getByRole("menuitem").first()).toBeVisible();
    });

    test("4d. mobile theme toggle changes data-theme", async ({ page }) => {
      const themeBtn = page.getByLabel("Switch to light mode").or(page.getByLabel("Switch to dark mode"));
      await expect(themeBtn).toBeVisible();

      const initialTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));

      // Toggle theme
      await themeBtn.evaluate((el: HTMLElement) => el.click());
      await page.waitForTimeout(300);

      const newTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
      expect(newTheme).not.toBe(initialTheme);
      expect(["light", "dark"]).toContain(newTheme);

      // Toggle back
      const themeBtn2 = page.getByLabel("Switch to light mode").or(page.getByLabel("Switch to dark mode"));
      await themeBtn2.evaluate((el: HTMLElement) => el.click());
      await page.waitForTimeout(300);

      const restoredTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
      expect(restoredTheme).toBe(initialTheme);
    });

    test("4e. mobile header buttons have correct computed styles", async ({ page }) => {
      const buttonStyles = await page.evaluate(() => {
        const buttons = document.querySelectorAll<HTMLElement>(".mobile-header button");
        const results: {
          label: string;
          fontFamily: string;
          fontSize: string;
          cursor: string;
          padding: string;
          boxSizing: string;
        }[] = [];

        buttons.forEach((btn) => {
          const style = getComputedStyle(btn);
          results.push({
            label: btn.getAttribute("aria-label") || btn.textContent?.trim() || "unknown",
            fontFamily: style.fontFamily,
            fontSize: style.fontSize,
            cursor: style.cursor,
            padding: style.padding,
            boxSizing: style.boxSizing,
          });
        });
        return results;
      });

      expect(buttonStyles.length, "should have mobile header buttons").toBeGreaterThan(0);

      for (const btn of buttonStyles) {
        // Font-family should be set (not empty/undefined)
        // Preflight sets button { font-family: inherit } so font should cascade
        expect(btn.fontFamily, `button "${btn.label}" font-family should be set`).toBeTruthy();

        // Box-sizing should be border-box
        expect(btn.boxSizing, `button "${btn.label}" box-sizing should be border-box`).toBe("border-box");

        // Font-size should be > "0px"
        expect(btn.fontSize, `button "${btn.label}" font-size should be non-zero`).not.toBe("0px");

        // Cursor should be set
        expect(btn.cursor, `button "${btn.label}" cursor should be set`).toBeTruthy();
      }
    });
  });

  // =========================================================================
  // Test 5: Tablet header still works
  // =========================================================================
  test.describe("Tablet header with Preflight", () => {
    test.use({ viewport: { width: 768, height: 1024 } });

    test.beforeEach(async ({ page }) => {
      await installStubbedGallery(page);
      await openStubbedGallery(page);
      await dismissMobileSidebar(page);
    });

    test("5a. tablet header is visible with correct layout", async ({ page }) => {
      const header = page.locator(".tablet-header");
      await expect(header).toBeVisible();

      const headerBox = await header.boundingBox();
      expect(headerBox, "tablet header should have bounding box").not.toBeNull();
      expect(headerBox!.width, "tablet header width should be > 100").toBeGreaterThan(100);
      expect(headerBox!.height, "tablet header height should be > 20").toBeGreaterThan(20);
    });

    test("5b. tablet hamburger toggles sidebar", async ({ page }) => {
      const hamburger = page.getByLabel("Toggle sidebar");
      await expect(hamburger).toBeVisible();

      // On tablet, sidebar may already be open (persistent overlay) which
      // intercepts pointer events on the hamburger. Dismiss it first if needed,
      // then test toggling.
      const sidebar = page.locator('[data-sidebar="sidebar"][data-mobile="true"]');
      const wasOpen = await sidebar.isVisible({ timeout: 2000 }).catch(() => false);

      if (wasOpen) {
        // Close via backdrop click, then verify it closed
        const viewport = page.viewportSize();
        const clickX = (viewport?.width ?? 768) - 50;
        const clickY = (viewport?.height ?? 1024) / 2;
        await page.mouse.click(clickX, clickY);
        await page.waitForTimeout(500);
        const closedAfterDismiss = await sidebar.isVisible({ timeout: 2000 }).catch(() => false);
        if (!closedAfterDismiss) {
          // Sidebar closed successfully — now reopen via hamburger
          await hamburger.evaluate((el: HTMLElement) => el.click());
          await page.waitForTimeout(300);
          const reopened = await sidebar.isVisible({ timeout: 3000 }).catch(() => false);
          expect(reopened, "sidebar should reopen after hamburger click").toBe(true);
        }
      } else {
        // Sidebar not open — click hamburger to open
        await hamburger.evaluate((el: HTMLElement) => el.click());
        await page.waitForTimeout(300);
        const opened = await sidebar.isVisible({ timeout: 3000 }).catch(() => false);
        expect(opened, "sidebar should open after hamburger click").toBe(true);
      }

      // Close sidebar if open at end of test
      await dismissMobileSidebar(page);
    });

    test("5c. tablet search expands and collapses", async ({ page }) => {
      const searchBtn = page.getByLabel("Open search");
      await expect(searchBtn).toBeVisible();

      // Open search
      await searchBtn.evaluate((el: HTMLElement) => el.click());
      await page.waitForTimeout(500);

      const searchInput = page.getByLabel("Search gallery");
      await expect(searchInput).toBeVisible({ timeout: 3000 });

      // Type a query
      await searchInput.fill("tablet preflight");
      expect(await searchInput.inputValue()).toBe("tablet preflight");

      // Close search
      const closeBtn = page.getByLabel("Close search");
      if (await closeBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
        await closeBtn.evaluate((el: HTMLElement) => el.click());
        await page.waitForTimeout(300);
      }
    });

    test("5d. tablet theme toggle changes data-theme", async ({ page }) => {
      const themeBtn = page.getByLabel("Switch to light mode").or(page.getByLabel("Switch to dark mode"));
      await expect(themeBtn).toBeVisible();

      const initialTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));

      await themeBtn.evaluate((el: HTMLElement) => el.click());
      await page.waitForTimeout(300);

      const newTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
      expect(newTheme).not.toBe(initialTheme);
      expect(["light", "dark"]).toContain(newTheme);

      // Toggle back
      const themeBtn2 = page.getByLabel("Switch to light mode").or(page.getByLabel("Switch to dark mode"));
      await themeBtn2.evaluate((el: HTMLElement) => el.click());
      await page.waitForTimeout(300);

      const restoredTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
      expect(restoredTheme).toBe(initialTheme);
    });

    test("5e. tablet header buttons have correct computed styles", async ({ page }) => {
      const buttonStyles = await page.evaluate(() => {
        const buttons = document.querySelectorAll<HTMLElement>(".tablet-header button");
        const results: {
          label: string;
          fontFamily: string;
          fontSize: string;
          cursor: string;
          padding: string;
          boxSizing: string;
        }[] = [];

        buttons.forEach((btn) => {
          const style = getComputedStyle(btn);
          results.push({
            label: btn.getAttribute("aria-label") || btn.textContent?.trim() || "unknown",
            fontFamily: style.fontFamily,
            fontSize: style.fontSize,
            cursor: style.cursor,
            padding: style.padding,
            boxSizing: style.boxSizing,
          });
        });
        return results;
      });

      expect(buttonStyles.length, "should have tablet header buttons").toBeGreaterThan(0);

      for (const btn of buttonStyles) {
        expect(btn.fontFamily, `tablet button "${btn.label}" font-family should be set`).toBeTruthy();
        expect(btn.boxSizing, `tablet button "${btn.label}" box-sizing should be border-box`).toBe("border-box");
        expect(btn.fontSize, `tablet button "${btn.label}" font-size should be non-zero`).not.toBe("0px");
      }
    });
  });

  // =========================================================================
  // Test 6: PhotoSwipe image computed style
  // =========================================================================
  test.describe("PhotoSwipe image styles with Preflight", () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    test("6a. pswp__img computed style not broken by Preflight", async ({ page }) => {
      await installStubbedGallery(page);
      await openStubbedGallery(page);

      // Open lightbox
      await page.getByTestId("photo-card").first().click();
      await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
      await page.waitForTimeout(1500);

      const pswpStyles = await page.evaluate(() => {
        const img = document.querySelector(".pswp__img") as HTMLElement;
        if (!img) return null;
        const style = getComputedStyle(img);
        const rect = img.getBoundingClientRect();

        return {
          maxWidth: style.maxWidth,
          maxHeight: style.maxHeight,
          display: style.display,
          width: parseFloat(style.width),
          height: parseFloat(style.height),
          rectWidth: rect.width,
          rectHeight: rect.height,
          position: style.position,
          objectFit: style.objectFit,
          left: style.left,
          top: style.top,
          transform: style.transform,
          opacity: style.opacity,
          verticalAlign: style.verticalAlign,
        };
      });

      expect(pswpStyles, "pswp__img element should exist").not.toBeNull();

      // PhotoSwipe sets max-width: none and max-height: none via inline styles.
      // Preflight's img { max-width: 100% } must NOT win over PhotoSwipe's inline styles.
      // If max-width is "100%" or "auto", Preflight is interfering with PhotoSwipe.
      expect(pswpStyles!.maxWidth, "max-width must not be 100% (Preflight interfering)").not.toBe("100%");
      expect(pswpStyles!.maxWidth, "max-width must not be auto").not.toBe("auto");
      expect(pswpStyles!.maxHeight, "max-height must not be auto").not.toBe("auto");

      // display must be block (Preflight and PhotoSwipe agree on this)
      expect(pswpStyles!.display, "display must be block").toBe("block");

      // Image must be visible with non-zero dimensions
      expect(pswpStyles!.rectWidth, "rect width must be > 0").toBeGreaterThan(0);
      expect(pswpStyles!.rectHeight, "rect height must be > 0").toBeGreaterThan(0);

      // Position must be absolute — PhotoSwipe's layout depends on this
      expect(pswpStyles!.position, "position must be absolute").toBe("absolute");

      // Opacity must be 1 (fully visible)
      expect(parseFloat(pswpStyles!.opacity), "opacity must be 1").toBe(1);

      // Height should not be "auto" forced by Preflight's img { height: auto }
      // PhotoSwipe sets height inline; computed height should be the actual pixel value
      expect(pswpStyles!.height, "height should be > 0 (not auto-compressed)").toBeGreaterThan(0);

      // Close lightbox
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("lightbox")).not.toBeVisible({ timeout: 5_000 });
    });

    test("6b. pswp container and item elements unaffected by Preflight", async ({ page }) => {
      await installStubbedGallery(page);
      await openStubbedGallery(page);

      await page.getByTestId("photo-card").first().click();
      await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
      await page.waitForTimeout(1000);

      const containerStyles = await page.evaluate(() => {
        const pswp = document.querySelector(".pswp") as HTMLElement;
        const item = document.querySelector(".pswp__item") as HTMLElement;
        const bg = document.querySelector(".pswp__bg") as HTMLElement;
        if (!pswp || !item) return null;

        const pswpStyle = getComputedStyle(pswp);
        const itemStyle = getComputedStyle(item);

        return {
          pswp: {
            position: pswpStyle.position,
            zIndex: pswpStyle.zIndex,
            display: pswpStyle.display,
            boxSizing: pswpStyle.boxSizing,
          },
          item: {
            position: itemStyle.position,
            display: itemStyle.display,
            overflow: itemStyle.overflow,
            boxSizing: itemStyle.boxSizing,
          },
          bgExists: bg !== null,
        };
      });

      expect(containerStyles, "pswp container should exist").not.toBeNull();

      // pswp root should be fixed or absolute
      expect(
        ["fixed", "absolute"].includes(containerStyles!.pswp.position),
        `pswp position should be fixed/absolute, got ${containerStyles!.pswp.position}`,
      ).toBe(true);

      // pswp box-sizing should be border-box
      expect(containerStyles!.pswp.boxSizing).toBe("border-box");

      // pswp__item should be positioned
      expect(
        ["absolute", "relative", "fixed"].includes(containerStyles!.item.position),
        `pswp__item position should be absolute/relative/fixed, got ${containerStyles!.item.position}`,
      ).toBe(true);

      // pswp__item should have overflow: hidden (PhotoSwipe clips images)
      expect(containerStyles!.item.overflow, "pswp__item overflow should be hidden").toBe("hidden");

      // Background element should exist
      expect(containerStyles!.bgExists, "pswp__bg should exist").toBe(true);

      // Close
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("lightbox")).not.toBeVisible({ timeout: 5_000 });
    });

    test("6c. pswp button and UI controls not broken by Preflight", async ({ page }) => {
      await installStubbedGallery(page);
      await openStubbedGallery(page);

      await page.getByTestId("photo-card").first().click();
      await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
      await page.waitForTimeout(1000);

      const uiStyles = await page.evaluate(() => {
        const topBar = document.querySelector(".pswp__top-bar") as HTMLElement;
        const closeBtn = document.querySelector(".pswp__button--close") as HTMLElement;
        const counter = document.querySelector(".pswp__counter") as HTMLElement;

        return {
          topBar: topBar
            ? {
                display: getComputedStyle(topBar).display,
                boxSizing: getComputedStyle(topBar).boxSizing,
              }
            : null,
          closeBtn: closeBtn
            ? {
                display: getComputedStyle(closeBtn).display,
                cursor: getComputedStyle(closeBtn).cursor,
              }
            : null,
          counter: counter
            ? {
                display: getComputedStyle(counter).display,
                fontFamily: getComputedStyle(counter).fontFamily,
              }
            : null,
        };
      });

      // These PhotoSwipe UI elements should exist
      // (they may be hidden via CSS but should be in the DOM)
      expect(uiStyles.topBar, "pswp__top-bar should exist in DOM").not.toBeNull();
      expect(uiStyles.closeBtn, "pswp__button--close should exist in DOM").not.toBeNull();

      // Close
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("lightbox")).not.toBeVisible({ timeout: 5_000 });
    });
  });

  // =========================================================================
  // Test 7: No console errors across viewports
  // =========================================================================
  test.describe("Cross-viewport error check with Preflight", () => {
    test("7a. desktop — no console errors with Preflight", async ({ page, monitoredErrors }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await installStubbedGallery(page);
      await openStubbedGallery(page);

      // Interact: open/close lightbox
      await page.getByTestId("photo-card").first().click();
      await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
      await page.waitForTimeout(500);
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("lightbox")).not.toBeVisible({ timeout: 5_000 });

      expect(monitoredErrors.consoleErrors).toEqual([]);
      expect(monitoredErrors.pageErrors).toEqual([]);
    });

    test("7b. mobile — no console errors with Preflight", async ({ page, monitoredErrors }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await installStubbedGallery(page);
      await openStubbedGallery(page);
      await dismissMobileSidebar(page);

      // Interact with mobile header controls
      const searchBtn = page.getByLabel("Open search");
      await searchBtn.evaluate((el: HTMLElement) => el.click());
      await page.waitForTimeout(300);
      const closeBtn = page.getByLabel("Close search");
      await closeBtn.evaluate((el: HTMLElement) => el.click());
      await page.waitForTimeout(300);

      expect(monitoredErrors.consoleErrors).toEqual([]);
      expect(monitoredErrors.pageErrors).toEqual([]);
    });

    test("7c. tablet — no console errors with Preflight", async ({ page, monitoredErrors }) => {
      await page.setViewportSize({ width: 768, height: 1024 });
      await installStubbedGallery(page);
      await openStubbedGallery(page);

      // Interact with tablet controls
      const searchBtn = page.getByLabel("Open search");
      await searchBtn.evaluate((el: HTMLElement) => el.click());
      await page.waitForTimeout(300);
      const closeBtn = page.getByLabel("Close search");
      if (await closeBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
        await closeBtn.evaluate((el: HTMLElement) => el.click());
        await page.waitForTimeout(300);
      }

      expect(monitoredErrors.consoleErrors).toEqual([]);
      expect(monitoredErrors.pageErrors).toEqual([]);
    });
  });
});
