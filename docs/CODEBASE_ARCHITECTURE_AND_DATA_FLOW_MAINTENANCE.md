# Codebase Architecture & Data Flow — Maintenance Guide

## Repo Overview

This is a local-first AI art gallery web application. Stack:

- **Backend**: Python FastAPI (async) — serves image files, generates WebP thumbnails, parses AI generation metadata (A1111/SwarmUI/ComfyUI/NovelAI/EasyDiffusion)
- **Frontend**: Vue 3 + TypeScript + Vite + Pinia — gallery grid with virtual scroll, PhotoSwipe 5 lightbox, responsive mobile/tablet/desktop layouts
- **Startup**: `start.py` (Python script) — auto-creates venv, installs pip & npm deps, launches both servers

The app is designed for **local/personal use only** (`is_safe_path` returns `True` for all paths).

---

## Directory Structure (Key Paths)

```
gallery-repo/
├── start.py                          # Auto-launch script (venv, pip, npm, servers)
├── backend/
│   ├── main.py                       # FastAPI server (~1218 lines) — all endpoints
│   └── requirements.txt
├── frontend/
│   ├── package.json                  # Vue 3.5, Vite 7, Pinia 3, PhotoSwipe 5.4, vue-virtual-scroller 3
│   ├── dist/                         # Production build output
│   ├── public/
│   │   └── landpage/                 # Intro screen HTML templates
│   └── src/
│       ├── main.ts                   # Entry: Pinia + global styles + eruda debug + mount App.vue
│       ├── App.vue                   # Root: dispatches per-device layout + Lightbox + modals
│       ├── constants.ts              # IMAGE_PAGE_SIZE = 200
│       ├── injectionKeys.ts          # Vue provide/inject keys (scroll container ref, closeSidebar)
│       ├── types/
│       │   └── index.ts              # FileNode, ScanResponse, MetadataResponse, etc.
│       ├── services/
│       │   └── api.ts                # Axios client + error types (GalleryAPIError)
│       ├── stores/
│       │   ├── gallery.ts            # Gallery state: folders, images, nav, search, sort, hasEverLoaded
│       │   ├── lightbox.ts           # Lightbox state: open/close, metadata, navigation
│       │   └── toast.ts              # Toast notification state (max 3, auto-dismiss)
│       ├── composables/              # (listed below)
│       ├── components/               # (listed below)
│       ├── layouts/                  # (listed below)
│       ├── styles/                   # (listed below)
│       ├── directives/
│       │   └── clickOutside.ts       # v-click-outside directive
│       └── utils/
│           ├── loraHighlighter.ts    # LoRA tag regex highlighting
│           ├── lightbox.ts           # buildPhotoSwipeItem() shared helper
│           ├── erudaDebug.ts         # Eruda mobile debug console (dev-only)
│           └── iconDebugOverlay.ts   # Icon metrics overlay (dev-only, ?iconDebug=1)
└── resource/                         # Reference materials (palettes, poses)
```

### Components

