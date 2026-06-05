# Responsive Layout & Breakpoints

## Breakpoint Sources of Truth

Three files define breakpoints. Changes must be kept in sync across all three:

| File | Scope |
|------|-------|
| `frontend/src/composables/useDevice.ts` | JavaScript device detection |
| `frontend/src/styles/_breakpoints.scss` | SCSS media query mixins |
| `frontend/src/composables/useColumnResize.ts` | Grid column mapping per device |

---

## Device Categories

| Category | JS Range | SCSS Mixin | Layout Component |
|----------|----------|------------|-----------------|
| **Compact** | `< 480px` | `@include compact` (`max-width: 479px`) | `MobileLayout.vue` |
| **Mobile** | `480–767px` | `@include mobile` (`max-width: 767px`) | `MobileLayout.vue` |
| **Tablet** | `768–1199px` | `@include tablet` (`min-width: 768px` and `max-width: 1199px`) | `TabletLayout.vue` |
| **Desktop** | `1200–1439px` | `@include desktop` (`min-width: 1200px`) | `DesktopLayout.vue` |
| **Wide** | `≥ 1440px` | `@include wide` (`min-width: 1440px`) | `DesktopLayout.vue` |

### JS Computed Properties (`useDevice.ts`)

```typescript
isCompact    = width < 480
isMobileOnly = 480 <= width < 768
isMobile     = isCompact || isMobileOnly  (width < 768)
isTablet     = 768 <= width < 1200
isDesktop    = 1200 <= width < 1440
isWide       = width >= 1440
isLargeScreen = isTablet || isDesktop || isWide
```

`useDevice` uses a **singleton pattern**: `refCount` tracks active subscribers. Only the first subscriber adds the `resize` listener; the last one removes it. This avoids duplicate listeners when multiple components call `useDevice()`.

### SCSS Mixins (`_breakpoints.scss`)

```scss
@mixin compact  { @media (max-width: 479px)  { @content; } }
@mixin mobile   { @media (max-width: 767px)  { @content; } }
@mixin tablet   { @media (min-width: 768px) and (max-width: 1199px) { @content; } }
@mixin below-desktop { @media (max-width: 1199px) { @content; } }
@mixin desktop  { @media (min-width: 1200px) { @content; } }
@mixin wide     { @media (min-width: 1440px) { @content; } }
```

JS `< 768` matches SCSS `max-width: 767px`. JS `< 480` matches SCSS `max-width: 479px`. These are functionally equivalent (widths are integers on real devices).

---

## Layout Component Dispatch

`App.vue` selects the layout component based on `useDevice()`:

```vue
<MobileLayout  v-else-if="isMobile"  ... />
<TabletLayout  v-else-if="isTablet"  ... />
<DesktopLayout v-else                ... />
```

Each layout is a self-contained shell with its own sidebar, header, content area, and `GalleryGrid`.

### Desktop (`DesktopLayout.vue`)

```
┌─────────────────────────────────────────────────────┐
│ ┌──────────┐ ┌────────────────────────────────────┐ │
│ │ Sidebar  │ │ AppHeader                          │ │
│ │ 280px    │ │ (search, sort, density, theme)     │ │
│ │          │ ├────────────────────────────────────┤ │
│ │ Tree     │ │                                    │ │
│ │          │ │ GalleryGrid (RecycleScroller)      │ │
│ │          │ │                                    │ │
│ └──────────┘ └────────────────────────────────────┘ │
│     ▲ edge toggle (collapses sidebar)               │
└─────────────────────────────────────────────────────┘
```

- Sidebar: 280px wide, persistent, collapsible via edge toggle button
- Grid: Virtual scroll with RecycleScroller
- Header: `AppHeader` with horizontal toolbar

### Tablet (`TabletLayout.vue`)

```
┌─────────────────────────────────────────────────────┐
│ TabletHeader (hamburger, breadcrumb, search, theme) │
├─────────────────────────────────────────────────────┤
│                                                     │
│ GalleryGrid (RecycleScroller)                       │
│ + TabletGalleryToolbar                              │
│                                                     │
└─────────────────────────────────────────────────────┘
  ┌──────────────┐  (drawer slides over — transform)
  │ Sidebar      │  open: translateX(0), pointer-events: auto
  │ 280px drawer │  closed: translateX(-100%), inert, pointer-events: none
  │              │  Backdrop: Transition opacity fade
  └──────────────┘
```

