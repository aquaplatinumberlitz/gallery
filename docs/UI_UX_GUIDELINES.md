# UI/UX Guidelines

Last reviewed: 2026-06-07

## Breakpoints

Breakpoint behavior is defined in three places and must stay synchronized:

| Source | Scope |
|--------|-------|
| `frontend/src/composables/useDevice.ts` | JavaScript device detection |
| `frontend/src/styles/_breakpoints.scss` | SCSS media query mixins |
| `frontend/src/composables/useColumnResize.ts` | Grid density by device |

| Category | Width | Layout | Default grid |
|----------|-------|--------|--------------|
| Compact | `<480px` | Mobile | 2 columns |
| Mobile | `480-767px` | Mobile | 2 columns |
| Tablet | `768-1199px` | Tablet | 4 columns |
| Desktop | `1200-1439px` | Desktop | 6 columns |
| Wide | `>=1440px` | Desktop | 6 columns |

JS `<768` and SCSS `max-width: 767px` are intentionally equivalent at integer viewport widths.

## Layout Rules

Desktop:

- Use `DesktopLayout.vue`.
- Keep the 280px sidebar persistent and collapsible by edge toggle.
- Use `AppHeader` and `GalleryGrid` with RecycleScroller.

Tablet:

- Use `TabletLayout.vue`.
- Keep the 280px sidebar as a transform-based drawer.
- Keep the drawer in the DOM and apply `inert` plus `aria-hidden` when closed.
- Use `TabletHeader` and `TabletGalleryToolbar`.

Mobile:

- Use `MobileLayout.vue`.
- Use the 240px overlay sidebar with backdrop close.
- Use native scroll instead of RecycleScroller.
- Keep fixed header and bottom bar safe-area-aware.

## Grid Density

`useColumnResize.ts` maps slider levels to columns:

```typescript
GRID_COLUMN_MAP = {
  desktop: [8, 7, 6, 5, 4],
  tablet:  [5, 5, 4, 3, 3],
  mobile:  [3, 3, 2, 2, 2],
}
```

- Default level is 3.
- Stored under `localStorage['gallery-grid-size']`.
- Legacy raw column counts are migrated to slider levels.
- The same slider level intentionally produces different column counts per device.
- Do not hardcode column counts in components.

## Lightbox UX

Desktop/wide:

- Use `PhotoSwipeViewer.vue` and `LightboxDesktopPanel.vue`.
- Reserve right-side panel space through PhotoSwipe `paddingFn`.
- Keep the counter centered over the image viewport using `--lightbox-sidebar-width`.
- Keep next-arrow placement outside the metadata sidebar.

Tablet:

- Use `TabletPhotoSwipe.vue` for PhotoSwipe plus counter, zoom, close, and info toolbar.
- Use `LightboxTabletPanel.vue` for metadata.
- Keep the tablet toolbar owned by the tablet wrapper, not the shared desktop wrapper.

Mobile:

- Use `MobilePhotoSwipe.vue` with a floating info button.
- Hide the info button while `LightboxMobileSheet.vue` is open.
- Use `@douxcode/vue-spring-bottom-sheet` for the mobile metadata sheet.
- Keep the sheet at 44dvh collapsed and 80dvh expanded unless changing the full interaction model.
- Let VSBS handle drag, snap, and scroll behavior. Do not restore the old `.sheet-panel` pointer-drag implementation.
- Keep VSBS `blocking=false` so its focus trap does not conflict with PhotoSwipe focus management.
- Keep VSBS width and background overrides in a non-scoped global style block because the library teleports its DOM to `<body>`.

## Metadata Panels

- Use `ExpandableText.vue` for prompt and negative prompt fields across desktop, tablet, and mobile.
- Preserve the collapsed prompt fade overlay and "Show more" behavior.
- Preserve `expanded-change` events so mobile sheet height and reset behavior remain accurate.
- When the mobile chevron collapses an expanded sheet, reset prompt expansion state through the keyed `ExpandableText` remount behavior.

## Mobile Lightbox Sheet

Last reviewed: 2026-06-07

Mobile lightbox metadata uses `@douxcode/vue-spring-bottom-sheet` through `LightboxMobileSheet.vue`.
See [Third-Party Libraries](THIRD_PARTY_LIBRARIES.md) for VSBS and PhotoSwipe integration rationale, customizations, and pitfalls.

- Approved behavior: the info button opens the sheet and is hidden while the sheet is open; PhotoSwipe left/right image swipes continue to work behind the sheet.
- VSBS owns sheet drag, snap, swipe-close, and scroll physics. Keep the old custom pointer drag code removed, including `.sheet-panel`, `.sheet-backdrop`, `.sheet-handle-wrapper`, `.sheet-handle`, pointer capture, drag thresholds, and `--sheet-drag-y`.
- The chevron expands the sheet and shows more Prompt/Negative Prompt text. The down chevron compacts the sheet and shows less text.
- Prompt, Params, and Model tabs remain available in the sheet. Copy buttons stay active for prompt, negative prompt, seed, and other copyable metadata.
- `blocking=false` is required to avoid focus-trap recursion with PhotoSwipe.
- VSBS styles must be global, not scoped, because the library teleports sheet DOM outside the component scope.
- Keep the width chain explicit for `[data-vsbs-sheet]`, `[data-vsbs-scroll]`, `[data-vsbs-content]`, `.sheet-content`, and `.expandable-text` so the sheet cannot collapse horizontally.
- Keep the sheet background black/dark through VSBS variables and scroll/content overrides so no gray strip appears.

## Empty States

The gallery distinguishes:

| State | Condition |
|-------|-----------|
| No path selected | `!rootPath` |
| Not loaded yet | `rootPath && !hasEverLoaded` |
| Loading | `isLoading` |
| Empty folder | loaded with no folders and no images |
| Folders only | loaded with folders and no images |
| Has images | loaded with images |

The `hasEverLoaded` guard prevents a false "empty" state before the first successful scan.

## Theme and Tokens

- Theme is set with `data-theme` on `<html>`.
- `frontend/index.html` performs inline theme detection before CSS renders to reduce FOUC.
- Prefer `--gallery-*` tokens for surfaces, text, borders, radii, shadows, timing, and icon sizes.
- Legacy variables exist for compatibility, but new work should use gallery tokens.

Icon rules:

- Prefer semantic icon tokens such as `--gallery-icon-toolbar`.
- Use `:deep()` where scoped component styles must reach Lucide SVGs.
- Set `flex-shrink: 0` for icons inside flex or grid layouts.
- Avoid hardcoded Lucide `:size` values unless a component has a specific reason.

## Mobile Interaction Rules

- Maintain 44x44px minimum touch targets for coarse pointers.
- Reset hover-only effects under `@media (hover: none)`.
- Use `:active` and transparent tap highlight for touch feedback.
- Keep mobile glow effects disabled for performance and clipping.
- Keep safe-area offsets for fixed bars and lightbox controls.
- Wrap localStorage reads/writes in try/catch for Safari Private Browsing.
