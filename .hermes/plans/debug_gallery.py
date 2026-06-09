"""Debug: dump page structure."""
import asyncio
from playwright.async_api import async_playwright

CHROMIUM_PATH = "/home/ubuntu/.cache/ms-playwright/chromium-1223/chrome-linux/chrome"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path=CHROMIUM_PATH)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("http://localhost:4173", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        # Screenshot
        await page.screenshot(path="/tmp/gallery_debug.png", full_page=True)
        
        # Dump all album-like elements
        elements = await page.evaluate("""() => {
            const cards = document.querySelectorAll('.album-card, [class*="album"], .folder-item, .search-album-card');
            return [...cards].map(c => ({
                tag: c.tagName,
                cls: c.className.slice(0, 80),
                text: c.textContent.trim().slice(0, 200),
                visible: c.offsetParent !== null,
                w: c.offsetWidth,
                h: c.offsetHeight,
            }));
        }""")
        print("Album-like elements:")
        for c in elements[:20]:
            print(f"  <{c['tag']}> .{c['cls']}")
            print(f"    text: \"{c['text'][:100]}\"")
            print(f"    visible={c['visible']} {c['w']}x{c['h']}")

        # Page info
        title = await page.title()
        print(f"\nPage title: {title}")
        body = await page.evaluate("document.body.innerText.slice(0, 2000)")
        print(f"\nBody text:\n{body}")
        
        await browser.close()

asyncio.run(main())
