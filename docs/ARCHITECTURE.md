# Architecture

Last reviewed: 2026-06-09

## Overview

AI Art Gallery is a local-first image browser with a FastAPI backend and a Vue 3 frontend.

- Backend: scans directories, serves originals, renders cached WebP thumbnails, parses generation metadata, and indexes prompt/metadata text in SQLite FTS5.
- Frontend: manages gallery state with Pinia, renders responsive layouts, virtualizes large grids, and opens images in a PhotoSwipe 5 lightbox.
- Startup: `start.py` creates the Python virtualenv, installs Python and Node dependencies, and starts both servers.

Major external library integrations are documented in [Third-Party Libraries](THIRD_PARTY_LIBRARIES.md).

## Backend

Backend modules live flat in `backend/` (no nested packages beyond `tests/`).

| File | Purpose |
|------|---------|
| `app.py` | FastAPI app creation, CORS, Prometheus, pyinstrument, router composition |
| `main.py` | Compatibility shim (`from .app import app`) + `__main__` uvicorn block |
| `config.py` | Environment variables, constants, cache dirs |
| `errors.py` | `APIError`, `ErrorType` |
| `models.py` | Pydantic `FileNode` and shared request/response schemas |
| `paths.py` | `resolve_path`, `is_path_safe`, GALLERY_ROOT boundary checks |
| `files.py` | `is_image`, `natural_sort_key`, `IMAGE_EXTENSIONS`, `check_image_limits` |
| `albums.py` | `build_album_metadata`, `has_subfolders`, cover/child detection |
| `scan.py` | `GET /api/scan`, `scan_directory`, perf helpers |
| `folders.py` | `GET /api/folders`, `POST /api/open-folder` |
| `images.py` | `GET /api/image` (original image serving) |
| `thumbnails.py` | `GET /api/thumbnail`, generation, persistent disk cache |
| `metadata_extract.py` | Raw metadata extraction from image files (lowest layer, no SQLite/API) |
| `metadata_parse.py` | `GET /api/metadata`, LRU cache, rich response shaping |
| `metadata_store.py` | SQLite metadata cache, FTS5 index/search |
| `search.py` | `GET /api/search`, `GET /api/search-metadata` |
| `health.py` | `GET /api/health`, favicon, GIT_COMMIT |
| `static_files.py` | `GET /`, `GET /api/landing-pages`, production SPA fallback |

### Route Reference

| Endpoint | Purpose | Module |
|----------|---------|--------|
| `GET /api/scan` | Return folders and paginated image files for a directory | `scan.py` |
| `GET /api/folders` | Return folder children only for folder tree expansion | `folders.py` |
| `GET /api/image` | Serve an original image file | `images.py` |
| `GET /api/thumbnail` | Serve a cached WebP thumbnail | `thumbnails.py` |
| `GET /api/metadata` | Parse AI generation metadata | `metadata_parse.py` |
| `GET /api/search` | Unified indexed search for albums, photo filenames, and prompt/metadata | `search.py` |
| `GET /api/search-metadata` | Search indexed AI prompt/metadata fields with SQLite FTS5 | `search.py` |
| `POST /api/open-folder` | Open a folder in the OS file explorer when enabled | `folders.py` |
| `GET /api/health` | Return service health | `health.py` |
| `GET /api/landing-pages` | List intro page HTML files | `static_files.py` |
| `GET /` and `GET /{path:path}` | Serve the built SPA in production mode | `static_files.py` |

Important backend behavior:

- `GALLERY_ROOT` bounds path safety. The default root is `/`, which is permissive for local use but still routes through path checks.
- `GALLERY_OPEN_FOLDER=false` disables OS folder opening by default.
- `ENABLE_METRICS=1` (default in dev) exposes Prometheus metrics at `/metrics` via `prometheus-fastapi-instrumentator`. Route-level labels only (no per-path cardinality explosion). Disable in production with `ENABLE_METRICS=0`.
- `ENABLE_PROFILER=0` by default. When enabled, selected endpoints (configurable via `PROFILE_ENDPOINTS`, default `/api/scan,/api/metadata,/api/thumbnail`) are profiled with pyinstrument. HTML profiles are saved to `backend/profiles/` (gitignored).
- Thumbnail cache keys include path, mtime, size, max size, and quality. Rendered WebP thumbnails are persisted under `backend/.cache/thumbnails/`, survive backend restarts, and are served with 24-hour browser caching headers.
- Metadata cache: two layers.
  - **In-memory LRU cache** (cachetools, 100MB max): caches parsed metadata dicts from `/api/metadata`. Keys include path + mtime + size.
  - **SQLite dimension cache** (same DB as search cache): `image_metadata` table with `width`, `height`, `mtime`, `size` per path. Populated by `/api/metadata` (full metadata parse) and `/api/thumbnail` (image already opened for thumbnailing). Queried by `/api/scan` as a single batch lookup to return cached dimensions without opening images.
