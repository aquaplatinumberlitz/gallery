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

type ApiRequest = { pathname: string; path: string; imageCursor: string };

function requestsFor(requests: ApiRequest[], pathname: string) {
  return requests.filter((r) => r.pathname === pathname);
}

function cursorZeroScans(requests: ApiRequest[]) {
  return requests.filter(
    (r) => r.pathname === "/api/scan" && r.imageCursor === "0"
  );
}

async function installStubbedGallery(page: Page) {
  const requests: ApiRequest[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const req: ApiRequest = {
      pathname: url.pathname,
      path: url.searchParams.get("path") ?? "",
      imageCursor: url.searchParams.get("image_cursor") ?? "0",
    };
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

    if (url.pathname === "/api/search") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          query: url.searchParams.get("q") ?? "",
          scope: "all",
          root: rootPath,
          albums: [],
          photos: [],
          prompt: [],
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

test("first album open shows photo cards", async ({ page }) => {
  const requests = await installStubbedGallery(page);

  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
  expect(requestsFor(requests, "/api/scan").length).toBeGreaterThanOrEqual(1);
});

test("soft revisit via search UI does not trigger duplicate cursor=0 scans", async ({ page }) => {
  const requests = await installStubbedGallery(page);

  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Wait for initial scan to settle, then clear request tracking
  await page.waitForTimeout(500);
  requests.length = 0;

  // Soft navigation: enter search (switches to search view)
  await page.locator("#gallery-search").fill("navigate-away");
  await page.locator("#gallery-search").press("Enter");
  await page.waitForTimeout(500);

  // Soft navigation back: clear search (restores gallery view)
  await page.locator("#gallery-search").fill("");
  await page.locator("#gallery-search").press("Enter");
  await page.waitForTimeout(500);

  // Photo cards should reappear quickly (no skeleton/flicker)
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });

  // No duplicate cursor=0 scan on revisit
  const cursorZero = cursorZeroScans(requests);
  expect(cursorZero.length).toBeLessThanOrEqual(1);

  // Verify photo cards are rendered
  const cardCount = await page.getByTestId("photo-card").count();
  expect(cardCount).toBeGreaterThanOrEqual(1);
});

test("revisit after browser back preserves gallery without duplicate scans", async ({ page }) => {
  const requests = await installStubbedGallery(page);

  await page.addInitScript((root) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", root);
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Navigate away
  await page.goto("data:text/html,<h1>Away</h1>", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(300);

  // Track requests after re-entry
  requests.length = 0;

  // Navigate back
  await page.goBack({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(500);

  // Photo cards should be visible without excessive new scans
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  const scanRequests = requestsFor(requests, "/api/scan");
  const cursorZero = cursorZeroScans(requests);

  // On revisit, cursor=0 scans should be minimal (cached data)
  expect(cursorZero.length).toBeLessThanOrEqual(2);

  // Cards should be rendered
  const cardCount = await page.getByTestId("photo-card").count();
  expect(cardCount).toBeGreaterThanOrEqual(1);
});
