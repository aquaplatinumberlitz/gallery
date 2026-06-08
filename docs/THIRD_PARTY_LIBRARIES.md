# Third-Party Libraries

Last reviewed: 2026-06-08

This document explains how major external libraries are used in this project.

## Quick Index

| Library | Used for | Main integration file(s) | Notes |
|---|---|---|---|
| `@douxcode/vue-spring-bottom-sheet` | Mobile lightbox metadata sheet, drag/snap/spring animation, native-feeling scroll | `frontend/src/components/LightboxMobileSheet.vue`, `frontend/src/styles/_lightbox-mobile.scss` | Used as the sheet and motion engine only; Gallery owns metadata UI and behavior |
| `@tanstack/vue-query` | Server-state caching for gallery scans | `frontend/src/query/index.ts`, `frontend/src/composables/useScanQuery.ts`, `frontend/src/stores/gallery.ts` | Caches `/api/scan` responses by normalized path and image page size |
| PhotoSwipe 5 | Responsive lightbox image viewer, image navigation, swipe/pan/zoom | `frontend/src/components/Lightbox.vue`, `MobilePhotoSwipe.vue`, `TabletPhotoSwipe.vue`, `PhotoSwipeViewer.vue`, `frontend/src/composables/usePhotoSwipe.ts`, `frontend/src/styles/_lightbox-*.scss` | Used as the image viewer engine; Gallery owns metadata panels, custom controls, and responsive layout |
| Vue 3 | Frontend framework | `frontend/src/main.ts`, `frontend/src/App.vue`, `frontend/src/components/`, `frontend/src/layouts/` | Composition API, SFC, and `<script setup>` |
| Vite | Frontend build tool and dev server | `frontend/` | No custom plugins beyond defaults |
| Lucide | Icons across the gallery | Vue components and shared UI styles | Prefer semantic icon tokens and component-level sizing rules |
| `@tanstack/vue-virtual` | Row-based virtual scrolling in the image grid | `frontend/src/components/GalleryGrid.vue` | Used for large desktop/tablet grids |
| `@tanstack/vue-form` | Future: metadata forms, batch editor, settings | `frontend/src/lib/tanstack/README.md` | Foundation only; not yet in use |
| `@tanstack/vue-table` | Future: metadata management table, admin views | `frontend/src/lib/tanstack/README.md` | Foundation only; not yet in use |
| Fuse.js | Lightweight client-side filtering helper for normal gallery folder/image lists | `frontend/src/utils/fuzzySearch.ts`, `frontend/src/components/GalleryGrid.vue`, `frontend/package.json` | Active non-empty gallery search is handled by backend `/api/search` |
| SQLite FTS5 | Backend full-text search for indexed albums, photo filenames, and prompt/metadata | `backend/services/metadata_index.py`, `backend/main.py` | Uses Python stdlib `sqlite3`; no external search service |
| Pillow | Image metadata extraction and image processing | `backend/main.py`, `backend/services/metadata_index.py`, `backend/requirements.txt` | Reads PNG/JPEG/WebP metadata exposed by Pillow; also used for thumbnails |
| diskcache | Persistent thumbnail byte cache | `backend/main.py`, `backend/requirements.txt` | Stores rendered WebP thumbnails under `backend/.cache/thumbnails/` across backend restarts |
| cachetools | In-memory metadata response cache | `backend/main.py`, `backend/requirements.txt` | Thumbnail caching moved to diskcache; cachetools remains for metadata only |

### @douxcode/vue-spring-bottom-sheet

Official links:

- Docs: https://github.com/megaarmos/vue-spring-bottom-sheet/tree/master/apps/docs/guide
- GitHub: https://github.com/megaarmos/vue-spring-bottom-sheet
- npm: https://www.npmjs.com/package/@douxcode/vue-spring-bottom-sheet

Used for: Mobile lightbox metadata sheet, drag/snap/spring animation, native-feeling scroll.

Core features we use: `BottomSheet` component, `v-model`, `snapToPoint`, `snapPoints`, built-in drag/swipe, scroll container, `headerClass`/`contentClass`, CSS variables.