- Search cache lives at `backend/.cache/gallery_metadata.db`. It contains `file_index` rows for indexed folders/photos, `file_index_fts` for recursive album/photo filename search, and normalized image metadata with SQLite FTS5 tables for prompt/metadata search.
- `/api/scan` must stay hot-path fast:
  - Returns `width=None, height=None` when no cached dimensions exist.
  - Performs a single batched SQL query (`get_cached_dimensions_for_files()`) to look up cached dimensions by path+mtime+size.
  - Does NOT open images with PIL, does NOT batch-read metadata for all images.
  - Indexes the scanned folder and its subfolders in the background (without re-indexing image metadata — `include_metadata=False`).
  - File entries are indexed for albums/photos; image metadata indexing is deferred to `/api/metadata` or `/api/thumbnail` endpoints that already open the image.
- `/api/scan` dimension flow:
  1. `os.scandir()` lists folder entries.
  2. Image files are filtered and their stat (mtime, size) collected.
  3. `get_cached_dimensions_for_files()` does a single `SELECT path, mtime, size, width, height FROM image_metadata WHERE path IN (...) AND width IS NOT NULL`.
  4. Results validated against current mtime/size; stale entries discarded.
  5. `FileNode` objects built with cached dimensions (or null if uncached).
- `/api/metadata` populates cache after parsing (via `upsert_metadata_result()`).
- `/api/thumbnail` populates cache after rendering thumbnail (via `upsert_image_dimensions()`).
- `/api/folders` is a lightweight folder-tree endpoint. It lists only direct, non-hidden folder children, does not return image rows, and does not compute image counts or cover images. `/api/folders` ignores symlinked directories and only lists real non-hidden child directories. For this endpoint, `has_children` means the folder has at least one non-hidden child directory, so sidebar chevrons are not shown for folders that contain only images. Album cover/count metadata remains part of `/api/scan`, not `/api/folders`.
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
| `frontend/src/query/` | TanStack Query client setup and default server-state cache options |
| `frontend/src/stores/` | Pinia stores for gallery, lightbox, and toasts |
| `frontend/src/styles/` | Global SCSS, tokens, breakpoint mixins, lightbox styles |
| `frontend/src/services/api.ts` | Axios client and API error handling |

## State Stores

| Store | Responsibilities |
|-------|------------------|
| `gallery.ts` | Root/current path, folder tree expansion state, navigation history, search input/scope, sort, loaded state |
| `lightbox.ts` | Open image, current index, gallery item list, metadata, navigation, neighbor preloading |
| `toast.ts` | Toast queue, type helpers, auto-dismiss |

## Server-State Caching

TanStack Query caches `/api/scan`, `/api/folders`, `/api/search`, and `/api/metadata` responses, while Pinia keeps UI/navigation state.

| Layer | Responsibilities |
|-------|------------------|
| TanStack Query | Cached scan first-page, folder-only tree child loads, active scan infinite image pages, unified search, and lightbox metadata responses, stale time, garbage collection, background refresh query keys |
| TanStack DB | Minimal beta foundation for local reactive collections and live queries over already loaded/API-backed data |
| Pinia gallery store | Current/root path, folder tree expanded/collapsed state, loaded/root flags, history, search input/scope, sort |

Migration rule: TanStack Query should own server/API state and cache. Pinia should own UI/navigation state. Do not add new Query -> Pinia duplicated server-state flows unless needed for compatibility. The active `/api/scan` gallery rendering flow, infinite image pagination, unified search, folder children, and lightbox metadata are Query-owned.

TanStack DB is available as a beta, incremental layer that complements TanStack Query. Query Collection should reuse the shared Query client for REST/API-backed collections; live queries can then query across those loaded collections locally. Do not migrate scan, infinite loading, folder tree, unified search, or lightbox metadata into DB without a dedicated follow-up design that proves stable keys and complete collection state for the endpoint scope.

Scan query keys use this deterministic pattern:

```text
["scan", normalizedPath, imageLimit]
["scan-infinite", normalizedPath, imageLimit]
```

`normalizedPath` is trimmed, converts backslashes to forward slashes, collapses duplicate slashes, and removes a trailing slash. For the first image page, `imageLimit` is `IMAGE_PAGE_SIZE`.

## Data Flow

### Folder Load

```text
Sidebar or album click
→ galleryStore.selectFolder(path)
→ useInfiniteScanQuery(path)
→ GET /api/scan
→ TanStack Query stores scan pages under ["scan-infinite", normalizedPath, IMAGE_PAGE_SIZE]
→ GalleryGrid renders albums and image rows from useInfiniteScanQuery()
```

Gallery loading behavior:

- First uncached folder load can show the full skeleton.
- Revisiting a cached folder can render cached albums/photos immediately and show only a subtle refreshing indicator while the background fetch completes.
- Search loading has its own skeleton path and does not replace cached normal-gallery content during scan refresh.

### Folder Tree Expansion

```text
FolderTreeItem toggle
→ galleryStore.toggleFolderExpanded(node.path) updates path-keyed UI state
→ useFolderChildrenQuery(node.path, galleryStore.isFolderExpanded(node.path) && node.has_children)
→ read/fetch TanStack Query cache for ["folder-children", normalizedPath]
→ GET /api/folders?path=... when cache policy requires it
→ FolderTreeItem renders query loading/error state
→ FolderTreeItem renders recursive children from Query data
```

