import { expect, test, type Page } from "@playwright/test";

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
    if (url.pathname === "/api/scan") {
      const image = { name: "photo.jpg", path: imagePath, type: "image", has_children: false, mtime: 2 };
      const video = {
        name: "clip.mp4",
        path: videoPath,
        type: "video",
        has_children: false,
        mtime: 1,
        duration_ms: 65_000,
        mime_type: "video/mp4",
      };
      await route.fulfill({
        json: {
          folders: [],
          images: [image],
          videos: [video],
          media: [image, video],
          next_cursor: null,
          total_images: 1,
          total_videos: 1,
          total_assets: 2,
        },
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
    if (url.pathname === "/api/index/status") {
      await route.fulfill({ json: { path: rootPath, total: 0, counts: {}, enabled: false } });
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
  await expect(player).toHaveAttribute("src", `/api/video?path=${encodeURIComponent(videoPath)}`);
  await expect(player).toHaveAttribute("controls", "");
});
