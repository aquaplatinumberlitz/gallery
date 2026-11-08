/**
 * Purpose:
 * Verifies breadcrumb rendering and navigation for deep gallery paths.
 *
 * Guarantees:
 * * long path segments remain accessible without breaking layout
 * * breadcrumb clicks update the gallery path through SPA navigation
 *
 * Run when:
 * * changing Breadcrumb, path routing, or gallery navigation state
 * * touching responsive header space used by breadcrumbs
 */

import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
// The breadcrumb starts at the import root. The import root sits one level above the deep
// folder, so the trail below it is long enough to collapse; the test walks down to it.
const importRoot = "/breadcrumb-root/alpha";
const rootPath = "/breadcrumb-root/alpha/beta/gamma/delta/epsilon/zeta";
const imagePath = `${rootPath}/image_1.png`;

function childFolderOf(path: string) {
  if (!rootPath.startsWith(`${path}/`)) return [];
  const name = rootPath.slice(path.length + 1).split("/")[0];
  return [{ name, path: `${path}/${name}`, type: "folder" as const, has_children: true, image_count: 0 }];
}
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64",
);

const stubLibrary = {
  id: 1,
  root_path: importRoot,
  import_paths: [{ id: 10, library_id: 1, path: importRoot, position: 0, created_at: 1, updated_at: 1 }],
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

async function installStubbedGallery(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());

    if (url.pathname === "/api/libraries") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([stubLibrary]),
      });
      return;
    }

    if (url.pathname === "/api/folders") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(childFolderOf(url.searchParams.get("path") ?? importRoot)),
      });
      return;
    }

    if (url.pathname === "/api/browse") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          browseResponse({
            libraryId: Number(url.searchParams.get("library_id") ?? 1),
            path: url.searchParams.get("path") ?? importRoot,
            folders: childFolderOf(url.searchParams.get("path") ?? importRoot),
            media: [
              {
                name: "image_1.png",
                path: imagePath,
                type: "image",
                has_children: false,
                cover_images: [],
                mtime: 1000,
                image_count: 0,
                width: 1600,
                height: 1000,
              },
            ],
          }),
        ),
      });
      return;
    }

    if (url.pathname === "/api/metadata") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          tool: "stub",
          prompt: "stub prompt",
          negative_prompt: "",
          params: {},
          width: 1600,
          height: 1000,
          name: "image_1.png",
        }),
      });
      return;
    }

    if (url.pathname === "/api/health") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ status: "ok" }),
      });
      return;
    }

    if (url.pathname === "/api/landing-pages") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([]) });
      return;
    }

    if (url.pathname === "/api/search") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ albums: [], photos: [], prompts: [] }),
      });
      return;
    }

    if (url.pathname === "/api/libraries/1/status") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(statusEnvelope({ libraryId: 1, path: url.searchParams.get("scope_path") ?? rootPath })),
      });
      return;
    }

    if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
      await route.fulfill({ contentType: "image/png", body: png1x1 });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
}

async function openStubbedGallery(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("photo-card").first()).toBeVisible({ timeout: 15_000 });
}

test.describe("Breadcrumb", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("opens collapsed breadcrumb menu without getBoundingClientRect runtime error", async ({
    page,
    monitoredErrors,
  }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);
    for (const name of ["beta", "gamma", "delta", "epsilon", "zeta"]) {
      await page.locator(`[data-testid="album-card"][data-album-name="${name}"]`).first().click();
    }
    await expect(
      page.locator(".expanded-header:not([inert]), .compact-header:not([inert])").getByText("zeta").first(),
    ).toBeVisible();

    const activeHeader = page.locator(".expanded-header:not([inert]), .compact-header:not([inert])");
    const ellipsisButton = activeHeader.locator('button[aria-label$="more folders"]');
    await expect(ellipsisButton).toBeVisible();

    await ellipsisButton.click();

    const menu = page.getByRole("menu");
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("menuitem", { name: "Show full path" })).toBeVisible();
    expect(
      monitoredErrors.consoleErrors.some(
        (message) =>
          message.includes("getBoundingClientRect is not a function") || message.includes("Unhandled Vue error"),
      ),
    ).toBe(false);
  });
});

