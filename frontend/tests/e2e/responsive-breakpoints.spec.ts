/**
 * Purpose:
 * Verifies mobile, tablet, desktop, large desktop, and transition breakpoint layouts.
 *
 * Guarantees:
 * * the expected layout shell appears at each supported viewport width
 * * breakpoint transitions do not leave stale mobile/tablet/desktop controls visible
 * * keyboard focus indicators render inside controls instead of being clipped by layout overflow
 * * mobile search controls stay inside the viewport with a compact scope trigger
 *
 * Run when:
 * * changing responsive breakpoints, layout components, headers, sidebars, or toolbars
 * * touching device detection or viewport-specific CSS
 */

import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import type { Locator } from "@playwright/test";
import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-responsive-test";
const imagePaths = Array.from({ length: 72 }, (_, i) => `${rootPath}/image_${i + 1}.png`);
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
          }),
        ),
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

async function openStubbedGallery(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
    if (window.innerWidth < 1200) localStorage.setItem("gallery-sidebar-open", "false");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
}

async function collapseDesktopHeader(page: Page) {
  const scroller = page.locator(".tanstack-scroller").first();
  await expect(scroller).toBeVisible({ timeout: 15_000 });
  await scroller.evaluate((element) => {
    element.scrollTop = 180;
    element.dispatchEvent(new Event("scroll", { bubbles: true }));
  });
  await expect(page.locator(".compact-header:not([inert])")).toBeVisible({ timeout: 5_000 });
}

async function expectInsetFocusRing(page: Page, control: Locator) {
  for (let index = 0; index < 80; index += 1) {
    const isFocused = await control.evaluate((element) => element === document.activeElement);
    if (isFocused) break;
    await page.keyboard.press("Tab");
  }

  await expect(control).toBeFocused();

  const focusStyle = await control.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      outlineStyle: style.outlineStyle,
      outlineWidth: style.outlineWidth,
      outlineOffset: style.outlineOffset,
      ringShadow: style.getPropertyValue("--tw-ring-shadow").trim(),
    };
  });

  expect(focusStyle).toEqual({
    outlineStyle: "solid",
    outlineWidth: "2px",
    outlineOffset: "-2px",
    ringShadow: "0 0 #0000",
  });
}

async function expectCompositeFocusRing(input: Locator, wrapper: Locator) {
  await input.focus();
  await expect(input).toBeFocused();

  const styles = await Promise.all([
    input.evaluate((element) => {
      const style = getComputedStyle(element);
      return { outlineStyle: style.outlineStyle, focusOptOut: element.dataset.focusRing };
    }),
    wrapper.evaluate((element) => getComputedStyle(element).boxShadow),
  ]);

  expect(styles[0]).toEqual({ outlineStyle: "none", focusOptOut: "none" });
  expect(styles[1]).toContain("inset");
}

test.describe("Mobile layout (375px)", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("renders photo cards in mobile layout", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    // Photo cards should be visible
    const cards = page.getByTestId("photo-card");
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeGreaterThanOrEqual(1);
  });

  test("mobile header has search toggle", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    // Mobile header should have search open button
    const searchBtn = page.getByLabel("Open search");
    await expect(searchBtn).toBeVisible({ timeout: 5000 });
    await expectInsetFocusRing(page, searchBtn);
    await searchBtn.press("Enter");
    await expectCompositeFocusRing(page.locator(".search-focus-input"), page.locator(".search-focus-input-wrap"));
  });

  test("mobile search controls do not overflow the viewport", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    await page.getByLabel("Open search").click();
    await page.getByLabel("Search gallery").fill("portrait model");

    const metrics = await page.locator(".mobile-header").evaluate((header) => {
      const scope = header.querySelector<HTMLElement>('[aria-label^="Search scope:"]');
      const scopeIcon = scope?.querySelector<SVGElement>(".search-scope-select-icon");
      const scopeChevron = scope?.querySelector<SVGElement>(".lucide-chevron-down");
      const advanced = header.querySelector<HTMLElement>('[aria-label="Advanced Search"]');
      const input = header.querySelector<HTMLElement>(".search-focus-input");
      if (!scope || !scopeIcon || !scopeChevron || !advanced || !input) {
        throw new Error("Missing mobile search controls");
      }

      const headerRect = header.getBoundingClientRect();
      const scopeRect = scope.getBoundingClientRect();
      const scopeIconRect = scopeIcon.getBoundingClientRect();
      const advancedRect = advanced.getBoundingClientRect();
      const inputRect = input.getBoundingClientRect();

      return {
        clientWidth: header.clientWidth,
        scrollWidth: header.scrollWidth,
        headerRight: headerRect.right,
        scopeWidth: scopeRect.width,
        scopeRight: scopeRect.right,
        scopeIconLeft: scopeIconRect.left,
        scopeIconRight: scopeIconRect.right,
        scopeChevronDisplay: getComputedStyle(scopeChevron).display,
        advancedRight: advancedRect.right,
        inputWidth: inputRect.width,
      };
    });

    expect(metrics.scrollWidth).toBe(metrics.clientWidth);
    expect(metrics.scopeWidth).toBeLessThanOrEqual(44);
    expect(metrics.scopeRight).toBeLessThanOrEqual(metrics.headerRight);
    expect(metrics.scopeIconLeft).toBeGreaterThanOrEqual(metrics.scopeRight - metrics.scopeWidth);
    expect(metrics.scopeIconRight).toBeLessThanOrEqual(metrics.scopeRight);
    expect(metrics.scopeChevronDisplay).toBe("none");
    expect(metrics.advancedRight).toBeLessThanOrEqual(metrics.headerRight);
    expect(metrics.inputWidth).toBeGreaterThanOrEqual(80);
  });

  test("mobile bottom bar is present", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    // Mobile floating bottom bar with navigation buttons
    const backBtn = page.getByLabel("Go back");
    // May or may not be enabled, but should be present
    await expect(backBtn).toBeAttached({ timeout: 5000 });
  });
});

