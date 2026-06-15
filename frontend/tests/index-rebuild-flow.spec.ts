import { expect, test } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const testRoot = "/home/ubuntu/gallery-repo/test-images";

/**
 * Diagnostic: measure rebuild → inspector fresh snapshot latency.
 *
 * Hits the real backend. Prints a JSON timing report via console.log.
 */
test.describe("rebuild flow diagnostic", () => {
  test("measure rebuild → inspector latency", async ({ page }) => {
    // ── 1. Navigate to app ──
    await page.goto(`${baseUrl}/`, { waitUntil: "load" });

    // ── 2. Dismiss IntroScreen ──
    await page.getByText("ENTER GALLERY").click();
    await page.waitForTimeout(1500);

    // ── 3. Set root path ──
    await page.locator("#root-path").fill(testRoot);
    await page.locator("#root-path").press("Enter");
    await page.waitForTimeout(5000);

    // ── 4. Navigate to /metadata (register before clicking) ──
    const initialInspectorPromise = page.waitForResponse(
      (resp) => resp.url().includes("/api/library/inspector") && resp.status() === 200,
      { timeout: 15_000 }
    );
    await page.getByRole("link", { name: "Metadata" }).click();
    const initialInspectorResp = await initialInspectorPromise;
    const initialBody = await initialInspectorResp.json();
    const initialGeneratedAt: number = initialBody.generated_at ?? 0;
    console.log(
      JSON.stringify({
        step: "initial_inspector_loaded",
        generated_at: initialGeneratedAt,
        total_indexed: initialBody.total_indexed,
        returned: initialBody.returned,
      })
    );
    await page.waitForTimeout(1000);

    // ── 5. Open Index Status popover ──
    const idxStatusBtn = page.getByRole("button", { name: "Index Status" });
    await expect(idxStatusBtn).toBeVisible({ timeout: 5_000 });
    await idxStatusBtn.click();
    await page.waitForTimeout(500);

    // ── 6. Register response promises BEFORE clicking Rebuild ──
    let t0 = 0;

    const rebuildRespPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/api/index/rebuild") &&
        resp.request().method() === "POST" &&
        resp.status() === 200,
      { timeout: 30_000 }
    );

    const freshInspectorPromise = page.waitForResponse(
      (resp) => resp.url().includes("/api/library/inspector") && resp.status() === 200,
      { timeout: 30_000 }
    );

    // ── 7. Click "Rebuild" (starts in popover) ──
    // The Rebuild button is inside the IndexStatusDetailsPopover
    // It says "Rebuild" (not "Rebuilding...") and is enabled
    const rebuildBtn = page.getByRole("button", { name: "Rebuild", exact: true }).first();
    await expect(rebuildBtn).toBeVisible({ timeout: 3_000 });
    t0 = performance.now();
    await rebuildBtn.click();

    // ── 8. Confirm rebuild — dialog has "Rebuild?" title ──
    const rebuildQuestion = page.getByText("Rebuild?");
    await expect(rebuildQuestion).toBeVisible({ timeout: 5_000 });

    // Find the confirm "Rebuild" button near the "Rebuild?" dialog
    // Use locator inside the dialog (which contains the "Rebuild?" text)
    const dialogContainer = page.getByText("Rebuild?").locator("..").locator("..");
    // Or simpler: just click the last "Rebuild" button (the confirm one, after the popover one)
    const confirmBtn = page.getByRole("button", { name: "Rebuild", exact: true }).last();
    await expect(confirmBtn).toBeVisible({ timeout: 3_000 });
    await confirmBtn.click();

    // ── 9. Capture POST /api/index/rebuild response ──
    const rebuildResp = await rebuildRespPromise;
    const tRebuildRespMs = performance.now() - t0;
    const rebuildBody = await rebuildResp.json();
    const rebuildStartedAt: number = rebuildBody.rebuild_started_at ?? 0;
    console.log(
      JSON.stringify({
        step: "rebuild_response",
        rebuildResponseMs: Math.round(tRebuildRespMs),
        rebuild_started_at: rebuildStartedAt,
        path: rebuildBody.path,
      })
    );

    // ── 10. Observe rebuild-notice in the DOM ──
    let noticeAppearedMs: number | null = null;
    let noticeHiddenMs: number | null = null;
    let noticeWasVisible = false;

    const noticeLocator = page.locator(".rebuild-notice");
    try {
      await noticeLocator.waitFor({ state: "visible", timeout: 10_000 });
      noticeAppearedMs = performance.now() - t0;
      noticeWasVisible = true;
      console.log(
        JSON.stringify({ step: "notice_appeared", noticeAppearedMs: Math.round(noticeAppearedMs) })
      );
    } catch {
      console.log(
        JSON.stringify({
          step: "notice_never_appeared",
          reason: "fresh snapshot arrived before notice could render",
        })
      );
    }

    // ── 11. Wait for fresh /api/library/inspector response ──
    const freshInspectorResp = await freshInspectorPromise;
    const tFreshMs = performance.now() - t0;
    const freshBody = await freshInspectorResp.json();
    const freshGeneratedAt: number = freshBody.generated_at ?? 0;

    const isFresh = freshGeneratedAt >= rebuildStartedAt;
    console.log(
      JSON.stringify({
        step: "fresh_inspector_loaded",
        freshInspectorSnapshotMs: Math.round(tFreshMs),
        fresh_generated_at: freshGeneratedAt,
        rebuild_started_at: rebuildStartedAt,
        is_fresh: isFresh,
        total_indexed: freshBody.total_indexed,
        returned: freshBody.returned,
      })
    );

    // ── 12. Observe notice hiding ──
    if (noticeWasVisible) {
      try {
        await noticeLocator.waitFor({ state: "hidden", timeout: 30_000 });
        noticeHiddenMs = performance.now() - t0;
        console.log(
          JSON.stringify({ step: "notice_hidden", noticeHiddenMs: Math.round(noticeHiddenMs) })
        );
      } catch {
        console.log(JSON.stringify({ step: "notice_never_hid", reason: "timed out" }));
      }
    }

    // ── 13. Print final JSON report ──
    const report: Record<string, unknown> = {
      rebuildResponseMs: Math.round(tRebuildRespMs),
      freshInspectorSnapshotMs: Math.round(tFreshMs),
      rebuildStartedAt,
      inspectorGeneratedAt: freshGeneratedAt,
      isFresh,
    };
    if (noticeAppearedMs !== null) report.noticeAppearedMs = Math.round(noticeAppearedMs);
    if (noticeHiddenMs !== null) report.noticeHiddenMs = Math.round(noticeHiddenMs);
    if (!noticeWasVisible) report.noticeNeverAppeared = true;
    report.initialInspectorGeneratedAt = initialGeneratedAt;

    console.log("=== REBUILD TIMING REPORT ===");
    console.log(JSON.stringify(report, null, 2));
    console.log("=== END REPORT ===");

    // ── 14. Basic assertions ──
    expect(isFresh).toBe(true);
    expect(rebuildBody.rebuild_started).toBe(true);
    expect(rebuildBody.path).toContain("test-images");
  });
});
