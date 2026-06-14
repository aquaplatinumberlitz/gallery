import { expect, test, type Page } from "./helpers/monitorErrors";

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
  "URBVHja7cEBDQAAAMKg909tDwcEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
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

// iPhone 14 Pro viewport
test.use({ viewport: { width: 390, height: 844 } });

test("mobile layout renders photo cards", async ({ page }) => {
  await installStubbedGallery(page);
  await openStubbedGallery(page);
  const count = await page.getByTestId("photo-card").count();
  expect(count).toBeGreaterThanOrEqual(1);
});

test("mobile header has search toggle", async ({ page }) => {
  await installStubbedGallery(page);
  await openStubbedGallery(page);

  const searchBtn = page.getByLabel("Open search");
  await expect(searchBtn).toBeVisible({ timeout: 5000 });
});

test("mobile navigation buttons are present", async ({ page }) => {
  await installStubbedGallery(page);
  await openStubbedGallery(page);

  const backBtn = page.getByLabel("Go back");
  await expect(backBtn).toBeAttached({ timeout: 5000 });
});

test("lightbox opens on mobile, metadata sheet opens and closes repeatedly", async ({ page }) => {
  await installStubbedGallery(page);
  await openStubbedGallery(page);

  // Dismiss mobile sidebar before interacting with photo cards
  await dismissMobileSidebar(page);

  // Open lightbox by clicking first photo
  await page.getByTestId("photo-card").first().click();

  // Assert lightbox is visible
  const lightbox = page.getByTestId("lightbox");
  await expect(lightbox).toBeVisible({ timeout: 10_000 });

  // Assert image counter shows (PhotoSwipe is active)
  const counter = lightbox.locator(".mobile-photo-counter");
  await expect(counter).toBeVisible({ timeout: 5000 });

  // --- Metadata sheet ---
  // Open metadata sheet via the "View image info" button
  // Use evaluate to click since force:true doesn't always penetrate SVG overlays
  const viewInfoBtn = page.getByLabel("View image info");
  await expect(viewInfoBtn).toBeVisible({ timeout: 5000 });
  await viewInfoBtn.evaluate((el: HTMLElement) => el.click());

  // Wait for BottomSheet to render (with animation)
  await expect(page.locator("[data-vsbs-sheet]")).toBeVisible({ timeout: 10_000 });

  // Assert metadata sheet is visible with prompt/copy UI
  const copyPromptBtn = page.getByLabel("Copy prompt");
  await expect(copyPromptBtn).toBeVisible({ timeout: 10_000 });

  // Assert seed param pill is visible (inside params tab)
  await page.locator("button.sheet-tab", { hasText: "Params" }).evaluate((el: HTMLElement) => el.click());
  await page.waitForTimeout(500);
  const seedPill = page.locator(".seed-row");
  await expect(seedPill).toBeVisible({ timeout: 3000 });
  await expect(seedPill).toContainText("12345");

  // Switch back to prompt tab
  await page.locator("button.sheet-tab", { hasText: "Prompt" }).evaluate((el: HTMLElement) => el.click());
  await page.waitForTimeout(300);

  // Close sheet — use the close mechanism exposed by the app's sheet.
  // Pointer events (mouse click) trigger PhotoSwipe closeOnVerticalDrag on mobile,
  // so we close programmatically by triggering the component's internal close handler.
  await page.evaluate(() => {
    // Find the BottomSheet's close button or trigger sheet close
    // The LightboxMobileSheet uses @douxcode/vue-spring-bottom-sheet
    // We can close via Vue's internal state by finding the sheet container
    const sheetEl = document.querySelector("[data-vsbs-sheet]") as HTMLElement;
    if (sheetEl) {
      // Dispatch a close-like event on the document
      // Sheet handles close via a pointerdown/up sequence with distance < threshold
      // Simulate a pointerdown outside + pointerup outside (tap on lightbox background)
      document.body.dispatchEvent(new PointerEvent("pointerdown", {
        bubbles: true, cancelable: true, pointerId: 99,
        clientX: 10, clientY: 10, isPrimary: true, pointerType: "mouse",
      }));
      document.body.dispatchEvent(new PointerEvent("pointerup", {
        bubbles: true, cancelable: true, pointerId: 99,
        clientX: 10, clientY: 10, isPrimary: true, pointerType: "mouse",
      }));
    }
  });
  await page.waitForTimeout(800);

  // Sheet should be dismissed - copy prompt button should no longer be visible
  await expect(copyPromptBtn).not.toBeVisible({ timeout: 5000 });

  // --- Repeat open/close 3 times ---
  for (let i = 0; i < 3; i++) {
    await expect(viewInfoBtn).toBeVisible({ timeout: 3000 });
    await viewInfoBtn.evaluate((el: HTMLElement) => el.click());
    await expect(page.locator("[data-vsbs-sheet]")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByLabel("Copy prompt")).toBeVisible({ timeout: 5000 });
    await page.evaluate((pid) => {
      document.body.dispatchEvent(new PointerEvent("pointerdown", {
        bubbles: true, cancelable: true, pointerId: 100 + pid,
        clientX: 10, clientY: 10, isPrimary: true, pointerType: "mouse",
      }));
      document.body.dispatchEvent(new PointerEvent("pointerup", {
        bubbles: true, cancelable: true, pointerId: 100 + pid,
        clientX: 10, clientY: 10, isPrimary: true, pointerType: "mouse",
      }));
    }, i);
    await page.waitForTimeout(500);
    await expect(page.getByLabel("Copy prompt")).not.toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(300);
  }

  // Assert copy buttons don't crash: open sheet, click copy, verify check icon appears
  await viewInfoBtn.evaluate((el: HTMLElement) => el.click());
  await expect(page.locator("[data-vsbs-sheet]")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByLabel("Copy prompt")).toBeVisible({ timeout: 5000 });
  await page.getByLabel("Copy prompt").evaluate((el: HTMLElement) => el.click());
  await page.waitForTimeout(300);
  // Verify the check icon appeared (copy succeeded)
  const checkIcon = page.locator(".inline-copy-icon").first();
  await expect(checkIcon).toBeVisible({ timeout: 3000 });
});

