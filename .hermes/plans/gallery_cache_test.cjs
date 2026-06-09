// Gallery cache performance smoke test
// Tests: TanStack Query fresh cache revisit + diskcache + 304

const { chromium } = require('playwright');

const GALLERY_URL = 'http://localhost:4173';
const ALBUM_NAME = 'test mika';
const TIMEOUT = 30000;
const SCAN_KEY_PATTERN = /\/api\/scan/;
const THUMB_KEY_PATTERN = /\/api\/thumbnail/;

function classifyEntry(entry) {
  const url = new URL(entry.name);
  const transferSize = entry.transferSize;
  const decodedBodySize = entry.decodedBodySize;
  const cacheGuess =
    transferSize === 0 && decodedBodySize > 0
      ? 'cache/304'
      : transferSize > 0
        ? 'network'
        : 'unknown';
  return {
    api: url.pathname,
    query: url.search,
    durationMs: Math.round(entry.duration),
    transferSize,
    decodedBodySize,
    cacheGuess,
  };
}

function snapshotGallery(page) {
  return page.evaluate(() => {
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
      thumbnailLoaded: `${imgs.filter(i => i.complete && i.naturalWidth > 0).length}/${imgs.length}`,
      brokenImages: imgs.filter(i => i.complete && i.naturalWidth === 0).length,
      visibleSkeletons: skeletons.length,
      refreshing,
    };
  });
}

