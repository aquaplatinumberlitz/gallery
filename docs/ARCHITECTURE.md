# Architecture

Last reviewed: 2026-06-08

## Overview

AI Art Gallery is a local-first image browser with a FastAPI backend and a Vue 3 frontend.

- Backend: scans directories, serves originals, renders cached WebP thumbnails, parses generation metadata, and indexes prompt/metadata text in SQLite FTS5.
- Frontend: manages gallery state with Pinia, renders responsive layouts, virtualizes large grids, and opens images in a PhotoSwipe 5 lightbox.
- Startup: `start.py` creates the Python virtualenv, installs Python and Node dependencies, and starts both servers.

Major external library integrations are documented in [Third-Party Libraries](THIRD_PARTY_LIBRARIES.md).

## Backend

All API routes live in `backend/main.py`.

| Endpoint | Purpose |
|----------|---------|
| `GET /api/scan` | Return folders and paginated image files for a directory |
| `GET /api/image` | Serve an original image file |
| `GET /api/thumbnail` | Serve a cached WebP thumbnail |
| `GET /api/metadata` | Parse AI generation metadata |
| `GET /api/search-metadata` | Search indexed AI prompt/metadata fields with SQLite FTS5 |
| `POST /api/open-folder` | Open a folder in the OS file explorer when enabled |
| `GET /api/health` | Return service health |
| `GET /api/landing-pages` | List intro page HTML files |
| `GET /` and `GET /{path:path}` | Serve the built SPA in production mode |

Important backend behavior:

- `GALLERY_ROOT` bounds path safety. The default root is `/`, which is permissive for local use but still routes through path checks.
- `GALLERY_OPEN_FOLDER=false` disables OS folder opening by default.
- Thumbnail cache keys include path, mtime, size, max size, and quality.
- Metadata cache keys include path, mtime, and size.
- Metadata search cache lives at `backend/.cache/gallery_metadata.db`. It stores normalized image metadata keyed by path, mtime, and size, with two FTS5 indexes: `unicode61` for normal prompt/model/filename terms and `trigram` for Japanese/CJK substring matching.
- `/api/scan` opportunistically indexes image metadata for the scanned folder in the background. Search covers indexed images only; unchanged files are not reparsed.
- Production mode is enabled with `PRODUCTION=1`, serving `frontend/dist/`.

## Frontend

Key paths:

| Path | Role |
|------|------|
| `frontend/src/App.vue` | Root orchestrator, layout dispatch, lightbox/modal/toast mounting |
| `frontend/src/main.ts` | Vue entry point, Pinia setup, global styles, debug utilities |
| `frontend/src/layouts/` | Desktop, tablet, and mobile layout shells |
| `frontend/src/components/` | Gallery, cards, headers, sidebars, lightbox wrappers, metadata panels |
| `frontend/src/composables/` | Device detection, grid density, PhotoSwipe lifecycle, scroll visibility, haptics |
| `frontend/src/stores/` | Pinia stores for gallery, lightbox, and toasts |
| `frontend/src/styles/` | Global SCSS, tokens, breakpoint mixins, lightbox styles |
| `frontend/src/services/api.ts` | Axios client and API error handling |

## State Stores

| Store | Responsibilities |
|-------|------------------|
| `gallery.ts` | Root/current path, folder tree, images, pagination, navigation history, search, sort, loaded state |
| `lightbox.ts` | Open image, current index, gallery item list, metadata, navigation, neighbor preloading |
| `toast.ts` | Toast queue, type helpers, auto-dismiss |

## Data Flow

### Folder Load

```text
Sidebar or album click
→ galleryStore.selectFolder(path)
→ galleryStore.scanFolder(path)
→ api.scanDirectory(path, { imageLimit: 200, imageCursor: 0 })
→ GET /api/scan
→ store updates folders, images, next cursor, total images
→ GalleryGrid renders albums and image rows
```

### Infinite Scroll

```text
IntersectionObserver sees loadMoreSentinel
→ galleryStore.loadMoreImages()
→ GET /api/scan with image_cursor
→ append returned images
→ grid rows recompute
```

### Search and Sort

```text
Header or toolbar emits search/sort change
→ gallery store updates query or sort state
→ GalleryGrid computed folder/image lists apply Fuse.js search over loaded frontend items
→ existing GalleryGrid sort applies by name/date
→ RecycleScroller or native mobile grid rerenders
```

Search has two explicit modes:

- Current view: client-side Fuse.js search over currently loaded folders/images in `galleryFolders` and `galleryImages`. This remains filename/folder search only and preserves current pagination, sort, folder navigation, and virtual/native scroll behavior.
- Metadata: backend-driven prompt/metadata search through `GET /api/search-metadata?q=...`. The backend extracts metadata with Pillow, normalizes fields, stores them in SQLite, and searches with SQLite FTS5. Japanese/CJK queries use trigram FTS when possible, with parameterized `LIKE` fallback for short queries or no-result fallback.

### Open Image

```text
PhotoCard click
→ lightboxStore.open({ path, name }, visibleImages)
→ preload neighboring images
→ GET /api/metadata
→ Lightbox.vue dispatches to the active device wrapper and metadata panel
```

### Lightbox Navigation

```text
PhotoSwipe change, arrow key, or toolbar action
→ wrapper emits indexChange or store navigation action
→ lightbox store updates current item
→ metadata reloads for the new path
→ PhotoSwipe index watcher syncs only when indices differ
```

## Lightbox Design

`Lightbox.vue` is the device-dispatch orchestrator:

```text
Desktop/Wide → PhotoSwipeViewer.vue + LightboxDesktopPanel.vue
Tablet       → TabletPhotoSwipe.vue + LightboxTabletPanel.vue
Mobile       → MobilePhotoSwipe.vue + LightboxMobileSheet.vue
```

