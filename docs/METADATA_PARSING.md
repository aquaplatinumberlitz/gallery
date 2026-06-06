# Metadata Parsing

Last reviewed: 2026-06-06

## Scan Pipeline

`GET /api/scan?path=...&image_limit=200&image_cursor=0`

1. Walk the directory with `os.scandir()`.
2. Split folders and image files.
3. Sort folders naturally.
4. Build folder cover images from the newest images in each folder.
5. Sort images by modified time and paginate with `image_cursor`.
6. Read dimensions for each image when possible.
7. Return folders, images, `next_cursor`, and `total_images`.

Returned image dimensions are consumed by PhotoSwipe to preserve aspect ratio.

## EXIF Orientation

For orientation-dependent dimensions and thumbnails, the backend applies `ImageOps.exif_transpose()` before reading or rendering the image.

Use it when:

- Reading dimensions for scanned `FileNode` objects.
- Rendering thumbnails.

Do not use it for file validation limits. The validation guard should check the raw stored image dimensions before transforms.

Why this matters:

- Portrait images may be stored as landscape pixels plus EXIF orientation.
- PhotoSwipe uses width and height to compute aspect ratio.
- Wrong dimensions cause stretched, squashed, or incorrectly sized lightbox images.

After a backend dimension fix, re-scan affected folders so the frontend receives updated width/height values.

## Thumbnail Pipeline

`GET /api/thumbnail?path=...&max_size=600`

1. Validate file size and pixel count.
2. Build cache key from path, mtime, file size, max size, and quality.
3. Open with Pillow.
4. Apply EXIF transpose.
5. Convert RGBA/transparency to RGB with a white background.
6. Resize with LANCZOS.
7. Encode WebP at quality 75, method 6.
8. Store in the 1GB LRU cache.
9. Return with long immutable cache headers.

## Metadata Pipeline

`GET /api/metadata?path=...`

The backend reads:

- PNG text chunks such as `parameters`, `prompt`, and `workflow`
- EXIF fields including `UserComment`
- Sidecar `.txt` files as fallback

Detection priority:

1. SwarmUI JSON
2. ComfyUI JSON
3. A1111 parameter text
4. NovelAI
5. EasyDiffusion
6. `.txt` sidecar

The metadata response includes parsed parameters, source, dimensions, and related generation fields when available.

## Frontend Consumption

`frontend/src/utils/lightbox.ts` builds PhotoSwipe items from scanned image data:

```typescript
const width = valid item.width ? item.width : 1200;
const height = valid item.height ? item.height : 1200;
```

The 1200x1200 fallback is intentionally neutral for missing or unreadable dimensions, but it should not hide parser or scan regressions.

`lightboxStore.loadMetadata()` fetches `/api/metadata` for the current image and updates metadata plus size display fields.

## Parser Maintenance

- Keep parser source detection order explicit.
- Preserve sidecar fallback behavior.
- Keep cache keys tied to mtime and size so edited files invalidate naturally.
- Treat unknown or malformed metadata as a recoverable parse failure, not a gallery-breaking error.
- Test with representative PNGs from every supported generator when changing parser logic.
