/**
 * Purpose:
 * Verifies that the advanced search drawer builds fielded search queries and renders scoped results.
 *
 * Guarantees:
 * * drawer controls send the expected backend query strings
 * * search results, empty states, and special field inputs remain usable
 *
 * Run when:
 * * changing AdvancedSearchDrawer, fielded search UI, or search request serialization
 * * touching search result rendering or gallery search state
 */

import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import type { Locator } from "@playwright/test";
import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-advanced-search-test";
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

      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- Test route fixtures build heterogeneous API payloads before JSON serialization.
      const photos: any[] = [];
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- Test route fixtures build heterogeneous API payloads before JSON serialization.
      const promptResults: any[] = [];

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

        if (
          q.includes("rain") ||
          q.includes("blue") ||
          q.includes("PonyXL") ||
          q.includes("seed") ||
          q.includes("steps") ||
          q.includes("cfg") ||
          q.includes("width") ||
          q.includes("height") ||
          q.includes("ratio") ||
          q.includes("size") ||
          q.includes("prompt")
        ) {
          photos.push({ ...resultItem, match_type: "filename" });
        }
        if (q.includes("mika") || q.includes("prompt") || q.includes("blue")) {
          promptResults.push({
            ...resultItem,
            match_type: "prompt",
            prompt_snippet: q.includes("mika")
              ? "mika, portrait"
              : q.includes("blue")
                ? "blue archive, masterpiece"
                : "test prompt",
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
          scope: searchPayload?.scope?.kind ?? "all",
          root: rootPath,
          albums: [],
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

    if (url.pathname === "/api/search/count") {
      const countPayload = route.request().postDataJSON() as { text?: string } | null;
      const q = countPayload?.text ?? "";
      const total =
        q &&
        (q.includes("rain") ||
          q.includes("blue") ||
          q.includes("PonyXL") ||
          q.includes("seed") ||
          q.includes("steps") ||
          q.includes("cfg") ||
          q.includes("width") ||
          q.includes("height") ||
          q.includes("ratio") ||
          q.includes("size") ||
          q.includes("prompt") ||
          q.includes("mika"))
          ? 1
          : 0;
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ schema_version: 1, total, has_more: false }),
      });
      return;
    }

    if (url.pathname === "/api/facets") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          model: [
            { value: "PonyXL", count: 10 },
            { value: "SDXL", count: 5 },
          ],
          sampler: [
            { value: "Euler a", count: 15 },
            { value: "DPM++", count: 8 },
          ],
          scheduler: [{ value: "Karras", count: 20 }],
          tool: [
            { value: "Unknown", count: 100 },
            { value: "SwarmUI", count: 46 },
          ],
          orientation: [
            { value: "portrait", count: 141 },
            { value: "square", count: 44 },
          ],
          seed_availability: [
            { value: "available", count: 107 },
            { value: "missing", count: 102 },
          ],
          metadata_availability: [
            { value: "available", count: 209 },
            { value: "missing", count: 3 },
          ],
        }),
      });
      return;
    }

    if (url.pathname === "/api/search/capabilities") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          schema_version: 1,
          enabled_modes: ["lexical"],
          supported_scopes: ["folder", "library", "all"],
          field_limits: {},
          workflow_registry: { version: 1, nodes: {} },
          raw_search: {
            enabled: false,
            query_min_chars: 3,
            query_max_chars: 128,
            limit_max: 50,
            deadline_ms: 250,
            max_document_bytes: 1_048_576,
            index_budget_bytes: 536_870_912,
          },
          index_requirements: {},
          indexes: [],
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

async function expectNoHorizontalOverflow(scrollBody: Locator) {
  const overflowMetrics = await scrollBody.evaluate((element) => {
    const rootRect = element.getBoundingClientRect();
    const offenders = [...element.querySelectorAll<HTMLElement>("*")]
      .map((child) => {
        const rect = child.getBoundingClientRect();
        return {
          tag: child.tagName,
          id: child.id,
          className: child.className,
          left: rect.left,
          right: rect.right,
        };
      })
      .filter(({ left, right }) => right > left && (left < rootRect.left - 0.5 || right > rootRect.right + 0.5));

    return {
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      offenders,
    };
  });

  expect(overflowMetrics, JSON.stringify(overflowMetrics.offenders, null, 2)).toMatchObject({
    scrollWidth: overflowMetrics.clientWidth,
    offenders: [],
  });
}

