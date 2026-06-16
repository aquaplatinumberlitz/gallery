# Third-Party Libraries

Last reviewed: 2026-06-16

This document records how major third-party libraries are used in the current codebase and which integration contracts should not be changed casually.

## Quick Index

| Library | Used for | Main integration file(s) | Notes |
|---|---|---|---|
| FastAPI | Backend API app and routing | `backend/app.py`, route modules in `backend/` | Routers are composed in `app.py`; `backend.main:app` is the uvicorn target |
| Uvicorn | ASGI dev/prod server | `start.py`, `backend/main.py` | `start.py` runs `python -m uvicorn backend.main:app` from repo root |
| Pydantic | Backend DTO validation | `backend/models.py` | Used for `FileNode` and shared response/request schemas |
| Pillow | Image opening, dimensions, metadata, derivative rendering | `backend/metadata_extract.py`, `backend/thumbnails.py`, `backend/files.py` | Honors project file size/pixel limits |
| diskcache | Persistent derivative cache | `backend/thumbnails.py`, `backend/config.py` | Stores rendered WebP thumbnail/preview files under `backend/.cache/thumbnails/` by default |
| cachetools | In-memory metadata response cache | `backend/metadata_parse.py` | Metadata cache only; thumbnail bytes are disk-backed |
| SQLite FTS5 | Folder/photo/metadata index and search | `backend/metadata_store.py`, `backend/search.py`, `backend/facets.py` | Uses Python stdlib `sqlite3`; no external search service |
| prometheus-fastapi-instrumentator / prometheus-client | Optional metrics | `backend/app.py`, `backend/scan.py`, `backend/indexer.py` | Enabled by default outside production through `ENABLE_METRICS` |
| pyinstrument | Optional endpoint profiling | `backend/app.py` | Enabled by `ENABLE_PROFILER=1`; writes HTML profiles to `backend/profiles/` |
| Vue 3 | Frontend framework | `frontend/src/main.ts`, `frontend/src/App.vue`, components/layouts | Composition API and SFCs |
| Vue Router | `/` gallery and `/metadata` inspector routing | `frontend/src/router/index.ts`, `frontend/src/layouts/DesktopLayout.vue`, `frontend/src/App.vue` | Production fallback is served by backend static route |
| Pinia | UI/navigation state stores | `frontend/src/stores/` | Server state belongs in TanStack Query, not Pinia |
| Axios | API client and error mapping | `frontend/src/services/api.ts` | Uses `VITE_API_URL` or same-origin proxy |
| Vite | Frontend build/dev server | `frontend/vite.config.ts` | Uses Vue plugin and Tailwind 4 Vite plugin |
| Tailwind CSS 4 | Utility layer and shadcn token bridge | `frontend/src/styles/tailwind.css`, `frontend/src/styles/_shadcn-token-bridge.css`, component classes | Coexists with SCSS lightbox/layout styles |
| SCSS / Sass | Global layout, lightbox, breakpoint styles | `frontend/src/styles/*.scss` | Keep breakpoints in sync with `useDevice.ts` |
| shadcn-vue-style local components / shadcn-vue package | Buttons, inputs, menus, sheets, sidebar, popover, tabs, tooltip, skeleton, select | `frontend/src/components/ui/` | Local components follow shadcn-vue patterns and are built on Reka UI, CVA, clsx, tailwind-merge, VueUse |
| Reka UI | Headless primitives for local UI components | `frontend/src/components/ui/` | Dialog, sheet, dropdown, select, tooltip, popover, tabs, primitive/sidebar context |
| class-variance-authority / clsx / tailwind-merge | Variant and class composition | `frontend/src/components/ui/Button.vue`, `Badge.vue`, `Input.vue`, `frontend/src/lib/utils.ts` | `cn()` merges Tailwind classes consistently |
| Lucide Vue | Icons | Gallery and UI components | Both `lucide-vue-next` and `@lucide/vue` are installed; code currently imports `lucide-vue-next` |
| @vueuse/core | Theme, v-model helpers, media queries, UI primitive helpers | `frontend/src/composables/useGalleryTheme.ts`, `frontend/src/components/ui/` | Used by shadcn-style components and theme handling |
| @tanstack/vue-query | Server-state caching | `frontend/src/query/`, Query composables | Owns API data, stale time, retries, GC |
| @tanstack/vue-query-devtools | Development Query inspection | `frontend/src/App.vue`, `frontend/package.json` | Dev mode only |
| @tanstack/vue-virtual | Row-based large gallery grid and Library Inspector table body | `frontend/src/components/GalleryGrid.vue`, `frontend/src/components/LibraryInspector.vue` | Desktop/tablet grid virtualization; inspector renders the visible table-row window plus overscan |
| @tanstack/vue-form | Advanced fielded search form | `frontend/src/components/search/AdvancedSearchDrawer.vue` | Active runtime usage |
| @tanstack/vue-table | Library Inspector data table | `frontend/src/components/LibraryInspector.vue` | Active runtime usage |
| @tanstack/db / @tanstack/vue-db / @tanstack/query-db-collection | Beta local reactive collection foundation | `frontend/src/db/` | Runtime pilot is landing pages only |
| PhotoSwipe 5 | Lightbox image viewer | `frontend/src/components/Lightbox.vue`, PhotoSwipe wrappers, `usePhotoSwipe.ts` | Gallery owns custom metadata UI and controls |
| @douxcode/vue-spring-bottom-sheet | Mobile lightbox metadata sheet | `frontend/src/components/LightboxMobileSheet.vue`, `frontend/src/styles/_lightbox-mobile.scss` | Sheet/motion engine only, non-modal inside PhotoSwipe |
| Fuse.js | Local fuzzy filtering helper | `frontend/src/utils/fuzzySearch.ts`, `GalleryGrid.vue` | Backend `/api/search` owns active recursive search |
| embla-carousel-vue | shadcn-style carousel primitive | `frontend/src/components/ui/carousel/` | Used by desktop album carousel through local carousel component |
| eruda | Optional mobile browser debug console | `frontend/src/debug/erudaDebug.ts`, `frontend/src/main.ts` | Enabled by query/localStorage debug flag |
| Playwright | Frontend and contract tests | `frontend/tests/`, `frontend/playwright.config.ts` | Also used by perf smoke scripts |

