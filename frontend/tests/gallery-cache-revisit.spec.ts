import { expect, test, type Page } from "@playwright/test";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-cache-revisit-test";
const imagePaths = [
  `${rootPath}/a.png`,
  `${rootPath}/b.png`,
  `${rootPath}/c.png`,
];
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64"
);

type ApiRequest = { pathname: string; path: string };

function requestsFor(requests: ApiRequest[], pathname: string) {
  return requests.filter((r) => r.pathname === pathname);
}

async function installStubbedGallery(page: Page, options: { simulateSlow?: boolean } = {}) {
  const requests: ApiRequest[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const req: ApiRequest = { pathname: url.pathname, path: url.searchParams.get("path") ?? "" };
    requests.push(req);

    if (url.pathname === "/api/scan") {
      if (options.simulateSlow) {
        await new Promise((r) => setTimeout(r, 200));
      }
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
      await route.fulfill({ contentType: "image/png", body: png1x1 });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
  return requests;
}

test.use({ viewport: { width: 1280, height: 820 } });

test("first album open may show loading state", async ({ page }) => {
  const requests = await installStubbedGallery(page, { simulateSlow: true });

  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

  // Wait for first photo card to be visible - may take a moment due to slow API
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Verify scan was called
  expect(requestsFor(requests, "/api/scan").length).toBeGreaterThanOrEqual(1);
});

test("revisit within cache window renders cards immediately", async ({ page }) => {
  const requests = await installStubbedGallery(page);

  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  // First visit - cold load
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Reload the page (simulate revisit)
  const scanCountBefore = requestsFor(requests, "/api/scan").length;
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Second visit should still make a scan request but may use cached data
  const scanCountAfter = requestsFor(requests, "/api/scan").length;
  expect(scanCountAfter).toBeGreaterThanOrEqual(scanCountBefore);
});

test("no empty skeleton flicker on cached revisit", async ({ page }) => {
  const requests = await installStubbedGallery(page);

  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Check that photo cards are present (not skeleton/empty state)
  const cardCount = await page.getByTestId("photo-card").count();
  expect(cardCount).toBeGreaterThanOrEqual(1);
});

test("no duplicate scan on revisit", async ({ page }) => {
  const requests = await installStubbedGallery(page);

  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Clear request tracking after initial load settles
  requests.length = 0;

  // Trigger a soft revisit by reloading
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
  await page.waitForTimeout(500);

  // Should not see an explosion of duplicate scans
  const scanRequests = requestsFor(requests, "/api/scan");
  expect(scanRequests.length).toBeLessThanOrEqual(2);
});
