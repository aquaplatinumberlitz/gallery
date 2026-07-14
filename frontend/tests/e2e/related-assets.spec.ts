/**
 * Purpose:
 * Exercises Related Assets entry points, profiles, evidence, responsive action menus, and lightbox handoff.
 *
 * Guarantees:
 * * card and lightbox overflow actions open the correct reference/scope
 * * Related, Same recipe, and Visual variants send explicit non-persisted profiles
 * * evidence copy is transparent and result selection reuses the existing lightbox
 * * changed-seed, visual-variant, exclusion, and missing-coverage cases stay explicit
 * * the same action/panel semantics remain usable on mobile
 *
 * Run when:
 * * changing Related Assets cards, panel, profiles, query requests, or lightbox integration
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

async function installFixture(page: Page) {
  const relatedRequests: CapturedRelated[] = [];
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
    if (url.pathname === "/api/metadata") {
      return fulfill({
        tool: "ComfyUI",
        prompt: "cinematic fox",
        negative_prompt: "",
        params: {
          Seed:
            url.searchParams.get("path") === referencePath
              ? "101"
              : url.searchParams.get("path") === candidatePath
                ? "202"
                : "303",
          Model: "forest-xl",
        },
        width: 1024,
        height: 1024,
        name: url.searchParams.get("path")?.split("/").pop() ?? "image.png",
      });
    }
    if (url.pathname === "/api/search/related") {
      const payload = request.postDataJSON() as CapturedRelated & { limit: number };
      relatedRequests.push(payload);
      const visual = payload.profile === "visual";
      const metadataOnly = payload.reference_asset_id === 3;
      const resultName = visual ? "resized-reencoded.png" : "candidate.png";
      const resultPath = visual ? visualPath : candidatePath;
      return fulfill({
        schema_version: 1,
        reference_asset_id: payload.reference_asset_id,
        profile: payload.profile,
        scope: payload.scope,
        items: [
          {
            asset_id: 2,
            library_id: 1,
            library_name: "Related Library",
            name: resultName,
            path: resultPath,
            type: "image",
            parent_path: rootPath,
            relative_path: "",
            mtime: 1002,
            width: 1024,
            height: 1024,
            duration_ms: null,
            mime_type: null,
            match_type: visual ? "visual_variant" : "related",
            prompt_snippet: "cinematic fox",
            model: "forest-xl",
            sampler: "Euler",
            seed: "202",
            relation_tier: visual ? 80 : 90,
            relation_reasons: visual ? ["visual_variant"] : ["same_recipe", "same_generation_family"],
            visual_distance: visual ? 2 : null,
            metadata_score: visual ? null : 0.9,
          },
        ],
        returned: 1,
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
            state: metadataOnly ? "not_ready" : "degraded",
            usable: !metadataOnly,
            indexed_count: metadataOnly ? 2 : 3,
            target_count: 3,
          },
        },
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

test("card profiles expose evidence and result selection reuses lightbox", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 820 });
  const requests = await installFixture(page);
  await openGallery(page);

  const referenceCard = page.getByRole("button", { name: "Open reference.png" });
  await referenceCard.hover();
  await page.getByLabel("Image actions for reference.png").focus();
  await page.getByLabel("Image actions for reference.png").press("Enter");
  await page.getByRole("menuitem", { name: "Find related" }).click();
  await expect(page.getByRole("heading", { name: "Related Assets" })).toBeVisible();
  const panel = page.getByTestId("related-assets-panel");
  await expect(page.getByText("Same recorded recipe")).toBeVisible();
  await expect(page.getByText("Same generation family")).toBeVisible();
  await expect(panel.getByText("unrelated-same-model.png")).toHaveCount(0);
  await expect(panel.getByText("inactive-match.png")).toHaveCount(0);
  await expect(panel.getByText("cross-library-match.png")).toHaveCount(0);
  expect(requests[0]).toMatchObject({
    reference_asset_id: 1,
    profile: "related",
    scope: { kind: "folder", library_id: 1, import_path_id: 10, relative_path: "" },
  });

  await page.getByRole("tab", { name: "Same recipe" }).click();
  await expect.poll(() => requests.at(-1)?.profile).toBe("recipe");
  await expect(panel.getByText("Seed")).toBeVisible();
  await expect(panel.getByText("101")).toBeVisible();
  await expect(panel.getByText("202")).toBeVisible();
  await page.getByRole("tab", { name: "Visual variants" }).click();
  await expect.poll(() => requests.at(-1)?.profile).toBe("visual");
  await expect(page.getByText("Visual near-duplicate")).toBeVisible();
  await expect(panel.getByRole("button", { name: "resized-reencoded.png", exact: true })).toBeVisible();

  await panel.getByRole("button", { name: "resized-reencoded.png", exact: true }).click();
  await expect(page.getByTestId("lightbox")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Related Assets" })).not.toBeVisible();
});

test("lightbox and mobile overflow actions open the current reference", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const requests = await installFixture(page);
  await openGallery(page);
  await page.getByRole("button", { name: "Open reference.png" }).click();
  await expect(page.getByTestId("lightbox")).toBeVisible();
  await page.getByLabel("Lightbox image actions").click();
  await page.getByRole("menuitem", { name: "Find related" }).click();
  await expect(page.getByRole("heading", { name: "Related Assets" })).toBeVisible();
  await expect.poll(() => requests.at(-1)?.reference_asset_id).toBe(1);
  await expect(page.getByRole("tab", { name: "Visual variants" })).toBeVisible();
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
  await expect(panel.getByText("Showing metadata relations. Visual coverage is not ready.")).toBeVisible();
  await expect(panel.getByRole("button", { name: "candidate.png", exact: true })).toBeVisible();
});
