import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-advanced-search-test";
const imagePaths = [
  `${rootPath}/rain_girl.png`,
  `${rootPath}/snow_landscape.png`,
  `${rootPath}/portrait.png`,
];
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64"
);

type ApiRequest = { pathname: string; path: string; q: string };

function requestsFor(requests: ApiRequest[], pathname: string) {
  return requests.filter((r) => r.pathname === pathname);
}

async function installStubbedGallery(page: Page) {
  const requests: ApiRequest[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const req: ApiRequest = {
      pathname: url.pathname,
      path: url.searchParams.get("path") ?? "",
      q: url.searchParams.get("q") ?? "",
    };
    requests.push(req);

    if (url.pathname === "/api/scan") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          folders: [],
          images: imagePaths.map((path, i) => ({
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
          next_cursor: null,
          total_images: imagePaths.length,
          index_source: "direct_scan",
        }),
      });
      return;
    }

    if (url.pathname === "/api/search") {
      const q = url.searchParams.get("q") ?? "";

      let photos: any[] = [];
      let promptResults: any[] = [];

      if (q) {
        const resultItem = {
          name: "rain_girl.png",
          path: `${rootPath}/rain_girl.png`,
          type: "photo",
          parent_path: rootPath,
          relative_path: "",
          mtime: 1001,
          width: 1600,
          height: 1000,
          match_type: "filename",
          prompt_snippet: "masterpiece, test",
          model: "TestModel",
          sampler: "Euler a",
          seed: "12345",
        };

        if (q.includes("rain") || q.includes("blue") || q.includes("PonyXL") || q.includes("seed") || q.includes("steps") || q.includes("cfg") || q.includes("width") || q.includes("height") || q.includes("ratio") || q.includes("size") || q.includes("prompt")) {
          photos.push({ ...resultItem, match_type: "filename" });
        }
        if (q.includes("mika") || q.includes("prompt") || q.includes("blue")) {
          promptResults.push({
            ...resultItem,
            match_type: "prompt",
            prompt_snippet: q.includes("mika") ? "mika, portrait" : q.includes("blue") ? "blue archive, masterpiece" : "test prompt",
          });
        }
        if (photos.length === 0 && promptResults.length === 0) {
          photos.push(resultItem);
        }
      }

      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          query: q,
          scope: url.searchParams.get("scope") ?? "all",
          root: rootPath,
          albums: [],
          photos,
          prompt: promptResults,
        }),
      });
      return;
    }

    if (url.pathname === "/api/facets") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          model: [{ value: "PonyXL", count: 10 }, { value: "SDXL", count: 5 }],
          sampler: [{ value: "Euler a", count: 15 }, { value: "DPM++", count: 8 }],
          scheduler: [{ value: "Karras", count: 20 }],
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

/** Get a form field by id within the drawer, scoped to avoid ambiguity. */
function drawerField(drawer: ReturnType<Page["getByRole"]>, id: string) {
  return drawer.locator(`#${id}`);
}

