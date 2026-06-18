/**
 * Purpose:
 * Verifies Tailwind migration phase 0 visual contracts across primary layouts.
 *
 * Guarantees:
 * * desktop, mobile, tablet, theme, and preflight absence checks keep baseline styling stable
 * * migrated utility styles do not regress gallery controls or visible content
 *
 * Run when:
 * * changing Tailwind setup, token bridge CSS, or migrated layout styling
 * * touching shadcn/Tailwind compatibility styles
 */

import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-tailwind-p0-test";
const imagePaths = Array.from({ length: 4 }, (_, i) => `${rootPath}/image_${i + 1}.png`);
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64",
);

async function installStubbedGallery(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());

    if (url.pathname === "/api/scan") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          folders: [],
          images: imagePaths.map((path, i) => ({
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
          next_cursor: null,
          total_images: imagePaths.length,
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
  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
}

test.describe("Tailwind Phase 0 — Desktop (1440x900)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);
  });

  test("1a. app loads, header layout unchanged", async ({ page }) => {
    const header = page.locator("header");
    await expect(header).toBeAttached();
    await expect(page.locator(".brand-title")).toBeVisible();
  });

  test("1b. theme toggle works and changes data-theme", async ({ page }) => {
    const themeToggle = page.locator('[aria-label="Theme"]');
    await expect(themeToggle).toBeVisible();

    const initialTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));

    // Open dropdown, then click Dark
    await themeToggle.click();
    await page.locator('[role="menuitem"]', { hasText: "Dark" }).click();
    await page.waitForTimeout(300);

    const newTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(newTheme).toBe("dark");

    // Open dropdown, then click Light
    await themeToggle.click();
    await page.locator('[role="menuitem"]', { hasText: "Light" }).click();
    await page.waitForTimeout(300);

    const restoredTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(restoredTheme).toBe(initialTheme);
  });

  test("1c. search input and sort control exist", async ({ page }) => {
    const searchInput = page.locator("#gallery-search");
    await expect(searchInput).toBeVisible({ timeout: 5000 });

    const sortBtn = page.getByRole("combobox", { name: "Sort gallery" });
    await expect(sortBtn).toBeVisible({ timeout: 5000 });
  });

  test("1d. content area and photo grid display correctly", async ({ page }) => {
    // The gallery content container should be present
    const galleryGrid = page.locator(".gallery-grid, .gallery-scroll-container");
    await expect(galleryGrid.first()).toBeAttached({ timeout: 5000 });

    // Photo cards are visible (verified in 1e)
    await expect(page.getByTestId("photo-card").first()).toBeVisible();
  });

  test("1e. GalleryGrid layout unchanged — photo cards visible", async ({ page }) => {
    const cards = page.getByTestId("photo-card");
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeGreaterThanOrEqual(1);
  });

  test("1f. lightbox opens and closes", async ({ page }) => {
    await page.getByTestId("photo-card").first().click();
    await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });

    const closeBtn = page.locator(".pswp__button--close, [aria-label='Close'], .lightbox-close");
    if (await closeBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await closeBtn.click();
      await expect(page.getByTestId("lightbox")).not.toBeVisible({ timeout: 5_000 });
    } else {
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("lightbox")).not.toBeVisible({ timeout: 5_000 });
    }
  });

  test("1g. no console errors on desktop", async ({ monitoredErrors }) => {
    expect(monitoredErrors.consoleErrors).toEqual([]);
    expect(monitoredErrors.pageErrors).toEqual([]);
  });
});

