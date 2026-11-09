/**
 * Purpose:
 * Verifies search-as-you-type behaviour in the real app: results stay visible while typing more (SE-01), Enter and
 * the 250 ms debounce send requests at the right time (SE-02), the count is never sent for empty text (SE-05), and
 * IME composition (CJ-01) and the IME-confirming Enter (CJ-02) behave on the desktop header, the mobile header and the
 * Advanced Search drawer.
 *
 * Guarantees:
 * * no browse fallback, "Keep typing" hint or skeleton between keystrokes once a search is showing
 * * one search request per pause; Enter sends the request without waiting for the debounce
 * * uncommitted IME text is never searched, and the committed text is searched once
 * * an Enter that confirms an IME candidate neither submits nor blurs
 *
 * Run when:
 * * changing search typing, debounce, header or drawer search inputs, or IME handling
 */

import { expect, test, type Page } from "./helpers/monitorErrors";
import { installSearchStub, openGallery } from "./helpers/searchStub";

/** Records, every animation frame, whether the search panel or the browse hint is on screen. */
async function startStateSampler(page: Page) {
  await page.evaluate(() => {
    const w = window as unknown as { __samples: string[]; __stop?: boolean };
    w.__samples = [];
    const tick = () => {
      if (w.__stop) return;
      const hint = Boolean(document.querySelector(".search-warmup-hint"));
      const panel = Boolean(document.querySelector(".search-results-panel"));
      const state = `${hint ? "hint" : "-"}|${panel ? "panel" : "-"}`;
      if (w.__samples.at(-1) !== state) w.__samples.push(state);
      requestAnimationFrame(tick);
    };
    tick();
  });
}

async function stopStateSampler(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const w = window as unknown as { __samples: string[]; __stop?: boolean };
    w.__stop = true;
    return w.__samples;
  });
}

test.describe("search typing (SE-01, SE-02, SE-05)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("typing more keeps the previous results on screen between keystrokes (SE-01)", async ({ page }) => {
    await installSearchStub(page);
    await openGallery(page);
    const box = page.locator("#gallery-search");
    await box.click();
    await box.pressSequentially("ni");
    await expect(page.locator(".search-results-panel")).toBeVisible({ timeout: 5_000 });

    await startStateSampler(page);
    for (const ch of "ght") {
      await box.pressSequentially(ch);
      await page.waitForTimeout(400);
    }
    await expect(page.locator(".search-results-panel")).toBeVisible();
    const samples = await stopStateSampler(page);

    expect(samples.some((s) => s.startsWith("hint"))).toBe(false);
    expect(samples.some((s) => s.endsWith("-"))).toBe(false);
  });

  test("Enter sends the request without waiting for the debounce (SE-02)", async ({ page }) => {
    const stub = await installSearchStub(page);
    await openGallery(page);
    const box = page.locator("#gallery-search");
    await box.click();
    await box.pressSequentially("night");
    const enterAt = await page.evaluate(() => Date.now());
    await box.press("Enter");

    await expect.poll(() => stub.queries.some((q) => q.text === "night")).toBe(true);
    const sent = stub.queries.find((q) => q.text === "night")!;
    expect(sent.at - enterAt).toBeLessThan(100);
  });

  test("fast typing sends one request for the settled text (SE-02)", async ({ page }) => {
    const stub = await installSearchStub(page);
    await openGallery(page);
    const box = page.locator("#gallery-search");
    await box.click();
    await box.pressSequentially("night", { delay: 30 });
    await expect.poll(() => stub.queries.length).toBeGreaterThan(0);
    await page.waitForTimeout(600);

    expect(stub.queries.map((q) => q.text)).toEqual(["night"]);
  });

  test("no search-count request is sent for empty text after Enter (SE-05)", async ({ page }) => {
    const stub = await installSearchStub(page);
    await openGallery(page);
    const box = page.locator("#gallery-search");
    await box.click();
    await box.pressSequentially("night");
    await box.press("Enter");
    await page.waitForTimeout(600);

    expect(stub.counts.length).toBeGreaterThan(0);
    expect(stub.counts.filter((c) => c.text.trim() === "")).toEqual([]);
  });
});

