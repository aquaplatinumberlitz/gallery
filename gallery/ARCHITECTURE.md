# Museum Art Gallery — Architecture

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend Framework** | Vue 3 (Composition API + `<script setup>`) |
| **Language** | TypeScript |
| **Styling** | SCSS + CSS Custom Properties (design tokens) |
| **Build Tool** | Vite |
| **State Management** | Pinia (3 stores) |
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
│       ├── App.vue                          (482 lines — layout orchestrator, theme/intro/settings)
│       ├── main.ts                          (13 lines — app bootstrap)
│       ├── constants.ts                     (1 line — IMAGE_PAGE_SIZE = 200)
│       ├── assets/
│       │   └── fonts.css                    (31 lines — Google Fonts @import)
│       ├── components/
│       │   ├── AppHeader.vue                (633 lines — search, theme toggle, brand hero, hamburger)
│       │   ├── AlbumCard.vue                (245 lines — album card with neon glow)
│       │   ├── AlbumScroller.vue            (300 lines — horizontal album scroll + arrows)
│       │   ├── BottomNavigationBar.vue      (76 lines — mobile bottom nav)
│       │   ├── Breadcrumb.vue               (526 lines — path breadcrumb with dropdown)
│       │   ├── EmptyState.vue               (491 lines — empty state illustrations)
│       │   ├── FolderTreeItem.vue           (221 lines — recursive folder tree item)
│       │   ├── GalleryGrid.vue              (1167 lines — main grid orchestrator)
│       │   ├── GlowContainer.vue            (48 lines — glow bleed wrapper, CSS variable-driven)
│       │   ├── IntroScreen.vue              (429 lines — intro/landing page with animations)
│       │   ├── Lightbox.vue                 (581 lines — image viewer orchestrator)
│       │   ├── LightboxDesktopPanel.vue     (217 lines — desktop metadata sidebar panel)
│       │   ├── LightboxTabletPanel.vue      (207 lines — iPad 2-column bottom sheet)
│       │   ├── LightboxMobileSheet.vue      (190 lines — phone bottom sheet, tabbed)
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
│       │   ├── env.d.ts                     (Vite env type declarations)
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
├── AppHeader.vue                (search bar, theme toggle, brand hero, hamburger, settings)
├── GalleryGrid.vue              (main content area — async component)
│   ├── AlbumScroller.vue        (horizontal scroll with arrow navigation)
│   │   └── AlbumCard.vue        (neon glow card — 1 per album)
│   │       └── GlowContainer.vue
│   ├── PhotoCard.vue            (thumbnail card — 1 per image, inside RecycleScroller)
│   ├── SkeletonLoader.vue       (loading state)
│   └── EmptyState.vue           (no results / empty folder state)
├── SettingsModal.vue            (conditional — settings dialog)
├── Lightbox.vue                 (lazy-loaded async component)
│   ├── LightboxDesktopPanel.vue (breakpoint: desktop)
│   ├── LightboxTabletPanel.vue  (breakpoint: tablet)
│   └── LightboxMobileSheet.vue  (breakpoint: phone/compact)
├── BottomNavigationBar.vue      (mobile bottom nav)
└── ToastContainer.vue
    └── ToastItem.vue            (1 per active toast)