test.describe("AdvancedSearchDrawer", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("drawer opens with intent groups and progressive disclosure", async ({ page }) => {
    await installStubbedGallery(page);
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });
    const closeBox = await page.getByLabel("Close").boundingBox();
    expect(closeBox?.width).toBeGreaterThanOrEqual(44);
    expect(closeBox?.height).toBeGreaterThanOrEqual(44);

    await expect(drawer).toContainText("Content and files");
    await expect(drawer).toContainText("Generation settings");
    await expect(drawer).toContainText("Dimensions");
    await expect(drawer).toContainText("Custom metadata");
    await expect(drawer.getByLabel("Tools indexed values")).toContainText("Unknown");
    await expect(drawer.getByLabel("Tools indexed values")).toContainText("SwarmUI");
    await expect(drawer.getByLabel("Seed indexed values")).toContainText("missing");
    await expect(drawer.getByLabel("Metadata indexed values")).toContainText("209");

    await expect(drawerField(drawer, "advanced-search-prompt")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-model")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-date")).toBeVisible();

    await expect(drawerField(drawer, "advanced-search-sampler")).not.toBeVisible();
    await drawer.getByRole("button", { name: /Generation settings/ }).click();
    await expect(drawerField(drawer, "advanced-search-sampler")).toBeVisible();
    await expectNoHorizontalOverflow(page.getByTestId("advanced-search-scroll-body"));
    await page.keyboard.press("Tab");
    await drawerField(drawer, "advanced-search-seed").focus();
    await expect
      .poll(
        () =>
          drawerField(drawer, "advanced-search-seed").evaluate((element) => {
            const control = element.closest(".advanced-search-numeric-control");
            return control ? getComputedStyle(control).boxShadow : "";
          }),
        { timeout: 1_000 },
      )
      .toMatch(/0px 0px 0px 3px/);
    const seedFocusStyle = await drawerField(drawer, "advanced-search-seed").evaluate((element) => {
      const control = element.closest(".advanced-search-numeric-control");
      const style = control ? getComputedStyle(control) : getComputedStyle(element);
      return {
        boxShadow: style.boxShadow,
        ringShadow: style.getPropertyValue("--tw-ring-shadow").trim(),
      };
    });
    expect(seedFocusStyle.boxShadow).toMatch(/0px 0px 0px 3px/);
    expect(seedFocusStyle.boxShadow).not.toContain("inset");

    await expect(drawerField(drawer, "advanced-search-seed")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-steps")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-cfg")).toBeVisible();

    await drawer.getByRole("button", { name: /Dimensions/ }).click();
    await expect(drawerField(drawer, "advanced-search-width")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-height")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-size")).toBeVisible();

    await expect(drawerField(drawer, "advanced-search-ratio")).toBeVisible();
    for (const preset of ["1:1", "4:3", "16:9", "3:2", "2:3", "9:16"]) {
      await expect(drawer.getByRole("button", { name: preset })).toBeVisible();
    }

    await drawer.getByRole("button", { name: /Custom metadata/ }).click();
    await expect(drawerField(drawer, "advanced-search-param")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-advanced")).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-raw")).not.toBeAttached();
    await expect(drawer.getByRole("button", { name: /Prompt discovery/ })).toBeVisible();
    await expect(drawer.getByRole("button", { name: /Workflow properties/ })).toBeVisible();
    await expect(drawer.getByRole("button", { name: /Index status/ })).toBeVisible();
    await expect(drawer.getByRole("button", { name: /Raw workflow/ })).not.toBeAttached();

    await expect(drawer.getByRole("button", { name: "Revert edits" })).toBeVisible();
    await expect(drawer.getByRole("button", { name: "Clear all" })).toBeVisible();
    await expect(drawer.getByRole("button", { name: "Cancel" })).toBeVisible();
    await expect(drawer.getByRole("button", { name: "Apply filters" })).toBeVisible();

    await page.getByLabel("Close").click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });
  });

  test("apply fielded search via drawer", async ({ page }) => {
    const requests = await installStubbedGallery(page);
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    await drawerField(drawer, "advanced-search-prompt").fill("blue archive");
    await drawerField(drawer, "advanced-search-model").fill("PonyXL");

    await drawer.getByRole("button", { name: /^Apply 2 filters$/ }).click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });
    await expect.poll(() => requestsFor(requests, "/api/search/query").length).toBeGreaterThanOrEqual(1);

    const searchReqs = requestsFor(requests, "/api/search/query");
    const lastSearch = searchReqs[searchReqs.length - 1]!;
    expect(lastSearch.q).toContain("prompt");
    expect(lastSearch.q).toContain("blue archive");
    expect(lastSearch.q).toContain("model");
    expect(lastSearch.q).toContain("PonyXL");
  });

  test("cancel restores previous state", async ({ page }) => {
    const requests = await installStubbedGallery(page);
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    await drawerField(drawer, "advanced-search-prompt").fill("test prompt");

    await drawer.getByRole("button", { name: "Cancel" }).click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });

    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer2 = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer2).toBeVisible({ timeout: 5_000 });

    // Verify fields returned to initial (empty) state
    const promptInput = drawerField(drawer2, "advanced-search-prompt");
    await expect(promptInput).toHaveValue("");

    // Verify no new search was executed after cancel
    const countBefore = requestsFor(requests, "/api/search/query").length;
    await drawer2.getByRole("button", { name: "Cancel" }).click();
    await expect(drawer2).not.toBeVisible({ timeout: 5_000 });
    const countAfter = requestsFor(requests, "/api/search/query").length;
    expect(countAfter).toBe(countBefore);
  });

  test("outside click does not discard dirty staged filters", async ({ page }) => {
    await installStubbedGallery(page);
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await drawerField(drawer, "advanced-search-prompt").fill("keep this edit");

    await page.mouse.click(100, 100);
    await expect(drawer).toBeVisible();
    await expect(drawerField(drawer, "advanced-search-prompt")).toHaveValue("keep this edit");
    await drawer.getByRole("button", { name: "Cancel" }).click();
  });

  test("clear all stages empty filters until apply", async ({ page }) => {
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
    await expect.poll(() => requestsFor(requests, "/api/search/query").some((r) => r.q.includes("seed"))).toBe(true);

    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    // Verify seed field is prefilled
    const seedInput = drawerField(drawer, "advanced-search-seed");
    await expect(seedInput).toHaveValue("12345");

    await drawer.getByRole("button", { name: "Clear all" }).click();
    await expect(drawer).toBeVisible();
    await expect(seedInput).toHaveValue("");
    await expect(searchInput).toHaveValue("seed:12345");

    await drawer.getByRole("button", { name: "Apply filters" }).click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });
    await expect(searchInput).toHaveValue("");
  });

  test("search filter chips render and remove", async ({ page }) => {
    const requests = await installStubbedGallery(page);
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    // Apply prompt filter via drawer
    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    await drawerField(drawer, "advanced-search-prompt").fill("mika");
    await drawer.getByRole("button", { name: "Apply 1 filter" }).click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });
    await expect.poll(() => requestsFor(requests, "/api/search/query").length).toBeGreaterThanOrEqual(1);

    // Verify chip appears
    const chip = page.getByLabel(/Remove filter:/i);
    await expect(chip).toBeVisible({ timeout: 5_000 });

    const chipText = await page.getByTestId("search-filter-chips").textContent();
    expect(chipText).toContain("prompt");
    expect(chipText).toContain("mika");

    // Remove chip
    await chip.click();
    await expect(chip).not.toBeVisible({ timeout: 3_000 });

    // Verify search input cleared
    const searchInput = page.locator("#gallery-search");
    await expect(searchInput).toHaveValue("");
  });

  test("numeric fields accept valid numbers", async ({ page }) => {
    const requests = await installStubbedGallery(page);
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    await drawer.getByRole("button", { name: /Generation settings/ }).click();
    await drawer.getByRole("button", { name: /Dimensions/ }).click();
    await drawerField(drawer, "advanced-search-seed").fill("12345");
    await drawerField(drawer, "advanced-search-steps").fill("30");
    await drawerField(drawer, "advanced-search-cfg").fill("7.5");
    await drawerField(drawer, "advanced-search-width").fill("1024");
    await drawerField(drawer, "advanced-search-height").fill("768");

    await drawer.getByRole("button", { name: /^Apply 5 filters$/ }).click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });
    await expect.poll(() => requestsFor(requests, "/api/search/query").length).toBeGreaterThanOrEqual(1);

    const searchReqs = requestsFor(requests, "/api/search/query");
    const lastSearch = searchReqs[searchReqs.length - 1]!;
    expect(lastSearch.q).toContain("seed:12345");
    expect(lastSearch.q).toContain("steps:30");
    expect(lastSearch.q).toContain("cfg:7.5");
    expect(lastSearch.q).toContain("width:1024");
    expect(lastSearch.q).toContain("height:768");
  });

  test("aspect ratio preset and size field", async ({ page }) => {
    const requests = await installStubbedGallery(page);
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    await drawer.getByRole("button", { name: /Dimensions/ }).click();
    // Click 16:9 preset button
    await drawer.getByRole("button", { name: "16:9" }).click();

    // Verify ratio input shows 16:9
    const ratioInput = drawerField(drawer, "advanced-search-ratio");
    await expect(ratioInput).toHaveValue("16:9");

    // Fill Size field
    await drawerField(drawer, "advanced-search-size").fill("1024x768");

    // Apply
    await drawer.getByRole("button", { name: /^Apply 2 filters$/ }).click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });
    await expect.poll(() => requestsFor(requests, "/api/search/query").length).toBeGreaterThanOrEqual(1);

    const searchReqs = requestsFor(requests, "/api/search/query");
    const lastSearch = searchReqs[searchReqs.length - 1]!;
    expect(lastSearch.q).toContain("ratio:16:9");
    expect(lastSearch.q).toContain("size:1024x768");
  });

  test("plain text search regression", async ({ page }) => {
    const requests = await installStubbedGallery(page);
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    const searchInput = page.locator("#gallery-search");
    await searchInput.fill("rain");
    await searchInput.press("Enter");
    await expect.poll(() => requestsFor(requests, "/api/search/query").some((r) => r.q === "rain")).toBe(true);

    const searchReqs = requestsFor(requests, "/api/search/query");
    expect(searchReqs.some((r) => r.q === "rain")).toBe(true);

    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });

    // Advanced Search button still works
    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    await page.getByLabel("Close").click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });

    // Clear and verify gallery returns
    await searchInput.fill("");
    await searchInput.press("Enter");
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });
  });

  test("between operator renders dual inputs and produces two staged filters", async ({ page }) => {
    const requests = await installStubbedGallery(page);
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    await drawer.getByRole("button", { name: /Generation settings/ }).click();

    // Select "between" operator on steps field
    const stepsField = drawerField(drawer, "advanced-search-steps");
    await stepsField.scrollIntoViewIfNeeded();
    const opTrigger = drawer.getByRole("combobox", { name: "Steps operator", exact: true });
    await opTrigger.click();
    await page.getByRole("option", { name: "Between" }).click();

    // Two inputs should appear
    const inputs = stepsField.locator("..").locator('input[type="text"], input[type="number"]');
    await expect(inputs).toHaveCount(2);

    // Fill low and high
    await inputs.nth(0).fill("20");
    await inputs.nth(1).fill("40");

    await drawer.getByRole("button", { name: /^Apply 2 filters$/ }).click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });
    await expect.poll(() => requestsFor(requests, "/api/search/query").length).toBeGreaterThanOrEqual(1);

    const searchReqs = requestsFor(requests, "/api/search/query");
    const lastSearch = searchReqs[searchReqs.length - 1]!;
    expect(lastSearch.q).toContain("steps:>=20");
    expect(lastSearch.q).toContain("steps:<=40");
  });

  test("facet combobox opens popover and selects value", async ({ page }) => {
    await installStubbedGallery(page);
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    // Model field uses facet combobox
    const modelField = drawerField(drawer, "advanced-search-model");
    await modelField.scrollIntoViewIfNeeded();

    // Click to open facet popover
    const popoverTrigger = drawer.getByRole("button", { name: "Browse Model suggestions" });
    await popoverTrigger.click();

    // Should see facet values with counts
    const suggestions = page.getByRole("listbox", { name: "Model suggestions" });
    await expect(suggestions.getByRole("option", { name: /PonyXL/ })).toBeVisible({ timeout: 3_000 });
    await expect(suggestions.getByRole("option", { name: /SDXL/ })).toBeVisible();

    // Select PonyXL
    await suggestions.getByRole("option", { name: /PonyXL/ }).click();
    await expect(modelField).toHaveValue("PonyXL");
  });

  test("jump-to-field quick input scrolls to target field", async ({ page }) => {
    await installStubbedGallery(page);
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    // Find jump-to input
    const jumpInput = drawer.locator('input[placeholder*="Jump"]');
    await expect(jumpInput).toBeVisible();

    // Type "seed" and press Enter
    await jumpInput.fill("seed");
    await jumpInput.press("Enter");

    // Seed field should be visible (scrolled into view)
    const seedField = drawerField(drawer, "advanced-search-seed");
    await expect(seedField).toBeVisible();
  });

  test("group headings separate discovery from filter sections", async ({ page }) => {
    await installStubbedGallery(page);
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    // Check for group heading text
    await expect(drawer.getByText("Discovery & tools")).toBeVisible();
    await expect(drawer.getByText("Filters", { exact: true })).toBeVisible();
  });

  test("drawer width matches responsive spec", async ({ page }) => {
    await installStubbedGallery(page);
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });

    // Desktop contract: min(640px, 42vw), matching the component class.
    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });
    const desktopBox = await drawer.boundingBox();
    const viewport = page.viewportSize();
    expect(desktopBox).not.toBeNull();
    expect(viewport).not.toBeNull();
    expect(desktopBox!.width).toBeCloseTo(Math.min(640, viewport!.width * 0.42), 0);

    await page.getByLabel("Close").click();
    await expect(drawer).not.toBeVisible({ timeout: 5_000 });
  });
});