| File | Role |
|------|------|
| `App.vue` | Root layout: dispatches to DesktopLayout / TabletLayout / MobileLayout + Lightbox (lazy-loaded) + SettingsModal + ToastContainer |
| `GalleryGrid.vue` | Photo grid with RecycleScroller (desktop) / native scroll (mobile), search/sort, tablet toolbar, pull-to-refresh |
| `Lightbox.vue` | Per-device lightbox: dispatches to PhotoSwipeViewer / TabletPhotoSwipe / MobilePhotoSwipe + metadata panels |
| `PhotoSwipeViewer.vue` | Thin PhotoSwipe 5 wrapper for desktop/wide (uses shared usePhotoSwipe composable) |
| `TabletPhotoSwipe.vue` | Dedicated PhotoSwipe 5 wrapper for tablet — owns counter, zoom toggle, bottom toolbar with close/zoom/info buttons |
| `MobilePhotoSwipe.vue` | PhotoSwipe 5 wrapper for mobile — self-registers metadata info button via PS5 UI API |
| `LightboxDesktopPanel.vue` | Right sidebar metadata panel (desktop/wide) — accordion sections |
| `LightboxTabletPanel.vue` | 2-column bottom sheet (tablet) — accordion, touch-to-expand |
| `LightboxMobileSheet.vue` | Tabbed bottom sheet (mobile) — Prompt/Params tabs, haptic feedback |
| `AlbumScroller.vue` | Horizontal album scroll with arrow navigation, collapse toggle |
| `AlbumCard.vue` | Folder card with neon glow (desktop) |
| `AlbumCardTablet.vue` | Folder card for tablet |
| `AlbumCardMobile.vue` | Folder card for mobile |
| `PhotoCard.vue` | Image card in grid |
| `AppHeader.vue` | Desktop header: search, sort, theme, settings |
| `MobileHeader.vue` | Mobile header: hamburger, search (expandable), theme |
| `TabletHeader.vue` | Tablet header: hamburger, breadcrumb, expandable search, theme |
| `MobileFloatingBottomBar.vue` | Mobile pill nav: back/forward, folder name, open-explorer |
| `SidebarHeader.vue` | Sidebar title + root path input + load button |
| `FolderTreeItem.vue` | Recursive folder tree (collapsible) |
| `Breadcrumb.vue` | Path breadcrumb with dropdown ellipsis |
| `TabletGalleryToolbar.vue` | Tablet toolbar: nav arrows, sort, density (popover menus) |
| `GlowContainer.vue` | CSS glow bleed wrapper |
| `SettingsModal.vue` | Settings dialog (intro preview, etc.) |
| `IntroScreen.vue` | Welcome/landing page (loads HTML from public/landpage) |
| `SkeletonLoader.vue` | Loading skeleton |
| `EmptyState.vue` | 7 empty/error states with inline SVG icons |
| `Toast*.vue` | Toast notification components |

### Composables

| File | Purpose |
|------|---------|
| `useDevice.ts` | Singleton breakpoint detection (compact <480, mobile <768, tablet <1200, desktop <1440, wide >=1440). Uses ref-count pattern for shared resize listener. |
| `usePhotoSwipe.ts` | Shared PhotoSwipe 5 lifecycle: init on isOpen, destroy on close/unmount, currentIndex sync, shared item building via buildPhotoSwipeItem(), avoids duplicate instances |
| `useColumnResize.ts` | Grid density: slider level (1–5) mapped to columns via GRID_COLUMN_MAP per device category (desktop/tablet/mobile). ResizeObserver on grid container, localStorage persistence |
| `useScrollVisibility.ts` | Mobile header/bottom-bar hide/show on scroll (rAF-throttled), polling fallback, MutationObserver |
| `usePullToRefresh.ts` | Touch pull-to-refresh gesture handler |
| `useMetadataSections.ts` | Metadata section config: core/secondary/advanced categories |
| `useClipboard.ts` | Clipboard copy with HTTP fallback (`document.execCommand('copy')`) |
| `useHaptic.ts` | `navigator.vibrate()` wrapper (10ms/20ms) |
| `useNaturalSort.ts` | Natural sort (1, 2, 10 instead of 1, 10, 2) |
| `useFocusTrap.ts` | WCAG focus trap for modals |
| `useToast.ts` | Toast composable helper |

### Stores (Pinia)

| Store | State | Actions |
|-------|-------|---------|
| `gallery.ts` | rootPath, sidebarTree, currentPath, galleryFolders, galleryImages, nextImageCursor, totalImages, history[], searchQuery, sortField/Order, hasEverLoaded | `setRootPath`, `toggleFolder`, `selectFolder`, `scanFolder`, `loadMoreImages`, `goBack`/`goForward`, `openInExplorer` |
| `lightbox.ts` | isOpen, itemPath, itemName, width, height, metadata, galleryItems[], currentIndex | `open`, `loadMetadata`, `next`, `prev`, `close`, `preloadNeighbors` |
| `toast.ts` | toasts[] | `addToast`, `removeToast`, `clearAll`, `success`, `error`, `warning`, `info` |

### Styles

