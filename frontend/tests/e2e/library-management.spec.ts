import { expect, test, type Page, type Request } from "@playwright/test";
import { browseResponse, statusBatch, statusEnvelope } from "./helpers/catalogFixtures";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://127.0.0.1:5173";

const library = {
  id: 1,
  root_path: "/registered/photos",
  import_paths: [
    {
      id: 10,
      library_id: 1,
      path: "/registered/photos",
      position: 0,
      created_at: 1_718_000_000,
      updated_at: 1_718_000_000,
    },
  ],
  exclusion_patterns: ["**/.cache/**"],
  name: "Family photos",
  state: "ready",
  watch_enabled: 1,
  warm_enabled: 1,
  asset_count: 12,
  created_at: 1_718_000_000,
  updated_at: 1_718_000_100,
  last_scan_at: 1_718_000_100,
  last_error: null,
};

const progress = {
  indexed_assets: 12,
  estimated_assets: 12,
  discovery_complete: true,
  library_state: "ready",
  active_job_id: null,
};

const stats = {
  photos: 10,
  videos: 2,
  total_assets: 12,
  active_assets: 12,
  offline_assets: 0,
  usage_bytes: 1_048_576,
  import_path_count: 1,
};

const job = {
  id: 31,
  library_id: 1,
  parent_job_id: null,
  type: "scan",
  state: "succeeded",
  progress_current: 12,
  progress_total: 12,
  message: "Scan complete",
  error: null,
  created_at: 1_718_000_000,
  updated_at: 1_718_000_100,
  started_at: 1_718_000_000,
  finished_at: 1_718_000_100,
};

function libraryJob(id: number, operation: "scan" | "rebuild") {
  return {
    library_id: id,
    job_id: operation === "scan" ? 41 : 42,
    scope_path: null,
    operation,
    trigger: "manual",
    state: "queued",
    coalesced: false,
  };
}

interface MockOptions {
  libraries?: (typeof library)[];
  listStatus?: number;
}

interface MockState {
  requests: Request[];
  libraries: (typeof library)[];
}

