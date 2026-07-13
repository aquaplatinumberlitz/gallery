/**
 * Purpose:
 * Exercises the managed browser contracts for Search V2 discovery surfaces.
 *
 * Guarantees:
 * * canonical searches survive reload and browser history navigation
 * * saved/recent, prompt, workflow, raw, and index controls execute their typed API contracts
 * * discovery controls remain available and labelled at desktop, tablet, and mobile widths
 *
 * Run when:
 * * changing Search V2 URL state or the advanced-search discovery components
 * * changing prompt/workflow/raw/index lifecycle API contracts
 */

import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-search-discovery-test";
const imagePath = `${rootPath}/rain_girl.png`;
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64",
);

const stubLibrary = {
  id: 1,
  root_path: rootPath,
  import_paths: [{ id: 10, library_id: 1, path: rootPath, position: 0, created_at: 1, updated_at: 1 }],
  exclusion_patterns: [],
  name: "Discovery Library",
  state: "ready",
  watch_enabled: 1,
  warm_enabled: 1,
  asset_count: 1,
  created_at: 1,
  updated_at: 1,
  last_scan_at: null,
  last_error: null,
};

const capabilities = {
  schema_version: 1,
  enabled_modes: ["lexical", "workflow", "raw"],
  supported_scopes: ["folder", "library", "all"],
  field_limits: {
    text_max_chars: 512,
    request_max_bytes: 32768,
    limit_min: 1,
    limit_max: 100,
    prompt_groups_max: 8,
    workflow_groups_max: 4,
    workflow_predicates_per_group_max: 8,
  },
  workflow_registry: {
    version: 1,
    nodes: {
      KSampler: {
        steps: { type: "integer", operators: ["eq", "gte", "lte"] },
        cfg: { type: "real", operators: ["eq", "gte", "lte"] },
      },
    },
  },
  raw_search: {
    enabled: true,
    query_min_chars: 3,
    query_max_chars: 128,
    limit_max: 50,
    deadline_ms: 250,
    max_document_bytes: 1048576,
    index_budget_bytes: 536870912,
  },
  index_requirements: {
    lexical: [],
    prompt_groups: ["prompt_values"],
    workflow: ["workflow_properties"],
    raw: ["workflow_raw"],
  },
  indexes: [
    { index_name: "prompt_values", enabled: true, schema_version: 1, extractor_version: 1, required_mode: "lexical" },
    {
      index_name: "workflow_properties",
      enabled: true,
      schema_version: 1,
      extractor_version: 1,
      required_mode: "workflow",
    },
    { index_name: "workflow_raw", enabled: true, schema_version: 1, extractor_version: 1, required_mode: "raw" },
  ],
};

type CapturedRequest = { pathname: string; method: string; payload: Record<string, unknown> | null };
type IndexRow = {
  index_name: string;
  library_id: number;
  library_name: string;
  state: string;
  usable: boolean;
  enabled: boolean;
  schema_version: number;
  extractor_version: number;
  indexed_count: number;
  target_count: number;
  failed_count: number;
  skipped_count: number;
  skip_reasons: Record<string, number>;
  active_job_id: number | null;
  error_code: string | null;
  error_summary: string | null;
  warning: string | null;
};

const indexRow = (overrides: Partial<IndexRow>): IndexRow => ({
  index_name: "prompt_values",
  library_id: 1,
  library_name: "Discovery Library",
  state: "ready",
  usable: true,
  enabled: true,
  schema_version: 1,
  extractor_version: 1,
  indexed_count: 1,
  target_count: 1,
  failed_count: 0,
  skipped_count: 0,
  skip_reasons: {},
  active_job_id: null,
  error_code: null,
  error_summary: null,
  warning: null,
  ...overrides,
});

function searchResponse(payload: Record<string, unknown> | null) {
  const text = typeof payload?.text === "string" ? payload.text : "";
  const item = {
    asset_id: 1,
    name: "rain_girl.png",
    path: imagePath,
    type: "photo",
    parent_path: rootPath,
    relative_path: "",
    mtime: 1001,
    width: 1600,
    height: 1000,
    match_type: "filename",
    prompt_snippet: "rain portrait",
    model: "PonyXL",
    sampler: "Euler a",
    seed: "12345",
  };
  return {
    query: text,
    scope: (payload?.scope as { kind?: string } | undefined)?.kind ?? "all",
    root: rootPath,
    albums: [],
    photos: [item],
    media: [item],
    prompt: [],
    videos: [],
    next_cursor: null,
    has_more: false,
    returned: 1,
    limit: typeof payload?.limit === "number" ? payload.limit : 60,
  };
}