| File | Content |
|------|---------|
| `main.scss` | Global styles, animations (iconFlicker, dark-title-shimmer), accessibility, responsive breakpoints, scroll-container chain |
| `tokens.css` | Design tokens v2: `--gallery-*` vars (surface, text, accent, border, shadow, radius, timing, typography, icon-sizes), light + dark theme, legacy variable mappings |
| `_breakpoints.scss` | SCSS mixins: compact (≤479px), mobile (≤767px), tablet (768-1199px), below-desktop (≤1199px), desktop (≥1200px), wide (≥1440px) |
| `_mobile-overrides.scss` | Mobile: disable glow, reset sticky hover, 44×44px touch targets, Safari background fix |
| `_lightbox-shared.scss` | Shared lightbox: loading/error, LoRA highlighter, param-pill, focus styles |
| `_lightbox-desktop.scss` | Desktop metadata panel: right sidebar 400px, backdrop-filter blur |
| `_lightbox-tablet.scss` | Tablet bottom sheet: 2-column grid, max-height 65vh, expandable |
| `_lightbox-mobile.scss` | Mobile bottom sheet: tabbed (Prompt/Params), draggable handle, 44dvh height |

### Layouts

| File | Role |
|------|------|
| `DesktopLayout.vue` | Desktop layout: 280px persistent sidebar + edge toggle + AppHeader + GalleryGrid |
| `TabletLayout.vue` | Tablet layout: 280px animated drawer (transform + inert) + backdrop + TabletHeader + GalleryGrid |
| `MobileLayout.vue` | Mobile layout: 240px overlay sidebar + MobileHeader + GalleryGrid + MobileFloatingBottomBar |

### Utilities

| File | Role |
|------|------|
| `lightbox.ts` | Shared `buildPhotoSwipeItem()` — builds PhotoSwipe data from FileNode with thumbnail/full-res URL, real dimensions (1200×1200 fallback) |
| `loraHighlighter.ts` | LoRA tag regex highlighting |
| `erudaDebug.ts` | Eruda mobile debug console — enable via `?eruda=1`, disable via `?eruda=0`, dev-only guard, localStorage persistence |
| `iconDebugOverlay.ts` | Icon SVG metrics overlay — enable via `?iconDebug=1`, shows viewport, layout presence, SVG computed metrics, force-40px buttons, dev-only |

---

## API Endpoints (All in `backend/main.py`)

| Method | Endpoint | Description | Key Details |
|--------|----------|-------------|-------------|
| GET | `/api/scan` | Scan directory — returns folders + images with pagination | Query params: `path`, `image_limit` (max 5000), `image_cursor`. Uses `os.scandir()` for perf. Folders sorted by natural sort, cover_images via `first_images_in_dir()` (3 newest). |
| GET | `/api/image` | Serve original image file | Returns `FileResponse` with `Cache-Control: public, max-age=31536000, immutable`. Blocks non-image files. |
| GET | `/api/thumbnail` | Serve WebP thumbnail (cached) | Query: `path`, `max_size` (1-4096, default 600). Quality 75, method 6. Uses 1GB LRU cache. Cache key includes (path, mtime, size, max_size, quality). |
| GET | `/api/metadata` | Parse AI generation metadata | Reads PNG chunks (`parameters`, `prompt`, `workflow`) and EXIF. Cached via 100MB LRU. Detects: SwarmUI, ComfyUI, A1111, NovelAI, EasyDiffusion. Falls back to `.txt` sidecar file. |
| POST | `/api/open-folder` | Open folder in OS file explorer | Disabled by default (`GALLERY_OPEN_FOLDER=false`). Uses `xdg-open` (Linux), `open` (macOS), `os.startfile` (Windows). |
| GET | `/api/health` | Health check | Returns `{"status": "ok"}` |
| GET | `/api/landing-pages` | List intro page HTML files | Walks `frontend/public/landpage/` for `.html` files |
| GET | `/` | Root (production) | In production mode serves `frontend/dist/index.html` |
| GET | `/{path:path}` | SPA catch-all | Production only — serves static files or falls back to `index.html` |

### Backend Details

- **Thumbnail pipeline**: `_check_image_limits()` (75MB / 100MP guard) → `_render_thumbnail_impl()` (EXIF auto-rotate, RGBA→RGB, thumbnail LANCZOS, WebP output) → LRU cache with dedup via `Future` pattern
- **Metadata pipeline**: `_parse_metadata_uncached()` → priority: SwarmUI JSON > ComfyUI JSON > A1111 text / NovelAI / EasyDiffusion > `.txt` sidecar
- **Security**: `is_path_safe()` checks resolved path is under `GALLERY_ROOT` env var (default `/`)
- **CORS**: origins from `FRONTEND_ORIGIN`/`FRONTEND_PORT` env vars + VPS IP origins
- **Production mode**: `PRODUCTION=1` env var — backend serves `frontend/dist/` as SPA