async function mockLibraryApi(page: Page, options: MockOptions = {}): Promise<MockState> {
  const state: MockState = {
    requests: [],
    libraries: structuredClone(options.libraries ?? [library]),
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
      if (options.listStatus && options.listStatus !== 200) {
        await route.fulfill({
          status: options.listStatus,
          json: { detail: { type: "internal", message: "Injected list failure" } },
        });
      } else {
        await route.fulfill({ json: state.libraries });
      }
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
        name: string;
        import_paths: string[];
        exclusion_patterns: string[];
      };
      const created = {
        ...library,
        id: 2,
        name: payload.name,
        root_path: payload.import_paths[0],
        import_paths: payload.import_paths.map((path, index) => ({
          id: 20 + index,
          library_id: 2,
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
    if (url.pathname === "/api/libraries/scan-all" && method === "POST") {
      await route.fulfill({
        status: 202,
        json: {
          job_id: 40,
          state: "queued",
          count: state.libraries.length,
          child_job_ids: state.libraries.map((_, index) => 41 + index),
        },
      });
      return;
    }
    if (url.pathname === "/api/libraries/status" && method === "GET") {
      await route.fulfill({
        json: statusBatch(
          state.libraries.map((item) => ({
            id: item.id,
            totalAssets: item.asset_count,
            readyAssets: item.asset_count,
          })),
        ),
      });
      return;
    }

    const match = url.pathname.match(/^\/api\/libraries\/(\d+)(?:\/(progress|stats|jobs|validate|scan|rebuild|status))?$/);
    if (match) {
      const id = Number(match[1]);
      const suffix = match[2];
      const selected = state.libraries.find((item) => item.id === id);

      if (suffix === "progress" && method === "GET") {
        await route.fulfill({ json: id === 1 ? progress : { ...progress, indexed_assets: 0, estimated_assets: 0 } });
        return;
      }
      if (suffix === "stats" && method === "GET") {
        await route.fulfill({ json: id === 1 ? stats : { ...stats, photos: 0, videos: 0, total_assets: 0 } });
        return;
      }
      if (suffix === "jobs" && method === "GET") {
        await route.fulfill({ json: id === 1 ? [job] : [] });
        return;
      }
      if (suffix === "validate" && method === "POST") {
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
      if (suffix === "scan" && method === "POST") {
        await route.fulfill({ status: 202, json: libraryJob(id, "scan") });
        return;
      }
      if (suffix === "rebuild" && method === "POST") {
        await route.fulfill({ status: 202, json: libraryJob(id, "rebuild") });
        return;
      }
      if (suffix === "status" && method === "GET") {
        await route.fulfill({
          json: statusEnvelope({
            libraryId: id,
            path: url.searchParams.get("scope_path") ?? selected?.root_path ?? null,
            totalAssets: selected?.asset_count ?? 0,
            readyAssets: selected?.asset_count ?? 0,
          }),
        });
        return;
      }
      if (!suffix && method === "PATCH" && selected) {
        const payload = request.postDataJSON() as {
          name: string;
          import_paths: string[];
          exclusion_patterns: string[];
        };
        Object.assign(selected, {
          name: payload.name,
          root_path: payload.import_paths[0],
          exclusion_patterns: payload.exclusion_patterns,
          import_paths: payload.import_paths.map((path, index) => ({
            id: selected.import_paths[index]?.id ?? 100 + index,
            library_id: id,
            path,
            position: index,
            created_at: selected.created_at,
            updated_at: 1_718_000_300,
          })),
        });
        await route.fulfill({ json: selected });
        return;
      }
      if (!suffix && method === "DELETE") {
        state.libraries = state.libraries.filter((item) => item.id !== id);
        await route.fulfill({ status: 204, body: "" });
        return;
      }
      if (!suffix && method === "GET" && selected) {
        await route.fulfill({ json: selected });
        return;
      }
    }

    if (url.pathname === "/api/stats") {
      await route.fulfill({ json: { ...stats, library_count: state.libraries.length } });
      return;
    }
    if (url.pathname === "/api/jobs") {
      await route.fulfill({ json: [job] });
      return;
    }
    if (url.pathname === "/api/browse") {
      await route.fulfill({
        json: browseResponse({
          libraryId: Number(url.searchParams.get("library_id") ?? 1),
          path: url.searchParams.get("path") ?? library.root_path,
        }),
      });
      return;
    }
    if (url.pathname === "/api/search") {
      await route.fulfill({ json: { query: "", scope: "current", albums: [], photos: [], videos: [], prompt: [] } });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: { type: "not_found" } } });
  });

  return state;
}

async function preparePage(page: Page) {
  await page.addInitScript(() => localStorage.setItem("intro_mode", "disabled"));
}

function matchingRequests(state: MockState, method: string, pathname: string): Request[] {
  return state.requests.filter((request) => {
    const url = new URL(request.url());
    return request.method() === method && url.pathname === pathname;
  });
}

test("renders the responsive library list on desktop and mobile", async ({ page }) => {
  await preparePage(page);
  await mockLibraryApi(page);
  await page.goto(`${baseUrl}/admin/libraries`);

  await expect(page.getByRole("heading", { name: "Libraries", exact: true })).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("table").getByRole("button", { name: "Family photos" })).toBeVisible();
  await expect(page.getByRole("table").getByText("10 photos · 2 videos")).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page).toHaveURL(/\/admin\/libraries$/);
  await expect(page.getByRole("table")).toBeHidden();
  await expect(page.getByRole("article").filter({ hasText: "Family photos" })).toBeVisible();
});

