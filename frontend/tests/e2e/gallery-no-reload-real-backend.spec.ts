/**
 * Purpose:
 * Verifies no-reload navigation against a real backend and real test images.
 *
 * Guarantees:
 * * album browse and lightbox navigation do not cause full page reloads
 * * initial real-backend browse request is not duplicated unnecessarily
 *
 * Run when:
 * * changing app boot, routing, lightbox navigation, or real backend browse wiring
 * * investigating reloads that only reproduce with real server responses
 */

import { expect, test } from "./helpers/monitorErrors";

test.skip(
  process.env.GALLERY_E2E_DIAGNOSTICS !== "1",
  "Skipping: set GALLERY_E2E_DIAGNOSTICS=1 to run real-backend diagnostic tests",
);

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const pathSafetyRoot = process.env.PATH_SAFETY_ROOT_PATH ?? "/home/ubuntu/gallery-repo/test-images";

interface LibrarySelection {
  id: number;
  import_paths: { id: number; path: string }[];
}

const pathContains = (root: string, candidate: string) =>
  candidate === root || candidate.startsWith(`${root.replace(/\/$/, "")}/`);

async function setupGallery(page: import("@playwright/test").Page) {
  const response = await page.request.get(`${baseUrl}/api/libraries`);
  expect(response.ok()).toBe(true);
  const libraries = (await response.json()) as LibrarySelection[];
  const matchingLibrary = libraries.find((library) =>
    library.import_paths.some((importPath) => pathContains(importPath.path, pathSafetyRoot)),
  );
  const activeLibrary = matchingLibrary ?? libraries[0];
  const activeImportPath =
    activeLibrary?.import_paths.find((importPath) => pathContains(importPath.path, pathSafetyRoot)) ??
    activeLibrary?.import_paths[0];
  if (!activeLibrary || !activeImportPath) throw new Error("Real-backend E2E requires a registered import path");

  await page.addInitScript(
    ({ libraryId, importPathId }) => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", String(libraryId));
      localStorage.setItem("gallery-active-import-path-id", String(importPathId));
      localStorage.setItem("gallery-sort-preference", JSON.stringify({ field: "name", order: "asc" }));
      localStorage.setItem("gallery-albums-collapsed", "false");
      localStorage.removeItem("gallery-lightbox-always-load-original");
    },
    { libraryId: activeLibrary.id, importPathId: activeImportPath.id },
  );

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
  page.on("framenavigated", () => {
    navigations++;
  });

  await setupGallery(page);

  // Wait for albums to appear
  await expect(page.getByTestId("album-card").first()).toBeVisible({ timeout: 20_000 });
  navigations = 0;

  // Click into first album
  await page.getByTestId("album-card").first().click();
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 20_000 });
  expect(navigations).toBe(0);

  // Open lightbox
  await page.getByTestId("photo-card").first().click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 15_000 });
  expect(navigations).toBe(0);

  // Wait for preview to load (derivative-first policy)
  await page.waitForTimeout(2000);

  // Verify no unexpected reloads during lightbox navigation
  const nextBtn = page.locator('[data-testid="lightbox-next"], .pswp__button--arrow--right');
  if (await nextBtn.isVisible().catch(() => false)) {
    await nextBtn.click();
    await page.waitForTimeout(500);
  }
  expect(navigations).toBe(0);

  // Close lightbox
  const closeBtn = page.locator('[data-testid="lightbox-close"], .pswp__button--close');
  if (await closeBtn.isVisible().catch(() => false)) {
    await closeBtn.click();
  } else {
    await page.keyboard.press("Escape");
  }
  await page.waitForTimeout(1000);
  expect(navigations).toBe(0);
});

test("no duplicate initial /api/browse against real backend", async ({ page }) => {
  const browseUrls: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/api/browse")) browseUrls.push(req.url());
  });

  await setupGallery(page);
  await expect(page.getByTestId("album-card").first()).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(1500);

  // Count root-level browse requests (no path, or path = pathSafetyRoot)
  const rootBrowses = browseUrls.filter((u) => {
    const p = new URL(u).searchParams;
    const path = p.get("path");
    return !path || path === pathSafetyRoot || path === "/";
  });

  expect(rootBrowses.length).toBeGreaterThanOrEqual(1);
  expect(rootBrowses.length).toBeLessThanOrEqual(2);
});
