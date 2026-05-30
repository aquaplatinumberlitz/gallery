# Frontend UI Interactions & Mobile Maintenance Guide

## UI Overview

The gallery has three main UI modes selected by viewport width (see `useDevice.ts`):

### Desktop (≥1200px)
- **Sidebar**: 280px persistent folder tree (collapsible via edge toggle button)
- **Header**: `AppHeader` — search box, sort dropdown, column slider, theme toggle, settings
- **Gallery**: `GalleryGrid` with `RecycleScroller` (virtual scroll), breadcrumb, AlbumScroller, PhotoCard grid
- **Lightbox**: `PhotoSwipeViewer` (full-res 2400px thumbnail) + `LightboxDesktopPanel` (right sidebar, 400px, `z-index: 10000`, `backdrop-filter: blur(20px)`)

### Tablet (768-1199px)
- **Sidebar**: 240px persistent (no edge toggle — hamburger always visible)
- **Grid**: 3-column default, no column slider
- **Lightbox**: `PhotoSwipeViewer` (2048px thumbnail, `allowPanToNext: true`) + Info button → `LightboxTabletPanel` (2-column bottom sheet, max 65vh)

### Mobile (<768px)
- **Sidebar**: Overlay (fixed, 240px, slides in from left, `z-index: 100`)
- **Header**: `MobileHeader` — hamburger + expandable search + theme toggle + settings
- **Bottom Bar**: `MobileFloatingBottomBar` — pill-shaped nav (back/forward, path, open-explorer)
- **Grid**: Native scroll (no RecycleScroller), 2-3 columns, no sort/column slider
- **Lightbox**: `MobilePhotoSwipe` (1600px thumbnail, `closeOnVerticalDrag: true`, `allowPanToNext: true`) + Info button → `LightboxMobileSheet` (tabbed bottom sheet, 44dvh, 3 tabs: Prompt, Params, Advanced)

### Compact (<480px)
- Same as mobile with tighter spacing in all components
- `LightboxMobileSheet`: 40dvh default, 75dvh expanded
- `MobileHeader`: 8px padding
- Grid: 1-column on smallest screens (but `useColumnResize` keeps 2 columns minimum — verify behavior)

---

## Interaction Map

| User Action | Component → Action → Store → API |
|-------------|----------------------------------|-----------------------------------|
| **Click folder in sidebar** | `FolderTreeItem` → `galleryStore.toggleFolder()` or `selectFolder()` → `api.scanDirectory()` → `GET /api/scan` |
| **Click album card** | `AlbumScroller` → emits `open-folder` → `galleryStore.selectFolder(path)` |
| **Search query typed** | `AppHeader.vue` / `MobileHeader.vue` → emits `update:search-query` → `galleryStore.searchQuery = $event` → `GalleryGrid` computed `images` filter |
| **Sort changed** | `GalleryGrid` sort dropdown → `galleryStore.setSortField()` / `toggleSortOrder()` → persisted to localStorage → computed re-sort |
| **Grid column slider** | `GalleryGrid` `<input type="range">` → `useColumnResize().columnCount` → saved to localStorage → RecycleScroller re-keyed |
| **Click photo** | `PhotoCard` → `GalleryGrid.handleOpenImage()` → `lightboxStore.open()` → metadata fetch |
| **Arrow keys (desktop)** | `Lightbox.handleKeydown()` → `lightboxStore.prev()`/`next()` → `loadMetadata()` → PhotoSwipe sync |
| **Swipe (mobile)** | `MobilePhotoSwipe` PS5 gesture → emits `change` → `Lightbox.handlePhotoSwipeIndexChange()` → `lightboxStore.loadMetadata()` |
| **Theme toggle** | `AppHeader`/`MobileHeader` → `App.vue.toggleTheme()` → `document.documentElement.setAttribute('data-theme', val)` → `localStorage.setItem('gallery-theme', val)` |
| **Pull to refresh (mobile)** | `GalleryGrid` touch events → `usePullToRefresh` → on threshold: `galleryStore.scanFolder()` |
| **Sidebar toggle** | Edge toggle / hamburger → `App.vue.toggleSidebar()` → `isSidebarOpen` reactive → CSS class toggle |
| **Lightbox close** | Escape key / PS5 close / Close button → `lightboxStore.close()` → focus trap deactivate |

---

## Mobile-Specific Behavior

### Device Breakpoints (`useDevice.ts`)

