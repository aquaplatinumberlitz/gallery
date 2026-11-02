/*
Purpose:
Guard the cumulative layout shift of a cold gallery home load.

Guarantees:
Loading "/" cold with a registered library, albums and photos produces a CLS far below the 0.1 "good" limit
(asserted < 0.01) at the desktop (1440x900) and phone (390x844) viewports. The two causes this protects against:
the Cinzel brand title wrapping to a second line when the web font swaps in (the fallback face in fonts.css must
wrap like Cinzel), and the sidebar/breadcrumb/toolbar painting in their pre-hydration state and moving when the
library list arrives (main.ts holds the first mount for the list).

Why it lives in perf/: the shifts only exist in the production build. The dev server loads the fonts and CSS
differently (the same spec passes on the pre-fix code there), so this runs against `vite preview` via
`playwright.perf.config.ts` (`./test.sh perf`), with the API mocked, and is skipped elsewhere.

Run when:
Changing fonts.css or the header brand title, the sidebar header, the breadcrumb/toolbar, the start-up sequence in
main.ts, or the active-library hydration.
*/

import type { Page } from "@playwright/test";
import { expect, test } from "../helpers/monitorErrors";
import { browseResponse } from "../helpers/catalogFixtures";

test.skip(
  process.env.GALLERY_PERF_E2E !== "1",
  "Set GALLERY_PERF_E2E=1 and run with playwright.perf.config.ts (production build via vite preview) to run the CLS guard.",
);
// The measured value is ~0.0004 after the fix and 0.03-0.2 before it, so a 0.05 limit would not fail the
// common 0.03 case. 0.01 leaves room for jitter while failing on any real shift (Google's "good" CLS limit is 0.1).
const CLS_LIMIT = 0.01;
const rootPath = "/registered/photos";
const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64",
);
const library = {
  id: 7,
  root_path: rootPath,
  import_paths: [{ id: 70, library_id: 7, path: rootPath, position: 0, created_at: 1, updated_at: 1 }],
  exclusion_patterns: [],
  name: "Photos",
  state: "ready",
  watch_enabled: 1,
  warm_enabled: 1,
  asset_count: 24,
  created_at: 1,
  updated_at: 1,
  last_scan_at: null,
  last_error: null,
};

const folders = Array.from({ length: 8 }, (_, index) => ({
  name: `album-${index + 1}`,
  path: `${rootPath}/album-${index + 1}`,
  type: "folder" as const,
  has_children: false,
  image_count: 12,
  cover_images: [`${rootPath}/album-${index + 1}/a.png`, `${rootPath}/album-${index + 1}/b.png`],
  cover_versions: ["1-1", "1-1"],
}));
const media = Array.from({ length: 24 }, (_, index) => ({
  name: `photo-${index + 1}.png`,
  path: `${rootPath}/photo-${index + 1}.png`,
  type: "image" as const,
  mtime: 1000 + index,
  width: 1200,
  height: 800,
}));

async function mockGallery(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/libraries") return route.fulfill({ json: [library] });
    if (url.pathname === "/api/browse") {
      return route.fulfill({
        json: browseResponse({ libraryId: library.id, path: url.searchParams.get("path") ?? rootPath, folders, media }),
      });
    }
    if (url.pathname === "/api/thumbnail") {
      return route.fulfill({ body: png, contentType: "image/png", headers: { "cache-control": "max-age=3600" } });
    }
    return route.fulfill({ json: [] });
  });
}

async function observeLayoutShifts(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    const w = window as unknown as { __cls: number; __shifts: unknown[] };
    w.__cls = 0;
    w.__shifts = [];
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as unknown as Array<{
        value: number;
        hadRecentInput: boolean;
        startTime: number;
        sources?: Array<{ node?: Element | null; previousRect: DOMRectReadOnly; currentRect: DOMRectReadOnly }>;
      }>) {
        if (entry.hadRecentInput) continue;
        w.__cls += entry.value;
        w.__shifts.push({
          at: Math.round(entry.startTime),
          value: Number(entry.value.toFixed(4)),
          sources: (entry.sources ?? []).map((source) => ({
            node: source.node ? `${source.node.tagName}.${String(source.node.className).slice(0, 50)}` : null,
            from: [source.previousRect.x, source.previousRect.y, source.previousRect.width, source.previousRect.height],
            to: [source.currentRect.x, source.currentRect.y, source.currentRect.width, source.currentRect.height],
          })),
        });
      }
    }).observe({ type: "layout-shift", buffered: true });
  });
}

const viewports = [
  { name: "desktop 1440x900", width: 1440, height: 900 },
  { name: "phone 390x844", width: 390, height: 844 },
];

for (const viewport of viewports) {
  test(`cold home load keeps CLS under ${CLS_LIMIT} (${viewport.name})`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await mockGallery(page);
    await observeLayoutShifts(page);
    await page.goto("/", { waitUntil: "load" });
    await expect(page.getByTestId("album-card").first()).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    // Late swaps (fonts, lazy chunks) land within a second or two of the first paint.
    await page.waitForTimeout(2000);

    const result = await page.evaluate(() => {
      const w = window as unknown as { __cls: number; __shifts: unknown[] };
      return { cls: w.__cls, shifts: w.__shifts };
    });
    expect(result.cls, `layout shifts: ${JSON.stringify(result.shifts)}`).toBeLessThan(CLS_LIMIT);
  });
}
