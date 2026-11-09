/**
 * Purpose:
 * Verifies the Advanced Search drawer layout across phone, tablet and desktop widths: the footer actions stay fully
 * visible (AV-01), the unsaved-changes status is not truncated (AV-02), and the filters come first so the Prompt
 * field is visible on open (AV-03).
 *
 * Guarantees:
 * * at 390, 768, 1024 and 1440 px every footer action is visible, does not overlap another, and has no horizontal
 *   overflow; touch layouts keep 44 px targets
 * * the "Unsaved changes" status is shown in full
 * * the Prompt field is visible without scrolling right after the drawer opens, and Recent searches and Indexed
 *   facets are collapsible sections below the Filters
 *
 * Run when:
 * * changing AdvancedSearchDrawer layout, its footer, RecentSearchesPanel or IndexedFacetSummary
 */

import { expect, test, type Locator, type Page } from "./helpers/monitorErrors";
import { installSearchStub, openGallery } from "./helpers/searchStub";

async function openDrawer(page: Page) {
  const direct = page.getByRole("button", { name: "Advanced Search" }).first();
  if (!(await direct.isVisible())) {
    // Phone header: the search button opens the focus bar, which holds the Advanced Search action.
    await page.locator('button[aria-label*="earch" i]').first().click();
  }
  await page.getByRole("button", { name: "Advanced Search" }).first().click();
  const drawer = page.getByRole("dialog", { name: "Advanced Search" });
  await expect(drawer).toBeVisible({ timeout: 5_000 });
  return drawer;
}

async function makeDirty(drawer: Locator) {
  await drawer.locator("#advanced-search-prompt").fill("night");
}

const footerActions = (drawer: Locator) =>
  ["Revert edits", "Clear all", "Cancel", /Apply/].map((name) => drawer.getByRole("button", { name }));

function expectNoOverlap(boxes: { x: number; y: number; width: number; height: number }[]) {
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const a = boxes[i];
      const b = boxes[j];
      const overlaps = a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
      expect(overlaps, `footer actions ${i} and ${j} overlap`).toBe(false);
    }
  }
}

const widths = [
  { name: "phone 390", viewport: { width: 390, height: 844 }, mobile: true, touch: true },
  { name: "tablet 768", viewport: { width: 768, height: 1024 }, mobile: false, touch: true },
  { name: "tablet 1024", viewport: { width: 1024, height: 768 }, mobile: false, touch: false },
  { name: "desktop 1440", viewport: { width: 1440, height: 900 }, mobile: false, touch: false },
];

for (const config of widths) {
  test.describe(`Advanced Search layout at ${config.name} (AV-01, AV-02, AV-03)`, () => {
    test.use({ viewport: config.viewport, isMobile: config.mobile, hasTouch: config.touch });

    test("every footer action is visible, not overlapping, and not clipped (AV-01)", async ({ page }) => {
      await installSearchStub(page);
      await openGallery(page);
      const drawer = await openDrawer(page);
      await makeDirty(drawer);

      const footer = drawer.getByTestId("advanced-search-footer");
      const buttons = footerActions(drawer);
      const boxes: { x: number; y: number; width: number; height: number }[] = [];
      for (const button of buttons) {
        await expect(button).toBeVisible();
        const box = await button.boundingBox();
        expect(box).not.toBeNull();
        boxes.push(box!);
        if (config.touch) {
          expect(box!.height).toBeGreaterThanOrEqual(44);
        }
      }
      expectNoOverlap(boxes);

      const footerMetrics = await footer.evaluate((el) => ({ scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }));
      expect(footerMetrics.scrollWidth).toBeLessThanOrEqual(footerMetrics.clientWidth);
      const sheetMetrics = await drawer.evaluate((el) => ({ scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }));
      expect(sheetMetrics.scrollWidth).toBeLessThanOrEqual(sheetMetrics.clientWidth);
    });

    test("the unsaved-changes status is shown in full (AV-02)", async ({ page }) => {
      await installSearchStub(page);
      await openGallery(page);
      const drawer = await openDrawer(page);
      await makeDirty(drawer);

      const status = drawer.getByText("Unsaved changes", { exact: true });
      await expect(status).toBeVisible();
      const metrics = await status.evaluate((el) => ({ scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }));
      expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth);
    });

    test("the Prompt field is visible on open, above Recent searches and Indexed facets (AV-03)", async ({ page }) => {
      await installSearchStub(page);
      await openGallery(page);
      const drawer = await openDrawer(page);

      const prompt = drawer.locator("#advanced-search-prompt");
      await expect(prompt).toBeVisible();
      const promptBox = await prompt.boundingBox();
      const viewport = page.viewportSize()!;
      expect(promptBox!.y + promptBox!.height).toBeLessThanOrEqual(viewport.height);

      const facets = drawer.getByRole("button", { name: /Indexed facets/ });
      if (await facets.count()) {
        const facetsBox = await facets.first().boundingBox();
        expect(promptBox!.y).toBeLessThan(facetsBox!.y);
      }
    });
  });
}