Folder tree ownership:

- Pinia owns root path, current path, selected path, history/back-forward, and expanded/collapsed state.
- TanStack Query owns folder child server data, per-path loading/fetching/error state, stale time, garbage collection, and cache reuse.
- Folder expansion is stored in Pinia as path-keyed UI state. `FileNode` objects returned from `/api/folders` are Query-owned server data and should not be mutated to store expansion state such as `isOpen`.
- `FolderTreeItem.vue` no longer writes Query results into `node.children`; static/prebuilt children are only a compatibility fallback before Query data is available.
- TanStack DB is not used for folder tree. Folder child loading is per-path server state, and Query owns it directly.

### Infinite Scroll

```text
IntersectionObserver sees loadMoreSentinel
→ guard hasNextPage and isFetchingNextPage/isFetching
→ useInfiniteScanQuery().fetchNextPage()
→ GET /api/scan with image_cursor from pageParam
→ TanStack Query appends returned page
→ grid rows recompute
```

### Search and Sort

```text
Header or toolbar emits search/sort change
→ gallery store updates query, scope, or sort state
→ non-search gallery view keeps existing loaded folders/images and sort behavior
→ non-empty search query enables TanStack Query for GET /api/search
→ GalleryGrid renders Albums, Photos, and Prompt sections
```

Unified gallery search uses one search box:

- Default scope is `This folder`, which means the current folder plus all indexed subfolders recursively.
- Optional scope is `All indexed`, which searches the whole indexed database under `GALLERY_ROOT`.
- Albums and Photos use `file_index_fts` over folder/photo names, scope-filtered by path.
- Prompt uses the existing metadata FTS5 tables, joined through `file_index` so prompt matches share the same recursive scope rules.
- Results are grouped as Albums, Photos, and Prompt. Subfolder matches include `relative_path`, computed from the current root for `This folder` and from `GALLERY_ROOT` for `All indexed`.
- Empty queries restore the normal gallery view. Fuse.js remains in the codebase for lightweight filtering behavior in the non-search gallery view, but backend `/api/search` owns active search results.
- TanStack Query owns active search result data, loading/fetching, errors, and cache. Pinia owns only the search input text, scope, and navigation context.
- `GET /api/search-metadata` remains available for backward compatibility, but the frontend no longer uses it for the main gallery search.

### Open Image

```text
PhotoCard click
→ lightboxStore.open({ path, name }, visibleImages)
→ preload neighboring images
→ GET /api/metadata
→ Lightbox.vue dispatches to the active device wrapper and metadata panel
```

### Thumbnail Request

```text
source image
→ cache key from resolved path + mtime_ns + size + max_size + quality
→ diskcache at backend/.cache/thumbnails/
→ persisted WebP thumbnail file
→ FileResponse
→ browser cache with Cache-Control: public, max-age=86400, immutable
```

### Lightbox Navigation

```text
PhotoSwipe change, arrow key, or toolbar action
→ wrapper emits indexChange or store navigation action
→ lightbox store updates current item
→ TanStack Query loads metadata for the new path
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

Historical dependency audit note, 2026-06-07:

- `npm audit` reported 6 vulnerabilities: axios high, follow-redirects moderate, immutable high, picomatch high, rollup high, and vite high.
- `npm audit --omit=dev` reported 2 production vulnerabilities: axios high and follow-redirects moderate.
- Audit output suggested `npm audit fix`; no automatic fix was applied during the VSBS cleanup.
- Re-run `npm audit` for current results before acting on these numbers.

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
| Tablet `768-1199px` | `TabletLayout.vue` | 280px drawer, always in DOM, `inert` when closed | TanStack Virtual row-based grid |
| Desktop/Wide `>=1200px` | `DesktopLayout.vue` | 280px persistent, collapsible | TanStack Virtual row-based grid |

## Fragile Contracts

- Keep `useDevice.ts`, `_breakpoints.scss`, and `useColumnResize.ts` synchronized when changing breakpoints.
- Keep desktop lightbox `DESKTOP_METADATA_WIDTH`, `--lightbox-sidebar-width`, PhotoSwipe `paddingFn`, counter positioning, and next-arrow offset synchronized.
- Keep mobile sheet drag/snap/scroll behavior delegated to VSBS; do not restore `.sheet-panel`, `.sheet-backdrop`, `.sheet-handle-wrapper` pointer drag, `--sheet-drag-y`, `dragDelta`, `sheetDragState`, custom pointer drag, or rAF drag-loop code.
- Keep mobile outside-tap close non-blocking: no `stopPropagation()`, track `pointerId` and `isPrimary`, require pointerdown and pointerup outside the sheet, use the 10px movement threshold, handle `pointercancel`, and do not block PhotoSwipe swipe.
- Keep `pswp.currIndex !== index` in the PhotoSwipe index watcher to prevent feedback loops.
- Keep `hasEverLoaded` behavior in the gallery store so the UI does not show a false empty state before the first scan finishes.