```typescript
BREAKPOINTS = {
  compact: 480,   // iPhone 6.1" portrait, small Android
  mobile: 768,    // iPad Mini portrait, large phones
  desktop: 1200,  // iPad Pro / small laptop
  wide: 1440,     // Full desktop monitors
}
```

| Computed | Logic |
|----------|-------|
| `isCompact` | `< 480` |
| `isMobileOnly` | `>= 480 && < 768` |
| `isMobile` | `isCompact || isMobileOnly` (i.e., `< 768`) |
| `isTablet` | `>= 768 && < 1200` |
| `isDesktop` | `>= 1200 && < 1440` |
| `isWide` | `>= 1440` |
| `isLargeScreen` | `isTablet || isDesktop || isWide` |

**IMPORTANT**: `isMobile` is `< 768px` which is used in `App.vue` and `Lightbox.vue` for template branching. The `_breakpoints.scss` `@include mobile` mixin uses `max-width: 767px` — functionally the same but boundary values differ (JS <768 vs SCSS ≤767).

### iPhone Safari Quirks

1. **Safe areas**: `env(safe-area-inset-top)` and `env(safe-area-inset-bottom)` used in `App.vue` CSS — `.content.bars-hidden` has `padding-top: max(8px, env(safe-area-inset-top))`. Mobile bars use similar.

2. **Sticky bars**: Both `MobileHeader` and `MobileFloatingBottomBar` are `position: fixed`. `useScrollVisibility` hides them via opacity/transform when scrolling down, shows on scroll up. Uses rAF-throttled handler + MutationObserver for DOM re-attach.

3. **backdrop-filter**: Used on `.sidebar-backdrop` (`backdrop-filter: blur(2px)`), `.mobile-info-btn` (`backdrop-filter: blur(6px)`), `LightboxDesktopPanel` (`backdrop-filter: blur(20px)`). iOS Safari supports `-webkit-backdrop-filter` — both prefixes are included. Performance can degrade on older devices.

4. **Clipboard on HTTP**: `useClipboard.ts` has a fallback for HTTP origins (non-HTTPS) using `document.execCommand('copy')` with a hidden textarea. This fires a toast on success/failure.

5. **localStorage in Private Browsing**: All localStorage access is wrapped in try/catch. Without the wrapper, the app crashes silently in Safari Private Browsing mode.

6. **Touch targets**: `_mobile-overrides.scss` (`@media (pointer: coarse)`) sets all interactive elements to min 44×44px. Individual components also have component-level overrides (e.g., `.nav-btn` in `GalleryGrid.vue`).

### Touch Events vs Hover

- **No sticky hover**: `_mobile-overrides.scss` `@media (hover: none)` resets `:hover` on `.album-card`, `.photo-card`, `.nav-btn`, `.mh-btn`, `.mbb-btn` — sets `box-shadow: none` and resets border color.
- **Active states**: `:active` works normally with `-webkit-tap-highlight-color: transparent`.
- **Desktop hover**: `@media (hover: hover) and (pointer: fine)` — reserved for future enhancements.
- **Glow disabled on mobile**: `--glow-color: transparent` on `max-width: 767px` to avoid clipping and improve performance. Set in both `tokens.css` and `_mobile-overrides.scss`.

---

## Virtual Scroll (`GalleryGrid.vue`)

### Desktop Mode (RecycleScroller)
- Uses `vue-virtual-scroller` v3's `RecycleScroller` component
- Activated when: `!props.isMobile && imageRows.length > 0 && rowHeight > 0`
- Items are **rows** (not individual images) — each row contains `columnCount` photos
- `key-field="id"` with `row-{columnCount}-{i}` pattern — forces re-render when column count changes
- `buffer="600"` — extra padding for smoother scroll
- `item-size` = computed `rowHeight` (item width + gap)

### Mobile Mode (Native Scroll)
- Regular `<div>` with `v-for` rows
- No DOM recycling — all items in DOM at once
- Same row structure as RecycleScroller

### Row Height Computation (`useColumnResize.ts`)
- `rowHeight = itemWidth + GAP(20)` — where `itemWidth = (containerWidth - totalGap) / columnCount`
- Uses `ResizeObserver` on `.scroller-container` for responsive recompute
- Column count persisted to `localStorage` key `gallery-grid-size`

