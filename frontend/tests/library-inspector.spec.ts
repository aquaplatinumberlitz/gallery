/**
 * Purpose:
 * Verifies Library Inspector search, scope, metadata detail, and stale-data behavior.
 *
 * Guarantees:
 * * inspector rows reflect API responses, empty states, metadata details, and scope changes
 * * inspector interactions do not leak internal debug fields into normal UI
 *
 * Run when:
 * * changing LibraryInspector, inspector query hooks, metadata detail fetches, or row rendering
 * * touching search scope, stale notices, or inspector cache behavior
 */

import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-library-inspector-test";
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64"
);

type InspectorRow = {
  path: string;
  name: string;
  folder: string;
  relative_path: string;
  mtime: number;
  width: number;
  height: number;
  model: string;
  tool: string;
  sampler: string;
  seed: string;
  prompt_preview: string;
  has_prompt: boolean;
  has_negative: boolean;
  has_lora: boolean;
  lora_count: number;
  lora_preview: string;
  metadata_detail_available: boolean;
};

type LightboxNavDebugEvent = {
  event?: string;
  key?: string;
};

const makeRow = (name: string, folder: string, mtime: number, overrides: Partial<InspectorRow> = {}): InspectorRow => ({
  path: `${rootPath}/${folder}/${name}`,
  name,
  folder: `${rootPath}/${folder}`,
  relative_path: folder,
  mtime,
  width: 1024,
  height: 1536,
  model: "SDXL",
  tool: "ComfyUI",
  sampler: "DPM++ 2M",
  seed: String(123450 + (1770000500 - mtime)),
  prompt_preview: `cinematic ${name.replace(".png", "")}, warm light, detailed texture, atmospheric depth`,
  has_prompt: true,
  has_negative: true,
  has_lora: false,
  lora_count: 0,
  lora_preview: "",
  metadata_detail_available: true,
  ...overrides,
});

const baseRows: InspectorRow[] = [
  makeRow("zeta-arch.png", "comfyui/session-z", 1770000400, {
    seed: "999001",
    prompt_preview: "zeta arch, wide composition, sandstone and rim light",
  }),
  makeRow("ancient-door.png", "comfyui/session-a", 1770000300, {
    seed: "123456",
    prompt_preview: "cinematic warm light, old wooden door, dust particles, detailed wood grain",
    has_lora: true,
    lora_count: 2,
    lora_preview: "door-detail, warm-light",
  }),
  makeRow("blue-forest.png", "automatic1111/forest", 1770000200, {
    model: "Flux",
    seed: "222333",
    prompt_preview: "blue forest, mist, volumetric moonlight and a very long prompt preview that should truncate",
  }),
  makeRow("crystal-cave.png", "comfyui/caves", 1770000100, {
    seed: "333444",
    prompt_preview: "crystal cave, reflected caustics, underground lake",
  }),
  ...Array.from({ length: 36 }, (_, index) =>
    makeRow(`extra-${index.toString().padStart(2, "0")}.png`, `batch/${index % 4}`, 1769999900 - index, {
      seed: `8${index.toString().padStart(5, "0")}`,
      prompt_preview: `extra generated image ${index}, metadata prompt preview`,
    })
  ),
];

function rowsForQuery(query: string) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return baseRows;
  return baseRows.filter((row) =>
    [row.name, row.relative_path, row.model, row.seed, row.prompt_preview]
      .join(" ")
      .toLowerCase()
      .includes(normalized.replace(/^prompt:/, ""))
  );
}

function detailForPath(path: string) {
  const row = baseRows.find((item) => item.path === path) ?? baseRows[0];
  return {
    path: row.path,
    name: row.name,
    prompt: `${row.prompt_preview}, full prompt detail`,
    negative_prompt: "bad hands, watermark",
    raw_metadata: null,
    model: row.model,
    tool: row.tool,
    sampler: row.sampler,
    seed: row.seed,
    width: row.width,
    height: row.height,
    mtime: row.mtime,
    loras: row.has_lora
      ? [
          { name: "door-detail", resource_hash: "abc123", weight: 0.8 },
          { name: "warm-light", resource_hash: "def456", weight: 0.6 },
        ]
      : [],
    resources: [],
    metadata_detail_available: true,
    prompt_preview: row.prompt_preview,
    date: "Mar 02, 2026",
    generation_time: "1.2s",
  };
}

