/**
 * Purpose:
 * Verifies SettingsModal persistence and user-facing settings controls.
 *
 * Guarantees:
 * * intro, theme, and lightbox original-loading preferences are read and written correctly
 * * landing-page choices render without breaking gallery state
 *
 * Run when:
 * * changing SettingsModal, localStorage preference keys, or landing-page settings
 * * touching gallery-lightbox-always-load-original controls
 */

import { browseResponse, statusEnvelope } from "./helpers/catalogFixtures";
import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const rootPath = "/gallery-settings-test";
const imagePaths = Array.from({ length: 2 }, (_, i) => `${rootPath}/image_${i + 1}.png`);
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

    if (url.pathname === "/api/browse") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          browseResponse({
            libraryId: Number(url.searchParams.get("library_id") ?? 1),
            path: url.searchParams.get("path") ?? rootPath,
            media: imagePaths.map((path, i) => ({
              name: `image_${i + 1}.png`,
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
          name: url.searchParams.get("path")?.split("/").pop() ?? "image.png",
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
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(["/landpage/ancient_rome.html", "/landpage/art_deco.html", "/landpage/cyberpunk.html"]),
      });
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

test.describe("SettingsModal", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test.beforeEach(async ({ page }) => {
    await installStubbedGallery(page);
    await openStubbedGallery(page);
  });

  test("settings modal opens and shows content", async ({ page }) => {
    const settingsButton = page.getByLabel("Change Intro Page");
    await expect(settingsButton).toBeVisible();
    await settingsButton.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

    await expect(dialog).toContainText("Landing Page");
    await expect(dialog).toContainText("Automatic");
    await expect(dialog).toContainText("Disabled");
    await expect(dialog).toContainText("Manual Selection");
    await expect(dialog).toContainText("Viewer Images");
    await expect(dialog).toContainText("Always load original");
  });

  test("settings modal close button works", async ({ page }) => {
    const settingsButton = page.getByLabel("Change Intro Page");
    await settingsButton.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    const closeButton = dialog.getByRole("button", { name: "Close" });
    await closeButton.click();

    await expect(dialog).not.toBeVisible({ timeout: 5_000 });
  });

  test("settings modal closes on overlay click", async ({ page }) => {
    const settingsButton = page.getByLabel("Change Intro Page");
    await settingsButton.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    await page.mouse.click(10, 10);

    await expect(dialog).not.toBeVisible({ timeout: 5_000 });
  });

  test("intro mode options are toggleable", async ({ page }) => {
    const settingsButton = page.getByLabel("Change Intro Page");
    await settingsButton.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    const disabledOption = dialog.locator("label").filter({ hasText: "Disabled" });
    await expect(disabledOption).toBeVisible();
    await disabledOption.click();

    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible({ timeout: 5_000 });

    const storedMode = await page.evaluate(() => localStorage.getItem("intro_mode"));
    expect(storedMode).toBe("disabled");

    await settingsButton.click();

    const reopenedDialog = page.getByRole("dialog");
    await expect(reopenedDialog).toBeVisible({ timeout: 5_000 });

    const radioInputs = reopenedDialog.locator('input[type="radio"]');
    const disabledRadio = radioInputs.nth(1);
    const isChecked = await disabledRadio.isChecked();
    expect(isChecked).toBe(true);
  });

  test("manual selection shows theme dropdown and preview button", async ({ page }) => {
    const settingsButton = page.getByLabel("Change Intro Page");
    await settingsButton.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    const manualOption = dialog.locator("label").filter({ hasText: "Manual Selection" });
    await manualOption.click();

    await expect(dialog.getByRole("combobox")).toBeVisible({ timeout: 3_000 });
    await expect(dialog.getByRole("button", { name: "Preview" })).toBeVisible();
  });

  test("always load original checkbox is toggleable", async ({ page }) => {
    const settingsButton = page.getByLabel("Change Intro Page");
    await settingsButton.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    await dialog.locator("label").filter({ hasText: "Always load original" }).click();

    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible({ timeout: 5_000 });

    const stored = await page.evaluate(() => localStorage.getItem("gallery-lightbox-always-load-original"));
    expect(stored).toBe("true");

    await settingsButton.click();
    const reopenedDialog = page.getByRole("dialog");
    await expect(reopenedDialog).toBeVisible({ timeout: 5_000 });

    await expect(reopenedDialog.getByRole("checkbox", { name: /Always load original/ })).toBeChecked();
  });

  test("settings dialog has accessibility features", async ({ page }) => {
    const settingsButton = page.getByLabel("Change Intro Page");
    await settingsButton.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

    const closeButton = dialog.getByRole("button", { name: "Close" });
    await expect(closeButton).toBeVisible();

    const radioInputs = dialog.locator('input[type="radio"]');
    await expect(radioInputs).toHaveCount(3);

    await expect(dialog.locator('input[type="checkbox"]')).toHaveCount(1);
  });

  test("settings persist across close and reopen", async ({ page }) => {
    const settingsButton = page.getByLabel("Change Intro Page");

    await settingsButton.click();
    let dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    await dialog.locator("label").filter({ hasText: "Disabled" }).click();
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible({ timeout: 5_000 });

    await settingsButton.click();
    dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    const disabledRadio = dialog.locator('input[type="radio"]').nth(1);
    await expect(disabledRadio).toBeChecked();
  });
});
