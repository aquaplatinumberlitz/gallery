/**
 * Purpose:
 * Verifies imported-data maintenance UX flows after scan/rebuild language was simplified.
 *
 * Guarantees:
 * * Update buttons still call the existing scan endpoints
 * * Clear removes derived catalog data without unregistering libraries
 * * Rebuild repopulates derived catalog data from registered import paths
 * * Reset app data requires the type-confirm phrase and returns the app to empty libraries state
 *
 * Run when:
 * Imported-data maintenance endpoints, labels, or destructive action flows change.
 */

import { browseResponse, statusBatch, statusEnvelope } from "./helpers/catalogFixtures";
import { expect, test, type Page, type Request } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://127.0.0.1:5173";
const rootPath = "/registered/imports";
const imagePath = `${rootPath}/repopulated.png`;
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64",
);

const registeredLibrary = {
  id: 1,
  root_path: rootPath,
  import_paths: [{ id: 10, library_id: 1, path: rootPath, position: 0, created_at: 1, updated_at: 1 }],
  exclusion_patterns: ["**/.cache/**"],
  name: "Imported Library",
  state: "ready",
  watch_enabled: 1,
  warm_enabled: 1,
  asset_count: 1,
  created_at: 1,
  updated_at: 1,
  last_scan_at: 1_782_036_040_000,
  last_error: null,
};

interface MockState {
  libraries: (typeof registeredLibrary)[];
  assets: string[];
  requests: Request[];
  nextLibraryId: number;
  nextImportPathId: number;
}

