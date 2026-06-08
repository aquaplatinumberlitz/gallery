# Third-Party Libraries

Last reviewed: 2026-06-08

This document explains how major external libraries are used in this project.

## Quick Index

| Library | Used for | Main integration file(s) | Notes |
|---|---|---|---|
| `@douxcode/vue-spring-bottom-sheet` | Mobile lightbox metadata sheet, drag/snap/spring animation, native-feeling scroll | `frontend/src/components/LightboxMobileSheet.vue`, `frontend/src/styles/_lightbox-mobile.scss` | Used as the sheet and motion engine only; Gallery owns metadata UI and behavior |
| PhotoSwipe 5 | Responsive lightbox image viewer, image navigation, swipe/pan/zoom | `frontend/src/components/Lightbox.vue`, `MobilePhotoSwipe.vue`, `TabletPhotoSwipe.vue`, `PhotoSwipeViewer.vue`, `frontend/src/composables/usePhotoSwipe.ts`, `frontend/src/styles/_lightbox-*.scss` | Used as the image viewer engine; Gallery owns metadata panels, custom controls, and responsive layout |
| Vue 3 | Frontend framework | `frontend/src/main.ts`, `frontend/src/App.vue`, `frontend/src/components/`, `frontend/src/layouts/` | Composition API, SFC, and `<script setup>` |
| Vite | Frontend build tool and dev server | `frontend/` | No custom plugins beyond defaults |
| Lucide | Icons across the gallery | Vue components and shared UI styles | Prefer semantic icon tokens and component-level sizing rules |
| `vue-virtual-scroller` | Virtual scrolling in the image grid | `frontend/src/components/GalleryGrid.vue` | Used for large desktop/tablet grids |
| Fuse.js | Client-side fuzzy search for gallery folders/images | `frontend/src/utils/fuzzySearch.ts`, `frontend/src/components/GalleryGrid.vue`, `frontend/package.json` | Searches currently loaded frontend data only |

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

Used for: Client-side fuzzy search for gallery folders/images.

Core features we use: weighted keys, fuzzy matching, typo tolerance, `ignoreLocation`, client-side index.

Features we intentionally do NOT use: match highlighting, server-side search, metadata/prompt full-text search, binary/image content search.

Why: Replaces fragile manual `includes()` search with typo-tolerant filename/folder search while keeping search local and simple.

Integration files: `frontend/src/utils/fuzzySearch.ts`, `frontend/src/components/GalleryGrid.vue`, `frontend/package.json`, `frontend/package-lock.json`

Common pitfalls: Do not rebuild Fuse per card, do not search unloaded paginated images unless backend search is added later, do not let `path` weight dominate `name`, do not break existing sort behavior, do not add match highlighting unless UI is designed for it.

Decision: Gallery search remains frontend-local. Fuse filters folders and the currently loaded image page set before the existing name/date sort is applied.

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

#### vue-virtual-scroller

- Used for: virtual scrolling in the image grid

## Do Not Change Casually

- Do not enable VSBS `blocking=true` without testing focus recursion with PhotoSwipe.
- Do not move VSBS overrides back into scoped-only styles.
- Do not remove VSBS width/background overrides.
- Do not reintroduce old custom mobile sheet drag code.
- Do not add `stopPropagation()` to mobile outside-tap close.
- Do not replace Vue overlay buttons with PhotoSwipe UI registration unless necessary.