test.describe("AdvancedSearchDrawer", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("drawer opens with all field groups visible", async ({ page }) => {
    await installStubbedGallery(page);
    await page.addInitScript((root) => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-root-path", root);
    }, rootPath);

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByLabel("Advanced Search").click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    await expect(drawer).toContainText("Text Fields");
    await expect(drawer).toContainText("Numeric Fields");
    await expect(drawer).toContainText("Dimensions");
    await expect(drawer).toContainText("Aspect Ratio");
    await expect(drawer).toContainText("Date");
    await expect(drawer).toContainText("Generic / Power-user");

    await expect(drawerField(drawer, "advanced-search-prompt")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-model")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-sampler")).toBeVisible();

    await expect(drawerField(drawer, "advanced-search-seed")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-steps")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-cfg")).toBeVisible();

    await expect(drawerField(drawer, "advanced-search-width")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-height")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-size")).toBeVisible();

    await expect(drawerField(drawer, "advanced-search-ratio")).toBeVisible();
    for (const preset of ["1:1", "4:3", "16:9", "3:2", "2:3", "9:16"]) {
      await expect(drawer.getByRole("button", { name: preset })).toBeVisible();
    }

    await expect(drawerField(drawer, "advanced-search-date")).toBeVisible();

    await expect(drawerField(drawer, "advanced-search-param")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-advanced")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-raw")).toBeVisible();

    await expect(drawer.getByRole("button", { name: /Reset/ })).toBeVisible();
    await expect(drawer.getByRole("button", { name: "Cancel" })).toBeVisible();
    await expect(drawer.getByRole("button", { name: "Apply" })).toBeVisible();

    await page.getByLabel("Close advanced search").click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });
  });

  test("apply fielded search via drawer", async ({ page }) => {
    const requests = await installStubbedGallery(page);
    await page.addInitScript((root) => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-root-path", root);
    }, rootPath);

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByLabel("Advanced Search").click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    await drawerField(drawer, "advanced-search-prompt").fill("blue archive");
    await drawerField(drawer, "advanced-search-model").fill("PonyXL");

    await drawer.getByRole("button", { name: "Apply" }).click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });
    await page.waitForTimeout(1500);

    const searchReqs = requestsFor(requests, "/api/search");
    expect(searchReqs.length).toBeGreaterThanOrEqual(1);
    const lastSearch = searchReqs[searchReqs.length - 1]!;
    expect(lastSearch.q).toContain("prompt");
    expect(lastSearch.q).toContain("blue archive");
    expect(lastSearch.q).toContain("model");
    expect(lastSearch.q).toContain("PonyXL");
  });

  test("cancel restores previous state", async ({ page }) => {
    const requests = await installStubbedGallery(page);
    await page.addInitScript((root) => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-root-path", root);
    }, rootPath);

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByLabel("Advanced Search").click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    await drawerField(drawer, "advanced-search-prompt").fill("test prompt");

    await drawer.getByRole("button", { name: "Cancel" }).click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });

    await page.getByLabel("Advanced Search").click();
    const drawer2 = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer2).toBeVisible({ timeout: 5_000 });

    // Verify fields returned to initial (empty) state
    const promptInput = drawerField(drawer2, "advanced-search-prompt");
    await expect(promptInput).toHaveValue("");

    // Verify no new search was executed after cancel
    const countBefore = requestsFor(requests, "/api/search").length;
    await drawer2.getByRole("button", { name: "Cancel" }).click();
    await expect(drawer2).not.toBeVisible({ timeout: 5_000 });
    const countAfter = requestsFor(requests, "/api/search").length;
    expect(countAfter).toBe(countBefore);
  });

  test("reset clears all fields and active filters", async ({ page }) => {
    const requests = await installStubbedGallery(page);
    await page.addInitScript((root) => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-root-path", root);
    }, rootPath);

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    const searchInput = page.locator("#gallery-search");
    await searchInput.fill("seed:12345");
    await searchInput.press("Enter");
    await page.waitForTimeout(500);

    await page.getByLabel("Advanced Search").click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    // Verify seed field is prefilled
    const seedInput = drawerField(drawer, "advanced-search-seed");
    await expect(seedInput).toHaveValue("12345");

    // Click Reset — should clear all filters and close
    await drawer.getByRole("button", { name: /Reset/ }).click();

    // Verify search query is cleared
    await expect(searchInput).toHaveValue("");
  });

  test("search filter chips render and remove", async ({ page }) => {
    const requests = await installStubbedGallery(page);
    await page.addInitScript((root) => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-root-path", root);
    }, rootPath);

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    // Apply prompt filter via drawer
    await page.getByLabel("Advanced Search").click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    await drawerField(drawer, "advanced-search-prompt").fill("mika");
    await drawer.getByRole("button", { name: "Apply" }).click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });
    await page.waitForTimeout(1500);

    // Verify chip appears
    const chip = page.getByLabel(/Remove filter:/i);
    await expect(chip).toBeVisible({ timeout: 5_000 });

    const chipText = await page.locator(".flex-wrap .gap-1").textContent();
    expect(chipText).toContain("prompt");
    expect(chipText).toContain("mika");

    // Remove chip
    await chip.click();
    await page.waitForTimeout(300);
    await expect(chip).not.toBeVisible({ timeout: 3_000 });

    // Verify search input cleared
    const searchInput = page.locator("#gallery-search");
    await expect(searchInput).toHaveValue("");
  });

  test("numeric fields accept valid numbers", async ({ page }) => {
    const requests = await installStubbedGallery(page);
    await page.addInitScript((root) => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-root-path", root);
    }, rootPath);

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByLabel("Advanced Search").click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    await drawerField(drawer, "advanced-search-seed").fill("12345");
    await drawerField(drawer, "advanced-search-steps").fill("30");
    await drawerField(drawer, "advanced-search-cfg").fill("7.5");
    await drawerField(drawer, "advanced-search-width").fill("1024");
    await drawerField(drawer, "advanced-search-height").fill("768");

    await drawer.getByRole("button", { name: "Apply" }).click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });
    await page.waitForTimeout(1500);

    const searchReqs = requestsFor(requests, "/api/search");
    const lastSearch = searchReqs[searchReqs.length - 1]!;
    expect(lastSearch.q).toContain("seed:12345");
    expect(lastSearch.q).toContain("steps:30");
    expect(lastSearch.q).toContain("cfg:7.5");
    expect(lastSearch.q).toContain("width:1024");
    expect(lastSearch.q).toContain("height:768");
  });

  test("aspect ratio preset and size field", async ({ page }) => {
    const requests = await installStubbedGallery(page);
    await page.addInitScript((root) => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-root-path", root);
    }, rootPath);

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByLabel("Advanced Search").click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    // Click 16:9 preset button
    await drawer.getByRole("button", { name: "16:9" }).click();
    await page.waitForTimeout(200);

    // Verify ratio input shows 16:9
    const ratioInput = drawerField(drawer, "advanced-search-ratio");
    await expect(ratioInput).toHaveValue("16:9");

    // Fill Size field
    await drawerField(drawer, "advanced-search-size").fill("1024x768");

    // Apply
    await drawer.getByRole("button", { name: "Apply" }).click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });
    await page.waitForTimeout(1500);

    const searchReqs = requestsFor(requests, "/api/search");
    const lastSearch = searchReqs[searchReqs.length - 1]!;
    expect(lastSearch.q).toContain("ratio:16:9");
    expect(lastSearch.q).toContain("size:1024x768");
  });

  test("plain text search regression", async ({ page }) => {
    const requests = await installStubbedGallery(page);
    await page.addInitScript((root) => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-root-path", root);
    }, rootPath);

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    const searchInput = page.locator("#gallery-search");
    await searchInput.fill("rain");
    await searchInput.press("Enter");
    await page.waitForTimeout(500);

    const searchReqs = requestsFor(requests, "/api/search");
    expect(searchReqs.some((r) => r.q === "rain")).toBe(true);

    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });

    // Advanced Search button still works
    await page.getByLabel("Advanced Search").click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    await page.getByLabel("Close advanced search").click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });

    // Clear and verify gallery returns
    await searchInput.fill("");
    await searchInput.press("Enter");
    await page.waitForTimeout(500);
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });
  });
});
