/**
 * Purpose:
 * Exercises the unified Related Assets entry points, evidence, readiness, responsive layout, and lightbox handoff.
 *
 * Guarantees:
 * * card and lightbox overflow actions open the correct reference/scope
 * * one non-persisted unified request replaces match-type tabs or selectors
 * * metadata and visual evidence share one deduplicated list and result selection reuses the existing lightbox
 * * changed-seed, visual-variant, exclusion, and missing-coverage cases stay explicit
 * * the same action/panel semantics remain usable on mobile
 *
 * Run when:
 * * changing Related Assets cards, panel, unified query requests, readiness, or lightbox integration
 */

import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-related-assets-test";
const referencePath = `${rootPath}/reference.png`;
const candidatePath = `${rootPath}/candidate.png`;
const visualPath = `${rootPath}/resized-reencoded.png`;
const metadataOnlyPath = `${rootPath}/metadata-only.png`;
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64",
);

type CapturedRelated = { reference_asset_id: number; profile: string; scope: Record<string, unknown> };

async function installFixture(page: Page, resultCount = 2) {
  const relatedRequests: CapturedRelated[] = [];
  let latestReferenceAssetId = 1;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const fulfill = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (url.pathname === "/api/libraries") {
      return fulfill([
        {
          id: 1,
          root_path: rootPath,
          import_paths: [{ id: 10, library_id: 1, path: rootPath, position: 0, created_at: 1, updated_at: 1 }],
          exclusion_patterns: [],
          name: "Related Library",
          state: "ready",
          watch_enabled: 1,
          warm_enabled: 1,
          asset_count: 3,
          created_at: 1,
          updated_at: 1,
          last_scan_at: 1,
          last_error: null,
        },
      ]);
    }
    if (url.pathname === "/api/libraries/1/status") {
      return fulfill(statusEnvelope({ libraryId: 1, path: url.searchParams.get("scope_path") ?? rootPath }));
    }
    if (url.pathname === "/api/browse") {
      return fulfill(
        browseResponse({
          libraryId: 1,
          path: rootPath,
          media: [
            {
              asset_id: 1,
              name: "reference.png",
              path: referencePath,
              type: "image",
              has_children: false,
              cover_images: [],
              mtime: 1001,
              image_count: 0,
              width: 1024,
              height: 1024,
            },
            {
              asset_id: 2,
              name: "candidate.png",
              path: candidatePath,
              type: "image",
              has_children: false,
              cover_images: [],
              mtime: 1002,
              image_count: 0,
              width: 1024,
              height: 1024,
            },
            {
              asset_id: 3,
              name: "metadata-only.png",
              path: metadataOnlyPath,
              type: "image",
              has_children: false,
              cover_images: [],
              mtime: 1003,
              image_count: 0,
              width: 1024,
              height: 1024,
            },
          ],
        }),
      );
    }
    if (url.pathname === "/api/search/related") {
      const payload = request.postDataJSON() as CapturedRelated & { limit: number };
      relatedRequests.push(payload);
      latestReferenceAssetId = payload.reference_asset_id;
      const metadataOnly = payload.reference_asset_id === 3;
      const extraItems = Array.from({ length: Math.max(0, resultCount - 2) }, (_, index) => {
        const assetId = index + 5;
        const name =
          assetId === 12
            ? "4a2339ff-2692-4cc4-94de-dbe1319d2954-extra-long-related-asset-name.png"
            : `related-${assetId}.png`;
        return {
          asset_id: assetId,
          library_id: 1,
          library_name: "Related Library",
          name,
          path: `${rootPath}/related-${assetId}.png`,
          type: "image",
          parent_path: rootPath,
          relative_path: "",
          mtime: 1000 + assetId,
          width: 1024,
          height: 1024,
          duration_ms: null,
          mime_type: null,
          match_type: "related",
          prompt_snippet: "cinematic fox",
          model: "forest-xl",
          sampler: "Euler",
          seed: `${200 + assetId}`,
          relation_tier: 60,
          relation_reasons: ["strong_prompt_overlap", "same_model_name"],
          visual_distance: null,
          metadata_score: 0.6,
        };
      });
      const items = [
        {
          asset_id: 2,
          library_id: 1,
          library_name: "Related Library",
          name: "candidate.png",
          path: candidatePath,
          type: "image",
          parent_path: rootPath,
          relative_path: "",
          mtime: 1002,
          width: 1024,
          height: 1024,
          duration_ms: null,
          mime_type: null,
          match_type: "related",
          prompt_snippet: "cinematic fox",
          model: "forest-xl",
          sampler: "Euler",
          seed: "202",
          relation_tier: 90,
          relation_reasons: metadataOnly
            ? ["same_recipe", "same_generation_family"]
            : ["same_recipe", "same_generation_family", "visual_variant"],
          visual_distance: metadataOnly ? null : 2,
          metadata_score: 0.9,
        },
        ...(metadataOnly
          ? []
          : [
              {
                asset_id: 4,
                library_id: 1,
                library_name: "Related Library",
                name: "resized-reencoded.png",
                path: visualPath,
                type: "image",
                parent_path: rootPath,
                relative_path: "",
                mtime: 1004,
                width: 1024,
                height: 1024,
                duration_ms: null,
                mime_type: null,
                match_type: "visual_variant",
                prompt_snippet: "",
                model: "",
                sampler: "",
                seed: "",
                relation_tier: 80,
                relation_reasons: ["visual_variant"],
                visual_distance: 3,
                metadata_score: null,
              },
            ]),
        ...extraItems,
      ];
      return fulfill({
        schema_version: 1,
        reference_asset_id: payload.reference_asset_id,
        profile: payload.profile,
        scope: payload.scope,
        items,
        returned: items.length,
        limit: payload.limit,
        status: {
          metadata: {
            index_name: "generation_signatures",
            state: "ready",
            usable: true,
            indexed_count: 2,
            target_count: 2,
          },
          visual: {
            index_name: "visual_fingerprints",
            state: metadataOnly ? "not_ready" : "ready",
            usable: !metadataOnly,
            indexed_count: metadataOnly ? 2 : 3,
            target_count: 3,
          },
        },
      });
    }
    if (url.pathname === "/api/search/indexes") {
      return fulfill([
        {
          index_name: "generation_signatures",
          library_id: 1,
          library_name: "Related Library",
          state: "ready",
          usable: true,
          enabled: true,
          schema_version: 1,
          extractor_version: 1,
          indexed_count: 3,
          target_count: 3,
          failed_count: 0,
          skipped_count: 0,
          skip_reasons: {},
          active_job_id: null,
        },
        {
          index_name: "visual_fingerprints",
          library_id: 1,
          library_name: "Related Library",
          state: latestReferenceAssetId === 3 ? "pending" : "ready",
          usable: latestReferenceAssetId !== 3,
          enabled: true,
          schema_version: 1,
          extractor_version: 1,
          indexed_count: latestReferenceAssetId === 3 ? 2 : 3,
          target_count: 3,
          failed_count: 0,
          skipped_count: 0,
          skip_reasons: {},
          active_job_id: null,
        },
      ]);
    }
    if (url.pathname === "/api/metadata") {
      return fulfill({
        tool: "ComfyUI",
        prompt: "cinematic fox",
        negative_prompt: "",
        params: { Model: "forest-xl" },
        width: 1024,
        height: 1024,
        name: url.searchParams.get("path")?.split("/").pop() ?? "image.png",
      });
    }
    if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
      return route.fulfill({ contentType: "image/png", body: png1x1 });
    }
    if (url.pathname === "/api/health") return fulfill({ status: "ok" });
    if (url.pathname === "/api/landing-pages") return fulfill([]);
    return fulfill({}, 404);
  });
  return relatedRequests;
}