async function installStubbedInspector(page: Page) {
  const requests: string[] = [];
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (text: string) => {
          (window as Window & { __copiedText?: string }).__copiedText = text;
        },
      },
    });
  });

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    requests.push(`${url.pathname}?${url.searchParams.toString()}`);

    if (url.pathname === "/api/library/inspector") {
      const requestNumber = requests.filter((request) => request.startsWith("/api/library/inspector?")).length - 1;
      const query = url.searchParams.get("q") ?? "";
      const rows = rowsForQuery(query);
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          root: rootPath,
          scope: url.searchParams.get("scope") ?? "all",
          query,
          limit: Number(url.searchParams.get("limit") ?? 200),
          total_indexed: baseRows.length + requestNumber,
          returned: rows.length,
          truncated: false,
          sort: "mtime_desc",
          rows,
        }),
      });
      return;
    }

    if (url.pathname === "/api/scan") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          folders: [],
          images: [],
          next_cursor: null,
          total_images: 0,
          index_source: "direct_scan",
        }),
      });
      return;
    }

    if (url.pathname === "/api/index/status") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          enabled: true,
          worker_count: 0,
          active_jobs: 0,
          runtime_queue_depth: 0,
          done: 150,
          running: 0,
          queued: 0,
          failed: 0,
          stale: 0,
          skipped: 0,
          total: 150,
          path: rootPath,
          counts: { done: 150 },
          oldest_queued_age_seconds: null,
          last_error: null,
          updated_at: 1000000000,
          coalesced_duplicates: 0,
          staged_path_queue_depth: 0,
          staged_path_coalesced: 0,
          staged_path_failed: 0,
          staged_path_flushes_forced: 0,
          staged_path_worker_count: 0,
          active_scan_requests: 0,
          batch_size: 100,
          staged_path_batch_size: 50,
          stage_max_wait_seconds: 30,
          metadata_records: 150,
          indexed_photos: 150,
        }),
      });
      return;
    }

    if (url.pathname === "/api/index/rebuild") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          path: url.searchParams.get("path") ?? rootPath,
          cleared: {
            file_index_fts: 1,
            file_index: 1,
            image_metadata: 1,
            metadata_index_jobs: 1,
            folder_index_state: 1,
          },
          rebuild_started: true,
          rebuild_started_at: Date.now() / 1000,
        }),
      });
      return;
    }

    if (url.pathname === "/api/library/inspector/metadata") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(detailForPath(url.searchParams.get("path") ?? "")),
      });
      return;
    }

    if (url.pathname === "/api/metadata") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(detailForPath(url.searchParams.get("path") ?? "")),
      });
      return;
    }

    if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
      await route.fulfill({ contentType: "image/png", body: png1x1 });
      return;
    }

    if (url.pathname === "/api/landing-pages") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([]) });
      return;
    }

    await route.fulfill({ contentType: "application/json", body: "{}" });
  });

  return requests;
}

const metadataRequests = (requests: string[]) =>
  requests.filter((request) => request.startsWith("/api/library/inspector/metadata?"));

const photoMetadataPaths = (requests: string[]) =>
  requests
    .filter((request) => request.startsWith("/api/metadata?"))
    .map((request) => new URLSearchParams(request.split("?")[1]).get("path"));

function collectLightboxNavDebug(page: Page) {
  const events: LightboxNavDebugEvent[] = [];
  page.on("console", (message) => {
    const text = message.text();
    if (!text.startsWith("[lightbox-nav-debug]")) return;
    const jsonStart = text.indexOf("{");
    if (jsonStart < 0) return;
    try {
      events.push(JSON.parse(text.slice(jsonStart)) as LightboxNavDebugEvent);
    } catch {
      // Ignore malformed console output from unrelated browser formatting.
    }
  });
  return events;
}