---

## Frontend Entry & Layout

### main.ts (Line 1-13)
```
import styles → createApp(App) → use(Pinia) → mount(#app)
```

### App.vue Layout Hierarchy
```
<App>
  <IntroScreen />                           (v-if showIntro)
  <MobileLayout v-else-if="isMobile" />      (props + events for store actions)
  <TabletLayout v-else-if="isTablet" />      (props + events for store actions)
  <DesktopLayout v-else />                   (props + events for store actions)
  <Lightbox />                               (defineAsyncComponent, always mounted, v-if show)
  <ToastContainer v-if="!isMobile" />
  <SettingsModal />
```

Each layout component is self-contained with its own sidebar, header, and GalleryGrid sections. App.vue acts as a state-passing orchestration layer.

### Device Breakpoints (from `useDevice.ts` + `_breakpoints.scss` + `useColumnResize.ts`)

| Breakpoint | JS Constant | SCSS Mixin | Range | Default Grid | Grid Range |
|------------|-------------|------------|-------|--------------|------------|
| Compact | `BREAKPOINTS.compact = 480` | `@include compact` | <480px | 2 col | 2–3 col |
| Mobile | `BREAKPOINTS.mobile = 768` | `@include mobile` | 480–767px | 2 col | 2–3 col |
| Tablet | n/a | `@include tablet` | 768–1199px | 4 col | 3–5 col |
| Desktop | `BREAKPOINTS.desktop = 1200` | `@include desktop` | 1200–1439px | 6 col | 4–8 col |
| Wide | `BREAKPOINTS.wide = 1440` | `@include wide` | ≥1440px | 6 col | 4–8 col |

Grid columns are derived from slider level (1–5) mapped through `GRID_COLUMN_MAP` in `useColumnResize.ts`:
```typescript
GRID_COLUMN_MAP = {
  desktop: [8, 7, 6, 5, 4],  // level 1=8 cols, ..., level 5=4 cols
  tablet:  [5, 5, 4, 3, 3],  // level 1=5 cols, ..., level 5=3 cols
  mobile:  [3, 3, 2, 2, 2],  // level 1=3 cols, ..., level 5=2 cols
}
```
The slider defaults to level 3 (Medium). Each `isMobile`/`isTablet`/`isDesktop` computed property in `useDevice` covers the correct range. JS `< 768` matches SCSS `max-width: 767px`; JS `< 1200` matches SCSS `max-width: 1199px`. These are functionally equivalent.

---

## Data Flow

### 1. User Loads a Folder (sidebar → scan → grid)

```
Click folder in sidebar → FolderTreeItem emits
→ galleryStore.selectFolder(path)
→ store.pushHistory(path)
→ store.scanFolder(path)
→ api.scanDirectory(path, { imageLimit: 200, imageCursor: 0 })
→ GET /api/scan?path=...&image_limit=200&image_cursor=0
→ Response: { folders: FileNode[], images: FileNode[], next_cursor, total_images }
→ store.galleryFolders = data.folders
→ store.galleryImages = data.images
→ GalleryGrid reactively renders AlbumScroller + RecycleScroller
```

### 2. User Clicks a Photo (grid → lightbox)

```
Click PhotoCard
→ GalleryGrid.handleOpenImage(path, name)
→ lightboxStore.open({ path, name }, images)
→ Store: isOpen=true, galleryItems=[...filtered images], currentIndex=N
→ lightboxStore.preloadNeighbors() — creates Image objects for +-1
→ lightboxStore.loadMetadata(path)
→ GET /api/metadata?path=...
→ Lightbox.vue: Transition "fade" renders
→ Desktop:  PhotoSwipeViewer + LightboxDesktopPanel (right sidebar, 400px)
→ Tablet:   TabletPhotoSwipe (bottom bar: counter + zoom + close + info) + toggle → LightboxTabletPanel
→ Mobile:   MobilePhotoSwipe (registers info button in PS5 UI) + toggle → LightboxMobileSheet
```

### 5. Lightbox Navigation (arrow keys / PS5 swipe / toolbar)