### Infinite Scroll (IntersectionObserver)
- `loadMoreSentinel`: a 1px-tall `<div>` placed at end of photo list
- `IntersectionObserver` with `root: null, rootMargin: "400px", threshold: 0`
- Fires `galleryStore.loadMoreImages()` when sentinel is 400px from viewport
- `IMAGE_PAGE_SIZE = 200` images per page

### SCSS Critical for Scroll
```scss
.scroller-container { flex: 1; min-height: 0; }
.scroller { height: 100%; overflow-y: auto; overflow-x: hidden; }
```
- `.scroller-container` must have `min-height: 0` for flex child height chain
- `.vue-recycle-scroller__item-wrapper` has `overflow: visible` (card hover shadows)
- `.vue-recycle-scroller__slot` has `overflow: visible` (glow/box-shadow)

### Pull to Refresh (Mobile Only)
- `usePullToRefresh.ts`: touch gesture handler with axis lock (prevents conflict with horizontal album scroll)
- Threshold: 80px, max distance: 120px
- `canStart` callback checks `scrollTop <= 5` and not on `.album-grid`
- Triggers `galleryStore.scanFolder()` on completion

---

## Style Architecture

### File Structure
```
frontend/src/styles/
├── main.scss              # Global styles, animations, a11y, responsive utilities
├── tokens.css             # Design tokens v2 — all --gallery-* CSS vars + legacy mappings
├── _breakpoints.scss      # SCSS mixins (compact/mobile/tablet/desktop/wide)
├── _mobile-overrides.scss # Mobile resets: glow, hover, touch targets, Safari background
├── _lightbox-shared.scss  # Shared lightbox: loading/error, loRA highlighter, param-pill
├── _lightbox-desktop.scss # Desktop panel: right sidebar 400px
├── _lightbox-tablet.scss  # Tablet panel: 2-column bottom sheet
└── _lightbox-mobile.scss  # Mobile panel: tabbed bottom sheet
```

Import order in `main.ts`:
```
main.scss → tokens.css → vue-virtual-scroller.css
```

### Theme System (CSS Custom Properties)

Two themes via `data-theme` attribute on `<html>`:

| Aspect | Light Mode | Dark Mode |
|--------|-----------|-----------|
| Surface default | `#ffffff` | `#1a1918` (warm near-black) |
| Primary accent | `#ff6b35` (orange) | `#d6a15d` (gold) |
| Text primary | `#143d60` | `#e4e6eb` |
| Border | `#e5ddd4` | `#2d2b28` |
| Glow | transparent (disabled) | Orange glow (`#FF6B35`) |

Theme persistence:
1. `index.html` inline script reads `localStorage['gallery-theme']` before CSS render (FOUC prevention)
2. `App.vue` `watchEffect` sets `document.documentElement.setAttribute("data-theme", theme.value)`
3. System preference via `prefers-color-scheme: dark` — only auto-switches if no manual preference saved

### Token Naming Convention (Primer-inspired)
```
--gallery-{category}-{group?}-{modifier}
```
- Categories: `surface`, `text`, `accent`, `border`, `shadow`, `radius`, `timing`
- Surface levels: `dim`, `default`, `elevated`, `hover`
- Text levels: `primary`, `secondary`, `tertiary`, `disabled`, `inverse`
- Legacy variables (`--bg-color`, `--text-color`, `--neon-color`) maintained for backward compat

### Key SCSS Mixins (`_breakpoints.scss`)
```scss
@mixin compact   { @media (max-width: 479px) { @content; } }
@mixin mobile    { @media (max-width: 767px) { @content; } }
@mixin tablet    { @media (min-width: 768px) and (max-width: 1199px) { @content; } }
@mixin desktop   { @media (min-width: 1200px) { @content; } }
@mixin wide      { @media (min-width: 1440px) { @content; } }
```

---

## Known Fragile Areas

### 1. PhotoSwipe Right Arrow vs Sidebar Overlap

**File**: `frontend/src/components/Lightbox.vue` (lines 436-452)

The `.lightbox-right` desktop panel (400px wide, `z-index: 10000`) covers the right side of the viewport. PhotoSwipe's native next arrow (`z-index` inside PS5 DOM) would be hidden behind it.

**The fix**: Override `.pswp__button--arrow--next` with:
```css
right: calc(var(--lightbox-sidebar-width) + var(--lightbox-arrow-gap));
```
Where `--lightbox-sidebar-width: 400px` and `--lightbox-arrow-gap: 16px`.

