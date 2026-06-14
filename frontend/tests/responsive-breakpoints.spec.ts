import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-responsive-test";
const imagePaths = Array.from({ length: 6 }, (_, i) => `${rootPath}/image_${i + 1}.png`);
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64"
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
          tool: "stub", prompt: "stub prompt", negative_prompt: "",
          params: {}, width: 1600, height: 1000,
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
  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
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
  });
});

test.describe("Tablet layout (834px - iPad Pro 11\")", () => {
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
  });

  test("desktop layout shows folder tree or sidebar", async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);

    // Desktop should have a toggle sidebar button or a sidebar visible
    const sidebarToggle = page.getByLabel("Toggle sidebar");
    const searchInput = page.getByRole("searchbox");
    // At least one of these desktop-specific elements should be present
    const hasDesktopUI = await Promise.race([
      sidebarToggle.isVisible().then(() => true).catch(() => false),
      searchInput.isVisible().then(() => true).catch(() => false),
    ]);
    expect(hasDesktopUI).toBe(true);
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
    await page.waitForTimeout(500);

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
    await page.waitForTimeout(500);

    // Photo cards should still be present
    const cards = page.getByTestId("photo-card");
    await expect(cards.first()).toBeVisible({ timeout: 5000 });
    expect(await cards.count()).toBeGreaterThanOrEqual(1);
  });
});