```
Desktop/Tablet/Mobile: usePhotoSwipe composable handles PS5 lifecycle
→ on("change") → emit("indexChange", index)
→ Lightbox.handleIndexChange / handlePhotoSwipeIndexChange
→ lightboxStore.currentIndex = newIndex; loadMetadata()
→ usePhotoSwipe watcher: pswp.goTo(index) only when pswp.currIndex !== index

Tablet: TabletPhotoSwipe additionally owns zoom toggle (via pswp ref)
Mobile: MobilePhotoSwipe additionally owns PS5 UI registration for info button
```
Click PhotoCard
→ GalleryGrid.handleOpenImage(path, name)
→ lightboxStore.open({ path, name }, images)
→ Store: isOpen=true, galleryItems=[...filtered images], currentIndex=N
→ lightboxStore.preloadNeighbors() — creates Image objects for +-1
→ lightboxStore.loadMetadata(path)
→ GET /api/metadata?path=...
→ Lightbox.vue: Transition "fade" renders
→ Desktop: PhotoSwipeViewer + LightboxDesktopPanel
→ Tablet: PhotoSwipeViewer + Info button → LightboxTabletPanel
→ Mobile: MobilePhotoSwipe + Info button → LightboxMobileSheet
```

### 3. Infinite Scroll (load more images)

```
IntersectionObserver on loadMoreSentinel fires
→ GalleryGrid checks: hasMoreImages && !isLoadingMore
→ galleryStore.loadMoreImages()
→ api.scanDirectory(path, { imageLimit: 200, imageCursor: next_cursor })
→ GET /api/scan?path=...&image_limit=200&image_cursor=42
→ store.galleryImages = [...existing, ...data.images]
→ RecycleScroller reactively renders new rows
```

### 4. Search/Filter (search → GalleryGrid)

```
AppHeader/MobileHeader emits update:search-query
→ galleryStore.searchQuery = $event
→ GalleryGrid's computed `images` filters by name.toLowerCase().includes(query)
→ RecycleScroller re-renders with filtered data
```

### 5. Lightbox Navigation (arrow keys / PS5 swipe)

```
Desktop: Keyboard → Lightbox.handleKeydown (ArrowLeft/Right)
→ lightboxStore.prev() / lightboxStore.next()
→ Store: currentIndex++, preloadNeighbors(), loadMetadata()
→ PhotoSwipeViewer watches currentIndex → pswp.goTo(index)
→ Metadata panel reactively updates

Mobile: PhotoSwipe handles swipe gestures
→ MobilePhotoSwipe emits "change" event
→ Lightbox.handlePhotoSwipeIndexChange(newIndex)
→ lightboxStore.currentIndex = newIndex; loadMetadata()
```

---

## Debug Quick-Start

| Symptom | Check These Files | What to Look For |
|---------|-------------------|------------------|
| **Scroll not loading more images** | `frontend/src/components/GalleryGrid.vue` (lines 219-255) | `loadMoreSentinel` ref, `IntersectionObserver` setup, `root: null` + `rootMargin: "400px"`. Ensure `.scroller` has `overflow-y: auto` and proper height. |
| **Lightbox shows black screen** | `frontend/src/components/PhotoSwipeViewer.vue` (lines 27-42) | `pswpItems` computed: are `src` URLs valid? Check `getThumbnailUrl()` or `getImageUrl()`. Check `containerRef` is mounted. |
| **Lightbox right arrow unclickable** | `frontend/src/components/Lightbox.vue` (lines 436-452) | `.pswp__button--arrow--next` `right: calc(var(--lightbox-sidebar-width) + var(--lightbox-arrow-gap))`. If `.lightbox-right` has different width, arrow is hidden under it. |
| **API errors / Mixed content warning** | `frontend/src/services/api.ts` (line 4) | `VITE_API_URL` fallback to `""` — in dev, this means API calls go to same origin as frontend. `start.py` sets `VITE_API_URL=http://127.0.0.1:{backend_port}`. If not set via env, check if Vite proxy is configured. |
| **Swipe on mobile flickers / doesn't close** | `frontend/src/components/MobilePhotoSwipe.vue` (lines 37-51) | `closeOnVerticalDrag: true`, `allowPanToNext: true`. Check that `pswpModule` is not causing issues (it's unused dead code). |
| **Metadata panel shows empty** | `backend/main.py` (lines 853-1067) | `_parse_metadata_uncached()` → check if metadata is in PNG `parameters` chunk, `prompt` chunk, `workflow` chunk, or EXIF `UserComment`. |
| **Grid layout broken / no columns** | `frontend/src/composables/useColumnResize.ts` (lines 22-27) | `columnCount` computed from viewport width. `rowHeight` must be >0 for RecycleScroller to render. Check ResizeObserver on `.scroller-container`. |
| **Mobile bars don't hide on scroll** | `frontend/src/composables/useScrollVisibility.ts` (lines 16-46) | Polls for `.vue-recycle-scroller` via `setInterval(200)`. Check that `attachedElement` has scroll events. Near-bottom guard (`scrollHeight - clientHeight - scrollTop < 150`). |
| **Theme persists wrong / flash** | `frontend/src/App.vue` (lines 40-56, 98-142) | `localStorage.getItem('gallery-theme')` on mount. `index.html` has inline FOUC prevention script. Check that `data-theme` attribute is applied synchronously. |
| **Backend 403 on API call** | `backend/main.py` (lines 316-325) | `is_path_safe()` — resolved path must be under `GALLERY_ROOT` (default `/`). Check `GALLERY_ROOT` env var. |
| **Backend CORS error** | `backend/main.py` (lines 79-107) | `_get_cors_origins()` uses `FRONTEND_ORIGIN` + `FRONTEND_PORT` env vars. Default: `http://localhost:5173`. `start.py` sets `FRONTEND_PORT` env. |