// The import root is the fixture library; the test walks down to the long album name.
const tabletImportRoot = "/tmp/scratch-session/fixture-lib";
const tabletFolderName = "Miku ver.2 — long album name for truncation testing";
const tabletRoot = `${tabletImportRoot}/Characters/${tabletFolderName}`;

function tabletFoldersOf(path: string) {
  if (path === tabletImportRoot) {
    return [
      { name: "Characters", path: `${tabletImportRoot}/Characters`, type: "folder" as const, has_children: true },
    ];
  }
  if (path === `${tabletImportRoot}/Characters`) {
    return [{ name: tabletFolderName, path: tabletRoot, type: "folder" as const, has_children: false }];
  }
  return [];
}

test.describe("Breadcrumb on tablet header", () => {
  test.use({ viewport: { width: 768, height: 1024 }, hasTouch: true, isMobile: true });

  test("segments stay on one line and the current folder truncates with an ellipsis", async ({ page }) => {
    const library = {
      ...stubLibrary,
      root_path: tabletImportRoot,
      import_paths: [{ ...stubLibrary.import_paths[0], path: tabletImportRoot }],
    };
    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/libraries") {
        await route.fulfill({ contentType: "application/json", body: JSON.stringify([library]) });
        return;
      }
      if (url.pathname === "/api/libraries/1/status") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify(
            statusEnvelope({ libraryId: 1, path: url.searchParams.get("scope_path") ?? tabletImportRoot }),
          ),
        });
        return;
      }
      if (url.pathname === "/api/browse") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify(
            browseResponse({
              libraryId: 1,
              path: url.searchParams.get("path") ?? tabletImportRoot,
              folders: tabletFoldersOf(url.searchParams.get("path") ?? tabletImportRoot),
              media: [
                {
                  name: "image_1.png",
                  path: `${tabletRoot}/image_1.png`,
                  type: "image",
                  mtime: 1,
                  width: 1600,
                  height: 1000,
                },
              ],
            }),
          ),
        });
        return;
      }
      if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
        await route.fulfill({ contentType: "image/png", body: png1x1 });
        return;
      }
      await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
    });
    await openStubbedGallery(page);
    for (const name of ["Characters", tabletFolderName]) {
      await page.locator(`[data-testid="album-card"][data-album-name="${name}"]`).first().click();
    }

    const breadcrumb = page.locator(".th-context-path .breadcrumb-list");
    await expect(breadcrumb).toBeVisible();
    const labels = await breadcrumb.evaluate((list) =>
      [...list.querySelectorAll<HTMLElement>(".breadcrumb-link, [aria-current='page']")].map((el) => {
        const style = getComputedStyle(el);
        // Count text line boxes. Height / line-height is not usable: touch-sized links
        // (min-height 44px) would always read as two lines.
        const range = document.createRange();
        range.selectNodeContents(el);
        const textLines = new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size;
        return {
          text: el.textContent?.trim(),
          lines: textLines,
          whiteSpace: style.whiteSpace,
          textOverflow: style.textOverflow,
          truncated: el.scrollWidth > el.clientWidth,
          right: el.getBoundingClientRect().right,
          listRight: list.getBoundingClientRect().right,
        };
      }),
    );
    expect(labels.length).toBeGreaterThan(1);
    expect(labels[0].text).toBe("fixture-lib");
    for (const label of labels) {
      expect(label.whiteSpace, label.text).toBe("nowrap");
      expect(label.lines, label.text).toBeLessThanOrEqual(1);
      expect(label.textOverflow, label.text).toBe("ellipsis");
      expect(label.right, label.text).toBeLessThanOrEqual(label.listRight + 1);
    }
    const current = labels[labels.length - 1];
    expect(current.text).toContain("Miku ver.2");
    expect(current.truncated).toBe(true);
  });
});
