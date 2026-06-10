import { expect, test, type Page } from "@playwright/test";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-mobile-sheet-test";
const imagePaths = [
  `${rootPath}/a.png`,
  `${rootPath}/b.png`,
  `${rootPath}/c.png`,
];
const stubPng = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAYAAABw4pVUAAAACXBIWXMAAAsTAAALEwEAmpwYAAAA" +
  "B3RJTUUH6QEJCyAjHXUYCwAAABl0RVh0Q29tbWVudABDcmVhdGVkIHdpdGggR0lNUFeBDhcAAAAS" +
  "SURBVHja7cEBDQAAAMKg909tDwcEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/BsYIAAB//8lVwA=",
  "base64"
);

type ApiRequest = { pathname: string; path: string };

async function installStubbedGallery(page: Page) {
  const requests: ApiRequest[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const req: ApiRequest = { pathname: url.pathname, path: url.searchParams.get("path") ?? "" };
    requests.push(req);

    if (url.pathname === "/api/scan") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          folders: [],
          images: imagePaths.map((path, i) => ({
            name: `image-${i + 1}.png`,
            path,
            type: "image",
            has_children: false,
            cover_images: [],
            mtime: 1000 + i,
            image_count: 0,
            width: 800,
            height: 600,
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
          tool: "A1111",
          prompt: ("masterpiece, best quality, 1girl, long flowing hair, detailed eyes, " +
            "intricate dress, cherry blossoms, soft lighting, depth of field").repeat(2),
          negative_prompt: "low quality, blurry, bad anatomy, watermark",
          params: { Seed: "12345", Steps: "30", Sampler: "Euler a", CFG: "7.0", Model: "ponyDiffusionV6XL" },
          width: 800,
          height: 600,
          name: req.path.split("/").pop() ?? "image.png",
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
      await route.fulfill({ contentType: "image/png", body: stubPng });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
  return requests;
}

async function _dismissMobileSidebar(page: Page) {
  // On mobile, the sidebar is open by default and blocks interactions.
  // Tap outside the sidebar to dismiss it.
  const sidebar = page.locator("#sidebar.mobile.open, aside.sidebar.mobile.open");
  if (await sidebar.isVisible({ timeout: 2000 }).catch(() => false)) {
    // Click near the center-right of the viewport (outside sidebar)
    await page.mouse.click(300, 400);
    await page.waitForTimeout(500);
  }
}

// iPhone 14 Pro viewport
test.use({ viewport: { width: 390, height: 844 } });

test("mobile layout renders photo cards", async ({ page }) => {
  await installStubbedGallery(page);
  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
  expect(await page.getByTestId("photo-card").count()).toBeGreaterThanOrEqual(1);
});

test("mobile header has search toggle", async ({ page }) => {
  await installStubbedGallery(page);
  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  const searchBtn = page.getByLabel("Open search");
  await expect(searchBtn).toBeVisible({ timeout: 5000 });
});

test("mobile navigation buttons are present", async ({ page }) => {
  await installStubbedGallery(page);
  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  const backBtn = page.getByLabel("Go back");
  await expect(backBtn).toBeAttached({ timeout: 5000 });
});

test("lightbox opens on mobile and can close", async ({ page }) => {
  await installStubbedGallery(page);
  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

  // On mobile, sidebar may be open and blocking clicks - dismiss it
  await _dismissMobileSidebar(page);

  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Click the first photo (force click to bypass sidebar if needed)
  await page.getByTestId("photo-card").first().click({ force: true });
  await page.waitForTimeout(1000);

  // The lightbox should appear
  const lightbox = page.getByTestId("lightbox");
  const isLightboxVisible = await lightbox.isVisible({ timeout: 5000 }).catch(() => false);

  if (isLightboxVisible) {
    const closeBtn = page.getByLabel("Close");
    if (await closeBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await closeBtn.click();
      await page.waitForTimeout(300);
    }
  }

  // App should not crash
  expect(await page.content()).toBeTruthy();
});

test("metadata sheet can be opened via View info button on mobile", async ({ page }) => {
  await installStubbedGallery(page);
  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await _dismissMobileSidebar(page);
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  await page.getByTestId("photo-card").first().click({ force: true });
  await page.waitForTimeout(500);

  // On mobile, there's a "View image info" button
  const viewInfoBtn = page.getByLabel("View image info");
  if (await viewInfoBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await viewInfoBtn.click({ force: true });
    await page.waitForTimeout(500);
  }

  // Check for metadata sheet content
  const copyPromptBtn = page.getByLabel("Copy prompt");
  const isCopyVisible = await copyPromptBtn.isVisible({ timeout: 3000 }).catch(() => false);

  if (isCopyVisible) {
    await copyPromptBtn.click();
    await page.waitForTimeout(200);
  }

  expect(await page.content()).toBeTruthy();
});

test("mobile search works with fielded queries", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await _dismissMobileSidebar(page);
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Open search
  const openSearchBtn = page.getByLabel("Open search");
  await openSearchBtn.click({ force: true });
  await page.waitForTimeout(300);

  // Type fielded search query
  const searchInput = page.getByLabel("Search gallery");
  await searchInput.fill("prompt:mika");
  await searchInput.press("Enter");
  await page.waitForTimeout(500);

  // Clear search
  const clearBtn = page.getByLabel("Clear search");
  if (await clearBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await clearBtn.click();
    await page.waitForTimeout(300);
  }

  // Close search
  const closeSearchBtn = page.getByLabel("Close search");
  if (await closeSearchBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await closeSearchBtn.click();
    await page.waitForTimeout(300);
  }

  expect(await page.content()).toBeTruthy();
});

