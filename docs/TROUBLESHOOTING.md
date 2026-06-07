# Troubleshooting

Last reviewed: 2026-06-07

## Quick Checks

| Symptom | Check |
|---------|-------|
| Grid shows no photos | `.scroller-container` and parent flex chain must keep `flex: 1` and `min-height: 0` |
| Infinite scroll does not load | `GalleryGrid.vue` sentinel, IntersectionObserver, and `rootMargin: "400px"` |
| API calls hit the wrong server | `VITE_API_URL` or Vite proxy configuration |
| Backend returns 403 | `GALLERY_ROOT` and resolved path safety |
| CORS failure | `FRONTEND_ORIGIN`, `FRONTEND_PORT`, and backend CORS origins |
| Lightbox black screen | PhotoSwipe container mount, item URLs from `buildPhotoSwipeItem()`, image dimensions |
| Desktop image overlaps sidebar | `DESKTOP_METADATA_WIDTH`, `paddingFn`, CSS sidebar width, counter and arrow offsets |
| Metadata panel empty | PNG chunks, EXIF `UserComment`, sidecar `.txt`, and parser source detection |
| Mobile bars do not hide | `useScrollVisibility.ts` scroll element detection and class names |
| Mobile sheet fights content scroll | Confirm VSBS is handling drag/snap/scroll and old `.sheet-panel` drag code has not been restored |
| Tablet drawer does not close | `TabletLayout.vue` Escape/backdrop handling and `closeSidebar()` injection |
| Theme flashes | Inline theme script in `frontend/index.html` and `data-theme` application |

## iOS and Safari Gotchas

| Issue | Workaround |
|-------|------------|
| Safe areas around notch/home indicator | Use `env(safe-area-inset-*)` in fixed bars and lightbox controls |
| `backdrop-filter` animation delay | Avoid expensive filters on animated tablet drawer elements |
| `color-mix()` support variance | Provide `rgba()` fallback before guarded `color-mix()` |
| Clipboard on HTTP origin | Use `document.execCommand('copy')` fallback |
| Private Browsing localStorage errors | Wrap localStorage access in try/catch |
| Elastic overscroll conflicts | Use `overscroll-behavior: contain` where appropriate |
| Input focus zoom/accessory bar | Keep viewport/input behavior tested on real iOS devices |
| Sticky hover states | Reset hover styles under touch media queries |

## RecycleScroller Height

RecycleScroller needs a fixed-height scroll container. The critical rule is that each flex parent in the chain allows shrinking:

```scss
.scroller-container {
  flex: 1;
  min-height: 0;
}

.scroller {
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
}
```

If a parent loses `min-height: 0`, the scroller can compute zero rows or no scroll overflow. Inspect `.scroller` computed height first, then walk up through layout parents.

## Desktop Lightbox Split Layout

The desktop lightbox has two independent but related protections:

- PhotoSwipe `paddingFn` reserves the metadata panel width for the image viewport.
- CSS offsets position the visible counter and next arrow relative to `--lightbox-sidebar-width`.

If the image, counter, or arrow drifts, check all of these together:

- `DESKTOP_METADATA_WIDTH`
- `.lightbox-right` width
- `--lightbox-sidebar-width`
- `desktopPaddingFn`
- `.desktop-lightbox-counter`
- `.pswp__button--arrow--next`

## Mobile Sheet Gestures

Expected behavior:

- See [Third-Party Libraries](THIRD_PARTY_LIBRARIES.md) for VSBS and PhotoSwipe integration rationale, customizations, and pitfalls.
- `@douxcode/vue-spring-bottom-sheet` handles drag, snap, swipe-close, and scroll.
- Drag down closes according to VSBS `can-swipe-close` and `swipe-close-threshold` behavior.
- Content inside the VSBS scroll area and `.sheet-content` scrolls normally.
- Chevron expand/collapse does not depend on drag.
- Chevron collapse resets expanded prompt text.
- `blocking=false` prevents VSBS focus trapping from conflicting with PhotoSwipe.

Do not restore the old `.sheet-panel`, `.sheet-handle-wrapper`, pointer capture, or threshold-based drag implementation.

## Scroll Visibility

`useScrollVisibility.ts` may attach to an injected scroll container or fall back to polling DOM selectors such as `.vue-recycle-scroller`, `.scroller`, and `.folders-only-container`.

If class names change, mobile bars may stop responding or polling may continue indefinitely. Update the selector list whenever the scroll container class names change.

The near-bottom guard reduces iOS rubber-band flicker. Tune it carefully because too high a threshold keeps bars visible too often, while too low a threshold can reintroduce rapid show/hide loops.

## Stale Notes Removed

Older investigation notes described mobile grid density as unresponsive and lacking device-specific clamps. That is stale: current behavior uses `GRID_COLUMN_MAP` with desktop, tablet, and mobile mappings. If mobile thumbnails are too small, debug the active `deviceCategory`, slider level, and loaded `gallery-grid-size` value rather than assuming there is no responsive mapping.

Older docs also claimed path safety simply allowed all paths. Current behavior uses a path safety check bounded by `GALLERY_ROOT`; the default root remains broad for local use.
