# Architecture

Last reviewed: 2026-06-19

## Overview

AI Art Gallery is a local-first image browser with a FastAPI backend and a Vue 3 frontend.

- Backend: scans folders, serves original images, generates cached WebP derivatives, extracts AI generation metadata, indexes folders/photos/metadata in SQLite FTS5, and exposes read-only inspection/search APIs.
- Frontend: uses Vue Router for the gallery and metadata inspector routes, Pinia for UI/navigation state, TanStack Query for API state, TanStack Virtual for large grids and the Library Inspector table body, PhotoSwipe for the lightbox, TanStack Form for advanced search, and TanStack Table for the Library Inspector.
- Startup: `start.py` creates/repairs the Python virtualenv, installs Python and pnpm frontend dependencies when needed, finds free backend/frontend ports, and starts both servers.
- Tooling: Ruff, ESLint, and Prettier scan the full codebase. Vitest/V8 covers frontend units; Playwright runs sharded functional E2E and isolated performance suites against deterministic FastAPI fixtures.

Major external library integrations are documented in [Third-Party Libraries](THIRD_PARTY_LIBRARIES.md).
Environment variables and parser behavior are documented in
[Configuration](CONFIGURATION.md) and [Metadata Parsing](METADATA_PARSING.md).

## Backend

Backend modules live flat in `backend/`.

| File | Purpose |
|------|---------|
| `app.py` | FastAPI app creation, CORS, optional Prometheus metrics, optional pyinstrument middleware, router composition, startup background services |
| `main.py` | Import-compatible `app` shim and uvicorn fallback block |
| `config.py` | Environment flags, cache paths, image limits, indexer tuning, production/static config |
| `errors.py` | `APIError`, `ErrorType`, and FastAPI error shaping |
| `models.py` | Shared Pydantic DTOs, including `FileNode` |
| `paths.py` | `resolve_path`, `is_path_safe`, and `PATH_SAFETY_ROOT` boundary checks |
| `files.py` | Image extension checks, natural sort, and image safety limits |
| `albums.py` | Album cover/count/child-folder metadata |
| `scan.py` | `/api/scan`, direct folder scans, optional warm SQLite listing, background index scheduling |
| `folders.py` | `/api/folders` folder-tree endpoint and `/api/open-folder` OS explorer hook |
| `images.py` | `/api/image` original file serving |
| `thumbnails.py` | `/api/thumbnail`, `/api/preview`, WebP derivative generation, persistent disk cache |
| `metadata_extract.py` | Raw metadata extraction/parsing helpers for A1111, SwarmUI, ComfyUI, NovelAI, EasyDiffusion, and generic EXIF/text fields |
| `metadata_parse.py` | `/api/metadata`, in-memory metadata cache, response shaping |
| `metadata_store.py` | SQLite schema, FTS5 search, folder/photo index, metadata rows, facets, Library Inspector data access |
| `fielded_search_parser.py` | Parser for `prompt:`, `seed:`, `model:`, numeric operators, quoted values, and related fielded search syntax |
| `search.py` | `/api/search`, `/api/search-metadata`, `/api/library/inspector`, `/api/library/inspector/metadata` |
| `facets.py` | `/api/facets` aggregation over indexed metadata |
| `indexer.py` | Background metadata queue, staged path batching, SQLite write batching, `/api/index/status` |
| `refresh.py` | Optional scheduled refresh loop |
| `watcher.py` | Optional filesystem watcher loop |
| `health.py` | `/api/health`, favicon, git commit reporting |
| `static_files.py` | `/`, `/api/landing-pages`, and production SPA fallback |

### Route Reference

