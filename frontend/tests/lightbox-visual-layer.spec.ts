import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-visual-layer-test";
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
  return requests.filter((request) => request.pathname === pathname);
}

async function installStubbedGallery(page: Page) {
  const requests: ApiRequest[] = [];

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const request: ApiRequest = {
      pathname: url.pathname,
      path: url.searchParams.get("path") ?? "",
    };
    requests.push(request);

    if (url.pathname === "/api/scan") {
      await route.fulfill({
        contentType: "application/json",
        headers: { "Cache-Control": "no-store" },
        body: JSON.stringify({
          folders: [],
          images: imagePaths.map((path, index) => ({
            name: `image-${index + 1}.png`,
            path,
            type: "image",
            mtime: 1000 + index,
            width: 1600,
            height: 1000,
          })),
          next_cursor: null,
          total_images: imagePaths.length,
        }),
      });
      return;
    }

    if (url.pathname === "/api/metadata") {
      await route.fulfill({
        contentType: "application/json",
        headers: { "Cache-Control": "no-store" },
        body: JSON.stringify({
          tool: "stub",
          prompt: "stub prompt",
          negative_prompt: "",
          params: {},
          date: "",
          generation_time: "",
          width: 1600,
          height: 1000,
          name: request.path.split("/").pop() ?? "image.png",
        }),
      });
      return;
    }

    if (url.pathname === "/api/landing-pages") {
      await route.fulfill({
        contentType: "application/json",
        headers: { "Cache-Control": "no-store" },
        body: JSON.stringify([]),
      });
      return;
    }

    if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
      await route.fulfill({
        contentType: "image/png",
        headers: { "Cache-Control": "no-store" },
        body: png1x1,
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });

  return requests;
}

async function openStubbedGallery(page: Page) {
  await page.addInitScript((rootForInit) => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-root-path", rootForInit);
    localStorage.setItem("gallery-sort-preference", JSON.stringify({ field: "name", order: "asc" }));
    localStorage.removeItem("gallery-lightbox-always-load-original");
  }, rootPath);

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
}

test.use({ viewport: { width: 1280, height: 820 } });

test("should have exactly one pswp root and no duplicate visible imgs", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await openStubbedGallery(page);

  await page.getByTestId("photo-card").first().click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
  await page.waitForTimeout(2000);

  const report = await page.evaluate(() => {
    const roots = document.querySelectorAll(".pswp");
    const allImgs = document.querySelectorAll<HTMLImageElement>(".pswp__img");
    const placeholders = document.querySelectorAll(".pswp__img--placeholder");

    const items = document.querySelectorAll<HTMLElement>(".pswp__item");
    const perItemCounts: { itemIdx: number; total: number; visible: number; visibleSrcs: string[] }[] = [];
    let totalVisibleImgs = 0;

    items.forEach((item, idx) => {
      const imgs = item.querySelectorAll<HTMLImageElement>(".pswp__img");
      let visible = 0;
      const visibleSrcs: string[] = [];
      imgs.forEach((img) => {
        const style = getComputedStyle(img);
        const rect = img.getBoundingClientRect();
        if (
          style.display !== "none" &&
          parseFloat(style.opacity) > 0 &&
          style.visibility !== "hidden" &&
          rect.width > 0 &&
          rect.height > 0
        ) {
          visible++;
          totalVisibleImgs++;
          visibleSrcs.push(img.src.slice(0, 120));
        }
      });
      perItemCounts.push({ itemIdx: idx, total: imgs.length, visible, visibleSrcs });
    });

    return {
      rootCount: roots.length,
      totalImgs: allImgs.length,
      totalVisibleImgs,
      placeholderCount: placeholders.length,
      perItemCounts,
    };
  });

  expect(report.rootCount).toBe(1);

  // Each .pswp__item must have at most 1 visible .pswp__img.
  // A count of 2+ signals the duplicate-img-tornado bug.
  for (const item of report.perItemCounts) {
    expect(
      item.visible,
      `.pswp__item[${item.itemIdx}] has ${item.visible} visible .pswp__img — duplicate bug?`
    ).toBeLessThanOrEqual(1);
  }

  // With preload: [1, 1], all 3 item holders may have loaded images.
  expect(report.totalVisibleImgs, "total visible imgs").toBeGreaterThanOrEqual(1);

  expect(requestsFor(requests, "/api/image")).toHaveLength(0);
});

test("should have exactly one pswp root after close and reopen", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await openStubbedGallery(page);

  // Open
  await page.getByTestId("photo-card").first().click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
  await page.waitForTimeout(1000);

  // Close
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("lightbox")).not.toBeVisible({ timeout: 5000 });
  await page.waitForTimeout(500);

  // Reopen
  await page.getByTestId("photo-card").first().click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
  await page.waitForTimeout(2000);

  const rootCount = await page.evaluate(() => document.querySelectorAll(".pswp").length);
  expect(rootCount).toBe(1);
});