## Backend Libraries

### FastAPI, Uvicorn, and Pydantic

FastAPI owns API routing, middleware, CORS, metrics/profiling hooks, and static production fallback. `backend/app.py` creates the app and includes route modules; `backend/main.py` exposes the import-compatible `app`.

Run targets:

```bash
python3 -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

`start.py` uses this form from repo root and sets `FRONTEND_PORT` so CORS includes the actual dev frontend port.

### Pillow

Pillow is used for:

- Opening images safely within configured pixel/file-size limits.
- Reading dimensions and format/mode information.
- Extracting PNG text chunks, EXIF/UserComment, WebP metadata where available, and other Pillow-exposed metadata.
- Rendering WebP thumbnails and previews.

Metadata extraction lives in `metadata_extract.py`; derivative rendering lives in `thumbnails.py`. ExifTool is not part of the runtime.

### diskcache

`diskcache` backs persistent WebP derivatives. Cache path defaults to `backend/.cache/thumbnails/` and can be changed with `GALLERY_THUMBNAIL_CACHE_DIR`.

Derivative cache keys include:

- derivative kind (`thumbnail` or `preview`)
- cache version
- resolved source path
- source mtime and size
- requested max long edge
- output format and quality

Changing the source file or derivative settings creates a new cache entry automatically.

### cachetools

`cachetools.LRUCache` is used for in-memory `/api/metadata` response caching. It is not used for thumbnail or preview bytes.

### SQLite FTS5

SQLite is the shared local index and cache, stored at `backend/.cache/gallery_metadata.db` by default or `GALLERY_METADATA_DB` if set.

Important tables:

- `file_index`: indexed folders/photos, parent path, type, mtime, size, dimensions.
- `file_index_fts`: FTS5 folder/photo filename search for Albums and Photos results.
- `image_metadata`: normalized metadata, dimensions, prompts, model/sampler/seed/steps/cfg/raw text.
- `image_metadata_fts`: unicode61 FTS5 metadata search.
- `image_metadata_fts_trigram`: trigram FTS5 for substring/CJK-oriented metadata search.
- `metadata_index_jobs`: queued/running/done/failed/stale background metadata indexing jobs.

Search behavior:

- `/api/search` returns grouped `albums`, `photos`, and `prompt` sections.
- `scope=current` searches the current folder recursively.
- `scope=all` searches all indexed files under `GALLERY_ROOT`.
- Fielded queries are parsed by `fielded_search_parser.py` and executed by metadata-store search helpers.
- `/api/library/inspector` returns bounded DB-backed metadata rows; detail popovers call `/api/library/inspector/metadata`.
- `/api/facets` derives counts from indexed DB metadata.

Not used: Meilisearch, Typesense, Tantivy, Whoosh, sqlite-vec, MeCab, Sudachi, Kuromoji, or an external search service.

### Metrics and Profiling

`prometheus-fastapi-instrumentator` exposes `/metrics` when `ENABLE_METRICS` is true. It defaults to true outside production and false in production can be forced with `ENABLE_METRICS=0`.

`pyinstrument` profiling is opt-in:

```bash
ENABLE_PROFILER=1 PROFILE_ENDPOINTS=/api/scan,/api/metadata python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Profiles are written to `backend/profiles/`.