| Endpoint | Purpose | Module |
|----------|---------|--------|
| `GET /api/scan` | Return folder albums and paginated image rows for a directory | `scan.py` |
| `GET /api/folders` | Return direct non-hidden child folders for sidebar expansion | `folders.py` |
| `GET /api/image` | Serve an original image file | `images.py` |
| `GET /api/thumbnail` | Serve a cached WebP thumbnail, default max long edge 512px | `thumbnails.py` |
| `GET /api/preview` | Serve a cached WebP preview, default max long edge 1440px | `thumbnails.py` |
| `GET /api/metadata` | Extract and normalize AI generation metadata for one image | `metadata_parse.py` |
| `GET /api/search` | Unified album/photo/prompt search, including fielded metadata queries | `search.py` |
| `GET /api/search-metadata` | Legacy metadata-only search endpoint | `search.py` |
| `GET /api/library/inspector` | Bounded read-only rows for the desktop metadata inspector | `search.py` |
| `GET /api/library/inspector/metadata` | DB-first full metadata detail for one inspector row | `search.py` |
| `GET /api/facets` | DB-derived model/tool/sampler/etc. aggregation counts | `facets.py` |
| `GET /api/index/status` | Metadata indexer queue/runtime status | `indexer.py` |
| `POST /api/open-folder` | Open a folder in the OS file explorer when enabled | `folders.py` |
| `GET /api/health` | Return service health and commit metadata | `health.py` |
| `GET /api/landing-pages` | List intro page HTML templates from `frontend/public/landpage/` | `static_files.py` |
| `GET /` and `GET /{path:path}` | Serve the built SPA in production mode | `static_files.py` |

### Backend Behavior

- `PATH_SAFETY_ROOT` bounds path safety. The default root is `/`, which is permissive for local use but all file routes still resolve and check paths.
- `GALLERY_OPEN_FOLDER=false` disables OS folder opening by default.
- `ENABLE_METRICS` defaults to enabled outside production and exposes `/metrics` with route-level labels.
- `ENABLE_PROFILER=0` by default. When enabled, selected endpoints are profiled with pyinstrument and HTML reports are written to `backend/profiles/`.
- Original images are served only by `/api/image`; thumbnails and previews are generated derivatives.
- Derivative cache keys include kind, cache version, resolved path, mtime, size, long-edge target, format, and quality. WebP files persist under `backend/.cache/thumbnails/`.
- The metadata DB defaults to `backend/.cache/gallery_metadata.db` and can be overridden with `GALLERY_METADATA_DB`.
- SQLite uses WAL mode and stores both file index rows and normalized metadata rows. FTS5 tables cover folder/photo names and metadata text.
- `/api/scan` stays hot-path focused: `os.scandir`, stat, natural sort, one batched dimension lookup, and no blanket metadata parsing.
- `/api/scan` schedules background indexing work for scanned folders/images and metadata jobs. `/api/metadata`, `/api/thumbnail`, and `/api/preview` also update cached metadata/dimensions when they already open the image.
- `ENABLE_WARM_INDEXED_LISTING=1` allows `/api/scan` to serve a warm SQLite-backed listing when the folder index is complete and fresh.
- Scheduled refresh is disabled by default. The file watcher is enabled for registered library roots by default and can be disabled with `ENABLE_FILE_WATCHER=0`.

## Frontend

Key paths:

| Path | Role |
|------|------|
| `frontend/src/main.ts` | Vue entry, global styles, Pinia, Vue Router, TanStack Query installation, dev debug utilities |
| `frontend/src/router/index.ts` | Routes: `/` gallery, `/metadata` Library Inspector, fallback redirect |
| `frontend/src/App.vue` | Root shell, layout dispatch, lightbox/settings/toast mounting, Query Devtools in dev |
| `frontend/src/layouts/` | Desktop, tablet, and mobile layout shells |
| `frontend/src/components/GalleryGrid.vue` | Main gallery renderer, album/photo sections, infinite loading, search result rendering |
| `frontend/src/components/Lightbox.vue` | Device-dispatch lightbox orchestrator |
| `frontend/src/components/LibraryInspector.vue` | Desktop metadata inspection table at `/metadata`; TanStack Table for returned-row sorting plus TanStack Virtual for table rows |
| `frontend/src/components/SortSelect.vue` | shadcn-vue Select sort control used by gallery desktop/tablet toolbars and the Library Inspector |
| `frontend/src/components/SortDropdown.vue` | Dropdown-menu sort control still used by the mobile header |
| `frontend/src/components/search/AdvancedSearchDrawer.vue` | Facet-backed fielded search form |
| `frontend/src/components/ui/` | shadcn-vue/Reka-inspired local UI primitives |
| `frontend/src/composables/` | Query wrappers, device detection, PhotoSwipe lifecycle, metadata helpers, theme, haptics |
| `frontend/src/query/` | TanStack Query client, normalized query keys, scan prefetch helpers |
| `frontend/src/db/` | TanStack DB beta foundation and landing-pages pilot collection |
| `frontend/src/stores/` | Pinia stores for gallery UI/navigation, lightbox, and toasts |
| `frontend/src/services/api.ts` | Axios client, endpoint wrappers, URL helpers, API error mapping |
| `frontend/src/styles/` | Tailwind 4 entry, shadcn token bridge, SCSS tokens, breakpoints, lightbox styles |

