"""Debug: navigate past landing page."""
import asyncio
from playwright.async_api import async_playwright

CHROMIUM_PATH = "/home/ubuntu/.cache/ms-playwright/chromium-1223/chrome-linux/chrome"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path=CHROMIUM_PATH)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        
        # Try with path parameter to bypass landing page
        await page.goto("http://localhost:4173/?path=/home/ubuntu/gallery-repo", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        
        await page.screenshot(path="/tmp/gallery_debug2.png", full_page=True)

        # Dump body text
        body = await page.evaluate("document.body.innerText.slice(0, 3000)")
        print(f"Body text:\n{body}")
        
        # Find clickable elements
        btns = await page.evaluate("""() => {
            const buttons = document.querySelectorAll('button, a, [role="button"], .album-card, [class*="album"]');
            return [...buttons].slice(0, 20).map(b => ({
                tag: b.tagName,
                cls: b.className.slice(0, 80),
                text: b.textContent.trim().slice(0, 100),
                visible: b.offsetParent !== null,
            }));
        }""")
        print("\nClickable elements:")
        for b in btns:
            if b['visible']:
                print(f"  <{b['tag']}> .{b['cls']} \"{b['text'][:60]}\"")
        
        await browser.close()

asyncio.run(main())
