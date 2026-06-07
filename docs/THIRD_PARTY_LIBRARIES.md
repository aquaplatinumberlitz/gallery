# Third-Party Libraries

Last reviewed: 2026-06-07

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

### @douxcode/vue-spring-bottom-sheet

Official links:

- Docs: https://vue-spring-bottom-sheet.douxcode.com/
- GitHub: https://github.com/megaarmos/vue-spring-bottom-sheet
- npm: https://www.npmjs.com/package/@douxcode/vue-spring-bottom-sheet

Used for: Mobile lightbox metadata sheet, drag/snap/spring animation, native-feeling scroll.

Core features we use: `BottomSheet` component, `v-model`, `snapToPoint`, `snapPoints`, built-in drag/swipe, scroll container, `headerClass`/`contentClass`, CSS variables.

Features we intentionally do NOT use: `blocking=true` / focus trap, default backdrop close, content drag expansion.

Why not: Sheet lives inside PhotoSwipe; `blocking=true` caused focus trap recursion; backdrop/swipe-close can conflict with image gestures.

Project customizations: `blocking=false`, VSBS used as sheet/motion engine only, gallery owns metadata content/tabs/copy/Show more/chevron, global CSS overrides required because VSBS teleports DOM, width chain override, background override, chevron expands sheet + Prompt details.

Integration files: `frontend/src/components/LightboxMobileSheet.vue`, `frontend/src/styles/_lightbox-mobile.scss`

Common pitfalls: Do not place overrides in scoped-only styles, do not rely on class passed to `BottomSheet` root (teleport/fragment), do not enable `blocking=true`, do not remove width-chain overrides (content collapses to 4px), do not remove scroll background override (gray strip returns), do not reintroduce old `.sheet-panel` pointer drag code, test on real iPhone/Safari.

Decision: We use VSBS as the mobile sheet motion engine, not as the owner of metadata UI. Gallery owns content and behavior; VSBS owns drag/snap/scroll.

### PhotoSwipe 5

Official links:

- Docs: https://photoswipe.com/
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

### Other libraries

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
- Do not replace Vue overlay buttons with PhotoSwipe UI registration unless necessary.