All PhotoSwipe wrappers share `usePhotoSwipe.ts` for lifecycle, item creation, index sync, and destroy guards. All wrappers build items through `frontend/src/utils/lightbox.ts`.

Device-specific behavior:

- Desktop/wide uses `PhotoSwipeViewer.vue` with a PhotoSwipe `paddingFn` supplied by `Lightbox.vue`. The padding reserves the 400px metadata sidebar so the image viewport does not sit under the panel.
- Tablet uses `TabletPhotoSwipe.vue`, which owns its top counter and bottom toolbar for close, zoom, and info.
- Mobile uses `MobilePhotoSwipe.vue`, which owns a floating info button and hides it while the metadata sheet is open.

Metadata panels:

- Desktop: fixed right sidebar, accordions, fullscreen and close controls.
- Tablet: two-column bottom sheet, expandable.
- Mobile: tabbed VSBS bottom sheet with Prompt, Params, and Model tabs; library-managed drag/snap/scroll; safe-area-aware controls.
- Planned, not yet implemented: a compact EXIF tab may be added across metadata panels only when `/api/metadata` returns `exif.hasData`. Without EXIF data, the tab set remains Prompt, Params, and Model. See [Metadata Parsing](METADATA_PARSING.md#planned-basic-exif-tab).

Mobile sheet integration:

- `LightboxMobileSheet.vue` uses `@douxcode/vue-spring-bottom-sheet` for mobile metadata only. Desktop and tablet lightbox panels are separate components and should not share this sheet code.
- Library-specific rationale, customization details, and pitfalls live in [Third-Party Libraries](THIRD_PARTY_LIBRARIES.md).
- PhotoSwipe owns image rendering, left/right swipe, pan/zoom, lightbox lifecycle, photo-area pointer/touch handling, and lightbox close.
- VSBS owns only the mobile metadata sheet container: drag, snap, scroll, sheet animation, sheet open/close, and its scroll container.
- Gallery glue owns the info button, hiding the info button while the sheet is open, chevron expand/compact behavior, Prompt and Negative Prompt Show more/less state, outside-tap sheet close, and the protections that keep VSBS from swallowing PhotoSwipe gestures.
- VSBS is deliberately non-modal: `blocking=false`, no VSBS backdrop, no VSBS focus trap, `teleport-defer`, and `v-model`. PhotoSwipe is already the modal/focus context.
- Enabling VSBS blocking/backdrop/focus trapping caused historical "too much recursion" focus-management failures. Keep VSBS as a non-modal metadata inspector inside PhotoSwipe.
- VSBS DOM is teleported to `<body>`, so the component keeps its VSBS overrides in a non-scoped global style block.
- Width and background overrides keep `[data-vsbs-sheet]`, `[data-vsbs-scroll]`, `[data-vsbs-content]`, `.sheet-content`, and `.expandable-text` full-width and dark themed.
- Because `blocking=false` means VSBS renders no backdrop, `canBackdropClose` does nothing. Outside-tap close is custom document pointer handling that closes the metadata sheet only, never PhotoSwipe.
- Approved UX: info opens the sheet, the info button is hidden while open, the chevron expands/collapses Prompt and Negative Prompt text, Prompt/Params/Model tabs work, copy buttons work, and PhotoSwipe image swipes continue to work.

Dependency audit, 2026-06-07:

- `npm audit` reported 6 vulnerabilities: axios high, follow-redirects moderate, immutable high, picomatch high, rollup high, and vite high.
- `npm audit --omit=dev` reported 2 production vulnerabilities: axios high and follow-redirects moderate.
- Audit output suggested `npm audit fix`; no automatic fix was applied during the VSBS cleanup.

## Layout Dispatch

`App.vue` selects the layout from `useDevice()`:

```vue
<MobileLayout  v-else-if="isMobile"  />
<TabletLayout  v-else-if="isTablet"  />
<DesktopLayout v-else                />
```

Each layout owns its sidebar/header/content shell and receives data/actions from `App.vue`.

| Device | Layout | Sidebar | Grid |
|--------|--------|---------|------|
| Mobile `<768px` | `MobileLayout.vue` | 240px overlay, destroyed on close | Native scroll |
| Tablet `768-1199px` | `TabletLayout.vue` | 280px drawer, always in DOM, `inert` when closed | RecycleScroller |
| Desktop/Wide `>=1200px` | `DesktopLayout.vue` | 280px persistent, collapsible | RecycleScroller |

## Fragile Contracts

- Keep `useDevice.ts`, `_breakpoints.scss`, and `useColumnResize.ts` synchronized when changing breakpoints.
- Keep desktop lightbox `DESKTOP_METADATA_WIDTH`, `--lightbox-sidebar-width`, PhotoSwipe `paddingFn`, counter positioning, and next-arrow offset synchronized.
- Keep mobile sheet drag/snap/scroll behavior delegated to VSBS; do not restore `.sheet-panel`, `.sheet-backdrop`, `.sheet-handle-wrapper` pointer drag, `--sheet-drag-y`, `dragDelta`, `sheetDragState`, custom pointer drag, or rAF drag-loop code.
- Keep mobile outside-tap close non-blocking: no `stopPropagation()`, track `pointerId` and `isPrimary`, require pointerdown and pointerup outside the sheet, use the 10px movement threshold, handle `pointercancel`, and do not block PhotoSwipe swipe.
- Keep `pswp.currIndex !== index` in the PhotoSwipe index watcher to prevent feedback loops.
- Keep `hasEverLoaded` behavior in the gallery store so the UI does not show a false empty state before the first scan finishes.
