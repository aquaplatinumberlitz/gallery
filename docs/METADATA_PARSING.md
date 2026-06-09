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

`GET /api/thumbnail?path=...&max_size=800`

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

## Planned Basic EXIF Tab

Status: planning only, not yet implemented.

The lightbox metadata UI should gain a separate camera/photo EXIF tab only when the backend returns meaningful EXIF data. Images without meaningful EXIF keep the existing tab set:

- Without EXIF: Prompt, Params, Model
- With EXIF: Prompt, Params, Model, EXIF

The first version should be a compact readable summary, not a raw EXIF dump. Hide empty fields and use human-readable labels instead of raw EXIF key names.

Planned groups and fields:

| Group | Fields |
| --- | --- |
| Camera | Make, Model, Lens model |
| Exposure | ISO, Aperture, Shutter speed, Focal length, Flash |
| Image | Resolution, File size, Orientation, Color space |
| Date | Date taken, File modified |
| Location | GPS latitude/longitude |

Keep the first version to roughly 12-15 fields. Do not include a raw EXIF accordion, GPS map, or Copy EXIF action in v1.

Backend responsibility:

- Extract and normalize basic EXIF with Pillow/PIL.
- Do not add ExifTool for the first version.
- Reuse the existing metadata cache key strategy based on path, mtime, and file size.
- Set `hasData` to `true` only when there is meaningful EXIF beyond basic filename/size.
- Include only sections and fields with values.
- Keep the `/api/metadata` response backward-compatible.

Planned response shape:

```typescript
exif?: {
  hasData: boolean
  camera?: { make?: string; model?: string; lensModel?: string }
  exposure?: { iso?: number; aperture?: string; shutterSpeed?: string; focalLength?: string; flash?: string }
  image?: { width?: number; height?: number; orientation?: string; colorSpace?: string; fileSizeBytes?: number }
  date?: { taken?: string; digitized?: string; fileModified?: string }
  location?: { latitude?: number; longitude?: number }
}
```

Frontend responsibility:

- Render normalized EXIF from the backend; do not parse EXIF from image files in the browser.
- Add the EXIF tab only when `exif.hasData` is true.
- Match the existing lightbox metadata design language used by Prompt, Params, and Model.
- Hide empty, null, and undefined rows.
- Use single-column grouped rows on mobile.
- Use compact grouped rows with one or two columns on tablet and desktop.

Do not do:

- No frontend EXIF parser.
- No full-size image fetch for browser EXIF parsing.
- No raw EXIF dump in v1.
- No ExifTool before the Pillow prototype.
- No EXIF tab when there is no meaningful EXIF data.

Implementation phases:

1. Backend EXIF extraction with Pillow: add a helper/service for basic EXIF fields, normalize names, add `exif` to `/api/metadata`, reuse the existing cache key, and keep backward compatibility.
2. Tests: cover JPEG camera EXIF, GPS EXIF, PNG/AI images without EXIF, EXIF orientation, partial EXIF, and existing AI metadata parsing.
3. Frontend EXIF tab: conditionally add the tab, render grouped fields, hide empty rows, leave Prompt/Params/Model unchanged, and verify mobile/tablet/desktop layouts.
4. Optional future work: ExifTool prototype, GPS map, XMP/IPTC, Copy EXIF, and raw EXIF accordion.

ExifTool remains an optional future enhancement, not a current dependency. Future use cases include XMP/IPTC, MakerNotes, better lens/camera coverage, GPS edge cases, HEIC/RAW/video metadata, and XMP sidecars. The model to follow is an Immich-style normalized metadata panel: backend normalizes metadata, frontend renders a readable panel, and map/GPS enhancements stay future work.

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

See [DiffusionToolkit Metadata Parse Analysis](DIFFUSIONTOOLKIT_METADATA_PARSE_ANALYSIS.md)
for parser-specific lessons from DiffusionToolkit and the proposed backlog for
unifying gallery-repo's lightbox parser and SQLite indexing parser.