Features we intentionally do NOT use: `blocking=true` / focus trap, VSBS backdrop close, content drag expansion.

Why not: The sheet lives inside PhotoSwipe, and PhotoSwipe is already the modal/focus context. `blocking=true` caused historical "too much recursion" focus recursion. With `blocking=false`, VSBS acts as a non-modal metadata inspector inside the lightbox.

Project customizations: `blocking=false`, no VSBS backdrop, no VSBS focus trap, `teleport-defer`, `v-model`, VSBS used as sheet/motion engine only, gallery owns metadata content/tabs/copy/Show more/chevron/outside-tap close, global CSS overrides required because VSBS teleports DOM, width chain override, background override, chevron expands sheet + Prompt details.

Integration files: `frontend/src/components/LightboxMobileSheet.vue`, `frontend/src/styles/_lightbox-mobile.scss`

Common pitfalls: Do not place overrides in scoped-only styles, do not rely on class passed to `BottomSheet` root (teleport/fragment), do not enable `blocking=true`, do not remove width-chain overrides (content collapses to 4px), do not remove scroll background override (gray strip returns), do not reintroduce old `.sheet-panel` pointer drag code, test on real iPhone/Safari.

Decision: We use VSBS as the mobile sheet motion engine, not as the owner of metadata UI. Gallery owns content and behavior; VSBS owns drag/snap/scroll.

Outside-tap close: Because `blocking=false` renders no VSBS backdrop, `canBackdropClose` does nothing. Gallery implements document pointer listeners that close the metadata sheet only. These listeners must not call `stopPropagation()` because that broke PhotoSwipe swipe. They must track `pointerId` and `isPrimary`, require pointerdown and pointerup outside the sheet, use the 10px movement threshold, and handle `pointercancel`.

Teleport styling: VSBS teleports DOM to `<body>`, so scoped SFC styles may not reach sheet internals. Keep global/non-scoped width rules for `[data-vsbs-sheet]`, `[data-vsbs-scroll]`, `[data-vsbs-content]`, `.sheet-content`, and `.expandable-text`. A previous scoped-only change collapsed `[data-vsbs-scroll]` to 4px, `[data-vsbs-content]` to 24px, and `.expandable-text` to 0px.

Legacy code warning: The old custom sheet drag implementation was removed. Do not reintroduce `.sheet-panel` drag transforms, `.sheet-backdrop`, `.sheet-handle-wrapper` pointer drag, `--sheet-drag-y`, `dragDelta`, `sheetDragState`, custom pointer drag, or an rAF drag loop. VSBS provides the smoother drag/snap/scroll behavior.

### @tanstack/vue-query

Official links:

- Docs: https://tanstack.com/query/v5/docs/framework/vue
- npm: https://www.npmjs.com/package/@tanstack/vue-query

Used for: Server-state caching for gallery folder scans.

Integration files: `frontend/src/query/index.ts`, `frontend/src/composables/useScanQuery.ts`, `frontend/src/stores/gallery.ts`

Query key: `["scan", normalizedPath, imageLimit]`, where `normalizedPath` is trimmed, slash-normalized, and has trailing slashes removed.

Default behavior: Scan data is fresh for 1 minute, retained for 10 minutes after last use, retries once, and does not refetch on window focus.

Decision: TanStack Query owns cached `/api/scan` server state. Pinia still owns UI state such as current path, history, search, sort, loading flags, and pagination cursors. The gallery store reads cached scan data before fetching so album revisits render immediately, then performs a background refresh and updates the cache with fresh data.

### PhotoSwipe 5

Official links:

- Docs: https://github.com/dimsemenov/PhotoSwipe/tree/master/docs
- Getting started: https://photoswipe.com/getting-started/
- Options: https://photoswipe.com/options/
- UI elements: https://photoswipe.com/adding-ui-elements/

Used for: Mobile/tablet/desktop lightbox image viewer, image navigation, swipe/pan/zoom.

Core features we use: PhotoSwipe core, slide navigation, image gestures, options (`closeOnVerticalDrag`, `allowPanToNext`), UI/event hooks.

Features we intentionally do NOT use: PhotoSwipe default topbar (custom UI used), PS5 UI registration for mobile info button (replaced with Vue overlay).

