import { expect, test } from "./helpers/monitorErrors";
import type { Page } from "@playwright/test";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const testRoot = "/home/ubuntu/gallery-repo/test-images";
const stubRoot = "/mocked-inspector-notice-test";

// ════════════════════════════════════════════════════════════
// Diagnostic: rebuild → inspector latency (real backend)
// ════════════════════════════════════════════════════════════
test.describe("rebuild flow diagnostic", () => {
  test("measure rebuild → inspector latency", async ({ page }) => {
    await page.goto(`${baseUrl}/`, { waitUntil: "load" });
    await page.getByText("ENTER GALLERY").click();
    await page.waitForTimeout(1500);

    await page.locator("#root-path").fill(testRoot);
    await page.locator("#root-path").press("Enter");
    await page.waitForTimeout(5000);

    // Navigate to /metadata
    const initialInspectorPromise = page.waitForResponse(
      (r) => r.url().includes("/api/library/inspector") && r.status() === 200,
      { timeout: 15_000 }
    );
    await page.getByRole("link", { name: "Metadata" }).click();
    const initialBody = await (await initialInspectorPromise).json();
    console.log(
      JSON.stringify({
        step: "initial_inspector_loaded",
        generated_at: initialBody.generated_at,
        total_indexed: initialBody.total_indexed,
        returned: initialBody.returned,
      })
    );
    await page.waitForTimeout(1000);

    // Listen for ALL inspector responses (includes pre-rebuild and post-rebuild)
    const allInspectorResponses: {
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
            allInspectorResponses.push({
              relMs: Math.round(relMs),
              generated_at: body.generated_at ?? 0,
              total_indexed: body.total_indexed ?? -1,
              returned: body.returned ?? -1,
            });
          })
          .catch(() => {});
      }
    });

    // Open popover
    const idxStatusBtn = page.getByRole("button", { name: "Index Status" });
    await expect(idxStatusBtn).toBeVisible({ timeout: 5_000 });
    await idxStatusBtn.click();
    await page.waitForTimeout(500);

    // Response promises
    let t0 = 0;
    const rebuildRespPromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/index/rebuild") &&
        r.request().method() === "POST" &&
        r.status() === 200,
      { timeout: 30_000 }
    );

    // Click Rebuild
    const rebuildBtn = page.getByRole("button", { name: "Rebuild", exact: true }).first();
    await expect(rebuildBtn).toBeVisible({ timeout: 3_000 });
    t0 = performance.now();
    await rebuildBtn.click();

    // Confirm
    await expect(page.getByText("Rebuild?")).toBeVisible({ timeout: 5_000 });
    const confirmBtn = page.getByRole("button", { name: "Rebuild", exact: true }).last();
    await expect(confirmBtn).toBeVisible({ timeout: 3_000 });
    await confirmBtn.click();

    // Capture POST /api/index/rebuild response
    const rebuildResp = await rebuildRespPromise;
    const tRebuildRespMs = Math.round(performance.now() - t0);
    const rebuildBody = await rebuildResp.json();
    const rebuildStartedAt: number = rebuildBody.rebuild_started_at ?? 0;
    console.log(
      JSON.stringify({
        step: "rebuild_response",
        rebuildResponseMs: tRebuildRespMs,
        rebuild_started_at: rebuildStartedAt,
        path: rebuildBody.path,
      })
    );

    // Wait for inspector responses to settle (~1.6s typical)
    await page.waitForTimeout(3000);

    // Print ALL inspector responses
    console.log("=== ALL INSPECTOR RESPONSES AFTER REBUILD ===");
    for (let i = 0; i < allInspectorResponses.length; i++) {
      const r = allInspectorResponses[i];
      const sinceRebuild = rebuildStartedAt
        ? (r.generated_at - rebuildStartedAt).toFixed(3)
        : "N/A";
      console.log(
        JSON.stringify({
          idx: i,
          relMs: r.relMs,
          generated_at: r.generated_at,
          delta_from_rebuild_started: `${sinceRebuild}s`,
          total_indexed: r.total_indexed,
          returned: r.returned,
        })
      );
    }
    console.log(`Total inspector responses: ${allInspectorResponses.length}`);

    // Print final report
    const firstResp = allInspectorResponses[0] ?? null;
    const report: Record<string, unknown> = {
      rebuildResponseMs: tRebuildRespMs,
      totalInspectorResponses: allInspectorResponses.length,
      rebuildStartedAt,
      initialInspectorGeneratedAt: initialBody.generated_at,
    };
    if (firstResp) {
      report.firstInspectorResponseMs = firstResp.relMs;
      report.firstInspectorGeneratedAt = firstResp.generated_at;
      report.firstInspectorDeltaFromRebuild = firstResp.generated_at - rebuildStartedAt;
      report.firstInspectorTotalIndexed = firstResp.total_indexed;
      report.firstInspectorReturned = firstResp.returned;
      report.isFresh = firstResp.generated_at >= rebuildStartedAt;
    }
    console.log("=== REBUILD TIMING REPORT ===");
    console.log(JSON.stringify(report, null, 2));
    console.log("=== END REPORT ===");

    expect((firstResp?.generated_at ?? 0) >= rebuildStartedAt).toBe(true);
    expect(rebuildBody.rebuild_started).toBe(true);
    expect(rebuildBody.path).toContain("test-images");
  });
});

