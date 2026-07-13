# UI/UX Guidelines

Status: Maintained

Last reviewed: 2026-07-08

## Breakpoints

Breakpoint behavior is defined in three places and must stay synchronized:

| Source                                        | Scope                       |
| --------------------------------------------- | --------------------------- |
| `frontend/src/composables/useDevice.ts`       | JavaScript device detection |
| `frontend/src/styles/_breakpoints.scss`       | SCSS media query mixins     |
| `frontend/src/composables/useColumnResize.ts` | Grid density by device      |

| Category | Width         | Layout  | Default grid |
| -------- | ------------- | ------- | ------------ |
| Compact  | `<480px`      | Mobile  | 2 columns    |
| Mobile   | `480-767px`   | Mobile  | 2 columns    |
| Tablet   | `768-1199px`  | Tablet  | 4 columns    |
| Desktop  | `1200-1439px` | Desktop | 6 columns    |
| Wide     | `>=1440px`    | Desktop | 6 columns    |

JS `<768` and SCSS `max-width: 767px` are intentionally equivalent at integer viewport widths.

## Layout Rules

Desktop:

- Use `DesktopLayout.vue`.
- Keep the 280px sidebar persistent and collapsible by edge toggle.
- Use `AppHeader` and `GalleryGrid` with TanStack Virtual.

Tablet:

- Use `TabletLayout.vue`.
- Keep the 280px sidebar as a transform-based drawer.
- Keep the drawer in the DOM and apply `inert` plus `aria-hidden` when closed.
- Use `TabletHeader` and `TabletGalleryToolbar`.
- Keep the tablet shell visually flat: the header may use a bounded chrome surface,
  but the gallery content must not be wrapped in an additional desktop-style card.
- Present browse context in the header and keep navigation, sort, and density in a
  separate compact toolbar below it.

Mobile:

- Use `MobileLayout.vue`.
- Use the 240px overlay sidebar with backdrop close.
- Mobile uses native scroll instead of virtual scrolling.
- Keep fixed header and bottom bar safe-area-aware.
- Show the current browse context in the top bar instead of filling the header with
  secondary shortcuts. Library selection and management remain available in the sidebar.
- Keep the bottom dock focused on back/forward history and the current folder label.
- In the expanded mobile search state, keep back, input, scope, and Advanced Search
  within one viewport-width row. Use the icon-only scope trigger on mobile while
  retaining the full scope labels and descriptions in its select menu.
- Close the empty-query search overlay from `pointerdown`, not a synthesized
  touch `click`, so opening or selecting a teleported scope option cannot dismiss
  the expanded search state.
- Render search album suggestions with the same device-specific card family used
  by gallery browsing: two-column `AlbumCardMobile` cards on mobile,
  `AlbumCardTablet` on tablet, and the layered desktop card on desktop.

## Grid Density

`useColumnResize.ts` maps slider levels to columns:

