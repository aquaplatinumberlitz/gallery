"""Debug: find album toggle."""
import asyncio
from playwright.async_api import async_playwright

CHROMIUM_PATH = "/home/ubuntu/.cache/ms-playwright/chromium-1223/chrome-linux/chrome"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path=CHROMIUM_PATH)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        
        # Set localStorage first
        await page.goto("http://localhost:4173", wait_until="domcontentloaded")
        await page.evaluate("localStorage.setItem('gallery-root-path', '/home/ubuntu/gallery-repo')")
        await page.evaluate("localStorage.setItem('gallery-albums-collapsed', 'false')")
        await page.reload(wait_until="networkidle")
        await page.wait_for_timeout(1000)
        
        # Click ENTER
        enter = page.locator("button:has-text('ENTER GALLERY')").first
        if await enter.is_visible():
            await enter.click()
        await page.wait_for_timeout(3000)
        
        body = await page.evaluate("document.body.innerText.slice(0, 2000)")
        print(f"Body:\n{body}")
        
        # Check for album cards now
        cards = await page.evaluate("""() => {
            const cards = document.querySelectorAll('.album-card');
            return [...cards].map(c => ({
                text: c.textContent.trim().slice(0, 100),
                visible: c.offsetParent !== null,
                rect: { w: c.offsetWidth, h: c.offsetHeight },
            }));
        }""")
        print(f"\nAlbum cards ({len(cards)}):")
        for c in cards:
            print(f"  visible={c['visible']} {c['rect']['w']}x{c['rect']['h']} \"{c['text'][:60]}\"")
        
        await browser.close()

asyncio.run(main())