---

## Known Regression Risks

1. **api.ts line 4 — Mixed content / missing VITE_API_URL**
   `const API_BASE = import.meta.env.VITE_API_URL || "";`
   If `VITE_API_URL` is not set at build time or start time, API calls use the same origin as the frontend. In dev (port 5173) this means requests to `/api/scan` go to Vite, which must proxy to FastAPI (port 8000). If no Vite proxy config exists and VITE_API_URL is empty, API calls fail silently.

2. **RecycleScroller `page-mode`** (vue-virtual-scroller v3)
   GalleryGrid uses RecycleScroller with the scroller container having `overflow-y: auto`. The scroller must have a **fixed height** (via `flex: 1; min-height: 0` on parent chain). If the height chain breaks (e.g., a parent removes `min-height: 0`), RecycleScroller renders zero items.

3. **Stacking context: sidebar vs PhotoSwipe arrows**
   - `.lightbox-overlay`: `z-index: 9999`
   - `.lightbox-right` (desktop panel): `z-index: 10000`
   - `.photoswipe-container`: `z-index: 1` (inside overlay)
   - `.pswp__button--arrow--next`: positioned by CSS `right: calc(400px + 16px)` to avoid being under `.lightbox-right`
   - If `.lightbox-right` width changes (min-width 320px, max-width 450px), the arrow position must be adjusted.

4. **`useDevice.ts` breakpoint changes**
   Any change to `BREAKPOINTS` values must be mirrored in `_breakpoints.scss` mixins AND in `useColumnResize.ts` (which has its own deviceCategory mapping). These are NOT DRY — updating one requires updating all three.

5. **`useScrollVisibility.ts` polling fallback**
   When no `containerRef` is provided (mobile path without injected ref), it falls back to polling `document.querySelector('.vue-recycle-scroller, .scroller, .folders-only-container')` every 200ms until found. This is fragile if the scroller CSS class changes.

6. **TabletPhotoSwipe vs PhotoSwipeViewer — separate component files**
   Tablet and Desktop lightbox now use different wrapper components. TabletPhotoSwipe owns its own bottom toolbar (counter, zoom, close, info buttons) and manages zoom state. Changes to the shared `usePhotoSwipe` composable must be tested on both. The `thumbnailSize` differs: desktop 2400px, tablet 2048px, mobile 1600px.

7. **GRID_COLUMN_MAP — device-specific column mapping**
   Changing slider level values or device column maps affects all three devices. The map entries are indexed by deviceCategory string. If a new device category is added, a corresponding entry must be added to the map or it falls back to `desktop`.

8. **Thumbnail cache invalidation**
   Cache key includes `(path, mtime, size, max_size, quality)`. If the file's mtime or size changes, the cache entry is re-created. However, the 1GB LRU cache has no TTL — old entries are only evicted when the cache is full.

