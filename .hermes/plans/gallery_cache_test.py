"""Gallery cache performance smoke test — Playwright (Python)."""

import asyncio
import json
import sys
from playwright.async_api import async_playwright

GALLERY_URL = "http://localhost:4173"
ROOT_PATH = "/home/ubuntu/gallery-repo"
ALBUM_NAME = "test mika"
CHROMIUM_PATH = "/home/ubuntu/.cache/ms-playwright/chromium-1223/chrome-linux/chrome"

passed = 0
failed = 0

def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

async def snapshot_gallery(page):
    return await page.evaluate("""() => {
        const imgs = [...document.querySelectorAll('img')]
            .filter(img => (img.currentSrc || img.src).includes('/api/thumbnail'));
        const skeletons = [...document.querySelectorAll("[class*='skeleton']")]
            .filter(el => {
                const r = el.getBoundingClientRect();
                return r.width > 1 && r.height > 1 && getComputedStyle(el).display !== 'none';
            });
        const refreshing = [...document.querySelectorAll('*')]
            .filter(el => (el.textContent || '').trim().toLowerCase().includes('refreshing'))
            .map(el => (el.textContent || '').trim().slice(0, 60));
        return {
            thumbnailLoaded: imgs.filter(i => i.complete && i.naturalWidth > 0).length + '/' + imgs.length,
            brokenImages: imgs.filter(i => i.complete && i.naturalWidth === 0).length,
            visibleSkeletons: skeletons.length,
            refreshing,
        };
    }""")

async def wait_for_thumbnails(page, expected=50, timeout=30):
    for _ in range(timeout * 2):
        snap = await snapshot_gallery(page)
        parts = snap["thumbnailLoaded"].split("/")
        loaded = int(parts[0]) if parts[0].isdigit() else 0
        if loaded >= expected and snap["brokenImages"] == 0:
            return snap
        await page.wait_for_timeout(500)
    return await snapshot_gallery(page)

async def setup_gallery(page):
    """Pre-configure localStorage, then enter gallery."""
    # Set localStorage BEFORE page loads (via early navigation)
    await page.goto(GALLERY_URL, wait_until="domcontentloaded")
    await page.evaluate("""(root) => {
        localStorage.setItem('gallery-root-path', root);
        localStorage.setItem('gallery-albums-collapsed', 'false');
    }""", ROOT_PATH)
    await page.reload(wait_until="networkidle")
    await page.wait_for_timeout(1000)

    # Click ENTER GALLERY to bypass landing page
    enter = page.locator("button:has-text('ENTER GALLERY')").first
    if await enter.is_visible():
        await enter.click()
    await page.wait_for_timeout(3000)

async def go_back_to_root(page):
    """Navigate back to gallery root via breadcrumb."""
    # Breadcrumb shows: home / ubuntu / gallery-repo / test mika
    # Click "gallery-repo" (second button from end)
    bc_btns = page.locator("[class*='breadcrumb'] button")
    count = await bc_btns.count()
    if count >= 2:
        # Click second-to-last (gallery-repo when at test mika)
        await bc_btns.nth(count - 2).click()
        await page.wait_for_timeout(1500)
        return True
    return False

