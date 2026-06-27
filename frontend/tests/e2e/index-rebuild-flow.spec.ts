/**
 * Purpose:
 * Verifies catalog rebuild request flow, stale notices, and inspector refresh convergence.
 *
 * Guarantees:
 * * rebuild actions invalidate and refetch Library Inspector and Catalog Status data
 * * debug-index-rebuild emits enough cache detail to diagnose stale rows
 *
 * Run when:
 * * changing LibraryInspector, IndexStatusPanel, rebuildLibrary, or query invalidation
 * * touching catalog rebuild debug logging or stale-row UX
 */

import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import { expect, test } from "./helpers/monitorErrors";
import type { Page } from "@playwright/test";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const testRoot = process.env.PATH_SAFETY_ROOT_PATH ?? "/home/ubuntu/gallery-repo/test-images";
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

function rebuildJob(scopePath: string | null) {
  return {
    library_id: 1,
    job_id: 9001,
    scope_path: scopePath,
    operation: "rebuild",
    trigger: "manual",
    state: "queued",
    coalesced: false,
  };
}

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
// Diagnostic: rebuild -> inspector latency (real backend)
// ---------------------------------------------------------------------------
test.describe("rebuild flow diagnostic", () => {
  test("measure rebuild -> inspector latency", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
    });
    await page.goto(`${baseUrl}/`, { waitUntil: "load" });
    await expect(page.getByRole("link", { name: "Metadata" })).toBeVisible({ timeout: 10_000 });

    const initialInspectorPromise = page.waitForResponse(
      (r) => r.url().includes("/api/library/inspector") && r.status() === 200,
      { timeout: 15_000 },
    );
    await page.getByRole("link", { name: "Metadata" }).click();
    const initialBody = await (await initialInspectorPromise).json();
    console.log(
      JSON.stringify({
        step: "initial_inspector_loaded",
        generated_at: initialBody.generated_at,
        total_indexed: initialBody.total_indexed,
        returned: initialBody.returned,
      }),
    );

    const inspectorResponses: {
      relMs: number;
      generated_at: number;
      total_indexed: number;
      returned: number;
    }[] = [];
    const tAnchor = performance.now();
    page.on("response", (resp) => {
      if (resp.url().includes("/api/library/inspector") && resp.status() === 200) {
        const relMs = performance.now() - tAnchor;
        resp
          .json()
          .then((body) => {
            inspectorResponses.push({
              relMs: Math.round(relMs),
              generated_at: body.generated_at ?? 0,
              total_indexed: body.total_indexed ?? -1,
              returned: body.returned ?? -1,
            });
          })
          .catch(() => undefined);
      }
    });

    const statusButton = page.getByRole("button", { name: "Catalog Status" });
    await expect(statusButton).toBeVisible({ timeout: 5_000 });
    await statusButton.click();

    let t0 = 0;
    const rebuildRespPromise = page.waitForResponse(
      (r) =>
        /\/api\/libraries\/\d+\/rebuild$/.test(new URL(r.url()).pathname) &&
        r.request().method() === "POST" &&
        [200, 202].includes(r.status()),
      { timeout: 30_000 },
    );

    const rebuildBtn = page.getByRole("button", { name: "Rebuild", exact: true }).first();
    await expect(rebuildBtn).toBeVisible({ timeout: 3_000 });
    t0 = performance.now();
    await rebuildBtn.click();

    await expect(page.getByText("Rebuild?")).toBeVisible({ timeout: 5_000 });
    const confirmBtn = page.getByRole("button", { name: "Rebuild", exact: true }).last();
    await confirmBtn.click();

    const rebuildResp = await rebuildRespPromise;
    const tRebuildRespMs = Math.round(performance.now() - t0);
    const rebuildBody = await rebuildResp.json();
    const rebuildStartedAt = Math.floor(Date.now() / 1000);
    console.log(
      JSON.stringify({
        step: "rebuild_response",
        rebuildResponseMs: tRebuildRespMs,
        rebuild_started_at: rebuildStartedAt,
        scope_path: rebuildBody.scope_path,
        operation: rebuildBody.operation,
      }),
    );

    await expect.poll(() => inspectorResponses.length).toBeGreaterThanOrEqual(1);

    const firstResp = inspectorResponses[0] ?? null;
    console.log("=== REBUILD TIMING REPORT ===");
    console.log(
      JSON.stringify(
        {
          rebuildResponseMs: tRebuildRespMs,
          totalInspectorResponses: inspectorResponses.length,
          rebuildStartedAt,
          initialInspectorGeneratedAt: initialBody.generated_at,
          firstInspectorResponseMs: firstResp?.relMs,
          firstInspectorGeneratedAt: firstResp?.generated_at,
          firstInspectorTotalIndexed: firstResp?.total_indexed,
          firstInspectorReturned: firstResp?.returned,
        },
        null,
        2,
      ),
    );
    console.log("=== END REPORT ===");

    expect(rebuildBody.operation).toBe("rebuild");
    expect(rebuildBody.scope_path ?? testRoot).toBe(testRoot);
  });
});

