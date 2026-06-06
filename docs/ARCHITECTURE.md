# Architecture

Last reviewed: 2026-06-06

## Overview

AI Art Gallery is a local-first image browser with a FastAPI backend and a Vue 3 frontend.

- Backend: scans directories, serves originals, renders cached WebP thumbnails, and parses generation metadata.
- Frontend: manages gallery state with Pinia, renders responsive layouts, virtualizes large grids, and opens images in a PhotoSwipe 5 lightbox.
- Startup: `start.py` creates the Python virtualenv, installs Python and Node dependencies, and starts both servers.

## Backend

All API routes live in `backend/main.py`.

| Endpoint | Purpose |
|----------|---------|
| `GET /api/scan` | Return folders and paginated image files for a directory |
| `GET /api/image` | Serve an original image file |
| `GET /api/thumbnail` | Serve a cached WebP thumbnail |
| `GET /api/metadata` | Parse AI generation metadata |
| `POST /api/open-folder` | Open a folder in the OS file explorer when enabled |
| `GET /api/health` | Return service health |
| `GET /api/landing-pages` | List intro page HTML files |
| `GET /` and `GET /{path:path}` | Serve the built SPA in production mode |

Important backend behavior:

- `GALLERY_ROOT` bounds path safety. The default root is `/`, which is permissive for local use but still routes through path checks.
- `GALLERY_OPEN_FOLDER=false` disables OS folder opening by default.
- Thumbnail cache keys include path, mtime, size, max size, and quality.
- Metadata cache keys include path, mtime, and size.
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
→ GalleryGrid computed image list filters and sorts
→ RecycleScroller or native mobile grid rerenders
```

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
- Mobile: tabbed bottom sheet with Prompt, Params, and Model tabs; handle-only drag; safe-area-aware controls.

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
- Keep mobile sheet drag handlers on the handle, not the whole sheet, so content scrolling remains independent.
- Keep `pswp.currIndex !== index` in the PhotoSwipe index watcher to prevent feedback loops.
- Keep `hasEverLoaded` behavior in the gallery store so the UI does not show a false empty state before the first scan finishes.