Why not: Custom metadata UI needs to match gallery design, PS5 UI registration required brittle overrides, Vue overlay controls easier to style.

Project customizations: Mobile info button/metadata sheet integration, desktop metadata panel, tablet panel/controls, interaction with VSBS mobile sheet, `metadataOpen` hides info button while sheet open.

Integration files: `frontend/src/components/Lightbox.vue`, `MobilePhotoSwipe.vue`, `TabletPhotoSwipe.vue`, `PhotoSwipeViewer.vue`, `frontend/src/composables/usePhotoSwipe.ts`, `frontend/src/styles/_lightbox-*.scss`

Common pitfalls: PhotoSwipe focus/keyboard can conflict with another modal/focus trap, do not enable another focus trap inside PhotoSwipe without testing, mobile vertical drag can conflict with bottom sheet, default PhotoSwipe UI styles can leak, desktop sidebar can overlap image if viewport is not adjusted.

Decision: We use PhotoSwipe as the image viewer engine. Gallery owns metadata panels, custom controls, and responsive layout around it.

Mobile contract: PhotoSwipe owns image rendering, swipe left/right, pan/zoom, lightbox lifecycle, photo-area pointer/touch handling, and lightbox close. VSBS and outside-tap glue must never block image swipe before or after the metadata sheet opens and closes.

### Other libraries

#### Fuse.js

Official links:

- Docs: https://www.fusejs.io/
- GitHub: https://github.com/krisk/Fuse
- npm: https://www.npmjs.com/package/fuse.js

Used for: Lightweight client-side fuzzy filtering of already loaded gallery folders/images when the normal gallery view needs local filtering behavior.

Core features we use: weighted keys, fuzzy matching, typo tolerance, `ignoreLocation`, client-side index.

Features we intentionally do NOT use: match highlighting, metadata/prompt full-text search, binary/image content search.

Why: Keeps a small local fuzzy-search helper available for loaded gallery rows without making the frontend responsible for recursive indexed search.

Integration files: `frontend/src/utils/fuzzySearch.ts`, `frontend/src/components/GalleryGrid.vue`, `frontend/package.json`, `frontend/package-lock.json`

Common pitfalls: Do not rebuild Fuse per card, do not use Fuse for active unified search results, do not let `path` weight dominate `name`, do not break existing sort behavior, do not add match highlighting unless UI is designed for it.

Decision: One visible search box calls backend `/api/search` for active search. Fuse remains as a local helper for normal loaded gallery rows only. Backend SQLite FTS5 owns recursive album/photo filename search and prompt/metadata search.

#### SQLite FTS5

- Official: https://www.sqlite.org/fts5.html
- Used for: backend unified search over indexed folders/photos and AI prompt/metadata text.
- Integration files: `backend/services/metadata_index.py`, `backend/main.py`
- Database location: `backend/.cache/gallery_metadata.db`
- Runtime dependency: Python stdlib `sqlite3` with SQLite FTS5 enabled.

The shared search database stores:

- `file_index`: one row per indexed folder/photo, including path, name, parent path, type, mtime, size, and dimensions when available.
- `file_index_fts`: standalone FTS5 table for folder/photo filename search. It powers the Albums and Photos result sections.
- `image_metadata`: normalized metadata keyed by image path.
- `image_metadata_fts` and `image_metadata_fts_trigram`: prompt/metadata FTS5 tables for the Prompt result section.

Unified search behavior:

- One search box in the frontend calls `GET /api/search`.
- Default scope is `This folder`, meaning the current folder and all indexed subfolders recursively.
- `All indexed` searches the whole indexed database under `GALLERY_ROOT`.
- Results are grouped into Albums, Photos, and Prompt.
- Recursive subfolder matches include `relative_path`, computed from the selected current folder or from `GALLERY_ROOT`.
- Prompt search joins metadata rows through `file_index`, so prompt matches follow the same scope filtering as album/photo filename matches.

The metadata index stores normalized fields in `image_metadata` and keeps two FTS5 virtual tables in sync with triggers:

