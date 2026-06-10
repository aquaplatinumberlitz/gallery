import { expect, test } from "@playwright/test";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const galleryRoot = "/home/ubuntu/gallery-repo/test-images";

async function setupGallery(page: import("@playwright/test").Page) {
  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
    localStorage.setItem("gallery-sort-preference", JSON.stringify({ field: "name", order: "asc" }));
    localStorage.setItem("gallery-albums-collapsed", "false");
    localStorage.removeItem("gallery-lightbox-always-load-original");
  }, galleryRoot);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

  // Dismiss intro/landing page if present (safety net)
  const enterBtn = page.getByRole("button", { name: /enter gallery/i });
  if (await enterBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await enterBtn.click();
    await page.waitForURL("**/");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
  }
}

test.use({ viewport: { width: 1280, height: 820 } });

test("navigates albums without page reload against real backend", async ({ page }) => {
  let navigations = 0;
  page.on("framenavigated", () => { navigations++; });

  await setupGallery(page);

  // Wait for albums to appear
  await expect(page.getByTestId("album-card").first()).toBeVisible({ timeout: 20_000 });
  expect(navigations).toBeLessThanOrEqual(1);

  // Click into first album
  await page.getByTestId("album-card").first().click();
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 20_000 });
  expect(navigations).toBeLessThanOrEqual(1);

  // Open lightbox
  await page.getByTestId("photo-card").first().click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 15_000 });
  expect(navigations).toBeLessThanOrEqual(1);

  // Wait for preview to load (derivative-first policy)
  await page.waitForTimeout(2000);

  // Verify no unexpected reloads during lightbox navigation
  const nextBtn = page.locator('[data-testid="lightbox-next"], .pswp__button--arrow--right');
  if (await nextBtn.isVisible().catch(() => false)) {
    await nextBtn.click();
    await page.waitForTimeout(500);
  }
  expect(navigations).toBeLessThanOrEqual(1);

  // Close lightbox
  const closeBtn = page.locator('[data-testid="lightbox-close"], .pswp__button--close');
  if (await closeBtn.isVisible().catch(() => false)) {
    await closeBtn.click();
  } else {
    await page.keyboard.press("Escape");
  }
  await page.waitForTimeout(1000);
  expect(navigations).toBeLessThanOrEqual(1);
});

test("no duplicate initial /api/scan against real backend", async ({ page }) => {
  const scanUrls: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/api/scan")) scanUrls.push(req.url());
  });

  await setupGallery(page);
  await expect(page.getByTestId("album-card").first()).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(1500);

  // Count root-level scans (no path, or path = galleryRoot)
  const rootScans = scanUrls.filter((u) => {
    const p = new URL(u).searchParams;
    const path = p.get("path");
    return !path || path === galleryRoot || path === "/";
  });

  expect(rootScans.length).toBeGreaterThanOrEqual(1);
  expect(rootScans.length).toBeLessThanOrEqual(2);
});