## Frontend Libraries

### Vue 3, Vue Router, and Pinia

Vue 3 is the app framework. Vue Router defines:

- `/`: gallery route through `GalleryRoute.vue`.
- `/metadata`: desktop Library Inspector route.
- fallback: redirect to `/`.

Pinia stores UI/navigation state:

- `gallery.ts`: root/current path, history, expanded folders, search input/scope, sort, loaded flags.
- `lightbox.ts`: open item, current index, visible image list, navigation.
- `toast.ts`: toast queue.

Pinia should not duplicate new server/API response state that belongs in TanStack Query.

### Axios

`frontend/src/services/api.ts` owns the Axios instance, API wrapper functions, URL builders, and backend error mapping to `GalleryAPIError`.

`VITE_API_URL` sets the base URL. In Vite dev without `VITE_API_URL`, requests are same-origin and `/api` is proxied by `vite.config.ts`.

### TanStack Query

TanStack Query owns API/server state.

Integration files:

- `frontend/src/query/index.ts`: shared `QueryClient` and Vue plugin installer.
- `frontend/src/query/keys.ts`: normalized query-key factory.
- `frontend/src/query/scan.ts`: scan prefetch/helper functions.
- `frontend/src/composables/useInfiniteScanQuery.ts`
- `frontend/src/composables/useFolderChildrenQuery.ts`
- `frontend/src/composables/useUnifiedSearchQuery.ts`
- `frontend/src/composables/usePhotoMetadataQuery.ts`
- `frontend/src/composables/useFacetsQuery.ts`
- `frontend/src/composables/useIndexStatusQuery.ts`
- `frontend/src/composables/useLibraryInspectorQuery.ts`
- `frontend/src/composables/useLibraryInspectorMetadataQuery.ts`

Default client behavior: 1 minute stale time, 10 minute garbage collection, one retry, no refetch on window focus.

### TanStack Virtual

`@tanstack/vue-virtual` provides row-based virtualization in `GalleryGrid.vue` for desktop/tablet grids. Mobile uses native scroll behavior rather than the same virtualized grid contract.

`LibraryInspector.vue` also uses `useVirtualizer` for the `/metadata` table body. The inspector still requests a bounded result set from `/api/library/inspector` and uses TanStack Table for row models/sorting, but the DOM contains only the currently visible rows plus overscan and spacer rows instead of all returned rows.

### TanStack Form

`@tanstack/vue-form` is active in `AdvancedSearchDrawer.vue`. It manages the fielded-search form state and validation for numeric fields and size-format fields, then emits structured filters that serialize to backend fielded query syntax.

Do not document this as unused; it is now production runtime code.

### TanStack Table

`@tanstack/vue-table` is active in `LibraryInspector.vue`. It builds columns and client-side returned-row sorting over rows returned by `/api/library/inspector`.

The backend remains responsible for query filtering, limit, DB-backed metadata fields, and detail lookup. The frontend table sorts the bounded returned row set.

### TanStack DB

TanStack DB is still an incremental beta foundation. Runtime usage is intentionally narrow:

- `frontend/src/db/collections/landingPagesCollection.ts` wraps `/api/landing-pages`.
- `frontend/src/db/composables/useLandingPagesLiveQuery.ts` exposes a Vue live query for settings/intro UI.

Do not migrate `/api/scan`, infinite loading, folder tree, unified search, lightbox metadata, PhotoSwipe, virtual scrolling, or the Pinia gallery store shape into TanStack DB without a dedicated design for stable keys and complete collection state.

### PhotoSwipe 5

PhotoSwipe is the image viewer engine only. Gallery owns metadata panels, custom controls, responsive layout, original-load policy, and copy actions.

Integration files:

- `frontend/src/components/Lightbox.vue`
- `frontend/src/components/MobilePhotoSwipe.vue`
- `frontend/src/components/TabletPhotoSwipe.vue`
- `frontend/src/components/PhotoSwipeViewer.vue`
- `frontend/src/composables/usePhotoSwipe.ts`
- `frontend/src/utils/lightbox.ts`
- `frontend/src/styles/_lightbox-*.scss`