### State Ownership

| Layer | Responsibilities |
|-------|------------------|
| TanStack Query | `/api/scan`, `/api/folders`, `/api/search`, `/api/metadata`, `/api/facets`, `/api/index/status`, Library Inspector rows/details, landing page fetches |
| TanStack DB | Beta local reactive collection foundation; currently only the landing-pages collection is a runtime pilot |
| Pinia gallery store | Root/current path, selected path, history, expanded folders, search text/scope, sort, loaded flags, settings UI state |
| Pinia lightbox store | Open image, current index, visible item list, navigation |
| Pinia toast store | Toast queue and auto-dismiss state |

Query keys are centralized in `frontend/src/query/keys.ts`. Paths are normalized by trimming, converting backslashes to forward slashes, collapsing duplicate slashes, and removing a trailing slash except for `/`.

Core keys:

```text
["scan", normalizedPath, imageLimit]
["scan-infinite", normalizedPath, imageLimit]
["folder-children", normalizedPath]
["search", query, scope, normalizedPath]
["metadata", normalizedPath]
["facets", normalizedPath]
["index-status", normalizedPath]
["library-inspector", query, scope, normalizedPath, limit]
["library-inspector-metadata", normalizedPath]
["landing-pages"]
```

## Data Flow

### Folder Load

```text
Folder selection
-> Pinia gallery store updates current path/history
-> useInfiniteScanQuery(path)
-> GET /api/scan
-> TanStack Query stores pages under ["scan-infinite", normalizedPath, IMAGE_PAGE_SIZE]
-> GalleryGrid renders albums and image rows
```

First uncached folder loads can show a skeleton. Cached revisits render immediately and show only subtle refresh state while Query refetches in the background.

### Folder Tree Expansion

```text
FolderTreeItem toggle
-> Pinia stores expanded/collapsed path state
-> useFolderChildrenQuery(path, enabled)
-> GET /api/folders when cache policy requires it
-> FolderTreeItem renders Query-owned child folder rows
```

Folder expansion state is UI state. Query-owned `FileNode` results should not be mutated to store expansion state.

### Infinite Scroll

```text
IntersectionObserver sees load-more sentinel
-> guard hasNextPage and fetch-in-progress flags
-> fetchNextPage()
-> GET /api/scan?image_cursor=...
-> TanStack Query appends page
-> grid rows recompute
```

### Search, Advanced Search, and Facets

```text
Header search or AdvancedSearchDrawer
-> Pinia stores search text/scope
-> useUnifiedSearchQuery()
-> GET /api/search
-> GalleryGrid renders Albums, Photos, and Prompt sections
```

- Default scope is `current`, meaning the current folder recursively.
- `all` searches the indexed database under `PATH_SAFETY_ROOT`.
- Fielded queries are parsed server-side, for example `prompt:"blue hair"`, `seed:12345`, `model:pony`, `steps:>25`, `width:>=1024`.
- The Advanced Search drawer uses TanStack Form and `/api/facets` to build the same fielded query syntax.
- `GET /api/search-metadata` remains available for older callers, but the main gallery UI uses `/api/search`.
- Desktop/tablet gallery sorting uses `SortSelect.vue`, a local shadcn-vue Select wrapper. `MobileHeader.vue` still uses `SortDropdown.vue`.

### Library Inspector

```text
/metadata route
-> LibraryInspector.vue
-> useInfiniteLibraryInspectorQuery(query, scope, currentPath, limit, sort)
-> GET /api/library/inspector
-> shadcn-vue Select controls filter by model/prompt state and choose sort
-> TanStack Table sorts returned rows client-side
-> TanStack Virtual renders the table body rows
-> popovers/copy actions fetch GET /api/library/inspector/metadata
```

