"""Debug: try sidebar to navigate back."""
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

        print(f"Current URL: {page.url}")
        
        # Try all breadcrumb items with their onClick/role
        bc_items = page.locator("[class*='breadcrumb'] button, [class*='breadcrumb'] [role='button'], [class*='breadcrumb'] a")
        count = await bc_items.count()
        print(f"\nBreadcrumb clickable items: {count}")
        for i in range(count):
            tag = await bc_items.nth(i).evaluate("el => el.tagName")
            text = await bc_items.nth(i).text_content()
            print(f"  [{i}] <{tag}> \"{text.strip() if text else ''}\"")
        
        print(f"\n--- Trying sidebar root ---")
        # Find sidebar tree items
        sidebar = page.locator("[class*='sidebar'] [class*='tree'], [class*='sidebar'] a, [class*='sidebar'] button")
        scount = await sidebar.count()
        print(f"Sidebar items: {scount}")
        for i in range(min(scount, 15)):
            text = await sidebar.nth(i).text_content()
            visible = await sidebar.nth(i).is_visible()
            tag = await sidebar.nth(i).evaluate("el => el.tagName")
            if visible:
                print(f"  [{i}] <{tag}> \"{text.strip()[:60] if text else ''}\"")
        
        # Try clicking "gallery-repo" in sidebar
        gallery_repo = page.locator("[class*='sidebar']").filter(has_text="gallery-repo").first
        if await gallery_repo.is_visible():
            print("\nClicking gallery-repo sidebar item...")
            await gallery_repo.click()
            await page.wait_for_timeout(2000)
            body = await page.evaluate("document.body.innerText.slice(0, 1000)")
            print(f"After click:\n{body}")
            
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