**Regression risk**: If `.lightbox-right` min-width (320px) or max-width (450px) changes, or if the sidebar is hidden in fullscreen mode, the arrow position won't be correct. The arrow position is defined in a **non-scoped** `<style lang="scss">` block to reach PS5-generated DOM.

### 2. Lightbox Right Panel z-index Stacking Context

**File**: `frontend/src/styles/_lightbox-desktop.scss` (line 13)

```scss
.lightbox-right { z-index: 10000; position: fixed; }
```

While `.lightbox-overlay` has `z-index: 9999`. If `.photoswipe-container` has `z-index: 1` (relative to overlay), and `.lightbox-right` is a sibling, the stacking is:
- Overlay (9999) > PS5 container (1 inside overlay) vs Right panel (10000, sibling of overlay)

This works because `.lightbox-right` is a direct child of `.lightbox-overlay` (Teleported to body), so it's a sibling of the container div. The right panel sits ABOVE the overlay which contains PS5. This is by design — the arrow offset fix avoids the overlap.

### 3. RecycleScroller page-mode + overflow-y

**File**: `frontend/src/components/GalleryGrid.vue` (lines 646-659)

```scss
.scroller-container { flex: 1; min-height: 0; }
.scroller { height: 100%; overflow-y: auto; overflow-x: hidden; }
```

RecycleScroller needs a **fixed height container** to compute its virtual scroll area. The `min-height: 0` on `.scroller-container` is the critical flex child constraint. If any parent in the chain removes `min-height: 0`, `.scroller` gets `height: auto` from content, RecycleScroller sees no scroll overflow, and **no items render** (zero rows).

**Debug**: In browser DevTools, check `.scroller` computed height. If it's 0 or matches content height rather than container height, trace the `min-height: 0` chain up through `.content-body` (App.vue line 394), `.content` (line 348), `.layout` (line 259).

### 4. api.ts VITE_API_URL Fallback (Mixed Content)

**File**: `frontend/src/services/api.ts` (line 4)

```typescript
const API_BASE = import.meta.env.VITE_API_URL || "";
```

When empty, API calls go to the **same origin** as the frontend. In development:
- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`

Without Vite proxy or `VITE_API_URL`, calls to `/api/scan` hit Vite's dev server which returns 404.

**start.py** sets `VITE_API_URL=http://127.0.0.1:{backend_port}` as an env variable. If running manually, the user must either:
- Set `VITE_API_URL=http://localhost:8000` in `.env` file
- Or configure Vite proxy in `vite.config.ts`

### 5. Lightbox.vue Template Branches (Desktop/Wide)

**File**: `frontend/src/components/Lightbox.vue` (lines 206-246)

The template uses:
```vue
<template v-if="isDesktop || isWide">...</template>
<template v-if="isTablet">...</template>
<MobilePhotoSwipe v-if="isMobile" />
```

Note: `isDesktop || isWide` means both desktop (1200-1439px) and wide (≥1440px) use `PhotoSwipeViewer` with different `thumbnailSize`:
- Desktop: 2400px
- Wide: 2400px (same — verify in code)

Tablet uses 2048px. Mobile uses 1600px (via MobilePhotoSwipe).

### 6. Mobile Bars Visibility — useScrollVisibility Polling

**File**: `frontend/src/composables/useScrollVisibility.ts` (lines 62-97)

Two attachment paths:
1. **Injected ref** (desktop): `containerRef` provided via `galleryScrollContainerRefKey` — watched immediately
2. **Polling** (mobile): falls back to polling `document.querySelector('.vue-recycle-scroller, .scroller, .folders-only-container')` every 200ms until found

The polling is necessary because RecycleScroller may not render immediately (conditional rendering). After finding the scroller, a `MutationObserver` watches its parent for DOM re-creation.

**Fragile because**: If the scroller CSS class name changes, the selector won't match and polling never stops. The 200ms interval runs indefinitely.

### 7. Mobile Bars Bottom Guard for iOS Rubber-Band

**File**: `frontend/src/composables/useScrollVisibility.ts` (lines 25-29)

```typescript
const nearBottom = el.scrollHeight - el.clientHeight - st < 150
if (nearBottom && st > 0) { lastScrollY = st; return; }
```

This prevents the bars from toggling when the user scrolls near the bottom, avoiding a layout-shift / rubber-band feedback loop on iOS. If the `150` threshold is too high or too low, users may experience:
- Too high: Bars don't hide near bottom when they should
- Too low: iOS rubber-band causes rapid show/hide flicker