async function installDiscoveryFixture(page: Page) {
  const requests: CapturedRequest[] = [];
  let indexes = [
    indexRow({ index_name: "prompt_values" }),
    indexRow({
      index_name: "workflow_properties",
      state: "failed",
      usable: false,
      indexed_count: 0,
      failed_count: 1,
      error_code: "extractor_failed",
      error_summary: "Workflow extraction failed",
    }),
    indexRow({
      index_name: "workflow_raw",
      state: "building",
      indexed_count: 2,
      target_count: 4,
      skipped_count: 1,
      skip_reasons: { document_too_large: 1 },
      active_job_id: 77,
    }),
  ];

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    let payload: Record<string, unknown> | null = null;
    if (request.method() !== "GET") {
      try {
        payload = request.postDataJSON() as Record<string, unknown>;
      } catch {
        payload = null;
      }
    }
    requests.push({ pathname: url.pathname, method: request.method(), payload });

    const fulfill = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (url.pathname === "/api/libraries") return fulfill([stubLibrary]);
    if (url.pathname === "/api/libraries/1/status") {
      return fulfill(statusEnvelope({ libraryId: 1, path: url.searchParams.get("scope_path") ?? rootPath }));
    }
    if (url.pathname === "/api/browse") {
      return fulfill(
        browseResponse({
          libraryId: 1,
          path: url.searchParams.get("path") ?? rootPath,
          media: [
            {
              name: "rain_girl.png",
              path: imagePath,
              type: "image",
              has_children: false,
              cover_images: [],
              mtime: 1001,
              image_count: 0,
              width: 1600,
              height: 1000,
            },
          ],
        }),
      );
    }
    if (url.pathname === "/api/search/capabilities") return fulfill(capabilities);
    if (url.pathname === "/api/search/query") return fulfill(searchResponse(payload));
    if (url.pathname === "/api/search/prompt-usage/query") {
      const negative = payload?.polarity === "negative";
      return fulfill({
        items: [
          {
            value_id: negative ? "n".repeat(43) : "p".repeat(43),
            kind: negative ? "negative" : "positive",
            text: negative ? "blurry watermark" : "cinematic rain portrait",
            asset_count: negative ? 2 : 5,
            last_asset_mtime_ns: 1001,
            sample_asset: { asset_id: 1, library_id: 1, path: imagePath },
          },
        ],
        next_cursor: null,
        has_more: false,
        returned: 1,
      });
    }
    if (url.pathname === "/api/search/workflow/raw") {
      return fulfill({
        query: payload?.query ?? "",
        items: [
          {
            asset_id: 1,
            library_id: 1,
            library_name: "Discovery Library",
            path: imagePath,
            name: "rain_girl.png",
            mtime_ns: 1001,
          },
        ],
        next_cursor: null,
        has_more: false,
        returned: 1,
        warning: "bounded raw search",
        capability: { deadline_ms: 250, max_query_chars: 128, max_limit: 50 },
      });
    }
    if (url.pathname === "/api/search/indexes") return fulfill(indexes);
    const rebuildMatch = url.pathname.match(/^\/api\/search\/indexes\/([^/]+)\/rebuild$/);
    if (rebuildMatch) {
      const indexName = rebuildMatch[1];
      indexes = indexes.map((row) =>
        row.index_name === indexName
          ? { ...row, state: "ready", usable: true, indexed_count: row.target_count, active_job_id: null }
          : row,
      );
      return fulfill(
        {
          id: 88,
          index_name: indexName,
          library_id: 1,
          mode: "missing",
          state: "queued",
          processed_count: 0,
          target_count: 1,
          failed_count: 0,
          skipped_count: 0,
        },
        202,
      );
    }
    if (url.pathname === "/api/search/index-jobs/77/cancel") {
      indexes = indexes.map((row) =>
        row.active_job_id === 77 ? { ...row, state: "failed", active_job_id: null, error_summary: "Cancelled" } : row,
      );
      return fulfill({
        id: 77,
        index_name: "workflow_raw",
        library_id: 1,
        mode: "missing",
        state: "cancel_requested",
        processed_count: 2,
        target_count: 4,
        failed_count: 0,
        skipped_count: 1,
      });
    }
    if (url.pathname === "/api/facets") {
      return fulfill({ model: [{ value: "PonyXL", count: 1 }], sampler: [], scheduler: [] });
    }
    if (url.pathname === "/api/health") return fulfill({ status: "ok" });
    if (url.pathname === "/api/landing-pages") return fulfill([]);
    if (url.pathname === "/api/metadata") {
      return fulfill({
        tool: "ComfyUI",
        prompt: "cinematic rain portrait",
        negative_prompt: "blurry watermark",
        params: {},
        width: 1600,
        height: 1000,
        name: "rain_girl.png",
      });
    }
    if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
      return route.fulfill({ contentType: "image/png", body: png1x1 });
    }
    return fulfill({}, 404);
  });

  return requests;
}