```typescript
GRID_COLUMN_MAP = {
  desktop: [8, 7, 6, 5, 4],
  tablet: [5, 5, 4, 3, 3],
  mobile: [3, 3, 2, 2, 2],
};
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
- Hide the floating PhotoSwipe toolbar while the metadata panel is open so controls never overlap sheet content.
- Only the 44px handle may expand or collapse the tablet panel. Scrolling or swiping either metadata column must never dismiss it.
- Treat the panel as a non-modal dialog, move focus to its handle on open, support Escape to close, and restore focus to the Info button.

Mobile:

- Use `MobilePhotoSwipe.vue` with a floating info button.
- Hide the info button while `LightboxMobileSheet.vue` is open.
- Use `@douxcode/vue-spring-bottom-sheet` for the mobile metadata sheet.
- Keep the VSBS snap points at `44%` collapsed and `80%` expanded unless changing the full interaction model.
- Let VSBS handle drag, snap, and scroll behavior. Do not restore the old `.sheet-panel` pointer-drag implementation.
- Keep VSBS `blocking=false` so its focus trap does not conflict with PhotoSwipe focus management.
- Disable PhotoSwipe's duplicate focus trap on mobile/tablet; the outer lightbox `FocusScope` owns trapping while metadata is closed and is temporarily non-trapping while the teleported mobile sheet is open.
- Expose the VSBS surface as a labelled non-modal dialog and remove its library-provided `aria-modal` attribute while `blocking=false`.
- Implement Prompt, Params, and Model with tablist/tab/tabpanel semantics and Left/Right/Home/End keyboard navigation.
- Keep all sheet actions at least 44x44px and include `env(safe-area-inset-bottom)` in bottom padding.
- Keep VSBS width and background overrides in a non-scoped global style block because the library teleports its DOM to `<body>`.
- PhotoSwipe owns image rendering, photo swipe left/right, pan/zoom, and lightbox close. The metadata sheet must not intercept these gestures outside the sheet body.

## Metadata Panels

- Use `ExpandableText.vue` for prompt and negative prompt fields across desktop, tablet, and mobile.
- Preserve the collapsed prompt fade overlay and "Show more" behavior.
- Preserve `expanded-change` events so mobile sheet height and reset behavior remain accurate.
- When the mobile chevron collapses an expanded sheet, reset prompt expansion state through the keyed `ExpandableText` remount behavior.
- Planned, not yet implemented: show an EXIF tab only when backend metadata includes `exif.hasData`. The EXIF panel should be a compact grouped summary with human-readable labels, hidden empty rows, single-column mobile layout, and one- or two-column tablet/desktop layout. Do not show an empty EXIF tab, a raw EXIF dump, a GPS map, or a Copy EXIF action in v1.

## Mobile Lightbox Sheet

Last reviewed: 2026-07-12

Mobile lightbox metadata uses `@douxcode/vue-spring-bottom-sheet` through `LightboxMobileSheet.vue`.
See [Third-Party Libraries](THIRD_PARTY_LIBRARIES.md) for VSBS and PhotoSwipe integration rationale, customizations, and pitfalls.

- Approved behavior: the info button opens the sheet and is hidden while the sheet is open; PhotoSwipe left/right image swipes continue to work behind the sheet.
- VSBS owns sheet drag, snap, swipe-close, and scroll physics. Keep the old custom pointer drag code removed, including `.sheet-panel`, `.sheet-backdrop`, `.sheet-handle-wrapper`, `.sheet-handle`, pointer capture, drag thresholds, and `--sheet-drag-y`.
- The chevron-up action expands the sheet and auto-shows more Prompt/Negative Prompt text. The chevron-down action compacts the sheet and auto-shows less Prompt/Negative Prompt text.
- Show more expands text and expands the sheet if needed. Show less collapses text without closing the sheet.
- Prompt, Params, and Model tabs remain available in the sheet. Copy buttons stay active for prompt, negative prompt, seed, and other copyable metadata.
- Body content scrolls normally inside the VSBS scroll area.
- Outside tap closes the metadata sheet only. It must not close PhotoSwipe or block image swipe left/right.
- `blocking=false` is required to avoid focus-trap recursion with PhotoSwipe.
- Because this is non-blocking, the teleported VSBS root must use `role="dialog"`, a stable accessible label, and no `aria-modal="true"`.
- The tab strip follows the WAI-ARIA tabs pattern, including roving tabindex and ArrowLeft/ArrowRight/Home/End navigation.
- Escape closes the sheet and focus returns to the floating Info button.
- Use the semantic `--gallery-z-lightbox` and `--gallery-z-lightbox-panel` tokens instead of one-off overlay z-index values.
- VSBS styles must be global, not scoped, because the library teleports sheet DOM outside the component scope.
- Keep the width chain explicit for `[data-vsbs-sheet]`, `[data-vsbs-scroll]`, `[data-vsbs-content]`, `.sheet-content`, and `.expandable-text` so the sheet cannot collapse horizontally.
- Keep the sheet background black/dark through VSBS variables and scroll/content overrides so no gray strip appears.
- Review the VSBS/PhotoSwipe constraints in [Third-Party Libraries](THIRD_PARTY_LIBRARIES.md) before changing this flow.

## Empty States

The gallery distinguishes:

| State            | Condition                                             |
| ---------------- | ----------------------------------------------------- |
| No path selected | `!rootPath`                                           |
| Not loaded yet   | active browse scope without an active query page      |
| Loading          | active browse scope with pending/fetching query state |
| Empty folder     | active query page with no folders and no images       |
| Folders only     | active query page with folders and no images          |
| Has images       | active query page with images                         |

The active query page must match the current library and browse path before gallery data is rendered or considered empty.

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

## Keyboard Focus

- Standalone interactive controls use the global `:focus-visible` halo from `main.scss`, sourced from `--focus-ring-shadow` in `tokens.css`.
- Preserve the established visual: a 3px external shadow using 50% of `--ring` in light mode and 70% in dark mode. Do not replace it with an inset outline or a thinner ring to work around clipping.
- Tailwind `ring-*` utilities and component-local focus rules must consume the same `--focus-ring-shadow` token so only one halo is rendered.
- Composite controls render the same halo on their outer wrapper only while the inner native input is `:focus-visible`. Mark that input with `data-focus-ring="none"`; focusable actions inside the composite keep their own single halo instead of also activating the wrapper halo.
- Fix clipping at the responsible layout boundary by allowing visible overflow or adding sufficient focus-safe spacing; never degrade the focus visual globally.
- Regression tests must verify the computed 3px shadow at mobile, tablet, and desktop breakpoints.

## Advanced Search

- Keep one shared Advanced Search drawer instance at the app shell so filter state and serialization stay consistent across layouts.
- Desktop exposes Advanced Search in both expanded and compact search headers.
- Tablet and mobile expose Advanced Search from the expanded search bar.
- Use a 560px right-side sheet where space allows and a full-width sheet on compact mobile viewports.
- Keep selected filters visible above collapsed sections. Repeated or unsupported filters must also open the Custom metadata section.
- Show validation counts on affected section headers and in the footer; submitting an invalid form must open and focus the first invalid field.
- Do not dismiss dirty edits from an outside pointer interaction. Explicit Cancel, Close, or Escape may discard staged changes.
- Maintain 44x44px touch targets for compact-header actions and sheet close controls.
- Keep discovery inside the same shared sheet on desktop, tablet, and mobile:
  saved/recent searches, prompt usage, typed workflow filters, optional raw
  workflow search, and derived-index status are independent sections rather
  than new header or root-component responsibilities.
- Prompt usage keeps positive/negative tabs, visible counts, a sample image,
  Copy, and Show assets. Workflow controls render only capability-advertised
  nodes/properties/operators and identify validation errors by predicate row.
- Raw workflow controls are absent when disabled. When enabled they require an
  explicit acknowledgement and Apply action; typing alone never sends a query.
- Index controls distinguish ready, usable-stale/building, degraded, failed,
  unavailable, and disabled. Confirm rebuilds and disable duplicate actions.

## Related Assets Language

- Use `Related Assets`, `Same Recipe`, and `Visual Variants`; never label the
  feature semantic search, AI similarity, or lineage detection.
- Visual evidence means near-duplicate or compositionally close pixels only.
  It does not prove a shared prompt, recipe, source file, or generation lineage.
- Expose honest limitations where visual results are explained: large crops,
  mirrors, rotations, and generative composition changes may not match, while
  similar colors/layouts can produce false positives.
- A missing current visual fingerprint is a coverage state, not an empty result.
  Show rebuild/index status context without blocking metadata-related results.