// ---------------------------------------------------------------------------
// Deterministic mocked: inspector stale-data notice
// ---------------------------------------------------------------------------
test.describe("inspector stale notice (mocked)", () => {
  async function installStubs(page: Page, inspectorData: object) {
    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());
      const method = route.request().method();

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
      if (url.pathname === "/api/libraries/1/rebuild" && method === "POST") {
        const body = route.request().postDataJSON() as { scope_path?: string } | null;
        await route.fulfill({
          contentType: "application/json",
          status: 202,
          body: JSON.stringify(rebuildJob(body?.scope_path ?? stubRoot)),
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

    await expect(page.locator(".rebuild-notice")).toBeHidden({ timeout: 3_000 });
    const summary = page.locator(".library-inspector .text-muted-foreground").first();
    await expect(summary).toBeVisible({ timeout: 5_000 });
    await expect(summary).toContainText("5 indexed photos");
  });

  test("stale data after rebuild shows notice", async ({ page }) => {
    await installStubs(page, {
      root: stubRoot,
      scope: "current",
      query: "",
      limit: 200,
      generated_at: 1,
      total_indexed: 5,
      returned: 5,
      truncated: false,
      sort: "mtime_desc",
      rows: [],
    });

    await navigateToMetadata(page);
    const notice = page.locator(".rebuild-notice");
    await expect(notice).toBeHidden({ timeout: 3_000 });

    await page.getByRole("button", { name: "Catalog Status" }).click();
    await page.getByRole("button", { name: "Rebuild", exact: true }).first().click();

    await expect(page.getByText("Rebuild?")).toBeVisible({ timeout: 5_000 });
    const confirmBtn = page.getByRole("button", { name: "Rebuild", exact: true }).last();
    await Promise.all([
      page.waitForResponse(
        (r) => new URL(r.url()).pathname === "/api/libraries/1/rebuild" && [200, 202].includes(r.status()),
        { timeout: 10_000 },
      ),
      confirmBtn.click(),
    ]);

    await expect(notice).toContainText("Refreshing photo details", { timeout: 5_000 });
  });
});

// ---------------------------------------------------------------------------
// Deterministic mocked: rebuild while staying on /metadata
// ---------------------------------------------------------------------------
test.describe("metadata rebuild refresh regression", () => {
  test.use({ viewport: { width: 1366, height: 900 } });

  const flowRoot = "/home/ubuntu/gallery-repo";
  const oldGeneratedAt = 1_800_000_000;

  function makeRows(count: number, prefix: string) {
    return Array.from({ length: count }, (_, index) => {
      const padded = String(index + 1).padStart(3, "0");
      return {
        path: `${flowRoot}/${prefix}-${padded}.png`,
        name: `${prefix}-${padded}.png`,
        folder: flowRoot,
        relative_path: ".",
        mtime: oldGeneratedAt - index,
        width: 1024,
        height: 1024,
        model: "SDXL",
        tool: "ComfyUI",
        sampler: "DPM++ 2M",
        seed: `${prefix}-${padded}`,
        prompt_preview: `${prefix} prompt ${padded}`,
        has_prompt: true,
        has_negative: false,
        has_lora: false,
        lora_count: 0,
        lora_preview: "",
        metadata_detail_available: true,
      };
    });
  }

  test("refreshes Library Inspector after rebuild without route remount", async ({ page }) => {
    const requestTimeline: Record<string, unknown>[] = [];
    const debugConsole: string[] = [];
    const oldRows = makeRows(88, "old-row");
    const newRows = makeRows(200, "new-row");
    let rebuildConfirmedAt = 0;
    let rebuildStarted = false;
    let reindexFinished = false;

    function relMs() {
      return rebuildConfirmedAt ? Math.round(performance.now() - rebuildConfirmedAt) : null;
    }

    function logResponse(url: URL, body: Record<string, unknown>) {
      requestTimeline.push({
        relMs: relMs(),
        requestUrl: `${url.pathname}?${url.searchParams.toString()}`,
        scope: url.searchParams.get("scope"),
        path: url.searchParams.get("path"),
        generated_at: body.generated_at,
        inspector_total_indexed: body.total_indexed,
        inspector_returned_row_count: body.returned,
        first_row_path: Array.isArray(body.rows) ? body.rows[0]?.path : undefined,
        status_summary_state: body.status && typeof body.status === "object" ? body.status.summary_state : undefined,
      });
    }

    page.on("console", (message) => {
      const text = message.text();
      if (text.includes("[index-rebuild-debug]")) debugConsole.push(text);
    });

    await page.addInitScript(() => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-active-library-id", "1");
      localStorage.setItem("gallery-active-import-path-id", "10");
      localStorage.setItem("gallery-sidebar-open", "true");
      localStorage.setItem("debug-index-rebuild", "true");
    });

    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());
      const method = route.request().method();

      if (url.pathname === "/api/libraries") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify([
            {
              id: 1,
              root_path: flowRoot,
              import_paths: [{ id: 10, library_id: 1, path: flowRoot, position: 0, created_at: 1, updated_at: 1 }],
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
            },
          ]),
        });
        return;
      }

      if (url.pathname === "/api/library/inspector") {
        const body = reindexFinished
          ? {
              root: flowRoot,
              scope: "current",
              query: url.searchParams.get("q") ?? "",
              limit: 200,
              generated_at: Date.now(),
              total_indexed: 205,
              returned: 200,
              truncated: true,
              sort: "mtime_desc",
              rows: newRows,
            }
          : {
              root: flowRoot,
              scope: "current",
              query: url.searchParams.get("q") ?? "",
              limit: 200,
              generated_at: oldGeneratedAt,
              total_indexed: 88,
              returned: 88,
              truncated: false,
              sort: "mtime_desc",
              rows: oldRows,
            };
        logResponse(url, body);
        await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
        return;
      }

      if (url.pathname === "/api/libraries/1/status") {
        const body = reindexFinished
          ? readyStatus(flowRoot, 205)
          : rebuildStarted
            ? readyStatus(flowRoot, 205, 0)
            : readyStatus(flowRoot, 88);
        logResponse(url, body as unknown as Record<string, unknown>);
        await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
        return;
      }

      if (url.pathname === "/api/libraries/1/rebuild" && method === "POST") {
        rebuildConfirmedAt = performance.now();
        rebuildStarted = true;
        const body = rebuildJob(flowRoot);
        logResponse(url, body);
        await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(body) });
        return;
      }

      if (url.pathname === "/api/browse") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify(browseResponse({ libraryId: 1, path: flowRoot })),
        });
        return;
      }
      if (url.pathname === "/api/landing-pages") {
        await route.fulfill({ contentType: "application/json", body: JSON.stringify([]) });
        return;
      }
      if (url.pathname === "/api/health") {
        await route.fulfill({ contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
        return;
      }
      if (url.pathname === "/api/facets") {
        await route.fulfill({ contentType: "application/json", body: JSON.stringify({}) });
        return;
      }
      if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
        await route.fulfill({ contentType: "image/png", body: png1x1 });
        return;
      }

      await route.fulfill({ contentType: "application/json", body: JSON.stringify({}) });
    });

    await page.goto(`${baseUrl}/metadata`, { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Photo Details" })).toBeVisible();
    await expect(page.getByText(`88 indexed photos · ${flowRoot} · Including subfolders`)).toBeVisible();
    await expect(page.getByText("old-row-001.png")).toBeVisible();

    await page.getByLabel("Catalog Status").click();
    const popover = page.getByRole("dialog").filter({ hasText: "Catalog" });
    await expect(popover).toBeVisible({ timeout: 5_000 });
    await popover.getByRole("button", { name: "Rebuild" }).click();

    const confirmDialog = page.getByRole("dialog", { name: "Rebuild?" });
    await expect(confirmDialog).toBeVisible({ timeout: 5_000 });
    await confirmDialog.getByRole("button", { name: "Rebuild" }).click();

    await expect(
      page.getByText("Refreshing photo details. Previous results are shown until the latest snapshot arrives."),
    ).toBeVisible({ timeout: 5_000 });
    await expect(page.locator(".table-shell")).toHaveClass(/table-shell--rebuilding/);
    await expect(page.getByText("old-row-001.png")).toBeVisible();

    await expect
      .poll(
        () => requestTimeline.filter((entry) => String(entry.requestUrl).startsWith("/api/library/inspector?")).length,
      )
      .toBeGreaterThan(1);

    reindexFinished = true;

    await expect(page.getByText(`200 of 205 indexed photos shown · ${flowRoot} · Including subfolders`)).toBeVisible({
      timeout: 8_000,
    });
    await expect(
      page.getByText("Refreshing photo details. Previous results are shown until the latest snapshot arrives."),
    ).toBeHidden();
    await expect(page.locator(".table-shell")).not.toHaveClass(/table-shell--rebuilding/);
    await expect(page.getByText("new-row-001.png")).toBeVisible();
    await expect(page.locator(".index-status-card")).toContainText("205 photo details ready", { timeout: 5_000 });

    const inspectorRequests = requestTimeline.filter((entry) =>
      String(entry.requestUrl).startsWith("/api/library/inspector?"),
    );
    expect(inspectorRequests.length).toBeGreaterThan(1);
    expect(inspectorRequests.every((entry) => entry.scope === "current")).toBe(true);
    expect(inspectorRequests.every((entry) => entry.path === flowRoot)).toBe(true);
    expect(debugConsole.some((line) => line.includes("inspector-refetch"))).toBe(true);
    expect(debugConsole.some((line) => line.includes('"activeLibraryInspectorQueryKey":["library-inspector"'))).toBe(
      true,
    );
    expect(debugConsole.some((line) => line.includes(`"current","${flowRoot}",200`))).toBe(true);

    console.log("=== CATALOG REBUILD REQUEST TIMELINE ===");
    console.log(JSON.stringify(requestTimeline, null, 2));
    console.log("=== CATALOG REBUILD QUERY DEBUG ===");
    console.log(debugConsole.join("\n"));
  });
});