async function installImportedDataApi(page: Page): Promise<MockState> {
  const state: MockState = {
    libraries: [structuredClone(registeredLibrary)],
    assets: [imagePath],
    requests: [],
    nextLibraryId: 2,
    nextImportPathId: 11,
  };

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    state.requests.push(request);

    if (url.pathname === "/api/events") {
      await route.fulfill({ status: 200, contentType: "text/event-stream", body: ": connected\n\n" });
      return;
    }

    if (url.pathname === "/api/libraries" && method === "GET") {
      await route.fulfill({
        json: state.libraries.map((library) => ({ ...library, asset_count: state.assets.length })),
      });
      return;
    }

    if (url.pathname === "/api/libraries/validate" && method === "POST") {
      const payload = request.postDataJSON() as { import_paths: string[]; exclusion_patterns: string[] };
      await route.fulfill({
        json: {
          is_valid: true,
          import_paths: payload.import_paths.map((value) => ({
            value,
            normalized_value: value,
            is_valid: true,
            message: null,
            warnings: [],
          })),
          exclusion_patterns: payload.exclusion_patterns.map((value) => ({
            value,
            normalized_value: value,
            is_valid: true,
            message: null,
            warnings: [],
          })),
        },
      });
      return;
    }

    if (url.pathname === "/api/libraries" && method === "POST") {
      const payload = request.postDataJSON() as {
        name?: string;
        import_paths: string[];
        exclusion_patterns: string[];
      };
      const libraryId = state.nextLibraryId++;
      const created = {
        ...registeredLibrary,
        id: libraryId,
        name: payload.name || "New Library",
        root_path: payload.import_paths[0],
        import_paths: payload.import_paths.map((path, index) => ({
          id: state.nextImportPathId++,
          library_id: libraryId,
          path,
          position: index,
          created_at: 1_718_000_200,
          updated_at: 1_718_000_200,
        })),
        exclusion_patterns: payload.exclusion_patterns,
        asset_count: 0,
      };
      state.libraries.push(created);
      await route.fulfill({ status: 201, json: created });
      return;
    }

    if (url.pathname === "/api/libraries/status" && method === "GET") {
      await route.fulfill({
        json: statusBatch(state.libraries.map((library) => ({ id: library.id, totalAssets: state.assets.length }))),
      });
      return;
    }

    if (url.pathname === "/api/libraries/scan-all" && method === "POST") {
      await route.fulfill({ status: 202, json: { job_id: 20, state: "queued", count: state.libraries.length } });
      return;
    }

    const libraryMatch = url.pathname.match(/^\/api\/libraries\/(\d+)(?:\/(status|progress|stats|jobs|scan))?$/);
    if (libraryMatch) {
      const id = Number(libraryMatch[1]);
      const suffix = libraryMatch[2];
      const library = state.libraries.find((item) => item.id === id);

      if (!library) {
        await route.fulfill({ status: 404, json: { detail: { type: "not_found" } } });
        return;
      }

      if (!suffix && method === "GET") {
        await route.fulfill({ json: { ...library, asset_count: state.assets.length } });
        return;
      }
      if (suffix === "status" && method === "GET") {
        await route.fulfill({
          json: statusEnvelope({
            libraryId: id,
            path: url.searchParams.get("scope_path") ?? rootPath,
            totalAssets: state.assets.length,
            readyAssets: state.assets.length,
          }),
        });
        return;
      }
      if (suffix === "progress" && method === "GET") {
        await route.fulfill({
          json: {
            indexed_assets: state.assets.length,
            estimated_assets: state.assets.length,
            discovery_complete: true,
            library_state: "ready",
            active_job_id: null,
          },
        });
        return;
      }
      if (suffix === "stats" && method === "GET") {
        await route.fulfill({
          json: {
            photos: state.assets.length,
            videos: 0,
            total_assets: state.assets.length,
            active_assets: state.assets.length,
            offline_assets: 0,
            usage_bytes: 100,
            import_path_count: library.import_paths.length,
          },
        });
        return;
      }
      if (suffix === "jobs" && method === "GET") {
        await route.fulfill({ json: [] });
        return;
      }
      if (suffix === "scan" && method === "POST") {
        await route.fulfill({
          status: 202,
          json: {
            library_id: id,
            job_id: 30,
            scope_path: request.postDataJSON()?.scope_path ?? null,
            operation: "scan",
            trigger: "manual",
            state: "queued",
            coalesced: false,
          },
        });
        return;
      }
    }

    if (url.pathname === "/api/browse") {
      await route.fulfill({
        json: browseResponse({
          libraryId: Number(url.searchParams.get("library_id") ?? 1),
          path: url.searchParams.get("path") ?? rootPath,
          media: state.assets.map((path) => ({
            name: path.split("/").pop() ?? "image.png",
            path,
            type: "image",
            has_children: false,
            cover_images: [],
            mtime: 1000,
            image_count: 0,
            width: 800,
            height: 600,
          })),
        }),
      });
      return;
    }

    if (url.pathname === "/api/maintenance/imported-data/clear" && method === "POST") {
      state.assets = [];
      await route.fulfill({
        json: {
          state: "cleared",
          libraries_preserved: state.libraries.length,
          assets_cleared: 1,
          thumbnail_disk_cache_entries_cleared: 0,
          preview_files_deleted: 1,
        },
      });
      return;
    }

    if (url.pathname === "/api/maintenance/imported-data/rebuild" && method === "POST") {
      state.assets = [imagePath];
      await route.fulfill({
        status: 202,
        json: {
          job_id: 40,
          state: "running",
          child_job_ids: [41],
          count: state.libraries.length,
          clear: { assets_cleared: 0, thumbnail_disk_cache_entries_cleared: 0, preview_files_deleted: 0 },
        },
      });
      return;
    }

    if (url.pathname === "/api/maintenance/catalog/reset" && method === "POST") {
      state.assets = [];
      state.libraries = [];
      state.nextLibraryId = 1;
      state.nextImportPathId = 1;
      await route.fulfill({
        json: {
          state: "reset",
          libraries_deleted: 1,
          import_paths_deleted: 1,
          exclusion_patterns_deleted: 1,
          assets_deleted: 1,
          image_metadata_rows_deleted: 1,
          metadata_jobs_deleted: 1,
          library_jobs_deleted: 1,
          derivative_catalog_entries_cleared: 1,
          derivative_jobs_cleared: 1,
          thumbnail_disk_cache_entries_cleared: 0,
          preview_files_deleted: 1,
          sequences_reset: 8,
          sequence_tables_reset: ["libraries"],
        },
      });
      return;
    }

    if (url.pathname === "/api/maintenance/runtime") {
      await route.fulfill({
        json: {
          global_runtime: {
            catalog_worker_count: 1,
            catalog_active_jobs: 0,
            catalog_queue_depth: 0,
            metadata_worker_count: 1,
            metadata_active_jobs: 0,
            metadata_queue_depth: 0,
            metadata_staged_queue_depth: 0,
            watcher_enabled: true,
            watcher_healthy: true,
            watcher_issue: null,
            scheduled_reconciliation_enabled: true,
          },
          metadata_lifecycle: {
            queued_metadata_jobs: 0,
            running_metadata_jobs: 0,
            failed_metadata_jobs: 0,
            stale_metadata_jobs: 0,
            assets_done_but_metadata_missing_or_stale: 0,
            repairable_metadata_assets: 0,
            metadata_jobs_without_matching_assets: 0,
          },
        },
      });
      return;
    }

    if (url.pathname === "/api/maintenance/file-health") {
      await route.fulfill({ json: { run: null } });
      return;
    }

    if (url.pathname === "/api/derivatives/status") {
      await route.fulfill({
        json: {
          ready_derivatives: state.assets.length,
          expected_derivatives: state.assets.length,
          pending_jobs: 0,
          failed_jobs: 0,
          quota_used_bytes: 0,
          quota_bytes: null,
          quota_utilization: null,
        },
      });
      return;
    }

    if (url.pathname === "/api/jobs") {
      await route.fulfill({ json: [] });
      return;
    }
    if (url.pathname === "/api/stats") {
      await route.fulfill({
        json: {
          library_count: state.libraries.length,
          photos: state.assets.length,
          videos: 0,
          usage_bytes: 100,
        },
      });
      return;
    }
    if (url.pathname === "/api/search") {
      await route.fulfill({ json: { albums: [], photos: [], videos: [], prompt: [] } });
      return;
    }
    if (url.pathname === "/api/health") {
      await route.fulfill({ json: { status: "ok" } });
      return;
    }
    if (url.pathname === "/api/landing-pages") {
      await route.fulfill({ json: [] });
      return;
    }
    if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
      await route.fulfill({ contentType: "image/png", body: png1x1 });
      return;
    }

    await route.fulfill({ status: 404, json: { detail: { type: "not_found", path: url.pathname } } });
  });

  return state;
}