async function waitForThumbnails(page, expected = 50, timeout = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const snap = await snapshotGallery(page);
    const [loaded] = snap.thumbnailLoaded.split('/').map(Number);
    if (loaded >= expected && snap.brokenImages === 0) return snap;
    await page.waitForTimeout(500);
  }
  return await snapshotGallery(page);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  let passed = 0;
  let failed = 0;
  const results = [];

  function check(name, ok, detail = '') {
    if (ok) { passed++; console.log(`  ✅ ${name}`); }
    else { failed++; console.log(`  ❌ ${name}${detail ? ' — ' + detail : ''}`); }
    results.push({ name, ok, detail });
  }

  try {
    // ── Navigate to gallery root ──
    console.log('\n=== Loading gallery ===');
    await page.goto(GALLERY_URL, { waitUntil: 'networkidle', timeout: TIMEOUT });
    await page.waitForTimeout(1000);

    // ── Scenario A: First load of test mika ──
    console.log('\n=== Scenario A: First open test mika ===');

    // Find and click the album card
    const albumCard = page.locator('.album-card').filter({ hasText: ALBUM_NAME }).first();
    await albumCard.waitFor({ state: 'visible', timeout: TIMEOUT });
    await albumCard.click();
    await page.waitForTimeout(500);

    // Wait for thumbnails to load
    const snapA = await waitForThumbnails(page, 50);
    check('A1. Thumbnails loaded on first open', snapA.thumbnailLoaded.startsWith('50/'), snapA.thumbnailLoaded);
    check('A2. No broken images on first open', snapA.brokenImages === 0, `${snapA.brokenImages} broken`);
    check('A3. No skeleton on first open', snapA.visibleSkeletons === 0, `${snapA.visibleSkeletons} skeletons`);

    // Collect first-load scan entries
    const entriesA = await page.evaluate(() =>
      performance.getEntriesByType('resource')
        .filter(e => e.name.includes('/api/scan'))
        .map(classifyEntry)
    );
    check('A4. /api/scan called on first open', entriesA.length > 0, `count: ${entriesA.length}`);
    if (entriesA.length > 0) {
      console.log(`     first scan: ${entriesA[0].durationMs}ms`);
    }

    // ── Scenario B: Fresh revisit within 60s ──
    console.log('\n=== Scenario B: Fresh revisit (within 60s) ===');

    // Navigate back to root
    const backBtn = page.locator('button').filter({ hasText: /^$/ }).or(page.locator('[aria-label="Back"]')).first();
    // Use breadcrumb click or go back via history
    // Click on the breadcrumb root to go back
    const breadcrumbRoot = page.locator('.breadcrumb-wrap a, .breadcrumb-wrap button, .breadcrumb-wrap [role="button"]').first();
    if (await breadcrumbRoot.isVisible()) {
      await breadcrumbRoot.click();
    } else {
      // Use keyboard shortcut or navigate
      await page.goBack();
    }
    await page.waitForTimeout(1000);

    // Clear performance timings BEFORE reopening
    await page.evaluate(() => performance.clearResourceTimings());

    // Reopen test mika
    const albumCard2 = page.locator('.album-card').filter({ hasText: ALBUM_NAME }).first();
    await albumCard2.waitFor({ state: 'visible', timeout: TIMEOUT });
    await albumCard2.click();
    await page.waitForTimeout(500);

    const snapB = await waitForThumbnails(page, 50);
    check('B1. Thumbnails loaded on revisit', snapB.thumbnailLoaded.startsWith('50/'), snapB.thumbnailLoaded);
    check('B2. No broken images on revisit', snapB.brokenImages === 0, `${snapB.brokenImages} broken`);
    check('B3. No skeleton on revisit', snapB.visibleSkeletons === 0, `${snapB.visibleSkeletons} skeletons`);

    // Check if any /api/scan was called during revisit
    const entriesB = await page.evaluate(() =>
      performance.getEntriesByType('resource')
        .filter(e => e.name.includes('/api/scan'))
        .map(classifyEntry)
    );
    check('B4. No /api/scan network request (fresh cache)', entriesB.length === 0, `count: ${entriesB.length}`);

    // Check for Refreshing badge
    const snapBui = await snapshotGallery(page);
    check('B5. No Refreshing badge on fresh data', snapBui.refreshing.length === 0, `${JSON.stringify(snapBui.refreshing)}`);

    // ── Scenario C: Thumbnail cache evidence ──
    console.log('\n=== Scenario C: Thumbnail cache ===');

    // Clear timings and navigate away and back
    await page.evaluate(() => performance.clearResourceTimings());
    // Go back
    const backBtn2 = page.locator('.breadcrumb-wrap a, .breadcrumb-wrap button, .breadcrumb-wrap [role="button"]').first();
    if (await backBtn2.isVisible()) {
      await backBtn2.click();
    } else {
      await page.goBack();
    }
    await page.waitForTimeout(1000);

    // Reopen again
    const albumCard3 = page.locator('.album-card').filter({ hasText: ALBUM_NAME }).first();
    await albumCard3.waitFor({ state: 'visible', timeout: TIMEOUT });
    await albumCard3.click();
    await page.waitForTimeout(500);
    await waitForThumbnails(page, 50);

    const entriesC = await page.evaluate(() =>
      performance.getEntriesByType('resource')
        .filter(e => e.name.includes('/api/thumbnail'))
        .map(classifyEntry)
    );

    const networkThumbs = entriesC.filter(e => e.cacheGuess === 'network');
    const cacheThumbs = entriesC.filter(e => e.cacheGuess === 'cache/304');
    check('C1. Some thumbnails served from cache/304', cacheThumbs.length > 0,
      `network: ${networkThumbs.length}, cache/304: ${cacheThumbs.length}`);
    check('C2. Grid thumbnails use max_size=800',
      entriesC.every(e => e.query.includes('max_size=800')),
      `non-800 queries: ${entriesC.filter(e => !e.query.includes('max_size=800')).length}`);

    // Summary
    console.log('\n' + '='.repeat(50));
    console.log(`\nResults: ${passed} passed, ${failed} failed out of ${passed + failed} checks\n`);
    if (failed === 0) {
      console.log('ALL CHECKS PASSED ✅\n');
    } else {
      console.log('SOME CHECKS FAILED ❌\n');
    }

  } catch (err) {
    console.error('\n❌ Test error:', err.message);
    failed++;
  } finally {
    await browser.close();
    process.exit(failed > 0 ? 1 : 0);
  }
})();