9. **Decompression bomb guards**
   `_check_image_limits()` (backend/main.py lines 354-384) checks file size (75MB) and pixel dimensions (100MP) before opening. If these limits are hit, the user gets a 400 error. The frontend displays this as "Invalid file" via `GalleryAPIError`.

10. **`useColumnResize.ts` grid size localStorage key**
    `GRID_SIZE_KEY = 'gallery-grid-size'` — stored per origin. Column count is now a slider level (1–5), not raw column count. Legacy raw values (1–8) are migrated via `migrateColumnsToLevel()`. The column mapping is per deviceCategory.

11. **Safari Private Browsing — localStorage**
    Multiple files wrap `localStorage` calls in try/catch for Safari Private Browsing compatibility: `App.vue`, `gallery.ts`, `useColumnResize.ts`, `AlbumScroller.vue`. If a new localStorage access is added without the try/catch, the app will crash in Private Browsing mode.

12. **Layout components — App.vue orchestration**
    App.vue no longer contains inline layout markup. Desktop/tablet/mobile layouts are separate components receiving props + emitting events. Props/event name changes in App.vue must be reflected in all three layout components.

---

## Component Tree (Detailed)

```
App.vue
├── IntroScreen.vue (v-if showIntro)
├── MobileLayout.vue (v-else-if isMobile)
│   ├── aside.sidebar (overlay, 240px)
│   │   ├── SidebarHeader.vue
│   │   └── FolderTreeItem.vue (recursive, v-for tree)
│   ├── section.content
│   │   ├── MobileHeader.vue
│   │   ├── div.content-body
│   │   │   └── GalleryGrid.vue
│   │   │       ├── pull-to-refresh
│   │   │       ├── AlbumScroller.vue (v-if folders.length)
│   │   │       │   ├── AlbumCardMobile.vue
│   │   │       │   └── GlowContainer.vue
│   │   │       ├── PhotoCard.vue (native scroll, v-for rows)
│   │   │       ├── SkeletonLoader.vue (v-if isLoading)
│   │   │       ├── Breadcrumb.vue
│   │   │       └── EmptyState.vue
│   │   └── MobileFloatingBottomBar.vue
│   └── sidebar-backdrop
├── TabletLayout.vue (v-else-if isTablet)
│   ├── aside.sidebar (drawer, 280px, transform + inert)
│   │   ├── SidebarHeader.vue
│   │   └── FolderTreeItem.vue
│   ├── sidebar-backdrop (Transition)
│   ├── section.content
│   │   ├── TabletHeader.vue
│   │   ├── div.content-body
│   │   │   └── GalleryGrid.vue
│   │   │       ├── TabletGalleryToolbar.vue
│   │   │       ├── AlbumScroller.vue
│   │   │       │   ├── AlbumCardTablet.vue
│   │   │       │   └── GlowContainer.vue
│   │   │       ├── PhotoCard.vue (RecycleScroller)
│   │   │       ├── SkeletonLoader.vue
│   │   │       └── EmptyState.vue
├── DesktopLayout.vue (v-else)
│   ├── aside.sidebar (persistent, 280px, collapsible)
│   │   ├── SidebarHeader.vue
│   │   ├── sidebar-edge-toggle
│   │   └── FolderTreeItem.vue
│   ├── section.content
│   │   ├── AppHeader.vue
│   │   ├── div.content-body
│   │   │   └── GalleryGrid.vue
│   │   │       ├── AlbumScroller.vue
│   │   │       │   ├── AlbumCard.vue
│   │   │       │   └── GlowContainer.vue
│   │   │       ├── PhotoCard.vue (RecycleScroller)
│   │   │       └── EmptyState.vue
├── Lightbox.vue (lazy-loaded, Teleport to body)
│   ├── PhotoSwipeViewer.vue (desktop/wide)
│   ├── TabletPhotoSwipe.vue (tablet) — counter + zoom/close/info toolbar
│   ├── MobilePhotoSwipe.vue (mobile) — self-registers info button
│   ├── LightboxDesktopPanel.vue (desktop/wide, v-if !isFullscreen)
│   ├── LightboxTabletPanel.vue (tablet, v-if showSheet)
│   └── LightboxMobileSheet.vue (mobile, v-if showSheet)
├── ToastContainer.vue (v-if !isMobile)
│   └── ToastItem.vue
└── SettingsModal.vue
```
