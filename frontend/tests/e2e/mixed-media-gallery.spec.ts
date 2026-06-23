/*
Purpose:
Cover mixed image/video gallery rendering and media-specific open behavior.

Guarantees:
Images still open through the lightbox, videos open through the video dialog,
and mixed-media browse rows preserve the correct UI affordances.

Run when:
Changing mixed-media browse responses, `VideoCard`, gallery rendering, or
lightbox/video routing.
*/

import { expect, test, type Page } from "@playwright/test";
import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://127.0.0.1:5173";
const rootPath = "/registered/mixed";
const imagePath = `${rootPath}/photo.jpg`;
const videoPath = `${rootPath}/clip.mp4`;

async function mockMixedGallery(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("intro_mode", "disabled");
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");
  });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/libraries") {
      await route.fulfill({
        json: [
          {
            id: 1,
            root_path: rootPath,
            import_paths: [{ id: 10, library_id: 1, path: rootPath, position: 0, created_at: 1, updated_at: 1 }],
            exclusion_patterns: [],
            name: "Mixed library",
            state: "ready",
            watch_enabled: 1,
            warm_enabled: 1,
            asset_count: 2,
            created_at: 1,
            updated_at: 1,
            last_scan_at: 1,
            last_error: null,
          },
        ],
      });
      return;
    }
    if (url.pathname === "/api/browse") {
      const image = { name: "photo.jpg", path: imagePath, type: "image" as const, has_children: false, mtime: 2 };
      const video = {
        name: "clip.mp4",
        path: videoPath,
        type: "video" as const,
        has_children: false,
        mtime: 1,
        duration_ms: 65_000,
        mime_type: "video/mp4",
      };
      await route.fulfill({
        json: browseResponse({
          libraryId: Number(url.searchParams.get("library_id") ?? 1),
          path: url.searchParams.get("path") ?? rootPath,
          media: [image, video],
        }),
      });
      return;
    }
    if (url.pathname === "/api/search") {
      await route.fulfill({
        json: { query: "", scope: "current", root: rootPath, albums: [], photos: [], videos: [], prompt: [] },
      });
      return;
    }
    if (url.pathname === "/api/video/poster") {
      await route.fulfill({ status: 503, json: { detail: { type: "video_poster_unavailable" } } });
      return;
    }
    if (url.pathname === "/api/libraries/1/status") {
      await route.fulfill({
        json: statusEnvelope({ libraryId: 1, path: url.searchParams.get("scope_path") ?? rootPath, totalAssets: 2 }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: "image/png", body: "" });
  });
}

test("mixed gallery preserves image lightbox and opens videos in the native player", async ({ page }) => {
  await mockMixedGallery(page);
  await page.goto(baseUrl);

  await expect(page.getByTestId("photo-card")).toBeVisible();
  await expect(page.getByTestId("video-card")).toBeVisible();
  await expect(page.getByTestId("video-poster-fallback")).toBeVisible();

  await page.getByTestId("photo-card").click();
  await expect(page.getByTestId("lightbox")).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByTestId("video-card").click();
  const player = page.getByTestId("video-player");
  await expect(player).toBeVisible();
  await expect(player).toHaveAttribute("src", /\/api\/video\?path=.*clip\.mp4/);
  await expect(player).toHaveAttribute("controls", "");
});
