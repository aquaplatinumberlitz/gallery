# Image Scan & Dimensions

## Overview

The backend extracts real image dimensions during directory scanning. These dimensions are used by the frontend to set the correct aspect ratio in PhotoSwipe and to display size information in metadata panels.

---

## The EXIF Orientation Bug (and Fix)

### Problem

Before the fix, `backend/main.py` read dimensions directly:

```python
with Image.open(entry.path) as img:
    img_width, img_height = img.size
```

This reads the **raw stored dimensions** without accounting for EXIF orientation. A portrait photo taken with a rotated camera would report landscape dimensions (e.g., 4032×3024 instead of 3024×4032), causing incorrect aspect ratios in the gallery.

### Fix

Apply `ImageOps.exif_transpose()` before reading dimensions:

```python
with Image.open(entry.path) as img:
    img = ImageOps.exif_transpose(img)  # rotate per EXIF orientation
    img_width, img_height = img.size    # now correct physical orientation
```

This is used in two places:

1. **Directory scan** (`backend/main.py` line 252) — extracts dimensions for `FileNode` objects returned to the frontend
2. **Thumbnail rendering** (`backend/main.py` line 404) — auto-rotates before generating WebP thumbnails

The image size check (`_check_image_limits()`) deliberately does NOT transpose — it reads raw `img.size` to check actual file dimensions before applying orientation transforms.

### Why This Matters

- `buildPhotoSwipeItem()` in `frontend/src/utils/lightbox.ts` uses `item.width` and `item.height` to set PhotoSwipe's `width` and `height` properties
- If these are wrong, PhotoSwipe renders the image with the wrong aspect ratio (stretched or squished)
- The fallback is 1200×1200 (neutral square), which is acceptable for missing data but wrong for incorrect data

### Old Scan Data

After deploying the backend fix, previously scanned folders still have incorrect dimensions cached in the frontend store. To fix:
- Clear the server's thumbnail cache (restart backend)
- Re-scan the folder in the gallery (navigate away and back, or reload)

---

## Scan Pipeline

```
GET /api/scan?path=...&image_limit=200&image_cursor=0
```

1. `os.scandir()` walks the directory
2. Folders: sorted naturally, cover images via `first_images_in_dir()` (3 newest)
3. Images: sorted by `mtime`, paginated via cursor
4. For each image file:
   - Check file extension (is_image)
   - Read `mtime` via `stat()`
   - Open with PIL, `exif_transpose()`, read `img.size`
   - Create `FileNode` with `width` and `height` fields
5. Return `ScanResponse`: `{ folders, images, next_cursor, total_images }`

## Thumbnail Pipeline

```
GET /api/thumbnail?path=...&max_size=600
```

1. `_check_image_limits()` — guard: 75MB file size, 100MP pixel dimensions
2. Cache lookup: 1GB LRU cache, key = `(path, mtime, size, max_size, quality)`
3. `_render_thumbnail_impl()`:
   - Open with PIL, `exif_transpose()` for orientation
   - RGBA → RGB (white background for transparency)
   - Resize with `LANCZOS` to `max_size`
   - Encode as WebP (quality 75, method 6)
4. Cache miss → render → store in cache
5. Return with `Cache-Control: public, max-age=31536000, immutable`

## Metadata Extraction

```
GET /api/metadata?path=...
```

1. Read PNG chunks: `parameters` (A1111/NovelAI/EasyDiffusion), `prompt`, `workflow` (ComfyUI)
2. Read EXIF `UserComment`
3. Priority: SwarmUI JSON > ComfyUI JSON > A1111 text > NovelAI > EasyDiffusion > `.txt` sidecar
4. Cache: 100MB LRU, key = `(path, mtime, size)`
5. Returns: `MetadataResponse` with `width`, `height`, `params`, `source`, etc.

---

## Frontend Consumption

### `buildPhotoSwipeItem()` (`frontend/src/utils/lightbox.ts`)

```typescript
const width  = typeof item.width  === "number" && item.width  > 0 ? item.width  : 1200;
const height = typeof item.height === "number" && item.height > 0 ? item.height : 1200;
```

- Guards against `null`, `undefined`, `0`, and `NaN`
- 1200×1200 is a neutral square fallback for images without dimension data
- URL: thumbnail URL (with size) for tablet/mobile, full-res for desktop

### `lightboxStore.loadMetadata()`

- Fetches metadata from `/api/metadata` for the current image
- Updates `lightbox.width` and `lightbox.height` from the metadata response
- Used by `Lightbox.vue` for the `sizeText` display

---

## Do / Don't

- **Do** always `exif_transpose()` before reading `img.size` for orientation-dependent uses
- **Don't** transpose for file validation checks (dimension guard, file size guard)
- **Do** re-scan folders after upgrading the backend if previous scans had orientation errors
- **Do** handle `width`/`height` being `null` in frontend — not all images have readable dimensions
- **Don't** assume `item.width` and `item.height` are always available