- Sidebar: 280px **drawer** (overlay). Always in DOM, never removed. Transform-based animation. `inert` attribute when closed.
- Backdrop: `<Transition>` with opacity. Click dismisses drawer.
- Close trigger: hamburger button, backdrop click, Escape key, successful path submit
- Gallery: `GalleryGrid` with `isMobile=false`, `showToolbarBreadcrumb=false`
- Toolbar: `TabletGalleryToolbar` — popover menus for sort and density (inside Grid)

**Why drawer, not persistent?** Tablet viewport is too narrow for a persistent sidebar alongside a meaningful grid. The drawer pattern conserves space while keeping the sidebar instantly accessible.

### Mobile (`MobileLayout.vue`)

```
┌─────────────────────────────────────────────────────┐
│ MobileHeader (hamburger, search, theme)             │
├─────────────────────────────────────────────────────┤
│                                                     │
│ GalleryGrid (native scroll, no RecycleScroller)     │
│                                                     │
├─────────────────────────────────────────────────────┤
│ MobileFloatingBottomBar (back/forward, path, open)  │
└─────────────────────────────────────────────────────┘
  ┌──────────────┐  (overlay slides in from left)
  │ Sidebar      │
  │ 240px        │
  └──────────────┘
```

- Sidebar: 240px overlay, `z-index: 100`, slides in via CSS transform
- Grid: Native scroll (no DOM recycling), pull-to-refresh
- Bars: Headers and bottom bar hide/show on scroll via `useScrollVisibility`

---

## Grid Column Mapping

`useColumnResize.ts` maps a 5-level density slider to actual column counts per device:

```typescript
GRID_COLUMN_MAP = {
  desktop: [8, 7, 6, 5, 4],  // 8 cols (compact) → 4 cols (largest)
  tablet:  [5, 5, 4, 3, 3],  // 5 cols (compact) → 3 cols (largest)
  mobile:  [3, 3, 2, 2, 2],  // 3 cols (compact) → 2 cols (largest)
}
```

- Default: level 3 (Medium) → 6 cols desktop, 4 cols tablet, 2 cols mobile
- Slider level persisted as number 1–5 in `localStorage` key `gallery-grid-size`
- Legacy raw column counts (1–8) are auto-migrated to levels via `migrateColumnsToLevel()`
- The same level produces different column counts on different devices

### Row Height Computation

```
itemWidth = (containerWidth - GAP * (columnCount - 1)) / columnCount
rowHeight = itemWidth + GAP
```

Where `GAP = 20px`. Uses `ResizeObserver` on `.scroller-container`.

---

## Component Splits Per Device

| Component | Desktop | Tablet | Mobile |
|-----------|---------|--------|--------|
| **Header** | `AppHeader` | `TabletHeader` | `MobileHeader` |
| **Bottom Bar** | — | — | `MobileFloatingBottomBar` |
| **PhotoSwipe** | `PhotoSwipeViewer` | `TabletPhotoSwipe` | `MobilePhotoSwipe` |
| **Metadata** | `LightboxDesktopPanel` | `LightboxTabletPanel` | `LightboxMobileSheet` |
| **Toolbar** | In `GalleryGrid` header | `TabletGalleryToolbar` | — (hidden) |
| **Album Card** | `AlbumCard` | `AlbumCardTablet` | `AlbumCardMobile` |
| **Sidebar** | Persistent 280px | Drawer 280px | Overlay 240px |

---

## Sort / Density Toolbar Differences

| | Desktop (`AppHeader`) | Tablet (`TabletGalleryToolbar`) | Mobile |
|---|---|---|---|
| **Layout** | Horizontal toolbar row | Popover dropdown menus | Hidden |
| **Sort** | Dropdown in GalleryGrid | Popover with check marks (TabletGalleryToolbar) | — |
| **Density** | Slider `<input type="range">` | Popover with label+columns (TabletGalleryToolbar) | — |
| **Nav arrows** | — | In Toolbar | In FloatingBottomBar |

---

## Do / Don't

- **Do** update all three files (`useDevice.ts`, `_breakpoints.scss`, `useColumnResize.ts`) when changing breakpoints
- **Do** keep `useDevice` as the single source of truth for JS device detection
- **Do** test layout changes at breakpoint boundaries (767↔768, 1199↔1200)
- **Don't** add `v-if` to remove the tablet drawer — use `inert` + CSS transform for animation
- **Don't** hardcode column counts in components — use `columnCount` from `useColumnResize`
