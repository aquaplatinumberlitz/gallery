# Museum Art Gallery — Architecture

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend Framework** | Vue 3 (Composition API + `<script setup>`) |
| **Language** | TypeScript |
| **Styling** | SCSS + CSS Custom Properties (design tokens) |
| **Build Tool** | Vite |
| **State Management** | Pinia (3 stores: gallery, lightbox, toast) |
| **Virtual Scrolling** | vue-virtual-scroller (RecycleScroller) |
| **Icons** | Lucide Vue Next |
| **HTTP Client** | Axios |
| **Backend** | FastAPI (Python 3.11) + Pillow + cachetools LRUCache |
| **Fonts** | Inter Variable, JetBrains Mono, Cinzel (Google Fonts) |

---

## File Structure

```
gallery/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.vue                          (502 lines — layout orchestrator, theme/intro/settings)
│       ├── main.ts                          (13 lines — app bootstrap)
│       ├── constants.ts                     (1 line — IMAGE_PAGE_SIZE = 200)
│       ├── env.d.ts                         (7 lines — Vite/Vue type declarations)
│       ├── assets/
│       │   └── fonts.css                    (31 lines — Google Fonts @import)
│       ├── components/
│       │   ├── AppHeader.vue                (633 lines — desktop search, theme toggle, brand hero, hamburger)
│       │   ├── AlbumCard.vue                (245 lines — album card with neon glow)
│       │   ├── AlbumScroller.vue            (400 lines — horizontal album scroll + arrows)
│       │   ├── BottomNavigationBar.vue      (76 lines — legacy mobile bottom nav, superseded by MobileFloatingBottomBar)
│       │   ├── Breadcrumb.vue               (526 lines — path breadcrumb with dropdown)
│       │   ├── EmptyState.vue               (491 lines — empty state illustrations)
│       │   ├── FolderTreeItem.vue           (221 lines — recursive folder tree item)
│       │   ├── GalleryGrid.vue              (1122 lines — main grid orchestrator)
│       │   ├── GlowContainer.vue            (49 lines — glow bleed wrapper, CSS variable-driven)
│       │   ├── IntroScreen.vue              (429 lines — intro/landing page with animations)
│       │   ├── Lightbox.vue                 (581 lines — image viewer orchestrator)
│       │   ├── LightboxDesktopPanel.vue     (217 lines — desktop metadata sidebar panel)
│       │   ├── LightboxTabletPanel.vue      (207 lines — iPad 2-column bottom sheet)
│       │   ├── LightboxMobileSheet.vue      (190 lines — phone bottom sheet, tabbed)
│       │   ├── MobileFloatingBottomBar.vue  (130 lines — mobile floating pill: back/forward, path, open in explorer)
│       │   ├── MobileHeader.vue             (197 lines — mobile header: hamburger, search, theme, settings)
│       │   ├── PhotoCard.vue                (304 lines — image thumbnail card, MD3 elevation)
│       │   ├── SettingsModal.vue            (390 lines — settings dialog)
│       │   ├── SidebarHeader.vue            (186 lines — sidebar top section)
│       │   ├── SkeletonLoader.vue           (108 lines — loading skeleton placeholders)
│       │   ├── ToastContainer.vue           (85 lines — toast notification container)
│       │   └── ToastItem.vue                (349 lines — individual toast notification)
│       ├── composables/
│       │   ├── useClipboard.ts              (51 lines — copy-to-clipboard with feedback)
│       │   ├── useColumnResize.ts           (85 lines — column count, row height, grid persistence)
│       │   ├── useDevice.ts                 (50 lines — singleton breakpoint detection)
│       │   ├── useFocusTrap.ts              (138 lines — focus trap for modals/lightbox)
│       │   ├── useNaturalSort.ts            (32 lines — natural sort for filenames)
│       │   ├── useScrollVisibility.ts       (58 lines — mobile header/bottom-bar show/hide on scroll)
│       │   └── useToast.ts                  (97 lines — toast notification management)
│       ├── directives/
│       │   └── clickOutside.ts              (30 lines — click-outside directive)
│       ├── services/
│       │   └── api.ts                       (197 lines — Axios API client)
│       ├── stores/
│       │   ├── gallery.ts                   (345 lines — main data store)
│       │   ├── lightbox.ts                  (111 lines — lightbox state)
│       │   └── toast.ts                     (148 lines — toast queue store)
│       ├── types/
│       │   ├── index.ts                     (62 lines — TypeScript interfaces/types)
│       │   └── vue-virtual-scroller.d.ts    (vue-virtual-scroller type declarations)
│       ├── utils/
│       │   └── loraHighlighter.ts           (36 lines — highlight <lora:...> tokens)
│       └── styles/
│           ├── main.scss                    (525 lines — global styles, dark mode overrides)
│           ├── tokens.css                   (60 lines — CSS custom properties for shadows/glow)
│           ├── _lightbox-shared.scss        (125 lines — shared lightbox panel styles)
│           ├── _lightbox-desktop.scss       (253 lines — desktop sidebar panel styles)
│           ├── _lightbox-mobile.scss        (237 lines — phone bottom sheet styles)
│           └── _lightbox-tablet.scss        (274 lines — iPad 2-column bottom sheet styles)
└── backend/
    └── main.py                              (1141 lines — FastAPI server)
```

