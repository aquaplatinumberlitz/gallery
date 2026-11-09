/**
 * Purpose:
 * Shared API stub and gallery bootstrap for search typing, IME and drawer layout specs. Every /api route is
 * fulfilled in the page, so the specs do not need the backend.
 *
 * Guarantees:
 * * every non-empty /api/search/query returns the same three images
 * * /api/search/count and /api/search/query calls are recorded with their text and time
 *
 * Run when:
 * * changing a spec that uses installSearchStub, or the search API shapes the UI reads
 */

import { browseResponse, statusEnvelope } from "./catalogFixtures";
import { expect, type Page } from "./monitorErrors";

export const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
export const rootPath = "/gallery-search-typing-test";
export const imagePaths = [`${rootPath}/night_city.png`, `${rootPath}/nightfall.png`, `${rootPath}/dawn.png`];
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

export interface SearchStub {
  queries: { text: string; at: number }[];
  counts: { text: string; at: number }[];
}

// Minimal API stub in the style of advanced-search-drawer.spec.ts. Every non-empty query matches the same images.
export async function installSearchStub(page: Page): Promise<SearchStub> {
  const stub: SearchStub = { queries: [], counts: [] };
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const json = (body: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });

    if (url.pathname === "/api/libraries") return json([stubLibrary]);
    if (url.pathname === "/api/libraries/1/status") {
      return json(statusEnvelope({ libraryId: 1, path: url.searchParams.get("scope_path") ?? rootPath }));
    }
    if (url.pathname === "/api/browse") {
      return json(
        browseResponse({
          libraryId: 1,
          path: url.searchParams.get("path") ?? rootPath,
          media: imagePaths.map((path, i) => ({
            name: path.split("/").pop()!,
            path,
            type: "image",
            has_children: false,
            cover_images: [],
            mtime: 1000 + i,
            image_count: 0,
            width: 1600,
            height: 1000,
          })),
        }),
      );
    }
    if (url.pathname === "/api/search/query") {
      const body = route.request().postDataJSON() as { text?: string; scope?: { kind?: string } } | null;
      const text = body?.text ?? "";
      stub.queries.push({ text, at: Date.now() });
      const media = text
        ? imagePaths.map((path, i) => ({
            name: path.split("/").pop()!,
            path,
            type: "photo",
            parent_path: rootPath,
            relative_path: "",
            mtime: 1000 + i,
            width: 1600,
            height: 1000,
            match_type: "filename",
            prompt_snippet: "",
            model: "",
            sampler: "",
            seed: "",
          }))
        : [];
      return json({
        query: text,
        scope: body?.scope?.kind ?? "all",
        root: rootPath,
        albums: [],
        photos: media,
        media,
        prompt: [],
        videos: [],
        next_cursor: null,
        has_more: false,
        returned: media.length,
        limit: 60,
      });
    }
    if (url.pathname === "/api/search/count") {
      const body = route.request().postDataJSON() as { text?: string } | null;
      stub.counts.push({ text: body?.text ?? "", at: Date.now() });
      return json({ schema_version: 1, total: imagePaths.length, has_more: false });
    }
    if (url.pathname === "/api/facets") {
      // Realistic indexed values, so the Indexed facets section has its real height (it is long on a real library).
      return json({
        model: [
          { value: "PonyXL", count: 10 },
          { value: "SDXL", count: 5 },
          { value: "Illustrious", count: 4 },
        ],
        sampler: [
          { value: "Euler a", count: 15 },
          { value: "DPM++ 2M Karras", count: 8 },
          { value: "DPM++ SDE", count: 3 },
        ],
        scheduler: [{ value: "Karras", count: 20 }],
        lora: [
          { value: "detail-tweaker", count: 6 },
          { value: "add-more-details", count: 3 },
        ],
        tool: [
          { value: "Unknown", count: 100 },
          { value: "SwarmUI", count: 46 },
        ],
        orientation: [
          { value: "portrait", count: 141 },
          { value: "square", count: 44 },
        ],
        seed_availability: [
          { value: "available", count: 107 },
          { value: "missing", count: 102 },
        ],
        metadata_availability: [
          { value: "available", count: 209 },
          { value: "missing", count: 3 },
        ],
      });
    }
    if (url.pathname === "/api/search/capabilities") {
      return json({
        schema_version: 1,
        enabled_modes: ["lexical"],
        supported_scopes: ["folder", "library", "all"],
        field_limits: {},
        workflow_registry: { version: 1, nodes: {} },
        raw_search: { enabled: false, query_min_chars: 3, query_max_chars: 128, limit_max: 50, deadline_ms: 250, max_document_bytes: 1_048_576, index_budget_bytes: 536_870_912 },
        index_requirements: {},
        indexes: [],
      });
    }
    if (url.pathname === "/api/health") return json({ status: "ok" });
    if (url.pathname === "/api/landing-pages") return json([]);
    if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
      await route.fulfill({ contentType: "image/png", body: png1x1 });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
  return stub;
}

export async function openGallery(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
}

