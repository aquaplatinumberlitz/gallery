/**
 * Purpose:
 * Verifies that lightbox navigation continues into pages the owning infinite query has not loaded yet, for the
 * folder (browse) view and for search results, and that it wraps only when every page is loaded.
 *
 * Guarantees:
 * * at the last loaded item with more pages available, next does not wrap to the first item
 * * the next page is requested from the browse or search endpoint and its first item is shown
 * * a page that is still loading leaves the lightbox on the last loaded item, without wrapping or errors
 * * a failed page load leaves the lightbox usable on the loaded items
 * * after the last page is loaded, next wraps to the first item again
 *
 * Run when:
 * * changing the lightbox store, usePhotoSwipe, the lazy data source, or how GalleryGrid opens the lightbox
 * * changing browse or search paging (cursor handling, page sizes)
 */

import type { Route } from "@playwright/test";
import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-paging-test";
const PAGE_SIZE = 60;
const PAGE_COUNT = 3;
const TOTAL = PAGE_SIZE * PAGE_COUNT;
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

const nameAt = (index: number) => `img-${String(index).padStart(3, "0")}.png`;
const pathAt = (index: number) => `${rootPath}/${nameAt(index)}`;

interface PagedStub {
  /** Page numbers (1-based) requested from the browse or search endpoint, in order. */
  pageRequests: number[];
  /** Holds (and optionally fails) the response of one page. */
  gate: { page: number; release: Promise<void> | null; fail: boolean };
}

async function installPagedGallery(page: Page): Promise<PagedStub> {
  const stub: PagedStub = { pageRequests: [], gate: { page: 0, release: null, fail: false } };
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());

    if (url.pathname === "/api/libraries") return json(route, [stubLibrary]);
    if (url.pathname === "/api/libraries/1/status") {
      return json(route, statusEnvelope({ libraryId: 1, path: url.searchParams.get("scope_path") ?? rootPath }));
    }

    const gated = async (pageNumber: number) => {
      stub.pageRequests.push(pageNumber);
      if (stub.gate.page !== pageNumber) return false;
      if (stub.gate.release) await stub.gate.release;
      return stub.gate.fail;
    };

    if (url.pathname === "/api/browse") {
      const cursor = Number(url.searchParams.get("cursor") ?? "0");
      const pageNumber = cursor / PAGE_SIZE + 1;
      if (await gated(pageNumber)) return json(route, { detail: "boom" }, 500);
      const media = Array.from({ length: PAGE_SIZE }, (_, i) => {
        const index = cursor + i;
        return {
          name: nameAt(index),
          path: pathAt(index),
          type: "image" as const,
          has_children: false,
          cover_images: [],
          mtime: 100_000 - index,
          image_count: 0,
          width: 1600,
          height: 1000,
        };
      });
      return json(
        route,
        browseResponse({
          libraryId: 1,
          path: url.searchParams.get("path") ?? rootPath,
          media,
          nextMediaCursor: pageNumber < PAGE_COUNT ? cursor + PAGE_SIZE : null,
          totalImages: TOTAL,
        }),
      );
    }

    if (url.pathname === "/api/search/count") return json(route, { schema_version: 1, total: TOTAL, has_more: false });

    if (url.pathname === "/api/search/query") {
      const body = route.request().postDataJSON() as { cursor?: string | null } | null;
      const cursor = body?.cursor ?? null;
      const pageNumber = cursor ? Number(cursor.replace("c", "")) : 1;
      if (await gated(pageNumber)) return json(route, { detail: "boom" }, 500);
      const media = Array.from({ length: PAGE_SIZE }, (_, i) => {
        const index = (pageNumber - 1) * PAGE_SIZE + i;
        return {
          name: nameAt(index),
          path: pathAt(index),
          type: "photo",
          parent_path: rootPath,
          relative_path: "",
          mtime: 100_000 - index,
          width: 1600,
          height: 1000,
          match_type: "filename",
          prompt_snippet: "",
          model: "",
          sampler: "",
          seed: "",
        };
      });
      const nextCursor = pageNumber < PAGE_COUNT ? `c${pageNumber + 1}` : null;
      return json(route, {
        query: "img",
        scope: "all",
        root: rootPath,
        albums: [],
        photos: media,
        media,
        prompt: [],
        videos: [],
        next_cursor: nextCursor,
        has_more: nextCursor !== null,
        returned: media.length,
        limit: PAGE_SIZE,
      });
    }

    if (url.pathname === "/api/metadata") {
      return json(route, {
        tool: "A1111",
        prompt: "test prompt",
        negative_prompt: "",
        params: {},
        width: 1600,
        height: 1000,
        name: (url.searchParams.get("path") ?? "").split("/").pop(),
      });
    }
    if (url.pathname === "/api/health") return json(route, { status: "ok" });
    if (url.pathname === "/api/landing-pages") return json(route, []);
    if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
      return route.fulfill({ contentType: "image/png", body: png1x1 });
    }
    return json(route, {}, 404);
  });
  return stub;
}

type Mode = "browse" | "search";