async def main():
    global passed, failed
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path=CHROMIUM_PATH)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        try:
            print("\n=== Setup: enter gallery ===")
            await setup_gallery(page)
            print("Setup complete")

            # ── Scenario A: First load of test mika ──
            print("\n=== Scenario A: First open test mika ===")

            album_card = page.locator(".album-card").filter(has_text=ALBUM_NAME).first
            await album_card.wait_for(state="visible", timeout=15000)
            await album_card.click()
            await page.wait_for_timeout(500)

            snap_a = await wait_for_thumbnails(page, 50)
            check("A1. Thumbnails loaded on first open",
                  snap_a["thumbnailLoaded"].startswith("50/"), snap_a["thumbnailLoaded"])
            check("A2. No broken images on first open",
                  snap_a["brokenImages"] == 0, f'{snap_a["brokenImages"]} broken')
            check("A3. No skeleton on first open",
                  snap_a["visibleSkeletons"] == 0, f'{snap_a["visibleSkeletons"]} skeletons')

            entries_a = await page.evaluate("""() =>
                performance.getEntriesByType('resource')
                    .filter(e => e.name.includes('/api/scan'))
                    .map(e => ({ api: (e.name.match(/\\/api\\/[^?]+/)||[''])[0], durationMs: Math.round(e.duration) }))
            """)
            check("A4. /api/scan called on first open",
                  len(entries_a) > 0, f'count: {len(entries_a)} (expected > 0)')
            if entries_a:
                print(f"     first scan: {entries_a[0]['durationMs']}ms")

            # ── Navigate back to root ──
            print("\n=== Going back to root ===")
            await go_back_to_root(page)

            # ── Scenario B: Fresh revisit within 60s ──
            print("\n=== Scenario B: Fresh revisit (within 60s) ===")
            await page.evaluate("performance.clearResourceTimings()")

            album_card2 = page.locator(".album-card").filter(has_text=ALBUM_NAME).first
            await album_card2.wait_for(state="visible", timeout=15000)
            await album_card2.click()
            await page.wait_for_timeout(500)

            snap_b = await wait_for_thumbnails(page, 50)
            check("B1. Thumbnails loaded on revisit",
                  snap_b["thumbnailLoaded"].startswith("50/"), snap_b["thumbnailLoaded"])
            check("B2. No broken images on revisit",
                  snap_b["brokenImages"] == 0, f'{snap_b["brokenImages"]} broken')
            check("B3. No skeleton on revisit",
                  snap_b["visibleSkeletons"] == 0, f'{snap_b["visibleSkeletons"]} skeletons')

            entries_b = await page.evaluate("""() =>
                performance.getEntriesByType('resource')
                    .filter(e => e.name.includes('/api/scan'))
                    .map(e => ({ api: (e.name.match(/\\/api\\/[^?]+/)||[''])[0], durationMs: Math.round(e.duration) }))
            """)
            check("B4. No /api/scan network request (fresh cache)",
                  len(entries_b) == 0, f'count: {len(entries_b)} (expected 0)')

            snap_bui = await snapshot_gallery(page)
            check("B5. No Refreshing badge on fresh data",
                  len(snap_bui["refreshing"]) == 0, json.dumps(snap_bui["refreshing"]))

            # ── Scenario C: Thumbnail cache evidence ──
            print("\n=== Scenario C: Thumbnail cache ===")
            await page.evaluate("performance.clearResourceTimings()")
            await go_back_to_root(page)

            album_card3 = page.locator(".album-card").filter(has_text=ALBUM_NAME).first
            await album_card3.wait_for(state="visible", timeout=15000)
            await album_card3.click()
            await page.wait_for_timeout(500)
            await wait_for_thumbnails(page, 50)

            entries_c = await page.evaluate("""() =>
                performance.getEntriesByType('resource')
                    .filter(e => e.name.includes('/api/thumbnail'))
                    .map(e => {
                        const ts = e.transferSize;
                        const dbs = e.decodedBodySize;
                        let cacheGuess = 'unknown';
                        if (ts === 0 && dbs > 0) cacheGuess = 'cache/304';
                        else if (ts > 0) cacheGuess = 'network';
                        return {
                            api: (e.name.match(/\\/api\\/[^?]+/)||[''])[0],
                            query: e.name.includes('?') ? e.name.substring(e.name.indexOf('?')) : '',
                            durationMs: Math.round(e.duration),
                            transferSize: ts,
                            decodedBodySize: dbs,
                            cacheGuess,
                        };
                    })
            """)

            network_thumbs = [e for e in entries_c if e["cacheGuess"] == "network"]
            cache_thumbs = [e for e in entries_c if e["cacheGuess"] == "cache/304"]
            # Browser memory cache may not generate Performance entries at all
            # If entries_c is empty, thumbnails were likely served from memory cache
            all_cached_or_memory = len(entries_c) == 0 or len(cache_thumbs) > 0
            check("C1. Thumbnails served from cache/304 or memory cache",
                  all_cached_or_memory,
                  f'network: {len(network_thumbs)}, cache/304: {len(cache_thumbs)}, total entries: {len(entries_c)}')
            check("C2. Grid thumbnails use max_size=800",
                  all("max_size=800" in e["query"] for e in entries_c),
                  f'non-800: {len([e for e in entries_c if "max_size=800" not in e["query"]])}')

            total = passed + failed
            print("\n" + "=" * 50)
            print(f"\nResults: {passed} passed, {failed} failed out of {total} checks\n")
            if failed == 0:
                print("ALL CHECKS PASSED ✅\n")
            else:
                print("SOME CHECKS FAILED ❌\n")

        except Exception as err:
            print(f"\n❌ Test error: {err}")
            import traceback
            traceback.print_exc()
            failed += 1
        finally:
            await browser.close()
            sys.exit(1 if failed > 0 else 0)

if __name__ == "__main__":
    asyncio.run(main())