### 8. Swipe on Mobile — PhotoSwipe Configuration Mismatch

**File**: 
- `frontend/src/components/MobilePhotoSwipe.vue` (line 43) — dead `pswpModule` parameter
- `frontend/src/components/MobilePhotoSwipe.vue` vs `PhotoSwipeViewer.vue` — different `closeOnVerticalDrag` and `allowPanToNext` values

MobilePhotoSwipe uses `thumbnailSize: 1600px` (large thumbnail, not full-res). PhotoSwipeViewer on desktop uses `2400px` or `null` (full-res via `getImageUrl`). The mobile PS5 uses thumbnails for bandwidth — but if the image quality is insufficient, the 1600px size may look blurry on retina displays.

### 9. Grid Column Slider Persistence

**File**: `frontend/src/composables/useColumnResize.ts` (lines 28-47)

Column count is saved to `localStorage` under `gallery-grid-size`. The default is computed from viewport width with a `GRID_THREE_COL_MIN_WIDTH = 460` threshold for large phones. 

**Issue**: The saved preference affects ALL folders. A user who sets 8 columns on desktop may want 3 on tablet — but the setting persists globally. The user would need to re-adjust on each device.

### 10. Breadcrumb with Deep Paths

**File**: `frontend/src/components/Breadcrumb.vue` (lines 22-23)

```typescript
const maxSegments = computed(() => props.maxVisible ?? 4);
```

If the path has more than 4 segments, breadcrumb shows an ellipsis dropdown. The dropdown path reconstruction uses `props.path` directly — if the path contains mixed separators (both `/` and `\`), parsing may produce incorrect segment boundaries.

---

## Debug Checklist

| Symptom | Likely File(s) | What to Check |
|---------|----------------|---------------|
| **Grid shows no photos** | `GalleryGrid.vue` (646-659), `App.vue` (388-398) | `.scroller-container` height chain — is `flex: 1; min-height: 0` intact? |
| **Scroll doesn't load more** | `GalleryGrid.vue` (219-255) | IntersectionObserver `rootMargin: "400px"`, `loadMoreSentinel` in DOM |
| **Mobile bars don't hide** | `useScrollVisibility.ts` (16-46) | Polling selector `.vue-recycle-scroller`, rAF handler, scroll event listener |
| **Grid layout wrong columns** | `useColumnResize.ts` (9-19, 49-55) | `getDefaultCols()` logic, `recomputeRowHeight()` formula |
| **Lightbox black screen** | `PhotoSwipeViewer.vue` (27-42) | `pswpItems` array — check URL construction. `getThumbnailUrl` vs `getImageUrl` |
| **Lightbox right arrow hidden** | `Lightbox.vue` (436-452) | `.pswp__button--arrow--next` `right` calc — sidebar width mismatch |
| **Lightbox metadata slow** | `backend/main.py` (1081-1131) | `parse_metadata()` cache — is it hitting cache or re-parsing? |
| **Swipe on mobile broken** | `MobilePhotoSwipe.vue` (37-51) | `closeOnVerticalDrag`, `allowPanToNext`, PS5 init timing |
| **Search doesn't filter** | `GalleryGrid.vue` (161-168) | `images` computed — `name.toLowerCase().includes(searchQuery)` |
| **Sort doesn't persist** | `gallery.ts` (16-33) | `SORT_STORAGE_KEY`, `getStoredSort()`, `saveSort()` |
| **Theme flash on load** | `frontend/index.html` (inline script) | `localStorage['gallery-theme']` read before CSS render |
| **PhotoSwipe arrows don't show** | `PhotoSwipeViewer.vue` (138-148) | `.pswp__button--close`, `.pswp__top-bar` hidden via `display: none` / `opacity: 0` |
| **Pull-to-refresh conflicts** | `usePullToRefresh.ts` (33-36, 67-75) | `isHorizontalScrollTarget` check, `axisLockThreshold`, `canStart` |
| **Grid slider not working** | `GalleryGrid.vue` (350-364) | `input[type="range"]`, `columnCount` v-model, opacity hidden slider |
| **Sidebar overlay on wrong breakpoint** | `App.vue` (451-507) | `@media (max-width: 767px)` — sidebar becomes fixed/overlay |
| **Clipboard copy fails** | `useClipboard.ts` (22-35) | `navigator.clipboard.writeText` vs `document.execCommand('copy')` fallback |