async function initializeGallery(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
    localStorage.setItem("gallery-sidebar-open", "false");
  });
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
}

async function openAdvancedSearch(page: Page, compact = false) {
  if (compact) await page.getByLabel("Open search").click();
  await page.getByRole("button", { name: "Advanced Search" }).click();
  const drawer = page.getByRole("dialog", { name: "Advanced Search" });
  await expect(drawer).toBeVisible();
  return drawer;
}

const byPath = (requests: CapturedRequest[], pathname: string) => requests.filter((item) => item.pathname === pathname);

test.describe("Search discovery evolution", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("shares, reloads, and navigates mixed text and fielded searches", async ({ page }) => {
    const requests = await installDiscoveryFixture(page);
    await initializeGallery(page);
    const input = page.locator("#gallery-search");

    await input.fill("rain prompt:mika");
    await input.press("Enter");
    await expect.poll(() => byPath(requests, "/api/search/query").at(-1)?.payload?.text).toBe("rain prompt:mika");
    await expect(page).toHaveURL(/search_v=1/);
    await expect(page).toHaveURL(/q=rain(?:\+|%20)prompt(?::|%3A)mika/);

    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(input).toHaveValue("rain prompt:mika");

    await input.fill("snow model:PonyXL");
    await input.press("Enter");
    await expect(page).toHaveURL(/q=snow(?:\+|%20)model(?::|%3A)PonyXL/);
    await page.goBack();
    await expect(input).toHaveValue("rain prompt:mika");
    await page.goForward();
    await expect(input).toHaveValue("snow model:PonyXL");
  });

  test("saves, reruns, renames, deletes, and refreshes recent searches", async ({ page }) => {
    const requests = await installDiscoveryFixture(page);
    await initializeGallery(page);
    const input = page.locator("#gallery-search");
    await input.fill("rain");
    await input.press("Enter");
    await expect.poll(() => byPath(requests, "/api/search/query").at(-1)?.payload?.text).toBe("rain");

    let drawer = await openAdvancedSearch(page);
    const library = drawer.getByRole("region", { name: "Search library" });
    await expect(library.getByText("rain", { exact: true })).toBeVisible();
    await library.getByLabel("Saved search name").fill("Rain study");
    await library.getByRole("button", { name: "Save" }).click();
    const renameInput = library.getByLabel("Rename Rain study");
    await renameInput.fill("Weather study");
    await renameInput.press("Tab");
    await expect(library.getByLabel("Rename Weather study")).toBeVisible();
    await page.getByLabel("Close").click();

    await input.fill("");
    await input.press("Enter");
    drawer = await openAdvancedSearch(page);
    const savedItem = drawer
      .getByLabel("Rename Weather study")
      .locator("xpath=ancestor::div[contains(@class, 'library-item')]");
    await savedItem.getByRole("button", { name: "Run" }).click();
    await expect(input).toHaveValue("rain");
    await expect(page).toHaveURL(/q=rain/);

    drawer = await openAdvancedSearch(page);
    await drawer.getByLabel("Delete Weather study").click();
    await expect(drawer.getByLabel("Rename Weather study")).not.toBeAttached();
  });

  test("browses positive and negative prompt groups and shows exact assets", async ({ page }) => {
    const requests = await installDiscoveryFixture(page);
    await initializeGallery(page);

    let drawer = await openAdvancedSearch(page);
    await drawer.getByRole("button", { name: /Prompt discovery/ }).click();
    await expect(drawer.getByText("cinematic rain portrait")).toBeVisible();
    await drawer.getByRole("button", { name: "Show assets" }).click();
    await expect
      .poll(() => byPath(requests, "/api/search/query").at(-1)?.payload?.filters)
      .toEqual({ prompt_groups: [{ kind: "positive", value_id: "p".repeat(43) }], workflow_groups: [] });

    drawer = await openAdvancedSearch(page);
    await drawer.getByRole("button", { name: /Prompt discovery/ }).click();
    await drawer.getByRole("tab", { name: "Negative" }).click();
    await expect(drawer.getByText("blurry watermark")).toBeVisible();
    await drawer.getByRole("button", { name: "Show assets" }).click();
    await expect
      .poll(() => byPath(requests, "/api/search/query").at(-1)?.payload?.filters)
      .toEqual({ prompt_groups: [{ kind: "negative", value_id: "n".repeat(43) }], workflow_groups: [] });
  });

  test("applies two typed predicates to the same ComfyUI node", async ({ page }) => {
    const requests = await installDiscoveryFixture(page);
    await initializeGallery(page);
    const drawer = await openAdvancedSearch(page);
    await drawer.getByRole("button", { name: /Workflow properties/ }).click();
    await drawer.getByRole("button", { name: "Add group" }).click();
    await drawer.getByLabel("Value for group 1, row 1").fill("20");
    await drawer.getByRole("button", { name: "Add predicate" }).click();
    await drawer.getByLabel("Property for group 1, row 2").selectOption("cfg");
    await drawer.getByLabel("Value for group 1, row 2").fill("7.5");
    await drawer.getByRole("button", { name: "Show matching assets" }).click();

    const workflowRequest = byPath(requests, "/api/search/query").at(-1)?.payload;
    expect(workflowRequest?.mode).toBe("workflow");
    expect(workflowRequest?.filters).toEqual({
      prompt_groups: [],
      workflow_groups: [
        {
          node_type: "KSampler",
          predicates: [
            { property: "steps", op: "eq", value: 20 },
            { property: "cfg", op: "eq", value: 7.5 },
          ],
        },
      ],
    });
  });

  test("runs raw workflow search only after explicit acknowledgement", async ({ page }) => {
    const requests = await installDiscoveryFixture(page);
    await initializeGallery(page);
    const drawer = await openAdvancedSearch(page);
    await drawer.getByRole("button", { name: /Raw workflow/ }).click();
    const raw = drawer.getByRole("region", { name: "Raw workflow search" });
    await raw.getByLabel("Raw workflow search term").fill("KSampler");
    await expect(raw.getByRole("button", { name: "Apply" })).toBeDisabled();
    expect(byPath(requests, "/api/search/workflow/raw")).toHaveLength(0);
    await raw.getByLabel(/I understand this can take up to/).check();
    await raw.getByRole("button", { name: "Apply" }).click();
    await expect(raw.getByText("rain_girl.png")).toBeVisible();
    expect(byPath(requests, "/api/search/workflow/raw").at(-1)?.payload?.query).toBe("KSampler");
  });

  test("renders index success and failure states and cancels an active rebuild", async ({ page }) => {
    const requests = await installDiscoveryFixture(page);
    await initializeGallery(page);
    const drawer = await openAdvancedSearch(page);
    await drawer.getByRole("button", { name: /Index status/ }).click();
    const indexPanel = drawer.getByRole("region", { name: "Search indexes" });
    const promptRow = indexPanel.locator(".index-row").filter({ hasText: "prompt values" });
    const failedRow = indexPanel.locator(".index-row").filter({ hasText: "workflow properties" });
    const buildingRow = indexPanel.locator(".index-row").filter({ hasText: "workflow raw" });

    await expect(promptRow).toContainText("ready");
    await expect(failedRow).toContainText("Workflow extraction failed");
    await expect(buildingRow).toContainText("document_too_large: 1");

    page.once("dialog", (dialog) => dialog.accept());
    await promptRow.getByRole("button", { name: "Rebuild" }).click();
    await expect.poll(() => byPath(requests, "/api/search/indexes/prompt_values/rebuild").length).toBeGreaterThan(0);
    await buildingRow.getByRole("button", { name: "Cancel" }).click();
    await expect.poll(() => byPath(requests, "/api/search/index-jobs/77/cancel").length).toBeGreaterThan(0);
  });
});

for (const viewport of [
  { name: "desktop", width: 1280, height: 900, compact: false },
  { name: "tablet", width: 800, height: 900, compact: true },
  { name: "mobile", width: 390, height: 844, compact: true },
]) {
  test(`exposes equivalent labelled discovery controls on ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await installDiscoveryFixture(page);
    await initializeGallery(page);
    const drawer = await openAdvancedSearch(page, viewport.compact);

    await expect(drawer.getByLabel("Saved search name")).toBeVisible();
    for (const name of [/Prompt discovery/, /Workflow properties/, /Raw workflow/, /Index status/]) {
      await expect(drawer.getByRole("button", { name })).toBeVisible();
    }
    const closeBox = await page.getByLabel("Close").boundingBox();
    expect(closeBox?.width).toBeGreaterThanOrEqual(44);
    expect(closeBox?.height).toBeGreaterThanOrEqual(44);
    const overflow = await page.getByTestId("advanced-search-scroll-body").evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
    }));
    expect(overflow.scrollWidth).toBe(overflow.clientWidth);
  });
}