async function openGallery(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
    localStorage.setItem("gallery-sidebar-open", "false");
  });
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
}

test("card action opens one unified result list and result selection reuses lightbox", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 600 });
  const requests = await installFixture(page, 10);
  await openGallery(page);

  const referenceCard = page.getByRole("button", { name: "Open reference.png" });
  await referenceCard.hover();
  await page.getByLabel("Image actions for reference.png").focus();
  await page.getByLabel("Image actions for reference.png").press("Enter");
  await page.getByRole("menuitem", { name: "Find related" }).click();
  await expect(page.getByRole("heading", { name: "Related assets" })).toBeVisible();
  const panel = page.getByTestId("related-assets-panel");
  await expect(panel.getByRole("tablist")).toHaveCount(0);
  await expect(panel.getByRole("tab")).toHaveCount(0);
  await expect(panel.locator("select")).toHaveCount(0);
  await expect(panel.getByLabel(/^Image actions for /)).toHaveCount(0);
  await expect(panel.getByTestId("related-results")).toHaveCount(1);
  await expect(panel.locator(".reason-chip", { hasText: "Same recipe" })).toBeVisible();
  await expect(panel.locator(".reason-chip", { hasText: "Same family" })).toBeVisible();
  await expect(panel.locator(".reason-chip", { hasText: "Visually similar" })).toHaveCount(2);
  await expect(panel.getByRole("button", { name: "candidate.png", exact: true })).toHaveCount(1);
  await expect(panel.getByRole("button", { name: "resized-reencoded.png", exact: true })).toBeVisible();
  await panel.getByLabel("How Related assets matches are found").hover();
  await expect(
    page.getByRole("paragraph").filter({
      hasText: "The backend combines indexed generation metadata with visual fingerprints",
    }),
  ).toBeVisible();
  await expect(panel.locator(".reason-chip", { hasText: "Visually similar" }).first()).toHaveAttribute(
    "aria-label",
    /does not prove a shared prompt or lineage/,
  );
  await expect(panel.getByText("unrelated-same-model.png")).toHaveCount(0);
  await expect(panel.getByText("inactive-match.png")).toHaveCount(0);
  await expect(panel.getByText("cross-library-match.png")).toHaveCount(0);
  expect(requests[0]).toMatchObject({
    reference_asset_id: 1,
    profile: "related",
    scope: { kind: "folder", library_id: 1, import_path_id: 10, relative_path: "" },
  });

  await expect(panel.getByText("Recorded-generation summary")).toHaveCount(0);
  expect(requests).toHaveLength(1);
  expect(requests.every((request) => request.profile === "related")).toBe(true);

  const reasonFontSize = await panel
    .locator(".reason-chip", { hasText: "Visually similar" })
    .first()
    .evaluate((element) => Number.parseFloat(getComputedStyle(element).fontSize));
  expect(reasonFontSize).toBeGreaterThanOrEqual(12);

  const scrollBody = panel.locator(".related-content");
  const lastResultName = "4a2339ff-2692-4cc4-94de-dbe1319d2954-extra-long-related-asset-name.png";
  const lastResult = panel.getByRole("button", {
    name: lastResultName,
    exact: true,
  });
  expect(
    await lastResult.evaluate((element) => ({
      lineClamp: getComputedStyle(element).webkitLineClamp,
      overflowWrap: getComputedStyle(element).overflowWrap,
    })),
  ).toEqual({ lineClamp: "2", overflowWrap: "anywhere" });
  expect(
    await scrollBody.evaluate((element) => ({
      isScrollable: element.scrollHeight > element.clientHeight,
      overflowY: getComputedStyle(element).overflowY,
    })),
  ).toEqual({ isScrollable: true, overflowY: "auto" });
  await lastResult.scrollIntoViewIfNeeded();
  await expect(lastResult).toBeVisible();
  expect(await scrollBody.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);

  await lastResult.click();
  await expect(page.getByTestId("lightbox")).toBeVisible();
  await expect(page.getByTestId("lightbox").getByAltText(lastResultName)).toBeVisible();
  await page.getByLabel("Close").click();
  await expect(page.getByTestId("lightbox")).not.toBeVisible();
  await expect(page.getByRole("heading", { name: "Related assets" })).toBeVisible();
  expect(await scrollBody.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
});