---

## Component Architecture

### App Shell

```
App.vue
├── IntroScreen.vue              (conditional — shown on first visit)
├── SidebarHeader.vue            (sidebar top section: root folder, reset, info)
│   └── FolderTreeItem.vue       (recursive, 1 per folder node)
├── Breadcrumb.vue               (path breadcrumb with folder dropdown)
├── AppHeader.vue                (desktop/tablet: search bar, theme toggle, brand hero, hamburger, settings)
├── MobileHeader.vue             (mobile only: hamburger, expandable search, theme, settings)
│                                — uses barsVisible from useScrollVisibility for show/hide
├── GalleryGrid.vue              (main content area)
│   ├── AlbumScroller.vue        (horizontal scroll with arrow navigation)
│   │   └── AlbumCard.vue        (neon glow card — 1 per album)
│   │       └── GlowContainer.vue
│   ├── PhotoCard.vue            (thumbnail card — 1 per image, inside RecycleScroller)
│   ├── SkeletonLoader.vue       (loading state)
│   └── EmptyState.vue           (no results / empty folder state)
├── MobileFloatingBottomBar.vue  (mobile only: back/forward nav, path pill, open-in-explorer)
│                                — uses barsVisible from useScrollVisibility for show/hide
├── SettingsModal.vue            (conditional — settings dialog)
├── Lightbox.vue                 (lazy-loaded async component)
│   ├── LightboxDesktopPanel.vue (breakpoint: desktop)
│   ├── LightboxTabletPanel.vue  (breakpoint: tablet)
│   └── LightboxMobileSheet.vue  (breakpoint: phone/compact)
└── ToastContainer.vue
    └── ToastItem.vue            (1 per active toast)
```

### Component Responsibilities

#### `App.vue` — Layout Orchestrator (502 lines)
- Sidebar + content CSS Grid layout
- Theme controller (light/dark) via `data-theme` attribute on `:root`
- Intro screen show/hide orchestration
- Settings modal state
- Sidebar collapse/expand with responsive breakpoints (mobile overlay, tablet persistent)
- Mobile detection via `window.innerWidth` (640px threshold)
- Uses `useScrollVisibility` composable for mobile header/bar show/hide
- **Responsive breakpoints** (handled in App.vue + scoped CSS):
  - **≥ 1025px**: Full sidebar (280px), AppHeader + edge toggle
  - **641–1024px** (tablet): Persistent sidebar (240px), AppHeader, edge toggle hidden
  - **≤ 640px** (phone): Sidebar becomes fixed overlay, MobileHeader + MobileFloatingBottomBar appear
  - **≤ 480px** (small phone): Compact padding, sidebar full-width overlay

