# Fix 3 issues in lightbox.perf.spec.ts

## Issue 1: `usedFullImageEndpoint` validates wrongly

**File:** `frontend/tests/perf/lightbox.perf.spec.ts` (line ~69)

Current code:
```ts
const usedImageEndpoint = (firstImageSample?.pathname === "/api/image" || firstThumbSample?.pathname === "/api/thumbnail");
```

This is **wrong** — it passes if EITHER `/api/image` OR `/api/thumbnail` was used. The spec says the final displayed image MUST load from `/api/image`, not `/api/thumbnail`.

**Fix:**
- Change to strictly require `/api/image`:
```ts
const usedFullImageEndpoint = firstImageSample?.pathname === "/api/image";
```
- Also, read the actual displayed image's `src` attribute from the DOM and verify it starts with `/api/image`:
```ts
const actualSrc = await lightboxImg.getAttribute("src");
const srcIsFullImage = actualSrc?.startsWith("/api/image") ?? false;
```
- Assert both `usedFullImageEndpoint` AND `srcIsFullImage` are true.
- If the app uses a high-quality thumbnail as intermediate preview then loads `/api/image` as final, check the **final** loaded src, not just the first sample.
- Rename variable to `usedFullImageEndpoint` everywhere for clarity.

## Issue 2: Report viewport + display size with warning if image too small

**File:** `frontend/tests/perf/lightbox.perf.spec.ts` (after display dimension measurement)

After measuring `displayW`/`displayH`, also capture viewport dimensions:
```ts
const viewport = page.viewportSize();
```

Add to the JSON report:
```json
{
  "open": {
    ...
    "displayWidth": ...,
    "displayHeight": ...,
    "viewportWidth": viewport?.width ?? 0,
    "viewportHeight": viewport?.height ?? 0
  }
}
```

After the report is logged, add a **soft warning** (not a hard assertion) if the displayed image is smaller than 50% of viewport in both dimensions:
```ts
if (dims.displayW < (viewport?.width ?? 1920) * 0.5 && dims.displayH < (viewport?.height ?? 1080) * 0.5) {
  console.warn(`WARNING: Lightbox image (${Math.round(dims.displayW)}×${Math.round(dims.displayH)}px) is smaller than 50% of viewport (${viewport?.width}×${viewport?.height}px). Image may be displaying a thumbnail instead of full-res.`);
}
```

Apply the same viewport reporting + warning to the **transition test** (test 2) too.

## Issue 3: Use root path env var, not hardcoded path

**File:** `frontend/tests/perf/lightbox.perf.spec.ts` (line ~9-11)

Current code:
```ts
await page.addInitScript(() => {
  localStorage.setItem("gallery-root-path", "/home/ubuntu/gallery-repo");
});
```

**Fix:**
Use the `GALLERY_PERF_ALBUM_PATH` env var and derive root path from it (assume the repo root is parent of the album path, or introduce a new env var `GALLERY_ROOT_PATH` with fallback):
```ts
const rootPath = process.env.GALLERY_ROOT_PATH ?? (
  albumPath ? albumPath.substring(0, albumPath.lastIndexOf('/')) : "/home/ubuntu/gallery-repo"
);

// In addInitScript:
await page.addInitScript((rootForInit) => {
  localStorage.setItem("gallery-root-path", rootForInit);
}, rootPath);
```

This way when running against VPS with `GALLERY_PERF_ALBUM_PATH=/home/ubuntu/gallery-repo/test mika`, the root is derived automatically.

## Files to change
1. `frontend/tests/perf/lightbox.perf.spec.ts` — all 3 issues
2. `docs/PERFORMANCE_TESTING.md` — update budget defaults in the doc to match the test file's actual defaults

## Do NOT change
- Backend code
- PhotoSwipe architecture
- album-open.perf.spec.ts
- perf-utils.ts
- Any CSS or layout

## Verification
```bash
cd /home/ubuntu/gallery-repo/frontend
npm run build
npm run perf:lightbox
```