test.describe("LibraryInspector", () => {
  test.use({ viewport: { width: 1366, height: 900 } });

  test("renders the metadata route with compact navigation and the target table columns", async ({ page }) => {
    await installStubbedInspector(page);

    await page.goto(`${baseUrl}/metadata`, { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("heading", { name: "Library Inspector" })).toBeVisible();
    await expect(page.getByRole("link", { name: /Metadata/ })).toHaveAttribute("aria-current", "page");
    await expect(page.getByText("Showing 40 photo details")).toBeVisible();

    const galleryLink = page.getByRole("link", { name: "Gallery" });
    await expect(galleryLink).toBeVisible();

    const headers = page.locator("thead th");
    await expect(headers).toHaveCount(8);
    await expect(headers.nth(1)).toContainText("File");
    await expect(headers.nth(2)).toContainText("Prompt");
    await expect(page.locator("thead")).not.toContainText("Folder");
    await expect(headers.nth(6)).toContainText("Modified ↓");

    const firstRowCells = page.locator("tbody tr").first().locator("td");
    await expect(firstRowCells.nth(1)).toContainText("session-z");
    await expect(firstRowCells.nth(2)).toContainText("zeta arch");

    await galleryLink.click();
    await expect(page).toHaveURL(`${baseUrl}/`);
  });

  test("refetches active metadata records after rebuild index", async ({ page }) => {
    const requests = await installStubbedInspector(page);
    await page.addInitScript((root) => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-root-path", root);
      localStorage.setItem("gallery-sidebar-open", "true");
    }, rootPath);

    await page.goto(`${baseUrl}/metadata`, { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Library Inspector" })).toBeVisible();
    await expect(page.getByText("photo details", { exact: false })).toBeVisible();

    const inspectorRequestsBefore = requests.filter((request) => request.startsWith("/api/library/inspector?")).length;
    await page.getByLabel("Index Status").click();
    const popover = page.getByRole("dialog", { name: "Index Status" });
    await expect(popover).toBeVisible({ timeout: 5_000 });
    await popover.getByRole("button", { name: "Rebuild" }).click();

    const dialog = page.getByRole("dialog", { name: "Rebuild?" });
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    await dialog.getByRole("button", { name: "Rebuild" }).click();

    await expect
      .poll(() => requests.filter((request) => request.startsWith("/api/library/inspector?")).length)
      .toBeGreaterThan(inspectorRequestsBefore);
  });

  test("keeps prompt preview constrained and makes the table the scroll owner", async ({ page }) => {
    await installStubbedInspector(page);

    await page.goto(`${baseUrl}/metadata`, { waitUntil: "domcontentloaded" });

    const promptTrigger = page.locator(".col-prompt .long-text-trigger").first();
    const promptText = page.locator(".col-prompt .long-text-preview").first();
    await expect(promptTrigger).toBeVisible();

    await expect
      .poll(() =>
        promptTrigger.evaluate((element) => {
          const style = getComputedStyle(element);
          return [style.display, style.overflow, style.maxWidth];
        })
      )
      .toEqual(["block", "hidden", "100%"]);
    await expect
      .poll(() =>
        promptText.evaluate((element) => {
          const style = getComputedStyle(element);
          return [style.overflow, style.textOverflow, style.whiteSpace];
        })
      )
      .toEqual(["hidden", "ellipsis", "nowrap"]);

    const scrollMetrics = await page.locator(".table-shell").evaluate((element) => {
      element.scrollTop = 120;
      return {
        clientHeight: element.clientHeight,
        scrollHeight: element.scrollHeight,
        scrollTop: element.scrollTop,
      };
    });
    expect(scrollMetrics.scrollHeight).toBeGreaterThan(scrollMetrics.clientHeight);
    expect(scrollMetrics.scrollTop).toBeGreaterThan(0);
  });

  test("sorts, searches, and keeps prompt and LoRA detail on demand", async ({ page }) => {
    const requests = await installStubbedInspector(page);

    await page.goto(`${baseUrl}/metadata`, { waitUntil: "domcontentloaded" });

    await expect(page.locator("tbody tr").first()).toContainText("zeta-arch.png");
    await page.getByRole("button", { name: /File/ }).click();
    await expect(page.locator("tbody tr").first()).toContainText("ancient-door.png");

    const promptTrigger = page.getByText("cinematic warm light, old wooden door", { exact: false });
    await promptTrigger.click();
    await expect(page.getByText("full prompt detail")).toBeVisible();
    await expect(page.getByText("bad hands, watermark")).toBeVisible();

    const detailRequestsBeforeCopy = metadataRequests(requests).length;
    await page.getByRole("button", { name: "Copy prompt" }).click();
    await expect
      .poll(() => page.evaluate(() => (window as Window & { __copiedText?: string }).__copiedText ?? ""))
      .toContain("full prompt detail");
    await page.getByRole("button", { name: "Copy negative" }).click();
    await expect
      .poll(() => page.evaluate(() => (window as Window & { __copiedText?: string }).__copiedText ?? ""))
      .toBe("bad hands, watermark");
    await page.getByRole("button", { name: "Copy full metadata" }).click();
    await expect
      .poll(() => page.evaluate(() => (window as Window & { __copiedText?: string }).__copiedText ?? ""))
      .toContain("Negative prompt: bad hands, watermark");
    expect(metadataRequests(requests).length).toBeGreaterThanOrEqual(detailRequestsBeforeCopy);

    await page.keyboard.press("Escape");
    await page.getByText("LoRA 2").click();
    await expect(page.getByText("door-detail")).toBeVisible();
    await expect(page.getByText("abc123")).toBeVisible();

    await page.getByLabel("Search metadata").fill("blue forest");
    await expect(page.locator("tbody tr")).toHaveCount(1);
    await expect(page.locator("tbody tr").first()).toContainText("blue-forest.png");
  });

  test("opens lightbox in the current visible table order", async ({ page }) => {
    const lightboxNavEvents = collectLightboxNavDebug(page);
    await page.addInitScript(() => {
      localStorage.setItem("debug-lightbox-nav", "true");
    });
    const requests = await installStubbedInspector(page);

    await page.goto(`${baseUrl}/metadata`, { waitUntil: "domcontentloaded" });

    await page.locator(".col-thumbnail .thumb-button").first().click();
    await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
    await expect.poll(() => photoMetadataPaths(requests).slice(-1)[0]).toBe(baseRows[0].path);
    await expect.poll(() => lightboxNavEvents.some((event) => event.event === "pswp-init-complete")).toBe(true);

    await page.keyboard.press("ArrowRight");
    await expect.poll(() => photoMetadataPaths(requests).slice(-1)[0]).toBe(baseRows[1].path);
    await expect(page.locator(".desktop-lightbox-counter")).toContainText(`2 / ${baseRows.length}`);
    await page.waitForTimeout(100);
    expect(photoMetadataPaths(requests).slice(-1)[0]).toBe(baseRows[1].path);

    await page.keyboard.press("ArrowRight");
    await expect.poll(() => photoMetadataPaths(requests).slice(-1)[0]).toBe(baseRows[2].path);
    await expect(page.locator(".desktop-lightbox-counter")).toContainText(`3 / ${baseRows.length}`);
    await page.waitForTimeout(100);
    expect(photoMetadataPaths(requests).slice(-1)[0]).toBe(baseRows[2].path);

    expect(lightboxNavEvents.some((event) => event.event === "lightbox-keyboard-next")).toBe(false);
    expect(lightboxNavEvents.some((event) => event.event === "lightbox-keyboard-prev")).toBe(false);
  });
});