test("lightbox and mobile overflow actions open the current reference", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const requests = await installFixture(page);
  await openGallery(page);
  await page.getByRole("button", { name: "Open reference.png" }).click();
  await expect(page.getByTestId("lightbox")).toBeVisible();
  await page.getByLabel("Lightbox image actions").click();
  await page.getByRole("menuitem", { name: "Find related" }).click();
  await expect(page.getByRole("heading", { name: "Related assets" })).toBeVisible();
  await expect.poll(() => requests.at(-1)?.reference_asset_id).toBe(1);
  const panel = page.getByTestId("related-assets-panel");
  await expect(panel.getByRole("tablist")).toHaveCount(0);
  expect(await panel.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
});

test("missing visual coverage keeps metadata relations available", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  const requests = await installFixture(page);
  await openGallery(page);
  await page.getByLabel("Image actions for metadata-only.png").click();
  await page.getByRole("menuitem", { name: "Find related" }).click();

  const panel = page.getByTestId("related-assets-panel");
  await expect.poll(() => requests.at(-1)?.reference_asset_id).toBe(3);
  await expect(panel.getByText("Visual: not ready")).toBeVisible();
  await expect(panel.getByText("Visual matching isn’t built yet")).toBeVisible();
  await expect(panel.getByRole("button", { name: "Build visual index" })).toHaveText("Build index");
  await expect(panel.getByRole("button", { name: "candidate.png", exact: true })).toBeVisible();
});
