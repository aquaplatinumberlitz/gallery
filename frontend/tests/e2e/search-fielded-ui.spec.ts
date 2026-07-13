/**
 * Purpose:
 * Verifies plain and fielded search behavior in the main gallery UI.
 *
 * Guarantees:
 * * query text is sent to the expected search endpoint parameters
 * * results, clear search, no-results, and special-character queries keep the UI stable
 * * album suggestions use the device-specific album card presentation
 *
 * Run when:
 * * changing search inputs, fielded query parsing UI, or search result rendering
 * * touching query serialization or search-scope behavior
 */

import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-search-ui-test";
const imagePaths = [`${rootPath}/rain_girl.png`, `${rootPath}/snow_landscape.png`, `${rootPath}/portrait.png`];
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

type ApiRequest = { pathname: string; path: string; q: string };
type SearchPayload = { text?: string; scope?: { kind?: string; relative_path?: string }; limit?: number };

function requestsFor(requests: ApiRequest[], pathname: string) {
  return requests.filter((r) => r.pathname === pathname);
}

async function installStubbedGallery(page: Page) {
  const requests: ApiRequest[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const searchPayload =
      url.pathname === "/api/search/query" ? (route.request().postDataJSON() as SearchPayload | null) : null;
    const req: ApiRequest = {
      pathname: url.pathname,
      path: searchPayload?.scope?.relative_path ?? url.searchParams.get("path") ?? "",
      q: searchPayload?.text ?? url.searchParams.get("q") ?? "",
    };
    requests.push(req);

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
              name: path.split("/").pop()!,
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

    if (url.pathname === "/api/search/query") {
      const q = req.q;
      const scope = searchPayload?.scope?.kind ?? "all";

      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- Test route fixtures build heterogeneous API payloads before JSON serialization.
      let photos: any[] = [];
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- Test route fixtures build heterogeneous API payloads before JSON serialization.
      let promptResults: any[] = [];
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- Test route fixtures build heterogeneous API payloads before JSON serialization.
      let albums: any[] = [];

      if (q.includes("album")) {
        albums = [
          {
            name: "Portrait studies",
            path: `${rootPath}/portrait-studies`,
            type: "album",
            parent_path: rootPath,
            relative_path: "portrait-studies",
            cover_images: [imagePaths[0], imagePaths[2]],
            image_count: 18,
            mtime: 1004,
          },
          {
            name: "Weather worlds",
            path: `${rootPath}/weather-worlds`,
            type: "album",
            parent_path: rootPath,
            relative_path: "weather-worlds",
            cover_images: [imagePaths[1]],
            image_count: 9,
            mtime: 1005,
          },
        ];
      } else if (q.includes("rain")) {
        photos = [
          {
            name: "rain_girl.png",
            path: `${rootPath}/rain_girl.png`,
            type: "photo",
            parent_path: rootPath,
            relative_path: "",
            mtime: 1001,
            width: 1600,
            height: 1000,
            match_type: "filename",
            prompt_snippet: "",
            model: "",
            sampler: "",
            seed: "",
          },
        ];
        promptResults = [
          {
            name: "rain_girl.png",
            path: `${rootPath}/rain_girl.png`,
            type: "photo",
            parent_path: rootPath,
            relative_path: "",
            mtime: 1001,
            width: 1600,
            height: 1000,
            match_type: "prompt",
            prompt_snippet: "masterpiece, rain",
            model: "TestModel",
            sampler: "Euler a",
            seed: "12345",
          },
        ];
      } else if (q.includes("mika")) {
        promptResults = [
          {
            name: "rain_girl.png",
            path: `${rootPath}/rain_girl.png`,
            type: "photo",
            parent_path: rootPath,
            relative_path: "",
            mtime: 1001,
            width: 1600,
            height: 1000,
            match_type: "prompt",
            prompt_snippet: "mika, portrait",
            model: "TestModel",
            sampler: "Euler a",
            seed: "12345",
          },
        ];
      }

      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          query: q,
          scope,
          root: rootPath,
          albums,
          photos,
          media: [...photos, ...promptResults],
          prompt: promptResults,
          videos: [],
          next_cursor: null,
          has_more: false,
          returned: photos.length + promptResults.length,
          limit: searchPayload?.limit ?? 60,
        }),
      });
      return;
    }

    if (url.pathname === "/api/metadata") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          tool: "A1111",
          prompt: "test prompt",
          negative_prompt: "",
          params: {},
          width: 1600,
          height: 1000,
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