for (const viewport of [
  { name: "tablet", width: 800, height: 900 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test.describe(`AdvancedSearchDrawer ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: "en-US" });

    test("opens from compact search and applies filters", async ({ page }) => {
      const requests = await installStubbedGallery(page);
      await page.addInitScript(() => {
        localStorage.setItem("intro_mode", "disabled");
        localStorage.setItem("gallery-active-library-id", "1");
        localStorage.setItem("gallery-active-import-path-id", "10");
        localStorage.setItem("gallery-sidebar-open", "false");
      });

      await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
      await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
      await page.getByLabel("Open search").click();
      await page.getByRole("button", { name: "Advanced Search" }).click();

      const drawer = page.getByRole("dialog", { name: "Advanced Search" });
      await expect(drawer).toBeVisible();
      const drawerBox = await drawer.boundingBox();
      expect(drawerBox?.width).toBeLessThanOrEqual(viewport.width);

      await drawer.getByRole("button", { name: /Generation settings/ }).click();
      await expectNoHorizontalOverflow(page.getByTestId("advanced-search-scroll-body"));

      await drawerField(drawer, "advanced-search-prompt").fill(`${viewport.name} search`);
      await drawer.getByRole("button", { name: "Apply 1 filter" }).click();
      await expect(drawer).not.toBeVisible();
      await expect.poll(() => requestsFor(requests, "/api/search/query").length).toBeGreaterThanOrEqual(1);
    });
  });
}