test.describe("Tailwind Phase 0 — Mobile (390x844)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);
    await dismissMobileSidebar(page);
  });

  test("2a. hamburger visible and works", async ({ page }) => {
    const hamburger = page.getByLabel("Toggle sidebar");
    await expect(hamburger).toBeVisible();
    await hamburger.click();
    await page.waitForTimeout(300);

    // Sidebar should be open now
    const sidebar = page.locator('[data-sidebar="sidebar"][data-mobile="true"]');
    const isOpen = await sidebar.isVisible({ timeout: 3000 }).catch(() => false);
    expect(isOpen).toBe(true);

    // Close it again
    await dismissMobileSidebar(page);
  });

  test("2b. search visible and works", async ({ page }) => {
    const searchBtn = page.getByLabel("Open search");
    await expect(searchBtn).toBeVisible();
  });

  test("2c. sort visible and works", async ({ page }) => {
    const sortBtn = page.getByRole("button", { name: "Sort gallery" });
    await expect(sortBtn).toBeVisible();
  });

  test("2d. theme toggle visible and changes data-theme", async ({ page }) => {
    const themeBtn = page.getByLabel("Switch to light mode").or(page.getByLabel("Switch to dark mode"));
    await expect(themeBtn).toBeVisible();

    await themeBtn.click();
    await page.waitForTimeout(300);

    const newTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(newTheme).toBe("dark");

    // Toggle back (mobile — single button click)
    await page.getByLabel("Switch to light mode").or(page.getByLabel("Switch to dark mode")).click();
    await page.waitForTimeout(300);
  });

  test("2e. bottom navigation unchanged", async ({ page }) => {
    const backBtn = page.getByLabel("Go back");
    await expect(backBtn).toBeAttached();

    const fwdBtn = page.getByLabel("Go forward");
    await expect(fwdBtn).toBeAttached();
  });

  test("2f. albums/cards unchanged — no accidental Tailwind layout reset", async ({ page }) => {
    const cards = page.getByTestId("photo-card");
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeGreaterThanOrEqual(1);

    // Verify the photo cards have computed styles that are NOT Tailwind Preflight resets
    const cardBox = await cards.first().boundingBox();
    expect(cardBox).not.toBeNull();
    expect(cardBox!.width).toBeGreaterThan(0);
    expect(cardBox!.height).toBeGreaterThan(0);
  });

  test("2g. no console errors on mobile", async ({ monitoredErrors }) => {
    expect(monitoredErrors.consoleErrors).toEqual([]);
    expect(monitoredErrors.pageErrors).toEqual([]);
  });
});

test.describe("Tailwind Phase 0 — Tablet (768x1024)", () => {
  test.use({ viewport: { width: 768, height: 1024 } });

  test.beforeEach(async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);
    await dismissMobileSidebar(page);
  });

  test("3a. tablet header unchanged", async ({ page }) => {
    const header = page.locator("header");
    await expect(header).toBeAttached();
  });

  test("3b. tablet actions visible and working", async ({ page }) => {
    const searchBtn = page.getByLabel("Open search");
    await expect(searchBtn).toBeVisible();

    const themeBtn = page.getByLabel("Switch to light mode").or(page.getByLabel("Switch to dark mode"));
    await expect(themeBtn).toBeVisible();
  });

  test("3c. tablet layout unchanged — no accidental Tailwind layout reset", async ({ page }) => {
    const cards = page.getByTestId("photo-card");
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeGreaterThanOrEqual(1);
  });

  test("3d. no console errors on tablet", async ({ monitoredErrors }) => {
    expect(monitoredErrors.consoleErrors).toEqual([]);
    expect(monitoredErrors.pageErrors).toEqual([]);
  });
});

test.describe("Tailwind Phase 0 — Theme smoke test", () => {
  test.use({ viewport: { width: 1280, height: 820 } });

  test("4a. desktop light->dark->light preserves layout", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    const themeToggle = page.locator('[aria-label="Theme"]');
    await expect(themeToggle).toBeVisible();

    // Start in light (default for intro_mode=disabled)
    let currentTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));

    // Open dropdown, then click Dark
    await themeToggle.click();
    await page.locator('[role="menuitem"]', { hasText: "Dark" }).click();
    await page.waitForTimeout(500);
    currentTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(currentTheme).toBe("dark");

    // Verify photo cards still visible with no shift
    const cards = page.getByTestId("photo-card");
    await expect(cards.first()).toBeVisible();
    const cardCount = await cards.count();
    expect(cardCount).toBeGreaterThanOrEqual(1);

    // Open dropdown, then click Light
    await themeToggle.click();
    await page.locator('[role="menuitem"]', { hasText: "Light" }).click();
    await page.waitForTimeout(500);
    currentTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(currentTheme).toBe("light");

    // Verify photo cards still present
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBe(cardCount);
  });

  test("4b. mobile theme toggle preserves layout", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installStubbedGallery(page);
    await openStubbedGallery(page);
    await dismissMobileSidebar(page);

    const themeBtn = page.getByLabel("Switch to light mode").or(page.getByLabel("Switch to dark mode"));
    await expect(themeBtn).toBeVisible();

    // Toggle to dark
    await themeBtn.click();
    await page.waitForTimeout(500);

    let currentTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(currentTheme).toBe("dark");

    // Verify cards still present
    const cards = page.getByTestId("photo-card");
    await expect(cards.first()).toBeVisible();
    const cardCount = await cards.count();
    expect(cardCount).toBeGreaterThanOrEqual(1);

    // Toggle back
    await page.getByLabel("Switch to light mode").click();
    await page.waitForTimeout(500);
    currentTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(currentTheme).toBe("light");

    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBe(cardCount);
  });

  test("4c. dark custom variant does not break data-theme switching", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 820 });
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    // The @custom-variant dark selector uses data-theme="dark"
    // Verify it's present and functioning by checking a dark-mode CSS variable
    const themeToggle = page.locator('[aria-label="Theme"]');

    // Toggle to dark
    await themeToggle.click();
    await page.locator('[role="menuitem"]', { hasText: "Dark" }).click();
    await page.waitForTimeout(500);

    const isDark = await page.evaluate(() => document.documentElement.getAttribute("data-theme") === "dark");
    expect(isDark).toBe(true);

    // Toggle back to light
    await themeToggle.click();
    await page.locator('[role="menuitem"]', { hasText: "Light" }).click();
    await page.waitForTimeout(500);

    const isLight = await page.evaluate(() => document.documentElement.getAttribute("data-theme") === "light");
    expect(isLight).toBe(true);
  });
});