test("plain search finds results and shows them in UI", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Verify initial photos are rendered
  const initialCount = await page.getByTestId("photo-card").count();
  expect(initialCount).toBeGreaterThanOrEqual(1);

  // Search for "rain" — should show result images
  const searchInput = page.locator("#gallery-search");
  await searchInput.fill("rain");
  await searchInput.press("Enter");
  await expect.poll(() => requestsFor(requests, "/api/search/query").some((r) => r.q.includes("rain"))).toBe(true);

  // Search request should have been made
  const searchRequests = requestsFor(requests, "/api/search/query");
  expect(searchRequests.length).toBeGreaterThanOrEqual(1);
  expect(searchRequests.some((r) => r.q.includes("rain"))).toBe(true);

  // Result images should be visible (photo-card or search result cards)
  const resultCards = page.getByTestId("photo-card");
  const resultCount = await resultCards.count();
  expect(resultCount).toBeGreaterThanOrEqual(1);
});

test("fielded search prompt:mika sends correct query and shows results", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  const searchInput = page.locator("#gallery-search");
  await searchInput.fill("prompt:mika");
  await searchInput.press("Enter");
  await expect.poll(() => requestsFor(requests, "/api/search/query").some((r) => r.q === "prompt:mika")).toBe(true);

  const searchRequests = requestsFor(requests, "/api/search/query");
  expect(searchRequests.some((r) => r.q === "prompt:mika")).toBe(true);

  // Result cards should be visible
  const resultCards = page.getByTestId("photo-card");
  const resultCount = await resultCards.count();
  expect(resultCount).toBeGreaterThanOrEqual(1);
});

test("seed query sends correct query string and shows results", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  const searchInput = page.locator("#gallery-search");
  await searchInput.fill("seed:12345");
  await searchInput.press("Enter");
  await expect.poll(() => requestsFor(requests, "/api/search/query").some((r) => r.q === "seed:12345")).toBe(true);

  const searchRequests = requestsFor(requests, "/api/search/query");
  expect(searchRequests.some((r) => r.q === "seed:12345")).toBe(true);
});

test("clear search restores gallery view", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Perform a search — wait for request to confirm search executed
  const searchInput = page.locator("#gallery-search");
  await searchInput.fill("rain");
  await searchInput.press("Enter");
  await expect.poll(() => requestsFor(requests, "/api/search/query").some((r) => r.q.includes("rain"))).toBe(true);

  // Clear the search
  await searchInput.fill("");
  await searchInput.press("Enter");
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });

  // Photo cards should still be visible (gallery restored)
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });

  // Original gallery photos should be back
  const cardCount = await page.getByTestId("photo-card").count();
  expect(cardCount).toBeGreaterThanOrEqual(1);
});

test("no-results state does not break layout", async ({ page }) => {
  await installStubbedGallery(page);
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Search for something that won't match
  const searchInput = page.locator("#gallery-search");
  await searchInput.fill("zzz_nonexistent_xyz_12345");
  await searchInput.press("Enter");
  await expect(searchInput).toHaveValue("zzz_nonexistent_xyz_12345");

  // The app should not crash - page should still be functional
  const pageContent = await page.content();
  expect(pageContent.length).toBeGreaterThan(0);

  // Clear search and verify gallery returns with photos
  await searchInput.fill("");
  await searchInput.press("Enter");
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });
});

test("search query with special characters does not crash", async ({ page }) => {
  const requests = await installStubbedGallery(page);
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

  // Try various special character queries
  const specialQueries = ['prompt:"test with spaces"', "model:test seed:123", "size:1024x768"];

  for (const q of specialQueries) {
    const searchInput = page.locator("#gallery-search");
    await searchInput.fill(q);
    await searchInput.press("Enter");

    // Verify search request was made
    await expect.poll(() => requestsFor(requests, "/api/search/query").some((r) => r.q === q)).toBe(true);
  }

  // Clear and restore
  const searchInput = page.locator("#gallery-search");
  await searchInput.fill("");
  await searchInput.press("Enter");
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });
});

test.describe("mobile album suggestions", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("uses the mobile album card visual in a two-column grid", async ({ page }) => {
    await installStubbedGallery(page);
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
      localStorage.setItem("gallery-sidebar-open", "false");
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByLabel("Open search").click();
    const searchInput = page.getByLabel("Search gallery");
    await searchInput.fill("album");
    await searchInput.press("Enter");

    await expect(page.getByText("Album suggestions", { exact: true })).toBeVisible();
    const cards = page.locator(".search-album-grid > .album-card-mobile");
    await expect(cards).toHaveCount(2);
    await expect(page.locator(".search-album-grid > .album-card")).toHaveCount(0);

    const cardBoxes = await cards.evaluateAll((elements) =>
      elements.map((element) => {
        const rect = element.getBoundingClientRect();
        return { width: rect.width, top: rect.top };
      }),
    );

    expect(cardBoxes[0].width).toBeLessThan(190);
    expect(Math.abs(cardBoxes[0].top - cardBoxes[1].top)).toBeLessThan(2);
  });
});