```

### Component Responsibilities

#### `App.vue` — Layout Orchestrator
- Sidebar + content CSS Grid layout
- Theme controller (light/dark) via `data-theme` attribute on `:root`
- Intro screen show/hide orchestration
- Settings modal state
- Sidebar collapse/expand on mobile

#### `AppHeader.vue` — Header UI
- Search bar with debounced input
- Theme toggle button (sun/moon icon)
- Brand hero / logo display
- Mobile hamburger menu trigger
- Settings gear button

#### `SidebarHeader.vue` — Sidebar Top
- Current root folder display
- Reset/refresh button
- Info/help trigger

#### `FolderTreeItem.vue` — Recursive Folder Tree
- Self-referential: renders children as more `FolderTreeItem` instances
- Expand/collapse toggle
- Active folder highlighting
- Lazy-loading of children on expand

#### `Breadcrumb.vue` — Path Navigation
- Breadcrumb trail from root to current folder
- Each segment is a clickable dropdown showing sibling folders
- Handles deep folder navigation

#### `BottomNavigationBar.vue` — Mobile Nav
- Fixed bottom bar on mobile devices
- Quick access to main sections

### Gallery Grid

#### `GalleryGrid.vue` — Main Orchestrator
The largest component (1167 lines). Responsibilities:
- **Album scroller**: renders `AlbumScroller` above the grid
- **Photo grid**: `RecycleScroller` with `PhotoCard` items
- **Sort controls**: dropdown for sort field (name/date) and order (asc/desc)
- **Infinite scroll**: detects scroll near bottom, loads next page
- **Column count**: delegates to `useColumnResize`
- **Natural sort**: delegates to `useNaturalSort`
- **Click handler**: opens `Lightbox` on image click

#### `AlbumScroller.vue` — Horizontal Album Scroll
- Horizontal scroll container with left/right arrow navigation
- Renders `AlbumCard` for each album
- Wrapped in `GlowContainer` for glow bleed

#### `AlbumCard.vue` — Album Card with Glow
- Thumbnail with album name and image count
- Neon orange glow effect on hover (dark mode only)
- Consumes `--glow-*` CSS variables from ancestor `GlowContainer`

#### `PhotoCard.vue` — Image Thumbnail
- Image thumbnail with MD3 elevation shadow
- Lazy-loaded image with aspect-ratio placeholder
- Filename overlay on hover
- Click emits `select` event to open lightbox

#### `SkeletonLoader.vue` — Loading State
- Animated placeholder cards matching grid layout
- Shown during initial load and page transitions

#### `EmptyState.vue` — Empty States
- Multiple illustrations for: no images, no results (search), error states
- Inline SVG illustrations
- Contextual help text

#### `GlowContainer.vue` — Glow Bleed Wrapper
- Reusable wrapper component
- Accepts `bleed` prop (px) to set `--glow-bleed-x` / `--glow-bleed-y` CSS variables
- Single source of truth for glow bleed padding across components

### Lightbox (Image Viewer)

#### `Lightbox.vue` — Orchestrator
- Lazy-loaded via `defineAsyncComponent` in `App.vue`
- Full-screen overlay with image display
- **Keyboard navigation**: Arrow keys (prev/next), Escape (close), F (fullscreen)
- **Wheel navigation**: scroll to navigate between images
- **Device routing**: renders the appropriate panel component based on `useDevice()` breakpoint
- **Preloading**: preloads adjacent images for instant navigation
- **Focus trap**: delegates to `useFocusTrap`

#### `LightboxDesktopPanel.vue` — Desktop Metadata Sidebar
- Breakpoint: `desktop` (≥1024px)
- Right sidebar panel with full metadata display
- Prompt, negative prompt, generation parameters (model, seed, steps, CFG, sampler, LoRAs)
- LoRA highlighting via `loraHighlighter`
- Copy-to-clipboard buttons via `useClipboard`

#### `LightboxTabletPanel.vue` — iPad 2-Column Bottom Sheet
- Breakpoint: `tablet` (768–1023px)
- Two-column layout at the bottom of the viewport
- Left column: image info (filename, dimensions, date)
- Right column: generation parameters
- Optimized for iPad Mini 8.4", iPad 10.2", iPad Pro 11"

#### `LightboxMobileSheet.vue` — Phone Bottom Sheet
- Breakpoint: `compact` / `phone` (<768px)
- Bottom sheet with tabbed interface (tabs: Info / Prompt / Params)
- Swipe-to-dismiss gesture area
- Compact layout for small screens (iPhone 6.1" and similar)

### UI Components

#### `SettingsModal.vue` — Settings Dialog
- Modal overlay with settings options
- Default sort field/order preferences
- Theme preference
- Other configurable options

#### `IntroScreen.vue` — Landing Page
- Full-screen animated intro shown on first visit
- Animated entrance with particle effects
- Preview mode from settings
- "Enter Gallery" button

#### `ToastContainer.vue` / `ToastItem.vue` — Notifications
- `ToastContainer` renders all active toasts from `toastStore`
- `ToastItem` handles individual toast: enter/exit animations, auto-dismiss, action buttons
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
4. **Theme toggle**: `AppHeader` toggles → sets `data-theme` on `:root` → CSS variables switch light/dark
5. **Toast**: Any component calls `toastStore.add({ type, message })` → `ToastContainer` renders `ToastItem` → auto-dismiss after timeout

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
  padding: 44px;       ← space for glow bleed
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

The component sets `--glow-bleed-x` and `--glow-bleed-y` CSS variables consumed by child components to calculate their negative margins / overflow space.

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
- **State**: `folders[]`, `images[]`, `currentPath`, `sortField`, `sortOrder`, `cursor`, `loading`, `totalImages`
- **Actions**: `openFolder(path)`, `loadImages()`, `loadMoreImages()`, `setSort(field, order)`, navigation history
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

## Key Architectural Decisions

1. **No Lightbox template split until 2+ device variants existed** — Premature abstraction avoided. The lightbox started as a single component; device-specific panels (`DesktopPanel`, `TabletPanel`, `MobileSheet`) were extracted only when three distinct layouts were needed.

2. **RecycleScroller kept** — Virtual scrolling via `vue-virtual-scroller` is well-optimized for large image grids. Coupling is limited to `GalleryGrid.vue` only.

3. **Gallery store NOT split** — At 345 lines, the gallery store has tightly coupled concerns (folder selection → history → image loading → sorting). Splitting would introduce circular dependency risks with minimal readability gain.

4. **CSS variables over inline values** — All shadows and glow effects are tokenized in `tokens.css`. One change to `--glow-color-*` propagates to every component. Dark/light mode switching is a single attribute change on `:root`.

5. **GlowContainer over per-component bleed** — A single reusable wrapper sets `--glow-bleed-x`/`--glow-bleed-y` variables, consumed by any child needing glow overflow. Avoids duplicating bleed logic across `AlbumScroller`, `PhotoCard`, etc.

6. **overflow:clip over overflow:hidden** — `overflow: clip` clips layout without clipping visual overflow (box-shadows). This is essential for the glow bleed effect where orange neon shadows extend past the content boundary.

7. **Singleton useDevice with ref-counting** — A single `resize` listener serves all components, avoiding N listeners for N component instances. Reference counting ensures the listener is removed when the last component unmounts.

8. **Lazy-loaded Lightbox** — `Lightbox.vue` is loaded via `defineAsyncComponent`, keeping the initial bundle small. The lightbox and its three panel variants are code-split into a separate chunk.

9. **Typed backend errors** — Backend returns structured errors (`{"error": "not_found", "message": "..."}`) mapped to `GalleryAPIError` on the frontend, enabling specific UI responses (retry, different empty state, etc.).

10. **LRU caches with size-based eviction** — Backend thumbnail (1GB) and metadata (100MB) caches use `cachetools.LRUCache` with `getsizeof` for byte-aware eviction, rather than item-count eviction. This prevents memory exhaustion from large thumbnails.