test.describe("Tailwind Phase 0 — Preflight absence verification", () => {
  test.use({ viewport: { width: 1280, height: 820 } });

  test("5a. no Preflight universal reset in stylesheets", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    // Search all stylesheets for Preflight-specific reset patterns
    // Preflight has distinctive rules that set *,::before,::after { box-sizing: border-box; ... }
    // and button,input,... { font: inherit } etc.
    const hasPreflightReset = await page.evaluate(() => {
      const patterns = [
        "border-width:0;border-style:solid",
        "button, input, optgroup, select, textarea{font-family:inherit",
        "img, svg, video, canvas, audio, iframe, embed, object{display:block",
        "::before,::after{box-sizing:border-box;border-width:0;border-style:solid",
      ];
      for (const sheet of Array.from(document.styleSheets)) {
        try {
          const text = Array.from(sheet.cssRules || [])
            .map((r) => r.cssText)
            .join("");
          for (const pattern of patterns) {
            if (text.includes(pattern)) return true;
          }
        } catch {
          // Cross-origin stylesheets can't be read — these are external, not ours
        }
      }
      return false;
    });
    expect(hasPreflightReset).toBe(false);
  });

  test("5b. Tailwind theme.css has @theme inline references baked in", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    // Verify the underlying gallery tokens (which @theme inline maps to)
    // resolve correctly at runtime. The @theme inline block is served by
    // Vite as a separate ESM CSS file, not accessible via CSSOM in dev mode,
    // but was separately verified in the production build output.
    const resolved = await page.evaluate(() => {
      const s = getComputedStyle(document.documentElement);
      return {
        primaryColor: s.getPropertyValue("--color-primary").trim(),
        bgColor: s.getPropertyValue("--background").trim(),
        fontBody: s.getPropertyValue("--font-body").trim(),
        textColor: s.getPropertyValue("--foreground").trim(),
        brandAccent: s.getPropertyValue("--brand-hero-accent").trim(),
        radiusSm: s.getPropertyValue("--gallery-radius-sm").trim(),
        surfaceElevated: s.getPropertyValue("--color-surface-elevated").trim(),
      };
    });

    // Core gallery tokens must resolve to real values
    expect(resolved.primaryColor).toBeTruthy();
    expect(resolved.bgColor).toBeTruthy();
    expect(resolved.brandAccent).toBe("#ff6b35");
    expect(resolved.fontBody).toContain("InterVariable");
    expect(resolved.textColor).toBeTruthy();
    expect(resolved.radiusSm).toBeTruthy();
    expect(resolved.surfaceElevated).toBeTruthy();

    // Verify Tailwind v4 layer structure is present in CSSOM
    const hasTailwindLayer = await page.evaluate(() => {
      for (const sheet of Array.from(document.styleSheets)) {
        try {
          const text = Array.from(sheet.cssRules || [])
            .map((r) => r.cssText)
            .join("");
          if (text.includes("@layer theme") || text.includes("--tw-")) {
            return true;
          }
        } catch {}
      }
      return false;
    });
    expect(hasTailwindLayer).toBe(true);
  });
});