#### `MobileHeader.vue` — Mobile Top Bar (197 lines)
- Fixed top bar shown only on mobile (≤ 640px)
- Hamburger menu for sidebar toggle
- Expandable search bar with inline input
- Theme toggle (sun/moon SVG icons matching AppHeader)
- Settings gear button
- Smooth slide-away animation when scrolling down (`barsVisible` prop from `useScrollVisibility`)

#### `MobileFloatingBottomBar.vue` — Mobile Navigation Pill (130 lines)
- Floating pill bar at bottom of screen, only on mobile (≤ 640px)
- Back/Forward navigation buttons (disabled when at history bounds)
- Current folder name display with FolderOpen icon
- "Open in File Explorer" button
- Smooth slide-away when scrolling down (`barsVisible` prop from `useScrollVisibility`)

#### `AppHeader.vue` — Desktop/Tablet Header UI (633 lines)
- Search bar with debounced input
- Theme toggle button (sun/moon icon)
- Brand hero / logo display
- Mobile hamburger menu trigger (tablet only)
- Settings gear button

#### `SidebarHeader.vue` — Sidebar Top (186 lines)
- Current root folder display
- Reset/refresh button
- Info/help trigger

#### `FolderTreeItem.vue` — Recursive Folder Tree (221 lines)
- Self-referential: renders children as more `FolderTreeItem` instances
- Expand/collapse toggle
- Active folder highlighting
- Lazy-loading of children on expand

#### `Breadcrumb.vue` — Path Navigation (526 lines)
- Breadcrumb trail from root to current folder
- Each segment is a clickable dropdown showing sibling folders
- Handles deep folder navigation

#### `BottomNavigationBar.vue` — Legacy Mobile Nav (76 lines)
- Superseded by `MobileFloatingBottomBar.vue`
- No longer rendered in App.vue component tree
- Kept in codebase for potential future use or reference

### Gallery Grid

#### `GalleryGrid.vue` — Main Orchestrator (1122 lines)
The largest component. Responsibilities:
- **Album scroller**: renders `AlbumScroller` above the grid
- **Photo grid**: `RecycleScroller` with `PhotoCard` items
- **Sort controls**: dropdown for sort field (name/date) and order (asc/desc)
- **Infinite scroll**: detects scroll near bottom, loads next page (200 images/page)
- **Column count**: delegates to `useColumnResize`
- **Natural sort**: delegates to `useNaturalSort`
- **Click handler**: opens `Lightbox` on image click

#### `AlbumScroller.vue` — Horizontal Album Scroll (400 lines)
- Horizontal scroll container with left/right arrow navigation
- Renders `AlbumCard` for each album
- Wrapped in `GlowContainer` for glow bleed
- Handles dynamic album loading as user navigates folders

#### `AlbumCard.vue` — Album Card with Glow (245 lines)
- Thumbnail with album name and image count
- Neon orange glow effect on hover (dark mode only)
- Consumes `--glow-*` CSS variables from ancestor `GlowContainer`

#### `PhotoCard.vue` — Image Thumbnail (304 lines)
- Image thumbnail with MD3 elevation shadow
- Lazy-loaded image with aspect-ratio placeholder
- Filename overlay on hover
- Click emits `select` event to open lightbox

#### `SkeletonLoader.vue` — Loading State (108 lines)
- Animated placeholder cards matching grid layout
- Shown during initial load and page transitions

#### `EmptyState.vue` — Empty States (491 lines)
- Multiple illustrations for: no images, no results (search), error states
- Inline SVG illustrations
- Contextual help text