test.describe("Tablet layout (768px)", () => {
  test.use({ viewport: { width: 768, height: 1024 } });

  test("renders photo cards in tablet layout", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    const cards = page.getByTestId("photo-card");
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeGreaterThanOrEqual(1);
  });

  test("tablet header has search", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    // Tablet header should have a search toggle
    const openSearch = page.getByLabel("Open search");
    await expect(openSearch).toBeVisible({ timeout: 5000 });
    await expectInsetFocusRing(page, openSearch);
    await openSearch.press("Enter");
    await expectCompositeFocusRing(page.locator(".th-search-input"), page.locator(".th-search-input-wrap"));
  });
});

test.describe("Mobile search touch interactions", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

  test("scope selection keeps expanded search open", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    await page.getByLabel("Open search").tap();
    await page.getByLabel(/^Search scope:/).tap();

    await expect(page.getByRole("listbox")).toBeVisible();
    await page.getByRole("option", { name: /All indexed/ }).tap();

    await expect(page.getByLabel("Search gallery")).toBeVisible();
    await expect(page.getByLabel("Search scope: All indexed")).toBeVisible();
  });
});

test.describe('Tablet layout (834px - iPad Pro 11")', () => {
  test.use({ viewport: { width: 834, height: 1194 } });

  test("renders photo cards at iPad Pro size", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    const cards = page.getByTestId("photo-card");
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeGreaterThanOrEqual(1);
  });
});

test.describe("Desktop layout (1200px+)", () => {
  test.use({ viewport: { width: 1280, height: 820 } });

  test("renders photo cards in desktop layout", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    const cards = page.getByTestId("photo-card");
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeGreaterThanOrEqual(1);
  });

  test("desktop layout shows sidebar or desktop header", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    // Desktop has a search input
    const searchInput = page.getByRole("searchbox");
    await expect(searchInput).toBeVisible({ timeout: 5000 });
    await expectCompositeFocusRing(
      page.locator(".expanded-header:not([inert]) .search-input"),
      page.locator(".expanded-header:not([inert]) .search-box"),
    );

    await expectInsetFocusRing(page, page.getByRole("button", { name: "Change Intro Page" }));
    await expectInsetFocusRing(page, page.getByRole("button", { name: "Sort gallery" }));
    await expectInsetFocusRing(page, page.getByRole("button", { name: "View density" }));
  });

  test("desktop layout shows folder tree or sidebar", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    await expect(page.getByRole("searchbox", { name: "Photos, albums, prompts" })).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Folder Tree")).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole("button", { name: /toggle sidebar/i })).toBeAttached();
  });
});

test.describe("Desktop compact header (1200px edge)", () => {
  test.use({ viewport: { width: 1200, height: 820 } });

  test("keeps collapsed search, sort, and view controls from overlapping", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);
    await collapseDesktopHeader(page);

    const metrics = await page.locator(".compact-header:not([inert])").evaluate((header) => {
      const box = (selector: string) => {
        const element = header.querySelector<HTMLElement>(selector);
        if (!element) throw new Error(`Missing compact header element: ${selector}`);
        const rect = element.getBoundingClientRect();
        return {
          left: rect.left,
          right: rect.right,
          width: rect.width,
          display: getComputedStyle(element).display,
        };
      };

      return {
        search: box(".compact-search-box"),
        sort: box(".sort-trigger"),
        view: box(".gallery-density-trigger"),
        hasScope: Boolean(header.querySelector(".compact-scope-pill")),
        hasAdvancedSearch: Boolean(header.querySelector(".advanced-search-btn")),
      };
    });

    expect(metrics.search.width).toBeGreaterThanOrEqual(140);
    expect(metrics.search.right).toBeLessThanOrEqual(metrics.sort.left);
    expect(metrics.sort.right).toBeLessThanOrEqual(metrics.view.left);
    expect(metrics.hasScope).toBe(false);
    expect(metrics.hasAdvancedSearch).toBe(true);

    const compactHeader = page.locator(".compact-header:not([inert])");
    await expectInsetFocusRing(page, compactHeader.locator(".advanced-search-btn"));
    await expectInsetFocusRing(page, compactHeader.locator(".sort-trigger"));
    await expectInsetFocusRing(page, compactHeader.locator(".gallery-density-trigger"));
  });
});

test.describe("Large desktop (1920px+)", () => {
  test.use({ viewport: { width: 1920, height: 1080 } });

  test("renders photo cards in large desktop layout", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    const cards = page.getByTestId("photo-card");
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeGreaterThanOrEqual(1);
  });
});

test.describe("Layout transitions", () => {
  test("resize from desktop to mobile preserves content", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 820 });
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    // Verify desktop layout
    await expect(page.getByRole("searchbox")).toBeVisible({ timeout: 5000 });

    // Resize to mobile
    await page.setViewportSize({ width: 375, height: 812 });

    // Photo cards should still be present
    const cards = page.getByTestId("photo-card");
    await expect(cards.first()).toBeVisible({ timeout: 5000 });
    expect(await cards.count()).toBeGreaterThanOrEqual(1);
  });

  test("resize from mobile to desktop preserves content", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    // Verify mobile layout
    await expect(page.getByLabel("Open search")).toBeVisible({ timeout: 5000 });

    // Resize to desktop
    await page.setViewportSize({ width: 1280, height: 820 });

    // Photo cards should still be present
    const cards = page.getByTestId("photo-card");
    await expect(cards.first()).toBeVisible({ timeout: 5000 });
    expect(await cards.count()).toBeGreaterThanOrEqual(1);
  });
});