- `image_metadata_fts` uses `tokenize='unicode61'` for English prompts, filenames, model names, and sampler names.
- `image_metadata_fts_trigram` uses `tokenize='trigram'` for Japanese/CJK substring search.

CJK support deliberately avoids MeCab, Sudachi, Kuromoji, and custom native tokenizers. Short CJK queries and no-result trigram searches fall back to safe parameterized `LIKE` over indexed text fields.

Not used: Meilisearch, Typesense, Tantivy, Whoosh, sqlite-vec, or any external search service.

Backward compatibility: `/api/search-metadata` still exists for older callers, but the main gallery UI uses `/api/search`.

#### Pillow

- Official: https://pillow.readthedocs.io/
- Used for: thumbnail generation, image dimensions, EXIF orientation, and metadata extraction for the SQLite index.

Metadata search reads Pillow-exposed PNG text chunks and basic EXIF/UserComment text. Current indexed formats include A1111/Forge `parameters`, ComfyUI `prompt`/`workflow` JSON as searchable raw/basic summary text, and generic keys such as `Description`, `Comment`, `UserComment`, and `Software`.

ExifTool is intentionally not used in this implementation. It remains deferred because it requires an external binary and process integration.

#### diskcache

- Official: https://grantjenks.com/docs/diskcache/
- Used for: persistent WebP thumbnail caching.
- Integration files: `backend/main.py`, `backend/requirements.txt`
- Cache location: `backend/.cache/thumbnails/`

Thumbnail cache keys include the resolved source path, source `mtime_ns`, source byte size, requested max size, and WebP quality. Changing the source image or requested thumbnail size creates a new cache key automatically. The endpoint serves persisted thumbnail files with `Cache-Control: public, max-age=86400, immutable`, `ETag`, `Content-Length`, and `Last-Modified` headers.

#### cachetools

- Official: https://cachetools.readthedocs.io/
- Used for: in-memory metadata response caching only.
- Integration files: `backend/main.py`, `backend/requirements.txt`

`cachetools.LRUCache` is no longer used for thumbnail bytes. Metadata caching still uses explicit locks and in-flight request de-duplication around the in-memory LRU cache.

#### Vue 3

- Official: https://vuejs.org/
- Used for: entire frontend framework
- Core usage: Composition API, SFC, `<script setup>`

#### Vite

- Official: https://vite.dev/
- Used for: frontend build tool, dev server
- Customization: no custom plugins beyond defaults

#### Lucide

- Official: https://lucide.dev/
- Used for: icons across the gallery

#### @tanstack/vue-virtual

- Library: TanStack Virtual (row-based virtualization)
- Official Vue docs: https://tanstack.com/virtual/latest/docs/framework/vue/vue-virtual
- Used for: `GalleryGrid.vue` desktop/tablet photo grid, with row-based virtualization via `useVirtualizer`

#### @tanstack/vue-form

- Library: TanStack Form (type-safe Vue form validation)
- Official Vue docs: https://tanstack.com/form/latest/docs/framework/vue
- Status: Foundation installed, not yet used in any component
- Planned use: photo metadata editing, batch editor, import settings
- See `frontend/src/lib/tanstack/README.md` for details

#### @tanstack/vue-table

- Library: TanStack Table (headless datagrid/table)
- Official Vue docs: https://tanstack.com/table/latest/docs/framework/vue
- Status: Foundation installed, not yet used in any component
- Planned use: metadata management table, duplicate/broken image audit, import history
- See `frontend/src/lib/tanstack/README.md` for details

#### @tanstack/vue-query-devtools

- Library: TanStack Query Devtools
- npm: @tanstack/vue-query-devtools
- Status: Installed as devDependency, active in dev mode only
- Usage: Floating devtools panel visible in browser during development; tree-shaken in production

## Do Not Change Casually

- Do not enable VSBS `blocking=true` without testing focus recursion with PhotoSwipe.
- Do not move VSBS overrides back into scoped-only styles.
- Do not remove VSBS width/background overrides.
- Do not reintroduce old custom mobile sheet drag code.
- Do not add `stopPropagation()` to mobile outside-tap close.
- Do not replace Vue overlay buttons with PhotoSwipe UI registration unless necessary.
