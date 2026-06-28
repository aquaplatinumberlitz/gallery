/**
 * Purpose:
 * Verifies stale notices and inspector freshness when imported data changes.
 *
 * Guarantees:
 * * fresh inspector snapshots do not show the stale-data notice
 *
 * Run when:
 * * changing LibraryInspector query invalidation or stale-row UX
 */

import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import { expect, test } from "./helpers/monitorErrors";
import type { Page } from "@playwright/test";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const stubRoot = "/mocked-inspector-notice-test";
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64",
);

const stubLibrary = {
  id: 1,
  root_path: stubRoot,
  import_paths: [{ id: 10, library_id: 1, path: stubRoot, position: 0, created_at: 1, updated_at: 1 }],
  exclusion_patterns: [],
  name: "Stub Library",
  state: "ready",
  watch_enabled: 1,
  warm_enabled: 1,
  asset_count: 0,
  created_at: 1,
  updated_at: 1,
  last_scan_at: null,
  last_error: null,
};

function readyStatus(path: string | null, totalAssets: number, readyAssets = totalAssets) {
  return statusEnvelope({
    libraryId: 1,
    path,
    summaryState: readyAssets >= totalAssets ? "ready" : "indexing",
    totalAssets,
    readyAssets,
    queuedAssets: readyAssets >= totalAssets ? 0 : Math.max(totalAssets - readyAssets, 0),
    runningAssets: readyAssets >= totalAssets ? 0 : 1,
    metadataState: readyAssets >= totalAssets ? "complete" : "indexing",
  });
}

async function openMetadata(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });
  await page.goto(`${baseUrl}/metadata`, { waitUntil: "domcontentloaded" });
}

// ---------------------------------------------------------------------------
// Deterministic mocked: inspector stale-data notice
// ---------------------------------------------------------------------------
test.describe("inspector stale notice (mocked)", () => {
  async function installStubs(page: Page, inspectorData: object) {
    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());

      if (url.pathname === "/api/libraries") {
        await route.fulfill({ contentType: "application/json", body: JSON.stringify([stubLibrary]) });
        return;
      }
      if (url.pathname === "/api/browse") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify(browseResponse({ libraryId: 1, path: stubRoot })),
        });
        return;
      }
      if (url.pathname === "/api/libraries/1/status") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify(readyStatus(url.searchParams.get("scope_path") ?? stubRoot, 5)),
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
      if (url.pathname === "/api/facets") {
        await route.fulfill({ contentType: "application/json", body: JSON.stringify({ facets: {}, total: 0 }) });
        return;
      }
      if (url.pathname === "/api/library/inspector") {
        await route.fulfill({ contentType: "application/json", body: JSON.stringify(inspectorData) });
        return;
      }
      if (url.pathname.includes("/api/thumbnail")) {
        await route.fulfill({ contentType: "image/png", body: png1x1 });
        return;
      }
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({}) });
    });
  }

  async function navigateToMetadata(page: Page) {
    await openMetadata(page);
    await expect(page.getByRole("link", { name: "Metadata" })).toBeVisible({ timeout: 10_000 });
  }

  test("fresh data without rebuild marker hides notice", async ({ page }) => {
    await installStubs(page, {
      root: stubRoot,
      scope: "current",
      query: "",
      limit: 200,
      generated_at: 9999,
      total_indexed: 5,
      returned: 5,
      truncated: false,
      sort: "mtime_desc",
      rows: [
        {
          path: `${stubRoot}/img.png`,
          name: "img.png",
          folder: stubRoot,
          relative_path: ".",
          mtime: 1000000,
          width: 512,
          height: 512,
          model: "test",
          tool: "test",
          sampler: "test",
          seed: "123",
          prompt_preview: "test image",
          has_prompt: true,
          has_negative: false,
          has_lora: false,
          lora_count: 0,
          lora_preview: "",
          metadata_detail_available: true,
        },
      ],
    });

    await navigateToMetadata(page);

    await expect(page.getByTestId("rebuild-notice")).toBeHidden({ timeout: 3_000 });
    const summary = page.getByTestId("inspector-summary");
    await expect(summary).toBeVisible({ timeout: 5_000 });
    await expect(summary).toContainText("5 indexed photos");
  });
});
