/**
 * Purpose:
 * Verifies search result cards with truncated names stay stable and styled across device widths.
 *
 * Guarantees:
 * * overflowing result names/paths never put OverflowTooltip into a render loop that freezes the page
 * * parent-scoped result card styles keep applying after a truncated label gains its tooltip
 *
 * Run when:
 * * changing OverflowTooltip, SearchResultsPanel card markup, or search result typography
 * * touching responsive search result column widths
 */

import { statusEnvelope, browseResponse } from "./helpers/catalogFixtures";
import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-search-overflow-test";
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

// Mix of names that overflow at every width and names that only overflow on narrow cards.
const resultNames = [
  ...Array.from({ length: 4 }, (_, i) => `0000${i}-73950478${i}0.png`),
  ...Array.from({ length: 4 }, (_, i) => `very_long_filename_generated_by_comfyui_0000${i}_${"x".repeat(20)}.png`),
];
const nestedFolder = "Characters/Miku ver.2 — long album name for truncation testing";

function searchResult(name: string, index: number) {
  return {
    name,
    path: `${rootPath}/${nestedFolder}/${name}`,
    type: "photo",
    asset_id: index + 1,
    parent_path: `${rootPath}/${nestedFolder}`,
    relative_path: nestedFolder,
    mtime: 1000 + index,
    width: 832,
    height: 1216,
    match_type: "prompt",
    prompt_snippet: "1girl, short blue hair, maid, red eyes, ribbon, indoors",
    model: "ponyDiffusionV6XL",
    sampler: "Euler a",
    seed: String(1000 + index),
  };
}

async function installStubbedGallery(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());

    if (url.pathname === "/api/libraries") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([stubLibrary]) });
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
        body: JSON.stringify(browseResponse({ libraryId: 1, path: url.searchParams.get("path") ?? rootPath })),
      });
      return;
    }
    if (url.pathname === "/api/search/query") {
      const payload = route.request().postDataJSON() as { text?: string; limit?: number } | null;
      const media = resultNames.map(searchResult);
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          query: payload?.text ?? "",
          scope: "all",
          root: rootPath,
          albums: [],
          photos: media,
          media,
          prompt: [],
          videos: [],
          next_cursor: null,
          has_more: false,
          returned: media.length,
          limit: payload?.limit ?? 60,
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

async function runSearch(page: Page, query: string) {
  const openSearch = page.getByRole("button", { name: "Open search" }).first();
  if (await openSearch.isVisible().catch(() => false)) {
    await openSearch.click();
  }
  const input = page.getByLabel("Search gallery").or(page.getByPlaceholder("Photos, albums, prompts")).first();
  await input.fill(query);
  await input.press("Enter");
}

/** Resolves false when the renderer main thread stays blocked (render loop) for the whole window. */
async function mainThreadResponsive(page: Page, timeoutMs = 3_000) {
  return Promise.race([
    page.evaluate(() => new Promise<boolean>((resolve) => requestAnimationFrame(() => resolve(true)))),
    new Promise<boolean>((resolve) => setTimeout(() => resolve(false), timeoutMs)),
  ]);
}

const viewports = [
  { name: "phone", width: 375, height: 667 },
  { name: "tablet portrait", width: 768, height: 1024 },
  { name: "tablet landscape", width: 1000, height: 800 },
  { name: "phone landscape", width: 844, height: 390 },
  { name: "wide desktop", width: 1920, height: 1080 },
];

for (const viewport of viewports) {
  test.describe(`search result overflow on ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("truncated result labels stay styled and never freeze the page", async ({ page, monitoredErrors }) => {
      // Thumbnail sockets can be torn down mid-flight under full-suite load; layout/responsiveness is under test.
      monitoredErrors.allowConsoleError("net::ERR_SOCKET_NOT_CONNECTED");
      await installStubbedGallery(page);
      await page.addInitScript(() => {
        try {
          localStorage.setItem("intro_mode", "disabled");
          localStorage.setItem("gallery-sidebar-open", "false");
          localStorage.setItem("gallery-active-library-id", "1");
          localStorage.setItem("gallery-active-import-path-id", "10");
        } catch {
          // Storage can be unavailable; the test still drives the default flow.
        }
      });
      await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
      await page
        .locator(".enter-btn")
        .click({ timeout: 2_000 })
        .catch(() => {});

      await runSearch(page, "maid");
      await expect(page.locator(".search-result-name").first()).toBeVisible();
      // Let ResizeObserver/tooltip state settle; a render loop keeps the main thread pinned.
      await page.waitForTimeout(1_500);
      expect(await mainThreadResponsive(page)).toBe(true);

      const labels = await page.evaluate(() =>
        [...document.querySelectorAll<HTMLElement>(".search-result-name, .search-result-path")].map((el) => {
          const style = getComputedStyle(el);
          return {
            className: el.className,
            whiteSpace: style.whiteSpace,
            overflow: style.overflowX,
            fontSize: style.fontSize,
            display: style.display,
          };
        }),
      );
      expect(labels.length).toBeGreaterThan(0);
      for (const label of labels) {
        expect(label.whiteSpace, label.className).toBe("nowrap");
        expect(label.overflow, label.className).toBe("hidden");
        if (label.className.includes("search-result-name")) {
          expect(["12px", "13px"], label.className).toContain(label.fontSize);
        } else {
          expect(label.display, label.className).toBe("flex");
        }
      }
    });
  });
}