The inspector is read-only. It is backed by indexed SQLite metadata and opens images in the same lightbox store used by the gallery. The table uses cursor-based infinite pagination plus body virtualization, so the DOM only contains the visible row window plus small overscan/spacer rows rather than every loaded row.

### Open Image

```text
PhotoCard or inspector row click
-> lightboxStore.open({ path, name }, visibleImages)
-> PhotoSwipe wrapper opens derivative-first item
-> usePhotoMetadataQuery(path)
-> GET /api/metadata
-> active device panel/sheet renders metadata
```

PhotoSwipe normal `src` is `/api/preview`. The original `/api/image` is used for explicit original-load paths such as zoom/fullscreen/download settings or animated images.

## Lightbox Design

`Lightbox.vue` dispatches by device:

```text
Desktop/Wide -> PhotoSwipeViewer.vue + LightboxDesktopPanel.vue
Tablet       -> TabletPhotoSwipe.vue + LightboxTabletPanel.vue
Mobile       -> MobilePhotoSwipe.vue + LightboxMobileSheet.vue
```

- All PhotoSwipe wrappers share `usePhotoSwipe.ts` for lifecycle, item creation, index sync, and destroy guards.
- Lightbox item URL construction lives in `frontend/src/utils/lightbox.ts`.
- Desktop reserves `DESKTOP_METADATA_WIDTH` through PhotoSwipe padding so the image is not hidden under the metadata sidebar.
- Tablet uses custom top/bottom controls and a bottom metadata panel.
- Mobile uses `@douxcode/vue-spring-bottom-sheet` as a non-modal metadata sheet inside PhotoSwipe.

Mobile sheet contract:

- PhotoSwipe owns image rendering, swipe, pan/zoom, keyboard/focus context, and lightbox lifecycle.
- VSBS owns mobile sheet drag, snap, scroll, and animation only.
- Gallery glue owns the info button, outside-tap sheet close, tab content, copy actions, prompt expansion, and protections that preserve PhotoSwipe gestures.
- Keep VSBS `blocking=false`; do not add a second focus trap inside PhotoSwipe.

## Layout Dispatch

`App.vue` selects the layout from `useDevice()`:

```vue
<MobileLayout  v-if="isMobile"  />
<TabletLayout  v-else-if="isTablet" />
<DesktopLayout v-else />
```

| Device | Layout | Sidebar | Grid |
|--------|--------|---------|------|
| Mobile `<768px` | `MobileLayout.vue` | Overlay/mobile shell | Native scroll |
| Tablet `768-1199px` | `TabletLayout.vue` | Drawer/sidebar shell | TanStack Virtual row grid |
| Desktop/Wide `>=1200px` | `DesktopLayout.vue` | Persistent/collapsible sidebar | TanStack Virtual row grid |

## Fragile Contracts

- Keep `useDevice.ts`, `_breakpoints.scss`, and `useColumnResize.ts` synchronized when changing breakpoints.
- Keep desktop lightbox `DESKTOP_METADATA_WIDTH`, `--lightbox-sidebar-width`, PhotoSwipe `paddingFn`, counter positioning, and next-arrow offset synchronized.
- Keep mobile sheet drag/snap/scroll delegated to VSBS; do not restore the old custom pointer-drag sheet implementation.
- Keep mobile outside-tap close non-blocking: no `stopPropagation()`, track `pointerId` and `isPrimary`, require pointerdown and pointerup outside the sheet, use the movement threshold, and handle `pointercancel`.
- Keep `pswp.currIndex !== index` in the PhotoSwipe index watcher to prevent feedback loops.
- Keep Query as the owner of server/API data and Pinia as the owner of UI/navigation state.
- Do not move scan, infinite loading, folder tree, unified search, or lightbox metadata into TanStack DB without a dedicated collection-state design.
- Keep shadcn-vue Select controls as the metadata toolbar contract for model, prompt, and sort filters. `toolbarTrigger.ts` is a shared dropdown/button trigger class, but `SortSelect.vue` uses the local `SelectTrigger` styling directly.