#### `GlowContainer.vue` — Glow Bleed Wrapper (49 lines)
- Reusable wrapper component
- Accepts `bleed`, `bleedX`, `bleedY` props (px) to set `--glow-bleed-x` / `--glow-bleed-y` CSS variables
- Accepts `disabled` prop to disable glow (sets padding/margin to 0)
- Applies negative margin + positive padding equal to bleed value for overflow space
- Uses `pointer-events: none` to prevent negative-margin overflow from intercepting hover events on sibling elements
- Single source of truth for glow bleed padding across components

### Lightbox (Image Viewer)

#### `Lightbox.vue` — Orchestrator (581 lines)
- Lazy-loaded via `defineAsyncComponent` in `App.vue`
- Full-screen overlay with image display
- **Keyboard navigation**: Arrow keys (prev/next), Escape (close), F (fullscreen)
- **Wheel navigation**: scroll to navigate between images
- **Device routing**: renders the appropriate panel component based on `useDevice()` breakpoint
- **Preloading**: preloads adjacent images for instant navigation
- **Focus trap**: delegates to `useFocusTrap`

#### `LightboxDesktopPanel.vue` — Desktop Metadata Sidebar (217 lines)
- Breakpoint: `desktop` (≥1024px)
- Right sidebar panel with full metadata display
- Prompt, negative prompt, generation parameters (model, seed, steps, CFG, sampler, LoRAs)
- LoRA highlighting via `loraHighlighter`
- Copy-to-clipboard buttons via `useClipboard`

#### `LightboxTabletPanel.vue` — iPad 2-Column Bottom Sheet (207 lines)
- Breakpoint: `tablet` (768–1023px)
- Two-column layout at the bottom of the viewport
- Left column: image info (filename, dimensions, date)
- Right column: generation parameters
- Optimized for iPad Mini 8.4", iPad 10.2", iPad Pro 11"