async function prepare(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });
}

function matchingRequests(state: MockState, method: string, pathname: string): Request[] {
  return state.requests.filter((request) => {
    const url = new URL(request.url());
    return request.method() === method && url.pathname === pathname;
  });
}

async function openMaintenance(page: Page) {
  await page.goto(`${baseUrl}/admin/maintenance`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Maintenance" })).toBeVisible();
}

test.describe("imported-data maintenance verification", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("Update buttons still call scan endpoints", async ({ page }) => {
    await prepare(page);
    const state = await installImportedDataApi(page);
    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
    await page.getByLabel("File catalog status").click();
    const popover = page.getByRole("dialog").filter({ hasText: "File catalog" });
    await popover.getByRole("button", { name: "Update library" }).click();
    await expect.poll(() => matchingRequests(state, "POST", "/api/libraries/1/scan").length).toBe(1);

    await page.goto(`${baseUrl}/admin/libraries`, { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "Update all libraries" }).click();
    await expect.poll(() => matchingRequests(state, "POST", "/api/libraries/scan-all").length).toBe(1);
  });

  test("Clear leaves registered libraries intact but empties the catalog", async ({ page }) => {
    await prepare(page);
    const state = await installImportedDataApi(page);
    await openMaintenance(page);

    await page.getByRole("button", { name: "Clear", exact: true }).first().click();
    const dialog = page.getByRole("dialog", { name: "Clear imported data?" });
    await expect(dialog).toContainText(
      "Libraries, folders, exclusion patterns, and source image files are not deleted.",
    );
    await dialog.getByRole("button", { name: "Clear" }).click();

    await expect.poll(() => state.assets.length).toBe(0);
    expect(state.libraries).toHaveLength(1);

    await page.goto(`${baseUrl}/admin/libraries`, { waitUntil: "domcontentloaded" });
    await expect(page.getByText("Imported Library")).toBeVisible();

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card")).toHaveCount(0);
  });

  test("Rebuild repopulates assets and metadata from existing import paths", async ({ page }) => {
    await prepare(page);
    const state = await installImportedDataApi(page);
    state.assets = [];
    await openMaintenance(page);

    await page.getByRole("button", { name: "Rebuild", exact: true }).first().click();
    const dialog = page.getByRole("dialog", { name: "Rebuild imported data?" });
    await expect(dialog).toContainText("from registered libraries");
    await dialog.getByRole("button", { name: "Rebuild" }).click();

    await expect.poll(() => state.assets).toEqual([imagePath]);
    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
    await page.getByLabel("File catalog status").click();
    const statusDialog = page.getByRole("dialog").filter({ hasText: "File catalog" });
    await expect(statusDialog).toContainText("Metadata ready");
    await expect(statusDialog.getByText("1").first()).toBeVisible();
  });

  test("Reset app data clears handoff state and restarts library ids", async ({ page }) => {
    await prepare(page);
    const state = await installImportedDataApi(page);
    state.libraries = [
      {
        ...registeredLibrary,
        id: 11,
        import_paths: [{ ...registeredLibrary.import_paths[0], id: 110, library_id: 11 }],
      },
    ];
    state.nextLibraryId = 12;
    state.nextImportPathId = 111;
    await page.addInitScript(() => {
      localStorage.setItem("gallery-active-library-id", "11");
      localStorage.setItem("gallery-active-import-path-id", "110");
      localStorage.setItem("gallery-root-path", "/registered/imports");
      localStorage.setItem("gallery-sort-preference", JSON.stringify({ field: "date", order: "desc" }));
      localStorage.setItem("gallery-grid-size", "5");
      localStorage.setItem("gallery-lightbox-always-load-original", "true");
    });
    await page.goto(`${baseUrl}/admin/libraries/11`, { waitUntil: "domcontentloaded" });

    await page.getByLabel("Change Intro Page").click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("Danger Zone");
    await expect(dialog).toContainText("Source photos and videos are not deleted.");
    const resetButton = dialog.getByRole("button", { name: "Reset app data" });
    await expect(resetButton).toBeDisabled();

    await dialog.locator("#catalog-reset-confirm").fill("RESET CATALOG DATABASE");
    await expect(resetButton).toBeEnabled();
    await resetButton.click();

    await expect.poll(() => state.libraries.length).toBe(0);
    await expect.poll(() => page.evaluate(() => window.location.pathname)).toBe("/");
    await expect(page.getByText("No library selected")).toBeVisible();
    await expect
      .poll(() =>
        page.evaluate(() =>
          [
            "gallery-active-library-id",
            "gallery-active-import-path-id",
            "gallery-root-path",
            "gallery-sort-preference",
            "gallery-grid-size",
            "gallery-lightbox-always-load-original",
          ].map((key) => localStorage.getItem(key)),
        ),
      )
      .toEqual([null, null, null, null, null, null]);
    await page.getByRole("button", { name: "Manage Libraries" }).click();
    await expect(page).toHaveURL(/\/admin\/libraries$/);
    await expect(page.getByText("No libraries registered")).toBeVisible();
    await page.getByRole("button", { name: "Add library" }).last().click();
    await page.getByRole("textbox", { name: "Display name" }).fill("Fresh Library");
    await page.getByPlaceholder("/absolute/path/to/library").fill("/handoff/fresh");
    await page.getByRole("button", { name: "Add and update" }).click();

    await expect(page).toHaveURL(/\/admin\/libraries\/1$/);
    await expect(page.getByRole("heading", { name: "Fresh Library" })).toBeVisible();
  });
});