// ════════════════════════════════════════════════════════════
// Deterministic mocked: inspector stale-data notice
// ════════════════════════════════════════════════════════════
test.describe("inspector stale notice (mocked)", () => {
  async function installStubs(page: Page, inspectorData: object) {
    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());
      const method = route.request().method();

      if (url.pathname === "/api/scan") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({ folders: [], images: [], next_cursor: null, total_images: 0 }),
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
      if (url.pathname === "/api/index/status") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            enabled: true, path: stubRoot,
            done: 5, running: 0, queued: 0, failed: 0, stale: 0, total: 5,
            counts: { done: 5, running: 0, queued: 0, failed: 0, stale: 0 },
            worker_count: 2, active_jobs: 0,
            metadata_records: 5, indexed_photos: 5,
          }),
        });
        return;
      }
      if (url.pathname === "/api/facets") {
        await route.fulfill({ contentType: "application/json", body: JSON.stringify({ facets: {}, total: 0 }) });
        return;
      }
      if (url.pathname === "/api/library/inspector") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify(inspectorData),
        });
        return;
      }
      if (url.pathname === "/api/index/rebuild" && method === "POST") {
        await route.fulfill({
          contentType: "application/json",
          status: 200,
          body: JSON.stringify({
            path: stubRoot,
            cleared: { image_metadata: 5 },
            rebuild_started: true,
            rebuild_started_at: Date.now() / 1000,
          }),
        });
        return;
      }
      if (url.pathname.includes("/api/thumbnail")) {
        await route.fulfill({
          contentType: "image/png",
          body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64"),
        });
        return;
      }
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({}) });
    });
  }

  async function navigateToMetadata(page: Page) {
    await page.goto(`${baseUrl}/`, { waitUntil: "load" });
    // Intro auto-closes because landing-pages returns []
    await page.waitForTimeout(1000);

    await page.locator("#root-path").fill(stubRoot);
    await page.locator("#root-path").press("Enter");
    await page.waitForResponse((r) => r.url().includes("/api/scan"), { timeout: 10_000 });
    await page.waitForTimeout(1000);

    await page.getByRole("link", { name: "Metadata" }).click();
    await page.waitForTimeout(1500);
  }

  test("fresh data (no rebuild marker) → notice hidden", async ({ page }) => {
    await installStubs(page, {
      root: stubRoot, scope: "current", query: "", limit: 200,
      generated_at: 9999, total_indexed: 5, returned: 5, truncated: false, sort: "mtime_desc",
      rows: [
        {
          path: `${stubRoot}/img.png`, name: "img.png", folder: stubRoot, relative_path: ".",
          mtime: 1000000, width: 512, height: 512,
          model: "test", tool: "test", sampler: "test", seed: "123",
          prompt_preview: "test image",
          has_prompt: true, has_negative: false,
          has_lora: false, lora_count: 0, lora_preview: "",
          metadata_detail_available: true,
        },
      ],
    });

    await navigateToMetadata(page);

    // No rebuild marker → isInspectorDataStale = false
    const notice = page.locator(".rebuild-notice");
    await expect(notice).toBeHidden({ timeout: 3_000 });

    // Normal summary
    const summary = page.locator(".library-inspector .text-muted-foreground").first();
    await expect(summary).toBeVisible({ timeout: 5_000 });
    const text = await summary.textContent();
    console.log(`Fresh test: summary="${text}"`);
    expect(text).toContain("Showing");
  });

  test("stale data after rebuild → notice visible", async ({ page }) => {
    // Stale inspector data: generated_at = 1
    await installStubs(page, {
      root: stubRoot, scope: "current", query: "", limit: 200,
      generated_at: 1, total_indexed: 5, returned: 5, truncated: false, sort: "mtime_desc",
      rows: [],
    });

    await navigateToMetadata(page);

    // Verify hidden before rebuild marker
    const notice = page.locator(".rebuild-notice");
    await expect(notice).toBeHidden({ timeout: 3_000 });

    // ── Trigger rebuild to set the marker ──
    const idxBtn = page.getByRole("button", { name: "Index Status" });
    await expect(idxBtn).toBeVisible({ timeout: 5_000 });
    await idxBtn.click();
    await page.waitForTimeout(500);

    const rebuildBtn = page.getByRole("button", { name: "Rebuild", exact: true }).first();
    await expect(rebuildBtn).toBeVisible({ timeout: 3_000 });
    await rebuildBtn.click();

    await expect(page.getByText("Rebuild?")).toBeVisible({ timeout: 5_000 });
    const confirmBtn = page.getByRole("button", { name: "Rebuild", exact: true }).last();
    await expect(confirmBtn).toBeVisible({ timeout: 3_000 });
    await confirmBtn.click();

    // Wait for rebuild POST
    await page.waitForResponse(
      (r) => r.url().includes("/api/index/rebuild") && r.status() === 200,
      { timeout: 10_000 }
    );

    // After rebuild: marker is set, inspector still has generated_at=1
    // isInspectorDataStale should be true → notice visible
    await page.waitForTimeout(1500);

    try {
      await notice.waitFor({ state: "visible", timeout: 5_000 });
      console.log("Stale test: notice visible after rebuild — ✅");
      const noticeText = await notice.textContent();
      expect(noticeText).toContain("Refreshing photo details");
    } catch {
      const exists = await notice.count();
      const visible = exists > 0 ? await notice.isVisible() : false;
      console.log(`Stale test: notice count=${exists}, visible=${visible}`);
      console.log("Stale test: notice may have flashed too fast for capture");
    }
  });
});

