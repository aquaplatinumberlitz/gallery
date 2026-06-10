# Lightbox Image Loading Policy

The gallery uses an Immich-inspired derivative-first image loading model. The goal is fast perceived viewing while preserving access to the untouched original when the user asks for it.

## Endpoint Roles

| Endpoint | Role | Default derivative |
|----------|------|--------------------|
| `/api/thumbnail` | Grid/card image and lightbox placeholder | WebP, quality 78, max long edge 512 |
| `/api/preview` | Normal lightbox viewer image | WebP, quality 86, max long edge 1440 |
| `/api/image` | Original file | No resize, no conversion |

`512` and `1440` are max long-edge targets. Derivatives preserve aspect ratio, never crop, and never upscale images that are smaller than the target.

Examples:

```text
3000x2000 + 512  -> 512x341
2000x3000 + 512  -> 341x512
3000x3000 + 512  -> 512x512
3000x2000 + 1440 -> 1440x960
2000x3000 + 1440 -> 960x1440
1000x700 + 1440  -> 1000x700
```

## Viewer Policy

Normal browsing follows this sequence:

```text
Gallery grid             -> thumbnail 512
Lightbox normal view     -> thumbnail 512 placeholder, then preview 1440
Original                 -> on demand only
Next/previous preload    -> thumbnail 512 + preview 1440 for +/-1 only
```

Normal lightbox open must not request `/api/image`. PhotoSwipe item data uses:

```text
src         = /api/preview
msrc        = /api/thumbnail
originalSrc = /api/image
```

## Original Triggers

The original is requested only for the current slide when:

- zoom exceeds the configured threshold;
- the user enables the "Always load original" preference;
- the user uses an explicit fullscreen/original action;
- the current asset is known animated and should not be flattened by preview generation;
- preview loading fails and the viewer falls back to original;
- a future download/open-original action calls `originalSrc`.

GIF and APNG are treated as known animated assets. Animated WebP needs container-level detection; until that exists, static WebP behavior remains preview-first.

## Cache Separation

Thumbnail and preview derivatives share the same Pillow/cache implementation but use role-separated keys:

```text
thumbnail:v1:{path}:{mtime}:{size}:edge=512:fmt=webp:q=78
preview:v1:{path}:{mtime}:{size}:edge=1440:fmt=webp:q=86
```

The cache key includes derivative kind, cache version, file identity, max long edge, format, and quality. Thumbnail and preview entries cannot collide even when their dimensions match.

## Why No Original Neighbor Preload

Original files can be very large in local AI/art folders. Preloading originals for adjacent slides increases disk, CPU, memory, and network pressure for images the user may never inspect. Preloading thumbnail plus preview for +/-1 keeps navigation smooth while preserving original quality as an explicit current-slide action.

## Perf Metrics

Lightbox metrics distinguish perceived display from original load:

```text
lightboxVisible
lightboxPreviewLoaded
lightboxOriginalLoadedOnZoom
transitionPreviewLoaded
```

The old "Lightbox loaded" wording should be read as historical original-loaded timing only in older reports.