async function startMode(page: Page, mode: Mode) {
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
  if (mode === "search") {
    const input = page.locator("#gallery-search");
    await input.fill("img");
    await input.press("Enter");
    await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 10_000 });
  }
}

async function openFirstCard(page: Page) {
  await page.getByTestId("photo-card").first().click();
  await expect(page.getByTestId("lightbox")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("desktop-lightbox-counter")).toBeVisible();
}

const counter = (page: Page) => page.getByTestId("desktop-lightbox-counter");
// The sidebar shows the metadata of the current item; the metadata stub echoes the requested file name.
const currentName = (page: Page) => page.getByTestId("lightbox").getByText(/^img-\d{3}\.png$/);

async function pressNext(page: Page, times: number) {
  for (let i = 0; i < times; i += 1) await page.keyboard.press("ArrowRight");
}

test.use({ viewport: { width: 1280, height: 820 } });

for (const mode of ["browse", "search"] as const) {
  test.describe(`${mode} lightbox paging`, () => {
    test("next at the last loaded item requests the next page instead of wrapping", async ({ page }) => {
      const stub = await installPagedGallery(page);
      await startMode(page, mode);
      expect(stub.pageRequests.filter((p) => p !== 1)).toEqual([]);

      // Hold page 2 so the last loaded item can be observed while the page is still on its way.
      let release!: () => void;
      stub.gate.page = 2;
      stub.gate.release = new Promise<void>((resolve) => {
        release = resolve;
      });

      await openFirstCard(page);
      await expect(counter(page)).toHaveText(`1 / ${PAGE_SIZE}`);
      await pressNext(page, PAGE_SIZE - 1);
      await expect(counter(page)).toHaveText(`${PAGE_SIZE} / ${PAGE_SIZE}`);
      await expect(currentName(page)).toHaveText(nameAt(PAGE_SIZE - 1));

      // The request is made on approach; pressing next at the end must not wrap while the page is loading.
      await expect.poll(() => stub.pageRequests.filter((p) => p === 2).length).toBe(1);
      await page.keyboard.press("ArrowRight");
      await page.waitForTimeout(400);
      await expect(counter(page)).toHaveText(`${PAGE_SIZE} / ${PAGE_SIZE}`);
      await expect(currentName(page)).toHaveText(nameAt(PAGE_SIZE - 1));

      release();
      await expect(counter(page)).toHaveText(`${PAGE_SIZE} / ${PAGE_SIZE * 2}`);
      await page.keyboard.press("ArrowRight");
      await expect(counter(page)).toHaveText(`${PAGE_SIZE + 1} / ${PAGE_SIZE * 2}`);
      await expect(currentName(page)).toHaveText(nameAt(PAGE_SIZE));
      expect(stub.pageRequests.filter((p) => p === 2)).toHaveLength(1);
    });

    test("walks across every page and wraps only after the last one", async ({ page }) => {
      const stub = await installPagedGallery(page);
      await startMode(page, mode);
      await openFirstCard(page);

      let index = 0;
      let loaded = PAGE_SIZE;
      while (index < TOTAL - 1) {
        if (index === loaded - 1) {
          // At the end of the loaded pages next waits for the next page: let it land, then continue into it.
          loaded += PAGE_SIZE;
          await expect(counter(page)).toHaveText(`${index + 1} / ${loaded}`);
        }
        await page.keyboard.press("ArrowRight");
        index += 1;
      }
      await expect(counter(page)).toHaveText(`${TOTAL} / ${TOTAL}`);
      await expect(currentName(page)).toHaveText(nameAt(TOTAL - 1));
      expect([...new Set(stub.pageRequests)]).toEqual([1, 2, 3]);

      // Every page is loaded: wrapping is restored.
      await page.keyboard.press("ArrowRight");
      await expect(counter(page)).toHaveText(`1 / ${TOTAL}`);
      await expect(currentName(page)).toHaveText(nameAt(0));
    });

    test("a failed page load leaves the lightbox usable on the loaded items", async ({ page, monitoredErrors }) => {
      // The stubbed 500 is logged by the browser as a failed resource; unhandled rejections still fail the test.
      monitoredErrors.allowConsoleError("Failed to load resource");
      const stub = await installPagedGallery(page);
      stub.gate.page = 2;
      stub.gate.fail = true;
      await startMode(page, mode);
      await openFirstCard(page);

      await pressNext(page, PAGE_SIZE - 1);
      await expect(counter(page)).toHaveText(`${PAGE_SIZE} / ${PAGE_SIZE}`);
      await expect.poll(() => stub.pageRequests.filter((p) => p === 2).length).toBeGreaterThanOrEqual(1);

      await page.keyboard.press("ArrowRight");
      await page.waitForTimeout(400);
      await expect(counter(page)).toHaveText(`${PAGE_SIZE} / ${PAGE_SIZE}`);

      await page.keyboard.press("ArrowLeft");
      await expect(counter(page)).toHaveText(`${PAGE_SIZE - 1} / ${PAGE_SIZE}`);
      await expect(page.getByTestId("lightbox")).toBeVisible();
    });
  });
}
