# Codebase Context for OpenCode Investigation

## Repo: /home/ubuntu/gallery-repo/frontend (Vue 3 + TS + SCSS + Pinia)

## Current breakpoint system
JS/TS: src/composables/useDevice.ts — BREAKPOINTS = { compact: 480, mobile: 768, desktop: 1200, wide: 1440 }
- isMobile = width < 768 (isCompact || isMobileOnly)
- isTablet = 768-1199
- isDesktop = 1200-1439, isWide = >= 1440

SCSS: src/styles/_breakpoints.scss — $bp-compact: 480px, $bp-mobile: 768px, $bp-desktop: 1200px, $bp-wide: 1440px
Mixins: @include compact (max-width:479px), @include mobile (max-width:767px), @include tablet (768-1199), @include below-desktop (max-width:1199px), @include desktop (min-width:1200px), @include wide (min-width:1440px)

JS/CSS consistent. GalleryGrid receives :is-mobile prop from App.vue (useDevice()). On tablet isMobile=false → PC template. On mobile isMobile=true → native scroll + slider hidden via CSS.

## Current column flow
File: src/composables/useColumnResize.ts
- sliderLevel (ref 1-5), localStorage key 'gallery-grid-size', default=3
- PHOTO_GRID_LEVELS: Level 1=8, 2=7, 3=6, 4=5, 5=4 columns
- getDefaultLevel() — ALL 3 branches return DEFAULT_PHOTO_GRID_LEVEL=3 (no responsive diff)
- effectiveColumnCount = computed(() => levelToColumns(sliderLevel.value))
- columnCount = alias of effectiveColumnCount
- rowHeight = (width - gap * (n-1)) / n + gap

WHERE columnCount is used in GalleryGrid.vue:
- Line 419: skeleton grid `repeat(${columnCount}, 1fr)`
- Line 462: PC virtual row `repeat(${columnCount}, 1fr)`
- Line 524: MOBILE virtual row `repeat(${columnCount}, 1fr)` — SAME as PC!
- Line 221: imageRows slicing by columnCount
- Line 394: slider badge showing column count
- Lines 433-438: RecycleScroller condition + key + item-size

PROBLEM: No responsive clamp. iPhone 375px level=3 → 6 cols → ~42px thumbnails.
Mobile grid-slider hidden via CSS `display:none` at @media (max-width:767px) but columnCount still 6.

## useColumnResize.ts full content
- Takes NO parameters (standalone composable)
- loadGridSize() reads localStorage, migrateColumnsToLevel() handles legacy values
- saveGridSize() writes on sliderLevel watch
- recomputeRowHeight(width) calculates itemWidth + GAP
- setGridRef(el) sets up ResizeObserver on grid container
- GAP = 20 constant

## GalleryGrid.vue relevant details
- PC template: `<RecycleScroller v-if="!props.isMobile && imageRows.length > 0 && rowHeight > 0" ...>`
- Mobile template: `<div v-else-if="props.isMobile && imageRows.length > 0" class="scroller mobile-scroller">`
- Mobile CSS @media (max-width:767px): hides grid-slider, hides sort-dropdown, gap 4px, padding 4px
- CSS @media (max-width:1199px): tighter grid-header gap, breadcrumb max-width clamp