#### `LightboxMobileSheet.vue` — Phone Bottom Sheet (190 lines)
- Breakpoint: `compact` / `phone` (<768px)
- Bottom sheet with tabbed interface (tabs: Info / Prompt / Params)
- Swipe-to-dismiss gesture area
- Compact layout for small screens (iPhone 6.1" and similar)

### UI Components

#### `SettingsModal.vue` — Settings Dialog (390 lines)
- Modal overlay with settings options
- Default sort field/order preferences
- Theme preference
- Intro page preview mode
- Other configurable options

#### `IntroScreen.vue` — Landing Page (429 lines)
- Full-screen animated intro shown on first visit
- Animated entrance with particle effects
- Preview mode triggered from settings
- "Enter Gallery" button
- Loads HTML landing pages from `public/landpage/` via iframe

#### `ToastContainer.vue` / `ToastItem.vue` — Notifications
- `ToastContainer` (85 lines) renders all active toasts from `toastStore`
- `ToastItem` (349 lines) handles individual toast: enter/exit animations, auto-dismiss, action buttons
- 4 types: success, error, warning, info

---

## Data Flow

```
┌─────────────────────────────────────────────────────────┐
│                   Backend (FastAPI :4180)                │
│  Endpoints:                                              │
│  GET  /api/scan?path=...&cursor=...&sort=...&order=...  │
│  POST /api/open-folder                                   │
│  GET  /api/thumbnail?path=...&size=...                   │
│  GET  /api/metadata?path=...                             │
│  GET  /api/image?path=...                                │
│                                                          │
│  Caching: LRUCache (1GB thumbnails, 100MB metadata)      │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTP (Axios)
                        ▼
┌─────────────────────────────────────────────────────────┐
│                   services/api.ts                        │
│  - openFolder(path): Promise<FileNode[]>                 │
│  - scanDirectory(path, cursor, sort, order): Promise<...>│
│  - fetchMetadata(path): Promise<MetadataResponse>        │
│  - getImageUrl(path): string                             │
│  - getThumbnailUrl(path, size): string                   │
│  - GalleryAPIError class for typed errors                │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                    Pinia Stores                          │
│                                                          │
│  galleryStore                                            │
│  ├── state: folders[], images[], currentPath,            │
│  │          sortField, sortOrder, cursor, loading, ...   │
│  ├── actions: openFolder(), loadImages(),                │
│  │            loadMoreImages(), setSort(), ...           │
│  └── getters: sortedImages, currentFolder, ...           │
│                                                          │
│  lightboxStore                                           │
│  ├── state: currentImage, isOpen, metadata, ...          │
│  └── actions: open(), close(), next(), prev(), ...       │
│                                                          │
│  toastStore                                              │
│  ├── state: toasts[] (queue)                             │
│  └── actions: add(), remove(), clear()                   │
└───────────────────────┬─────────────────────────────────┘
                        │ (via storeToRefs / direct store access)
                        ▼
┌─────────────────────────────────────────────────────────┐
│                  Vue Components                          │
│  Components subscribe to stores via storeToRefs().       │
│  User interactions dispatch store actions.               │
│  Data flows down as props where component-local.         │
└─────────────────────────────────────────────────────────┘
```

### Key Data Flow Paths

1. **Folder navigation**: User clicks folder → `galleryStore.openFolder(path)` → `api.openFolder()` → updates `folders`/`images` state → `GalleryGrid` re-renders
2. **Infinite scroll**: `GalleryGrid` detects scroll near bottom → `galleryStore.loadMoreImages()` → `api.scanDirectory(cursor)` → appends to `images` array
3. **Lightbox**: User clicks image → `lightboxStore.open(image)` → fetches metadata + preloads adjacent images → `Lightbox.vue` renders with appropriate device panel
4. **Theme toggle**: `AppHeader` or `MobileHeader` toggles → sets `data-theme` on `:root` → CSS variables switch light/dark
5. **Toast**: Any component calls `toastStore.add({ type, message })` → `ToastContainer` renders `ToastItem` → auto-dismiss after timeout
6. **Mobile scroll visibility**: `App.vue` calls `useScrollVisibility()` → `barsVisible` reactively controls MobileHeader/MobileFloatingBottomBar show/hide based on scroll direction inside `.vue-recycle-scroller`

---

## CSS Architecture

### Design Tokens (`tokens.css`)

60 lines of CSS custom properties on `:root` and `:root[data-theme="dark"]`.

**Light mode** (`:root`):
- `--shadow-card`, `--shadow-card-hover`, `--shadow-card-level2`, `--shadow-card-level4` — MD3 elevation shadows
- `--glow-color: transparent` (no glow in light mode)

**Dark mode** (`:root[data-theme="dark"]`):
- `--shadow-card`, `--shadow-card-level2` — dark layer shadows
- `--shadow-dark-layer-back`, `--shadow-dark-layer-front` — layered depth
- `--glow-color-20` through `--glow-color-70` — 8 opacity levels of `#FF6B35` (orange)
- `--glow-card-hover` — 6-layer composite orange glow
- `--glow-card-hover-front` — stronger glow for foreground elements
- `--glow-card-hover-back` — softer glow for background elements
- `--glow-card-active` — glow for active/selected state

→ Change the glow color in one place, all components update.

### SCSS Partials

| File | Lines | Purpose |
|------|-------|---------|
| `main.scss` | 525 | Global styles, CSS reset, layout grid, scrollbar, dark mode overrides, responsive breakpoints |
| `tokens.css` | 60 | Design tokens (CSS custom properties) |
| `_lightbox-shared.scss` | 125 | Shared styles for all lightbox panels (typography, buttons, metadata fields) |
| `_lightbox-desktop.scss` | 253 | Desktop sidebar panel (≥1024px) |
| `_lightbox-tablet.scss` | 274 | iPad 2-column bottom sheet (768–1023px) |
| `_lightbox-mobile.scss` | 237 | Phone bottom sheet (<768px) |

### Overflow Chain (Glow Bleed)

```
.content {
  overflow: clip;      ← allows children to render past boundary
  padding: 44px;       ← space for glow bleed (desktop)
}
  └── .content-body {
        overflow: visible;
        min-height: 0;
      }
        └── GalleryGrid
              └── GlowContainer (:bleed="50")
                    └── AlbumScroller
                          └── AlbumCard (box-shadow: var(--glow-card-hover))
```

`overflow: clip` (not `overflow: hidden`) is the key — it clips layout but allows visual overflow like box-shadows to bleed past the content boundary.

### Glow Bleed Pattern

`GlowContainer.vue` wraps any element that needs glow bleed:

```html
<GlowContainer :bleed="50">
  <AlbumScroller ... />
</GlowContainer>
```

The component sets `--glow-bleed-x` and `--glow-bleed-y` CSS variables, applies negative margin + positive padding, and uses `pointer-events: none` on the container to prevent overflow regions from intercepting pointer events on adjacent elements. The `disabled` prop can disable glow entirely.

---

## Responsive Breakpoints

Breakpoints are handled in two layers:

### App.vue Layout Breakpoints (mobile detection)

| Breakpoint | Width | Layout |
|-----------|-------|--------|
| Desktop | ≥ 1025px | 280px sidebar + content grid, AppHeader, sidebar edge toggle |
| Tablet | 641–1024px | 240px persistent sidebar, AppHeader (hamburger visible), edge toggle hidden |
| Phone | ≤ 640px | Sidebar becomes fixed overlay, MobileHeader + MobileFloatingBottomBar, 1-column grid |
| Small phone | ≤ 480px | Compact padding, sidebar full-width overlay |

### useDevice Breakpoints (component-level)

| Breakpoint | Width Range | Typical Devices |
|-----------|-------------|-----------------|
| `compact` | < 480px | iPhone 6.1", small phones |
| `phone` | 480–767px | Larger phones, phone landscape |
| `tablet` | 768–1023px | iPad Mini 8.4", iPad 10.2", iPad Pro 11" |
| `desktop` | ≥ 1024px | iPad Pro 13", desktop monitors |

**Used by**: Lightbox panels, GalleryGrid column count, other device-aware components.

---

## Device Detection (`useDevice.ts`)

Singleton composable with ref-counted resize listener. Multiple component instances share one `resize` event listener.

**Breakpoints** (from `BREAKPOINTS` constant):

| Breakpoint | Width Range | Typical Devices |
|-----------|-------------|-----------------|
| `compact` | < 480px | iPhone 6.1", small phones |
| `phone` | 480–767px | Larger phones, phone landscape |
| `tablet` | 768–1023px | iPad Mini 8.4", iPad 10.2", iPad Pro 11" |
| `desktop` | ≥ 1024px | iPad Pro 13", desktop monitors |

**Exports**: `{ breakpoint, isCompact, isPhone, isTablet, isDesktop, isMobile, isLargeScreen }`

**Singleton pattern**: First call to `useDevice()` starts the resize listener; last component unmounting removes it. Uses `refCount` to track subscriber count.

---

## Composables

| Composable | Lines | Primary User | Purpose |
|-----------|-------|-------------|---------|
| `useScrollVisibility` | 58 | App.vue (MobileHeader, MobileFloatingBottomBar) | Detects scroll direction inside RecycleScroller, returns `barsVisible` + `isScrollingDown` refs. Uses MutationObserver to re-attach when DOM changes. |
| `useDevice` | 50 | App, Lightbox, GalleryGrid | Singleton breakpoint detection via resize listener |
| `useNaturalSort` | 32 | GalleryGrid | Natural sorting (handles numbers in filenames) |
| `useColumnResize` | 85 | GalleryGrid | Column count computation, row height, grid persistence |
| `useClipboard` | 51 | LightboxDesktopPanel | Copy text to clipboard with success/error toast |
| `useFocusTrap` | 138 | Lightbox, SettingsModal | Focus trap for modals (Tab/Shift+Tab cycling) |
| `useToast` | 97 | Various | Convenience wrapper around toastStore for showing toasts |

---

## Directives

| Directive | Lines | Purpose |
|-----------|-------|---------|
| `clickOutside` | 30 | Detects clicks outside a bound element, emits callback. Used by dropdowns and modals. |

---

## Utilities

| Utility | Lines | User | Purpose |
|---------|-------|------|---------|
| `loraHighlighter` | 36 | LightboxDesktopPanel | HTML-escapes and highlights `<lora:...>` tokens in prompt strings with special styling |

---

## Stores

### `galleryStore` (345 lines)
The central data store. Manages:
- **State**: `folders[]`, `images[]`, `currentPath`, `sortField`, `sortOrder`, `cursor`, `loading`, `totalImages`, `searchQuery`, `history[]`, `historyIndex`, `sidebarTree[]`
- **Actions**: `openFolder(path)`, `loadImages()`, `loadMoreImages()`, `setSort(field, order)`, `goBack()`, `goForward()`, `openInExplorer()`
- **Search**: client-side filtering of loaded images by filename
- **Error handling**: typed API errors surfaced to UI

### `lightboxStore` (111 lines)
Manages image viewer state:
- **State**: `currentImage`, `isOpen`, `metadata`, `images[]` (context for prev/next)
- **Actions**: `open(image, imageList)`, `close()`, `next()`, `prev()`, `fetchMetadata()`
- **Preloading**: preloads adjacent images into browser cache for instant navigation

### `toastStore` (148 lines)
Manages toast notification queue:
- **State**: `toasts[]` (array of `{ id, type, message, duration }`)
- **Actions**: `add(toast)`, `remove(id)`, `clear()`
- **Auto-dismiss**: each toast auto-removes after `duration` ms (default varies by type)

---

## Services

### `api.ts` (197 lines)
Axios-based HTTP client for the FastAPI backend (port 4180):
- **`openFolder(path)`** — POST, returns folder tree for sidebar navigation
- **`scanDirectory(path, cursor, sort, order)`** — GET, paginated image listing (200 per page)
- **`fetchMetadata(path)`** — GET, image generation metadata (prompt, params, models)
- **`getImageUrl(path)`** — returns full-resolution image URL string
- **`getThumbnailUrl(path, size)`** — returns thumbnail URL with size parameter
- **`GalleryAPIError`** — typed error class with `errorType` and `message` for frontend error handling

---

## Types

### `types/index.ts` (62 lines)
Core TypeScript interfaces:
- **`FileNode`** — file/folder node with `name`, `path`, `type` (`"folder"` | `"image"`), `children`, `cover_images`, `mtime`, `image_count`
- **`SortField`** / **`SortOrder`** — `"name"` | `"date"` / `"asc"` | `"desc"`
- **`GenerationParams`** — image generation parameters (Seed, Steps, CFG, Sampler, Model, LoRAs, etc.)
- **`MetadataResponse`** — full metadata including `prompt`, `negative_prompt`, `params`, `models[]`, dimensions, tool name
- **`ScanResponse`** — paginated scan result with `folders[]`, `images[]`, `next_cursor`, `total_images`

---

## Backend (`backend/main.py`)

1141-line FastAPI server running on port 4180.

**Endpoints:**
- `GET /api/scan` — paginated directory scan with sorting (cursor-based pagination, 200 images/page)
- `POST /api/open-folder` — returns folder tree structure for sidebar
- `GET /api/thumbnail` — on-the-fly thumbnail generation (WebP, cached)
- `GET /api/metadata` — extract generation metadata from image EXIF/PNG info
- `GET /api/image` — serve full-resolution image
- `GET /api/preview` — preview image for intro screen landing pages

**Caching:**
- **Thumbnail cache**: 1GB LRU cache (size-based, thread-safe) for generated WebP thumbnails
- **Metadata cache**: 100MB LRU cache for parsed generation metadata
- Both use `cachetools.LRUCache` with `threading.Lock` for concurrent access

**Error handling**: Custom `APIError` class with typed error codes (`not_found`, `not_directory`, `permission`, `invalid_file`, `timeout`, `server_error`) for granular frontend error handling.

---

## Known Limitations

1. **Glow clipping on mobile `overflow-x:auto`**: On mobile devices, the horizontal album scroller uses `overflow-x: auto`. The glow bleed from `GlowContainer` with negative margins can be clipped by the auto-scroll container, causing the neon glow shadow to be cut off at the edges. This is a CSS limitation — `overflow: auto` clips visual overflow even with `overflow: clip` on ancestor elements. A potential fix would require restructuring the scroll container to use `overflow: clip` with programmatic scroll controls.

2. **`BottomNavigationBar.vue` is legacy**: This component still exists in the codebase but is no longer used in the App.vue component tree. It has been replaced by `MobileFloatingBottomBar.vue`. Consider removing it in future cleanup.

3. **No WebSocket support**: Folder changes on disk require manual refresh. Real-time updates (e.g., via WebSocket or file watcher) are on the roadmap.

---

## Key Architectural Decisions

1. **No Lightbox template split until 2+ device variants existed** — Premature abstraction avoided. The lightbox started as a single component; device-specific panels (`DesktopPanel`, `TabletPanel`, `MobileSheet`) were extracted only when three distinct layouts were needed.

2. **RecycleScroller kept** — Virtual scrolling via `vue-virtual-scroller` is well-optimized for large image grids. Coupling is limited to `GalleryGrid.vue` only.

3. **Gallery store NOT split** — At 345 lines, the gallery store has tightly coupled concerns (folder selection → history → image loading → sorting). Splitting would introduce circular dependency risks with minimal readability gain.

4. **CSS variables over inline values** — All shadows and glow effects are tokenized in `tokens.css`. One change to `--glow-color-*` propagates to every component. Dark/light mode switching is a single attribute change on `:root`.

5. **GlowContainer over per-component bleed** — A single reusable wrapper sets `--glow-bleed-x`/`--glow-bleed-y` variables, consumed by any child needing glow overflow. Also handles `pointer-events: none` to prevent interaction issues. Avoids duplicating bleed logic across `AlbumScroller`, `PhotoCard`, etc.

6. **`overflow:clip` over `overflow:hidden`** — `overflow: clip` clips layout without clipping visual overflow (box-shadows). This is essential for the glow bleed effect where orange neon shadows extend past the content boundary.

7. **Singleton useDevice with ref-counting** — A single `resize` listener serves all components, avoiding N listeners for N component instances. Reference counting ensures the listener is removed when the last component unmounts.

8. **Lazy-loaded Lightbox** — `Lightbox.vue` is loaded via `defineAsyncComponent`, keeping the initial bundle small. The lightbox and its three panel variants are code-split into a separate chunk.

9. **Typed backend errors** — Backend returns structured errors (`{"error": "not_found", "message": "..."}`) mapped to `GalleryAPIError` on the frontend, enabling specific UI responses (retry, different empty state, etc.).

10. **LRU caches with size-based eviction** — Backend thumbnail (1GB) and metadata (100MB) caches use `cachetools.LRUCache` with `getsizeof` for byte-aware eviction, rather than item-count eviction. This prevents memory exhaustion from large thumbnails.

11. **Mobile bar visibility via scroll direction** — `useScrollVisibility` composable attaches to `.vue-recycle-scroller` element, tracking scroll direction with rAF-throttled handler. Uses `MutationObserver` to handle DOM re-creation when RecycleScroller's key changes. Bars slide away on scroll-down, return on scroll-up, creating a reading-mode UX pattern.
