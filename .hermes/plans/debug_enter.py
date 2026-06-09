"""Debug: full flow after ENTER GALLERY."""
import asyncio
from playwright.async_api import async_playwright

CHROMIUM_PATH = "/home/ubuntu/.cache/ms-playwright/chromium-1223/chrome-linux/chrome"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path=CHROMIUM_PATH)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        await page.goto("http://localhost:4173", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1000)
        print("1. Initial page loaded")

        # Click ENTER GALLERY
        enter_btn = page.locator("button:has-text('ENTER GALLERY')").first
        await enter_btn.wait_for(state="visible", timeout=10000)
        await enter_btn.click()
        print("2. Clicked ENTER GALLERY")
        await page.wait_for_timeout(3000)

        # Screenshot
        await page.screenshot(path="/tmp/g_after_enter.png", full_page=True)
        print("3. Screenshot saved")

        # Dump full page text
        body = await page.evaluate("document.body.innerText.slice(0, 3000)")
        print(f"\nBody text:\n{body}")

        # Check for album cards
        cards = await page.evaluate("""() => {
            const els = document.querySelectorAll('[class*=\"album\"], [class*=\"card\"]');
            return [...els].slice(0, 30).map(e => ({
                tag: e.tagName,
                cls: e.className.slice(0, 80),
                text: e.textContent.trim().slice(0, 80),
                visible: e.offsetParent !== null,
                rect: { w: e.offsetWidth, h: e.offsetHeight },
            }));
        }""")
        print(f"\nAlbum/card elements ({len(cards)}):")
        for c in cards:
            if c['visible'] and c['rect']['w'] > 0:
                print(f"  <{c['tag']}> .{c['cls']}")
                print(f"    \"{c['text'][:60]}\" [{c['rect']['w']}x{c['rect']['h']}]")

        # Check current URL
        print(f"\nCurrent URL: {page.url}")

        # Check for any scan API calls
        scans = await page.evaluate("""() =>
            performance.getEntriesByType('resource')
                .filter(e => e.name.includes('/api/scan'))
                .map(e => ({ url: e.name.slice(0, 120), dur: Math.round(e.duration) }))
        """)
        print(f"\n/api/scan calls: {len(scans)}")
        for s in scans:
            print(f"  {s['dur']}ms — {s['url']}")

        await browser.close()

asyncio.run(main())