test("metadata sheet can be opened via View info button on mobile", async ({ page }) => {
  await installStubbedGallery(page);
  await openStubbedGallery(page);

  // Dismiss mobile sidebar
  await dismissMobileSidebar(page);

  // Open lightbox
  await page.getByTestId("photo-card").first().evaluate((el: HTMLElement) => el.click());
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });

  // Open metadata sheet via evaluate to bypass SVG overlay
  await page.getByLabel("View image info").evaluate((el: HTMLElement) => el.click());
  await expect(page.locator("[data-vsbs-sheet]")).toBeVisible({ timeout: 10_000 });

  // Verify metadata content is visible
  await expect(page.getByLabel("Copy prompt")).toBeVisible({ timeout: 5000 });
  await expect(page.getByLabel("Copy negative prompt")).toBeVisible({ timeout: 3000 });

  // Verify copy buttons work without crash
  await page.getByLabel("Copy prompt").evaluate((el: HTMLElement) => el.click());
  await page.waitForTimeout(300);
  await page.getByLabel("Copy negative prompt").evaluate((el: HTMLElement) => el.click());
  await page.waitForTimeout(300);

  // Page should still be functional
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 3000 });
});

test("mobile search works with fielded queries", async ({ page }) => {
  await installStubbedGallery(page);
  await openStubbedGallery(page);

  // Dismiss mobile sidebar
  await dismissMobileSidebar(page);

  // Open search
  const openSearchBtn = page.getByLabel("Open search");
  await expect(openSearchBtn).toBeVisible({ timeout: 5000 });
  await openSearchBtn.evaluate((el: HTMLElement) => el.click());
  await page.waitForTimeout(500);

  // Type fielded search query
  const searchInput = page.getByLabel("Search gallery");
  await expect(searchInput).toBeVisible({ timeout: 3000 });
  await searchInput.fill("prompt:mika");
  await searchInput.press("Enter");
  await page.waitForTimeout(500);

  // Close search
  const closeSearchBtn = page.getByLabel("Close search");
  await expect(closeSearchBtn).toBeVisible({ timeout: 3000 });
  await closeSearchBtn.evaluate((el: HTMLElement) => el.click());
  await page.waitForTimeout(300);

  // Photo cards should still be visible
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });
});