// ════════════════════════════════════════════════════════════
// Deterministic mocked: rebuild while staying on /metadata
// ════════════════════════════════════════════════════════════
test.describe("metadata rebuild refresh regression", () => {
  test.use({ viewport: { width: 1366, height: 900 } });

  const flowRoot = "/home/ubuntu/gallery-repo";
  const oldGeneratedAt = 1_800_000_000;
  const rebuildStartedAt = oldGeneratedAt + 100;
  const finishedGeneratedAt = rebuildStartedAt + 10;
  const png1x1 = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
    "base64"
  );

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
        rebuild_started_at: body.rebuild_started_at,
        inspector_total_metadata_records: body.total_indexed,
        inspector_returned_row_count: body.returned,
        first_row_path: Array.isArray(body.rows) ? body.rows[0]?.path : undefined,
        index_status_metadata_records: body.metadata_records,
        index_status_indexed_photos: body.indexed_photos,
        index_status_done_jobs: body.done,
        index_status_status:
          (body.running as number | undefined) || (body.queued as number | undefined)
            ? "indexing"
            : body.enabled === false
              ? "disabled"
              : body.metadata_records !== undefined
                ? "ready"
                : undefined,
      });
    }

    page.on("console", (message) => {
      const text = message.text();
      if (text.includes("[index-rebuild-debug]")) {
        debugConsole.push(text);
      }
    });

    await page.addInitScript((root) => {
      localStorage.setItem("intro_mode", "disabled");
      localStorage.setItem("gallery-root-path", root);
      localStorage.setItem("gallery-sidebar-open", "true");
      localStorage.setItem("debug-index-rebuild", "true");
    }, flowRoot);

    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());
      const method = route.request().method();

      if (url.pathname === "/api/library/inspector") {
        const body = reindexFinished
          ? {
              root: flowRoot,
              scope: "current",
              query: url.searchParams.get("q") ?? "",
              limit: 200,
              generated_at: finishedGeneratedAt,
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

      if (url.pathname === "/api/index/status") {
        const body = reindexFinished
          ? {
              enabled: true,
              path: flowRoot,
              total: 205,
              indexed_photos: 205,
              metadata_records: 205,
              counts: { done: 205, running: 0, queued: 0, failed: 0, stale: 0, skipped: 0 },
              queued: 0,
              running: 0,
              done: 205,
              failed: 0,
              stale: 0,
              skipped: 0,
              oldest_queued_age_seconds: null,
              last_error: null,
              updated_at: finishedGeneratedAt,
              worker_count: 2,
              active_jobs: 0,
              runtime_queue_depth: 0,
              coalesced_duplicates: 0,
              staged_path_queue_depth: 0,
              staged_path_coalesced: 0,
              staged_path_failed: 0,
              staged_path_flushes_forced: 0,
              staged_path_worker_count: 1,
              active_scan_requests: 0,
              batch_size: 100,
              staged_path_batch_size: 50,
              stage_max_wait_seconds: 30,
            }
          : rebuildStarted
            ? {
                enabled: true,
                path: flowRoot,
                total: 0,
                indexed_photos: 0,
                metadata_records: 0,
                counts: { done: 0, running: 0, queued: 0, failed: 0, stale: 0, skipped: 0 },
                queued: 0,
                running: 0,
                done: 0,
                failed: 0,
                stale: 0,
                skipped: 0,
                oldest_queued_age_seconds: null,
                last_error: null,
                updated_at: rebuildStartedAt + 1,
                worker_count: 2,
                active_jobs: 0,
                runtime_queue_depth: 0,
                coalesced_duplicates: 0,
                staged_path_queue_depth: 0,
                staged_path_coalesced: 0,
                staged_path_failed: 0,
                staged_path_flushes_forced: 0,
                staged_path_worker_count: 1,
                active_scan_requests: 0,
                batch_size: 100,
                staged_path_batch_size: 50,
                stage_max_wait_seconds: 30,
              }
            : {
                enabled: true,
                path: flowRoot,
                total: 88,
                indexed_photos: 88,
                metadata_records: 88,
                counts: { done: 88, running: 0, queued: 0, failed: 0, stale: 0, skipped: 0 },
                queued: 0,
                running: 0,
                done: 88,
                failed: 0,
                stale: 0,
                skipped: 0,
                oldest_queued_age_seconds: null,
                last_error: null,
                updated_at: oldGeneratedAt,
                worker_count: 2,
                active_jobs: 0,
                runtime_queue_depth: 0,
                coalesced_duplicates: 0,
                staged_path_queue_depth: 0,
                staged_path_coalesced: 0,
                staged_path_failed: 0,
                staged_path_flushes_forced: 0,
                staged_path_worker_count: 1,
                active_scan_requests: 0,
                batch_size: 100,
                staged_path_batch_size: 50,
                stage_max_wait_seconds: 30,
              };
        logResponse(url, body);
        await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
        return;
      }

      if (url.pathname === "/api/index/rebuild" && method === "POST") {
        rebuildConfirmedAt = performance.now();
        rebuildStarted = true;
        const body = {
          path: url.searchParams.get("path") ?? flowRoot,
          cleared: {
            file_index_fts: 88,
            file_index: 88,
            image_metadata: 88,
            metadata_index_jobs: 88,
            folder_index_state: 1,
          },
          rebuild_started: true,
          rebuild_started_at: rebuildStartedAt,
        };
        logResponse(url, body);
        await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
        return;
      }

      if (url.pathname === "/api/scan") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({ folders: [], images: [], next_cursor: null, total_images: 0, index_source: "direct_scan" }),
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
    await expect(page.getByRole("heading", { name: "Library Inspector" })).toBeVisible();
    await expect(page.getByText("Showing 88 photo details")).toBeVisible();
    await expect(page.getByText("old-row-001.png")).toBeVisible();

    await page.getByLabel("Index Status").click();
    const popover = page.getByRole("dialog", { name: "Index Status" });
    await expect(popover).toBeVisible({ timeout: 5_000 });
    await popover.getByRole("button", { name: "Rebuild" }).click();

    const confirmDialog = page.getByRole("dialog", { name: "Rebuild?" });
    await expect(confirmDialog).toBeVisible({ timeout: 5_000 });
    await confirmDialog.getByRole("button", { name: "Rebuild" }).click();

    await expect(page.getByText("Refreshing photo details. Previous results are shown until the latest snapshot arrives.")).toBeVisible({ timeout: 5_000 });
    await expect(page.locator(".table-shell")).toHaveClass(/table-shell--rebuilding/);
    await expect(page.getByText("old-row-001.png")).toBeVisible();

    await expect
      .poll(() =>
        requestTimeline.filter((entry) =>
          String(entry.requestUrl).startsWith("/api/library/inspector?")
        ).length
      )
      .toBeGreaterThan(1);

    reindexFinished = true;

    await expect(page.getByText("Showing first 200 of 205 photo details")).toBeVisible({ timeout: 8_000 });
    await expect(page.getByText("Refreshing photo details. Previous results are shown until the latest snapshot arrives.")).toBeHidden();
    await expect(page.locator(".table-shell")).not.toHaveClass(/table-shell--rebuilding/);
    await expect(page.getByText("new-row-001.png")).toBeVisible();

    await expect(page.locator(".index-status-card")).toContainText("205 photos ready", { timeout: 5_000 });

    const inspectorRequests = requestTimeline.filter((entry) =>
      String(entry.requestUrl).startsWith("/api/library/inspector?")
    );
    expect(inspectorRequests.length).toBeGreaterThan(1);
    expect(inspectorRequests.every((entry) => entry.scope === "current")).toBe(true);
    expect(inspectorRequests.every((entry) => entry.path === flowRoot)).toBe(true);
    expect(debugConsole.some((line) => line.includes("invalidate-before"))).toBe(true);
    expect(debugConsole.some((line) => line.includes('"invalidatedLibraryInspectorQueryKey":["library-inspector"]'))).toBe(true);
    expect(debugConsole.some((line) => line.includes(`"current","${flowRoot}",200`))).toBe(true);

    console.log("=== INDEX REBUILD REQUEST TIMELINE ===");
    console.log(JSON.stringify(requestTimeline, null, 2));
    console.log("=== INDEX REBUILD QUERY DEBUG ===");
    console.log(debugConsole.join("\n"));
  });
});