test("renders empty and recoverable error states", async ({ page }) => {
  await preparePage(page);
  await mockLibraryApi(page, { libraries: [] });
  await page.goto(`${baseUrl}/admin/libraries`);
  await expect(page.getByText("No libraries registered")).toBeVisible();
  await expect(page.getByRole("button", { name: "Add library" }).last()).toBeVisible();

  const errorPage = await page.context().newPage();
  await preparePage(errorPage);
  await mockLibraryApi(errorPage, { listStatus: 500 });
  await errorPage.goto(`${baseUrl}/admin/libraries`);
  await expect(errorPage.getByRole("heading", { name: "Could not load libraries" })).toBeVisible();
  await expect(errorPage.getByRole("main").getByRole("button", { name: "Retry" })).toBeVisible();
});

test("creates and scans a library from the compact layout", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await preparePage(page);
  const state = await mockLibraryApi(page, { libraries: [] });
  await page.goto(`${baseUrl}/admin/libraries`);
  await page.locator("button:visible").filter({ hasText: "Add library" }).first().click();

  await page.getByLabel("Display name").fill("Trips");
  await page.getByPlaceholder("/absolute/path/to/library").fill("/registered/trips");
  await page.getByRole("button", { name: "Add pattern" }).click();
  await page.getByPlaceholder("**/private/**").fill("**/private/**");
  await page.getByRole("button", { name: "Add and scan" }).click();

  await expect(page).toHaveURL(/\/admin\/libraries\/2$/);
  await expect(page.getByRole("heading", { name: "Trips" })).toBeVisible();
  expect(matchingRequests(state, "POST", "/api/libraries/validate")).toHaveLength(1);
  expect(matchingRequests(state, "POST", "/api/libraries")).toHaveLength(1);
  expect(matchingRequests(state, "POST", "/api/libraries/2/scan")).toHaveLength(1);
});

test("runs detail actions, updates settings, and unregisters safely", async ({ page }) => {
  await preparePage(page);
  const state = await mockLibraryApi(page);
  await page.goto(`${baseUrl}/admin/libraries/1`);

  await expect(page.getByRole("heading", { name: "Family photos" })).toBeVisible();
  await expect(page.getByText("Recent job history")).toBeVisible();
  await expect(page.getByText("Scan complete")).toBeVisible();

  await page.getByRole("button", { name: "Scan", exact: true }).click();
  await expect.poll(() => matchingRequests(state, "POST", "/api/libraries/1/scan").length).toBe(1);
  await expect(page.getByRole("button", { name: "Repair", exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Edit", exact: true }).first().click();
  await page.getByLabel("Display name").fill("Family archive");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("heading", { name: "Family archive" })).toBeVisible();
  expect(matchingRequests(state, "POST", "/api/libraries/1/validate")).toHaveLength(1);
  expect(matchingRequests(state, "PATCH", "/api/libraries/1")).toHaveLength(1);

  await page.getByRole("button", { name: "Unregister", exact: true }).click();
  await expect(page.getByText("Source files will not be deleted.")).toBeVisible();
  await page.getByRole("button", { name: "Unregister library" }).click();
  await expect(page).toHaveURL(/\/admin\/libraries$/);
  const deleteRequest = matchingRequests(state, "DELETE", "/api/libraries/1")[0];
  expect(deleteRequest).toBeDefined();
  expect(new URL(deleteRequest.url()).searchParams.get("confirm")).toBe("true");
});

test("scan-all and use-in-gallery stay available from the list", async ({ page }) => {
  await preparePage(page);
  const state = await mockLibraryApi(page);
  await page.goto(`${baseUrl}/admin/libraries`);

  await page.getByRole("button", { name: "Scan all" }).click();
  await expect.poll(() => matchingRequests(state, "POST", "/api/libraries/scan-all").length).toBe(1);

  await page.getByRole("button", { name: "Library actions" }).click();
  await page.getByRole("menuitem", { name: "Use in gallery" }).click();
  await expect(page).toHaveURL(`${baseUrl}/`);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("gallery-active-library-id"))).toBe("1");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("gallery-active-import-path-id"))).toBe("10");
});