test.describe("IME composition (CJ-01, CJ-02)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("uncommitted IME text is never searched; the committed text is (CJ-01)", async ({ page }) => {
    const stub = await installSearchStub(page);
    await openGallery(page);
    const box = page.locator("#gallery-search");
    await box.click();
    await composeAndCommitInField(page, box, "桜花");
    await page.waitForTimeout(600);

    expect(stub.queries.map((q) => q.text)).toEqual(["桜花"]);
  });

  test("the Enter that confirms an IME candidate does not submit (CJ-02)", async ({ page }) => {
    const stub = await installSearchStub(page);
    await openGallery(page);
    const box = page.locator("#gallery-search");
    await box.click();
    // Type, then compose and press the candidate Enter straight away. A submit would flush the 250 ms debounce and
    // send "night" at once; the IME Enter must not, so no request for "night" may leave within 100 ms of it.
    await box.pressSequentially("night");
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Input.imeSetComposition", { text: "しょうじょ", selectionStart: 5, selectionEnd: 5 });
    const enterAt = await page.evaluate(() => Date.now());
    await cdp.send("Input.dispatchKeyEvent", {
      type: "rawKeyDown",
      key: "Enter",
      code: "Enter",
      windowsVirtualKeyCode: 13,
    });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
    await page.waitForTimeout(600);

    expect(stub.queries.filter((q) => q.text === "night" && q.at - enterAt < 100)).toEqual([]);
    expect(await box.evaluate((el) => document.activeElement === el)).toBe(true);
  });
});

test.describe("IME composition on the mobile header (CJ-01, CJ-02)", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test("mobile: composing text is not searched and the candidate Enter keeps focus (CJ-01, CJ-02)", async ({
    page,
  }) => {
    const stub = await installSearchStub(page);
    await openGallery(page);
    await page.locator('button[aria-label*="earch" i]').first().click();
    const box = page.locator("#mobile-gallery-search");
    await expect(box).toBeVisible();
    await box.click();

    const cdp = await page.context().newCDPSession(page);
    for (const text of ["さ", "さく", "さくら"]) {
      await cdp.send("Input.imeSetComposition", { text, selectionStart: text.length, selectionEnd: text.length });
      await page.waitForTimeout(400);
    }
    await cdp.send("Input.dispatchKeyEvent", {
      type: "rawKeyDown",
      key: "Enter",
      code: "Enter",
      windowsVirtualKeyCode: 13,
    });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
    await page.waitForTimeout(300);
    expect(await box.evaluate((el) => document.activeElement === el)).toBe(true);
    await cdp.send("Input.insertText", { text: "桜花" });
    await page.waitForTimeout(600);

    expect(stub.queries.map((q) => q.text)).toEqual(["桜花"]);
  });
});

test.describe("IME composition in the Advanced Search drawer (CJ-01, CJ-02)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("drawer prompt and jump fields hold composition and ignore the candidate Enter", async ({ page }) => {
    const stub = await installSearchStub(page);
    await openGallery(page);
    await page.getByRole("button", { name: "Advanced Search" }).click();
    const drawer = page.getByRole("dialog", { name: "Advanced Search" });
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    const prompt = drawer.locator("#advanced-search-prompt");
    await prompt.click();
    await composeAndCommitInField(page, prompt, "桜花");
    await page.waitForTimeout(400);
    expect(stub.counts.filter((c) => c.text.includes("さ") || c.text.includes("さく"))).toEqual([]);

    // "se" is a composition that matches the "seed" field label. The candidate Enter must not jump to it (CJ-02).
    const jump = drawer.locator("#advanced-search-jump-input");
    await jump.click();
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Input.imeSetComposition", { text: "se", selectionStart: 2, selectionEnd: 2 });
    await page.waitForTimeout(200);
    await cdp.send("Input.dispatchKeyEvent", {
      type: "rawKeyDown",
      key: "Enter",
      code: "Enter",
      windowsVirtualKeyCode: 13,
    });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
    await page.waitForTimeout(300);
    await expect(drawer).toBeVisible();
    expect(await jump.evaluate((el) => document.activeElement === el)).toBe(true);
    expect(await page.evaluate(() => document.activeElement?.id === "advanced-search-seed")).toBe(false);
  });
});

/** Japanese composition as an IME produces it: pauses while composing (さ, さく, さくら), then a committed 桜. */
async function composeAndCommitInField(page: Page, input: ReturnType<Page["locator"]>, committed: string) {
  const cdp = await page.context().newCDPSession(page);
  for (const text of ["さ", "さく", "さくら"]) {
    await cdp.send("Input.imeSetComposition", { text, selectionStart: text.length, selectionEnd: text.length });
    await page.waitForTimeout(400);
  }
  await cdp.send("Input.insertText", { text: committed });
  expect(await input.inputValue()).toBe(committed);
}