Normal PhotoSwipe image URLs use `/api/preview`. Original `/api/image` is reserved for explicit original-load behavior such as zoom/fullscreen/download settings or animated images.

### @douxcode/vue-spring-bottom-sheet

VSBS is used only for the mobile lightbox metadata sheet.

Core contract:

- Use `blocking=false`; PhotoSwipe is already the modal/focus context.
- Do not enable VSBS backdrop/focus trap inside PhotoSwipe.
- Keep VSBS as the sheet and motion engine only.
- Gallery owns tabs, metadata content, copy actions, prompt expansion, info button visibility, and custom outside-tap close.
- VSBS DOM is teleported, so required width/background overrides must stay in global/non-scoped CSS.

Common pitfalls:

- Do not move VSBS overrides into scoped-only styles.
- Do not add `stopPropagation()` to outside-tap close; it can break PhotoSwipe swipe.
- Do not reintroduce the removed custom sheet drag implementation.
- `canBackdropClose` does not close anything when `blocking=false` because no VSBS backdrop is rendered.

### Tailwind CSS 4, shadcn-vue-style Components, and Reka UI

The frontend uses Tailwind 4 through `@tailwindcss/vite` and `frontend/src/styles/tailwind.css`. Existing SCSS still owns core gallery layout and lightbox styles.

Local UI primitives live under `frontend/src/components/ui/` and follow shadcn-vue patterns:

- Reka UI provides headless primitives for dialog, sheet, dropdown menu, select, tooltip, popover, tabs, separator, and primitive/sidebar context.
- `class-variance-authority` defines component variants.
- `clsx` and `tailwind-merge` are wrapped by `cn()` in `frontend/src/lib/utils.ts`.
- `_shadcn-token-bridge.css` maps neutral shadcn tokens without replacing gallery brand/design tokens.
- Select primitives live in `frontend/src/components/ui/select/` and wrap Reka Select. They are used by the `/metadata` toolbar model/prompt filters and by `SortSelect.vue` for gallery/tablet/metadata sort controls.
- `MobileHeader.vue` still uses `SortDropdown.vue`, which is based on the dropdown-menu primitive rather than Select.
- Shared UI focus rings should use `focus-visible` styling so pointer clicks do not show keyboard focus rings. Reka menu/select item highlight classes still use Reka's `focus:` data behavior where appropriate for roving focus.

Keep standard UI component styling neutral and avoid mapping gallery-specific decorative colors into generic shadcn tokens.

### Lucide Vue

Code imports icons from `lucide-vue-next`. `@lucide/vue` is also installed, but the current source tree uses `lucide-vue-next` in gallery and UI components.

Prefer Lucide icon components for buttons and controls where a semantic icon exists.

### @vueuse/core

VueUse is used for theme mode, media/v-model helpers, and several local shadcn-style UI components. Examples include `useColorMode`, `useMediaQuery`, `useVModel`, `reactiveOmit`, and carousel injection helpers.

### Fuse.js

Fuse.js remains a local fuzzy filtering helper for already loaded folder/image rows. Backend `/api/search` owns active recursive indexed search and metadata/prompt search.

Do not use Fuse for the main unified search result set or indexed metadata search.

### embla-carousel-vue

Embla powers the local shadcn-style carousel primitive in `frontend/src/components/ui/carousel/`. The desktop album carousel uses that primitive through `AlbumCarouselDesktop.vue`.

### eruda

Eruda is an optional mobile debugging console. `frontend/src/debug/erudaDebug.ts` loads it dynamically when enabled by the debug query/localStorage flag. It should stay out of the normal production path.

## Do Not Change Casually

- Do not run backend docs/examples with the wrong import target; prefer `python3 -m uvicorn backend.main:app` from repo root.
- Do not move server/API state from TanStack Query into Pinia.
- Do not move scan/infinite/folder/search/lightbox metadata flows into TanStack DB without a specific collection-state design.
- Do not enable VSBS `blocking=true` or add a second focus trap inside PhotoSwipe.
- Do not move VSBS teleported DOM overrides into scoped-only styles.
- Do not add `stopPropagation()` to mobile sheet outside-tap close.
- Do not replace backend SQLite FTS5 search with a client-side search path for active recursive search.
- Do not document TanStack Form/Table as unused; both are active runtime integrations.
