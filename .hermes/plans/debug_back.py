"""Debug: what happens after breadcrumb click."""
import asyncio
from playwright.async_api import async_playwright

CHROMIUM_PATH = "/home/ubuntu/.cache/ms-playwright/chromium-1223/chrome-linux/chrome"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path=CHROMIUM_PATH)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        # Setup
        await page.goto("http://localhost:4173", wait_until="domcontentloaded")
        await page.evaluate("""() => {
            localStorage.setItem('gallery-root-path', '/home/ubuntu/gallery-repo');
            localStorage.setItem('gallery-albums-collapsed', 'false');
        }""")
        await page.reload(wait_until="networkidle")
        await page.wait_for_timeout(1000)
        enter = page.locator("button:has-text('ENTER GALLERY')").first
        if await enter.is_visible():
            await enter.click()
        await page.wait_for_timeout(3000)

        # Open test mika
        album = page.locator(".album-card").filter(has_text="test mika").first
        await album.wait_for(state="visible", timeout=15000)
        await album.click()
        await page.wait_for_timeout(3000)

        print(f"After open: URL={page.url}")
        
        # Try clicking first breadcrumb
        bc_items = page.locator(".breadcrumb-wrap a, .breadcrumb-wrap button, .breadcrumb-wrap span")
        count = await bc_items.count()
        print(f"Breadcrumb items: {count}")
        for i in range(count):
            text = await bc_items.nth(i).text_content()
            print(f"  [{i}] \"{text.strip() if text else ''}\"")
        
        if count > 0:
            await bc_items.nth(0).click()
            await page.wait_for_timeout(2000)
            print(f"\nAfter breadcrumb click: URL={page.url}")
            
            body = await page.evaluate("document.body.innerText.slice(0, 1500)")
            print(f"Body:\n{body}")
            
            cards = await page.evaluate("""() => {
                const cards = document.querySelectorAll('.album-card');
                return [...cards].map(c => ({
                    text: c.textContent.trim().slice(0, 80),
                    visible: c.offsetParent !== null,
                }));
            }""")
            print(f"\nAlbum cards ({len(cards)}):")
            for c in cards:
                print(f"  visible={c['visible']} \"{c['text'][:60]}\"")
        
        await browser.close()

asyncio.run(main())
