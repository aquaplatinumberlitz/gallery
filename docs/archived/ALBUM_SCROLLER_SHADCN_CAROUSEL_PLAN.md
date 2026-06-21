# Desktop AlbumScroller shadcn-vue Carousel Refactor Plan

> **Archived:** Implemented in commit `f6144ea` on 2026-06-14. The current
> implementation keeps `AlbumScroller.vue` as the responsive wrapper, uses
> `AlbumCarouselDesktop.vue` with shadcn-vue Carousel/Embla on desktop, and
> retains `AlbumScrollerNative.vue` for mobile and tablet. This document is
> historical design context, not an active plan or current source of truth.

Date: 2026-06-14

Status: implemented and archived.

Primary sources:

- Current codebase audit in `frontend/src/components/AlbumScroller.vue`, album card components, device helpers, style tokens, and Playwright tests.
- shadcn-vue Carousel docs: https://www.shadcn-vue.com/docs/components/carousel
- shadcn-vue registry item inspected read-only: `https://shadcn-vue.com/r/styles/default/carousel.json` and `https://shadcn-vue.com/r/styles/new-york-v4/carousel.json`
- Embla options docs for option tradeoffs: https://www.embla-carousel.com/api/options/

## Executive Summary

Replace only the desktop AlbumScroller scroll engine with shadcn-vue Carousel primitives backed by Embla. Keep mobile and tablet on the current native horizontal scroll implementation in this phase.

Recommended architecture:

- Keep `AlbumScroller.vue` as the public component API: `folders` prop and `open-folder` emit stay unchanged.
- Keep the existing album header, count, collapsed state, transition, and `localStorage` key in `AlbumScroller.vue`.
- Add `AlbumCarouselDesktop.vue` for the desktop shadcn Carousel branch.
- Add `AlbumScrollerNative.vue` for the existing native mobile/tablet branch when desktop migration replaces the current mixed implementation.
- Do not create a separate `AlbumScrollerMobile.vue` in the first implementation unless native mobile/tablet code becomes too large after extraction.

This gives a clean desktop Embla implementation while preserving the proven mobile/tablet behavior and avoiding lightbox or PhotoSwipe risk.

## Current Implementation Audit

### Public API and Mount Points

`AlbumScroller.vue` currently accepts:

- `folders: FileNode[]`
- emits `open-folder` with the selected folder path

`GalleryGrid.vue` mounts `AlbumScroller` in three paths:

- Desktop/tanstack scroller with images: `GlowContainer disabled=false`, then `AlbumScroller`.
- Mobile native scroller with images: `GlowContainer disabled=true`, then `AlbumScroller`.
- Folders-only fallback: `GlowContainer :disabled="props.isMobile"`, then `AlbumScroller`.

The component itself hides entirely when `folders.length` is zero via `section v-if="folders.length"`.

### Current DOM Structure

The current `AlbumScroller.vue` renders:

```txt
section.album-scroller
  button.album-toggle
    GallerySectionHeader(title="Albums", count=folders.length, collapsed=collapsed)
  Transition(name="album-collapse")
    div.album-grid-wrapper[shown when !collapsed]
      button.album-scroll-btn.album-scroll-btn--left
      button.album-scroll-btn.album-scroll-btn--right
      div.album-grid(ref=gridRef)
        component AlbumCard | AlbumCardTablet | AlbumCardMobile per folder
```

The album card is chosen at render time:

```txt
isMobile ? AlbumCardMobile : isTablet ? AlbumCardTablet : AlbumCard
```

### Current Scroll Container

The scroll container is `div.album-grid`.

Desktop base styles:

- `display: flex`
- `flex-wrap: nowrap`
- `gap: 24px`
- `overflow-x: auto`
- `overflow-y: hidden`
- `padding: 24px 12px`
- hidden scrollbars
- `touch-action: pan-x`
- `overscroll-behavior-x: contain`
- `scroll-behavior: smooth`

Children get:

- `flex-shrink: 0`
- `min-width: 180px`
- `max-width: 240px`
- `will-change: transform, opacity`

### Current Arrow Implementation

The arrows are native `<button>` elements in `AlbumScroller.vue`, absolutely positioned inside `.album-grid-wrapper`:

- Left: `.album-scroll-btn.album-scroll-btn--left`
- Right: `.album-scroll-btn.album-scroll-btn--right`
- Icons: `ArrowLeft` and `ArrowRight` from `lucide-vue-next`
- Disabled state is also visually hidden through `opacity: 0` and `pointer-events: none`
- Buttons are conditionally shown with `v-show`

The arrow controls are not shadcn-vue Button controls today. They use custom gallery styling, including warm/orange hover and dark-mode styling.

Warm control styles to neutralize in the future desktop implementation:

- `.album-scroll-btn:not(:disabled):hover` uses `color: var(--primary-color)`, warm border, and warm background.
- Dark mode `.album-scroll-btn` uses warm gold border color.
- `@supports color-mix` block mixes `var(--primary-color, #ffb84d)` into button background, border, and inset shadow.

These should not be reused for shadcn Carousel controls.

### Arrow Visibility Calculation

Current arrow state is manual:

```txt
showLeftArrow = scrollLeft > 4
showRightArrow = scrollLeft < scrollWidth - clientWidth - 4
```

This runs from:

- scroll events on `.album-grid`
- a RAF-throttled `scheduleArrowsUpdate`
- `ResizeObserver`
- `window.resize`
- re-init when `props.folders.length` changes

The desktop Carousel branch should let Embla own this through `canScrollPrev` and `canScrollNext`, exposed by shadcn-vue Carousel slot props or `useCarousel`.

### Scroll Amount Calculation

Current manual scroll uses:

```txt
card = grid.querySelector('[class*="album-card"]')
cardWidth = card.offsetWidth || 200
gap = parseInt(getComputedStyle(grid).gap) || 24
scrollAmount = (cardWidth + gap) * direction
grid.scrollBy({ left: scrollAmount, behavior: "smooth" })
```

It schedules a delayed arrow update after 350 ms.

This logic should be removed from the desktop branch after Embla migration. If tablet remains native, this logic can remain isolated in `AlbumScrollerNative.vue`.

### Mobile Scroll-Snap

Mobile is scoped at `max-width: 767px`:

- `.album-grid-wrapper` has no padding/margin.
- edge fade overlays are hidden.
- `.album-grid` uses `gap: 12px`, `padding: 4px 0 8px`, and `scroll-snap-type: x mandatory`.
- children use `min-width: 130px`, `max-width: 170px`, and `scroll-snap-align: start`.
- arrows are `display: none`.

Compact mobile at `max-width: 480px` tightens:

- gap to `6px`
- child width to `min-width: 110px`, `max-width: 140px`

Mobile should stay native in the future implementation.

### Tablet Behavior

Tablet is defined by shared breakpoints as `768px <= width <= 1199px`.

Tablet branch currently differs from desktop in two ways:

- The component renders `AlbumCardTablet`.
- CSS changes `.album-grid` to `gap: 12px`, `padding: 4px 8px 20px`, and child width to `min-width: 150px`, `max-width: 200px`.

Tablet currently still uses the same native scroll engine and visible arrow buttons as desktop, with 46px controls positioned 8px from each side. It does not use mobile scroll-snap. For this migration, keep tablet native unless a future scoped task explicitly approves tablet Embla testing.

### Collapsed/Expanded State Persistence

State is local to `AlbumScroller.vue`:

- Key: `gallery-albums-collapsed`
- Default: `true`
- `onMounted` reads `localStorage`
- `toggleCollapsed` flips the ref and writes `String(collapsed.value)` back to `localStorage`
- Header button has `aria-expanded="!collapsed"` and an expand/collapse `aria-label`

Future implementation should keep this in the public `AlbumScroller.vue` wrapper, not duplicate it in desktop/mobile child components.

### Album Card Width and Gap Definitions

Widths are controlled by `AlbumScroller.vue` CSS, not the card components:

- Desktop child: `min-width: 180px`, `max-width: 240px`, `gap: 24px`.
- Tablet child: `min-width: 150px`, `max-width: 200px`, `gap: 12px`.
- Mobile child: `min-width: 130px`, `max-width: 170px`, `gap: 12px`.
- Compact child: `min-width: 110px`, `max-width: 140px`, `gap: 6px`.

The desktop Carousel must reproduce these dimensions with either:

- Tailwind arbitrary basis/width classes on `CarouselItem`, or
- a scoped desktop carousel CSS class on `CarouselItem`.

Because shadcn Carousel spacing defaults to `CarouselContent class="-ml-4"` and `CarouselItem class="pl-4"`, the future implementation should intentionally map the current 24px desktop gap. The cleanest match is likely `CarouselContent class="-ml-6"` and `CarouselItem class="basis-[180px] max-w-[240px] pl-6"` or equivalent scoped CSS.

### CSS Desktop-Only vs Mobile/Tablet

Desktop/base CSS:

- `.album-scroller`
- `.album-grid-wrapper`
- edge fade overlays
- `.album-grid`
- `.album-grid > *`
- `.album-scroll-btn` and related arrow styling
- collapse transition
- toggle button

Tablet CSS:

- `@include tablet` block changes gap, padding, item widths, fade width, and arrow offsets.

Mobile CSS:

- `@media (max-width: 767px)` block adds scroll-snap, hides arrows and fades, changes item widths and padding.
- `@media (max-width: 480px)` compact block tightens gap and item widths.

Other mobile-sensitive code:

- `usePullToRefresh.ts` treats `.album-grid` and `.albums-grid` as horizontal scroll targets to avoid triggering pull-to-refresh from horizontal album gestures.
- `_mobile-overrides.scss` resets sticky hover effects on `.album-card` and `.album-card-mobile` for touch devices.

### Existing Tests Covering AlbumScroller

There is no direct AlbumScroller arrow/carousel test today.

Current indirect coverage:

- `gallery-no-reload-real-backend.spec.ts` sets `gallery-albums-collapsed` to `"false"`, waits for `data-testid="album-card"`, clicks the first album card, and verifies no page reload.
- `gallery-no-reload.spec.ts` covers no reload and boot id behavior, but its stubbed scan returns no folders, so it does not exercise AlbumScroller in that path.
- `responsive-breakpoints.spec.ts` verifies mobile, tablet, desktop, and large desktop photo card layout, but its scan stubs folders as empty, so it does not exercise AlbumScroller.
- `tailwind-phase0.spec.ts` verifies `[data-theme="dark"]` based theme switching and shadcn/Tailwind token behavior, but not AlbumScroller.

Future implementation needs new direct tests for desktop Carousel behavior and mobile/tablet native preservation.

### Known Frozen-Zone Risks

Mobile/tablet and lightbox are risky zones:

- iOS Safari horizontal gesture behavior is sensitive.
- Mobile album scroll-snap is simple and proven.
- Pull-to-refresh intentionally excludes `.album-grid`.
- Mobile hover/glow resets explicitly target album card classes.
- Mobile `GlowContainer` is disabled where `GalleryGrid` knows it is mobile.
- PhotoSwipe/lightbox tests exist and should not be touched for this task.

## shadcn-vue Carousel Research

### Required Package and Component Additions

The project currently has:

- `shadcn-vue` installed.
- `@vueuse/core` installed.
- `lucide-vue-next` and `@lucide/vue` installed.
- Existing shadcn-like primitives under `frontend/src/components/ui`.
- No `frontend/src/components/ui/carousel` directory.
- No `embla-carousel-vue` or `embla-carousel` installed.
- No existing Carousel usage.

The shadcn-vue Carousel registry item requires:

- `embla-carousel-vue`
- `@vueuse/core`
- registry dependency: `button`

`@vueuse/core` already exists. `embla-carousel-vue` does not. The implementation phase should install only what the official shadcn-vue Carousel add requires.

### Expected shadcn Component Files

The official registry generates a carousel directory with:

- `Carousel.vue`
- `CarouselContent.vue`
- `CarouselItem.vue`
- `CarouselNext.vue`
- `CarouselPrevious.vue`
- `index.ts`
- `interface.ts`
- `useCarousel.ts`

Important local integration note:

- The checked-in shadcn primitives currently use direct files such as `frontend/src/components/ui/Button.vue`.
- Several subcomponent families use folder `index.ts` exports, but Button does not currently have a `components/ui/button/index.ts` folder.
- The future implementation should reconcile the generated Carousel imports with the local Button convention. Either let the shadcn CLI create the expected `ui/button` structure and audit duplicates, or adapt Carousel button imports to the existing `Button.vue` file. Do not overwrite current Button behavior blindly.
- The current `Button.vue` defines a local `ButtonVariants` type but does not export it. Some current registry styles expect `ButtonVariants` exports. This is a likely typecheck issue to handle in Phase B if the installed Carousel variant imports that type.

### Usage Pattern

The docs show this Vue structure:

```vue
<Carousel>
  <CarouselContent>
    <CarouselItem>...</CarouselItem>
    <CarouselItem>...</CarouselItem>
  </CarouselContent>
  <CarouselPrevious />
  <CarouselNext />
</Carousel>
```

For album desktop:

```vue
<Carousel
  v-slot="{ canScrollNext, canScrollPrev }"
  class="album-carousel-desktop"
  :opts="carouselOpts"
>
  <CarouselContent class="album-carousel-content">
    <CarouselItem
      v-for="item in folders"
      :key="item.path"
      class="album-carousel-item"
    >
      <AlbumCard :node="item" @click="emit('open-folder', item.path)" />
    </CarouselItem>
  </CarouselContent>

  <CarouselPrevious v-if="canScrollPrev" aria-label="Previous album" />
  <CarouselNext v-if="canScrollNext" aria-label="Next album" />
</Carousel>
```

However, hiding controls with `v-if` can cause layout or focus changes depending on positioning. Prefer reserving stable arrow space in the wrapper and using either:

- always render controls with disabled state, or
- render controls only when useful but position them over reserved gutters so layout does not shift.

### Options and API

shadcn-vue passes `opts` through to Embla and sets the Embla axis from `orientation`.

The docs show:

```vue
<Carousel :opts="{ align: 'start', loop: true }">
```

The docs expose API access in two ways:

- `@init-api="setApi"` to receive `CarouselApi`
- template ref on `<Carousel />` and then `carouselRef.value?.carouselApi`

The docs also expose slot props:

- `carouselRef`
- `canScrollNext`
- `canScrollPrev`
- `scrollNext`
- `scrollPrev`

The desktop AlbumScroller should use slot props first. It should avoid custom API subscriptions unless tests show the built-in control state is insufficient.

### Disabled Prev/Next States

The generated Carousel controls use `canScrollPrev` and `canScrollNext` from `useCarousel`.

`useCarousel.ts` updates those refs on Embla:

- `init`
- `reInit`
- `select`

`CarouselPrevious` disables itself with `:disabled="!canScrollPrev"`.
`CarouselNext` disables itself with `:disabled="!canScrollNext"`.

For this app, "show controls only when useful" can mean:

- desktop controls are visually hidden when `!canScrollPrev` or `!canScrollNext`, or
- controls remain rendered and disabled at edges but the whole arrow area is absent when there is no overflow.

Use Embla state rather than measuring `scrollWidth`.

### Keyboard Navigation

Generated `Carousel.vue`:

- renders a focusable root with `tabindex="0"`
- sets `role="region"`
- sets `aria-roledescription="carousel"`
- handles `ArrowLeft`/`ArrowRight` for horizontal carousels
- handles `ArrowUp`/`ArrowDown` for vertical carousels
- calls `scrollPrev()` or `scrollNext()`

This is a net improvement over the current desktop native scroller, but the existing album cards are `div`s with click and keydown handlers and no `tabindex` or explicit role. That existing issue should not block the carousel migration, but keyboard testing should verify that:

- the carousel root can receive focus,
- arrow keys work while the root is focused,
- tab order does not trap focus,
- album card click behavior remains unchanged.

### Generated CSS Classes and Tokens

Core generated classes:

- `Carousel`: `relative`
- `CarouselContent` viewport: `overflow-hidden`
- `CarouselContent` inner: `flex`, default horizontal `-ml-4`
- `CarouselItem`: `min-w-0 shrink-0 grow-0 basis-full`, default horizontal `pl-4`
- `CarouselPrevious` and `CarouselNext`: absolute, `size-8`, `rounded-full`, `variant="outline"`, `size="icon"` in current registry styles

Controls use the local shadcn Button variant classes. The current `Button.vue` outline/icon defaults map to neutral tokens:

- `border-input`
- `bg-background`
- `hover:bg-accent`
- `hover:text-accent-foreground`
- `focus-visible:ring-ring`
- disabled opacity/pointer behavior

The project's `_shadcn-token-bridge.css` maps those shadcn tokens to neutral Stone values and keeps dark mode under `[data-theme="dark"]`. Do not replace that with `.dark`.

## Proposed Architecture

### Recommended Split

Use a small public wrapper plus two implementation children:

```txt
AlbumScroller.vue
  owns header, collapsed state, localStorage, transition, empty behavior
  branches by device

AlbumCarouselDesktop.vue
  desktop only
  uses shadcn Carousel and AlbumCard
  emits open-folder

AlbumScrollerNative.vue
  tablet/mobile native implementation extracted from current AlbumScroller
  uses AlbumCardTablet or AlbumCardMobile
  keeps native .album-grid mechanics, scroll-snap, and tablet arrows
```

Why this split:

- It preserves the external `AlbumScroller.vue` API.
- It removes desktop scroll engine complexity from the native mobile/tablet path.
- It keeps Embla imports out of mobile/tablet code.
- It makes future deletion of desktop-only native scroll code straightforward.
- It limits risk better than rewriting the current component in place.

Do not split `AlbumScrollerMobile.vue` yet. Native mobile and tablet share enough current behavior that one `AlbumScrollerNative.vue` is lower churn. Split later only if tablet and mobile diverge further.

### Device Branching

Use `useDevice()` from the wrapper:

- `isMobile` -> native
- `isTablet` -> native
- otherwise desktop/wide -> shadcn Carousel

Keep the breakpoints unchanged:

- compact `< 480`
- mobile `< 768`
- tablet `< 1200`
- desktop `< 1440`
- wide `>= 1440`

### State and Events

Preserve exactly:

- `folders` prop
- `open-folder` emit
- `gallery-albums-collapsed` key
- default collapsed state
- header title/count/icon
- `section v-if="folders.length"`
- album click behavior
- collapse transition unless future visual review explicitly changes it

## Desktop Carousel Requirements and Decisions

### Carousel Options

Recommended starting options:

```ts
const carouselOpts = {
  align: "start",
  loop: false,
  containScroll: "trimSnaps",
  dragFree: false,
  skipSnaps: false,
};
```

Tradeoffs:

- `align: "start"`: Best match for the current left-aligned row and shadcn docs examples for multiple visible items. It avoids centered partial-card behavior.
- `loop: false`: Best match for current native scroll boundaries and disabled/hidden edge controls. Looping would make edge state less clear and can duplicate slides internally.
- `containScroll: "trimSnaps"`: Embla default and a good fit for avoiding awkward empty trailing space when the last album is selected.
- `dragFree: false`: More premium and predictable for a button-driven desktop carousel. It snaps to album positions and makes tests less flaky.
- `dragFree: true`: Closer to native trackpad/free scroll feel, but can make arrow state and visual snapshots harder to reason about. Defer unless desktop UX review specifically wants free glide.
- `skipSnaps: false`: More controlled, one snap step per command. Consider `true` only if long rows feel too slow with many albums.
- `slidesToScroll`: Leave default `1` initially. Consider `"auto"` only after measuring whether one-card arrow movement feels too slow on wide desktop.

### Desktop Item Sizing

Goal: preserve desktop card width and 24px gap as closely as possible.

Implementation options:

1. Scoped CSS on Carousel classes:

```scss
.album-carousel-content {
  margin-left: -24px;
}

.album-carousel-item {
  flex: 0 0 180px;
  max-width: 240px;
  padding-left: 24px;
}
```

2. Tailwind classes:

```txt
CarouselContent class="-ml-6"
CarouselItem class="basis-[180px] max-w-[240px] pl-6"
```

Prefer scoped CSS if Tailwind arbitrary class generation or future refactors make the class string harder to audit. Prefer Tailwind if the generated Carousel files already follow shadcn utility conventions cleanly after Phase B.

### Desktop Controls

Use shadcn Carousel controls or equivalent wrappers around shadcn Button. Requirements:

- Stone neutral outline/icon buttons.
- No warm/orange hover or focus states.
- No heavy custom shadows.
- Stable arrow placement that does not cause layout shift.
- No native browser tooltip leaks. Do not use `title` on controls.
- Accessible labels such as `aria-label="Previous album"` and `aria-label="Next album"`.

Important: generated CarouselPrevious/Next default to `-left-12` and `-right-12`. In this layout, `GlowContainer` and the scroller width may make outside-positioned controls risky. Future implementation should test whether outside arrows create horizontal page overflow. If they do, override placement inside a reserved control gutter or use inset positioning.

Suggested approach:

- Wrap the carousel in a desktop-only `.album-carousel-frame` with stable horizontal padding/gutters for arrows.
- Position controls absolutely within that reserved frame.
- Keep controls mounted but disabled at edges, or hide with opacity while preserving layout.
- Use `v-slot` state to suppress both controls when there is no overflow if needed.

### Mouse Wheel and Trackpad

Do not add wheel gesture support in the first desktop Carousel migration.

Reason:

- shadcn Carousel does not include wheel gestures by default.
- Embla wheel gestures require an additional plugin and package.
- Desktop trackpads may already drag horizontally through pointer gestures, but wheel-to-horizontal behavior can conflict with the page's vertical scroller.

Revisit only after the basic desktop carousel is tested. If wheel support is requested later, scope it to desktop only and add explicit Playwright/manual testing for vertical page scroll and horizontal album scroll conflict.

### Reduced Motion

Embla's button scroll motion is JS-driven and not the same as CSS `scroll-behavior`. The implementation should:

- avoid extra CSS animation on controls,
- avoid autoplay,
- avoid custom transition effects beyond shadcn Button defaults,
- verify behavior with `prefers-reduced-motion` in visual/manual smoke tests if motion complaints appear.

### Dark Mode

Keep `[data-theme="dark"]`.

The controls should rely on shadcn tokens:

- `--background`
- `--foreground`
- `--accent`
- `--accent-foreground`
- `--border`
- `--input`
- `--ring`

Do not use `--primary-color`, `--gallery-accent-*`, `--neon-color`, or album glow variables for standard carousel controls.

## Mobile and Tablet Freeze Policy

For this phase:

- Mobile stays native scroll-snap.
- Tablet stays current native scroll behavior.
- Do not change mobile/tablet class names or scroll mechanics unless separately approved.
- Do not change PhotoSwipe, lightbox components, or mobile lightbox sheets.

Why:

- iOS Safari horizontal swiping and scroll chaining are sensitive.
- The current mobile native scroll-snap is simple, direct, and proven in the app.
- Embla would change touch/drag feel and may interact differently with pull-to-refresh and vertical page scroll.
- Desktop cleanup can ship independently with focused risk.

Native mobile/tablet must keep `.album-grid` unless `usePullToRefresh.ts` is updated and tested, because pull-to-refresh uses that selector to avoid starting a vertical refresh from album horizontal gestures.

## Visual and shadcn Styling Policy

Desktop Carousel controls should align with shadcn-vue Stone:

- Use shadcn Button `variant="outline"` and `size="icon"` or the generated CarouselPrevious/Next defaults.
- Use neutral `hover:bg-accent`, `hover:text-accent-foreground`, `focus-visible:ring-ring`.
- Avoid `var(--primary-color)`, orange/gold borders, warm `color-mix`, neon glow, and heavy custom shadows.
- Keep cards visually unchanged.
- Keep gallery/museum identity in the brand hero and album cards, not the standard carousel controls.

Implementation should delete or isolate desktop-only `.album-scroll-btn` styles when the desktop native path is removed. Tablet/mobile native styles can keep their current selectors until a later tablet/mobile migration.

## Risks

- Desktop layout shift if arrows appear/disappear without reserved space.
- Card width mismatch because shadcn Carousel uses item padding and negative content margin instead of CSS flex gap.
- Arrow disabled state mismatch if Embla reInit does not fire after folders or container size changes as expected.
- Lost carousel position when folders change or when the album section collapses/expands.
- Collapsed/expanded `localStorage` regression if state moves into child components.
- Accessibility regression if the focusable Carousel root changes tab order unexpectedly.
- Keyboard regression if carousel arrow key handling conflicts with focused child content.
- Dark mode mismatch if controls use old gallery tokens instead of shadcn Stone tokens.
- Mobile/tablet accidental behavior change if `.album-grid` selectors, scroll-snap, or card branches are touched.
- Embla dependency size and added abstraction complexity.
- Test flakiness from carousel movement and async Embla state updates.
- CSS specificity conflicts between old `.album-scroll-btn` and new carousel control styles.
- Generated Carousel import mismatch with this repo's existing `Button.vue` layout and non-exported `ButtonVariants` type.
- Default shadcn `-left-12` and `-right-12` control placement may create horizontal overflow or clipping in this app's `GlowContainer` layout.

## Implementation Phases

The runtime migration described below was implemented in commit `f6144ea`.
The original phase wording is retained to record the design and rollout plan;
none of these phases should be treated as pending work.

### Phase A: Audit and Plan Only

Historical planning phase, completed in commit `0f9f5ba`.

Deliver:

- This plan document.
- No runtime changes.
- No package changes.
- Docs-only commit.

### Phase B: Add shadcn Carousel Primitives

Scope:

- Add official shadcn-vue Carousel component files.
- Install required `embla-carousel-vue` dependency if not present.
- Do not migrate AlbumScroller yet.
- Reconcile generated imports with local `Button.vue` conventions.

Checks:

- `npm run build`
- typecheck through build
- inspect generated files for `[data-theme="dark"]` compatibility and neutral tokens

Decision point:

- If generated Carousel expects `ButtonVariants`, either export it from the existing Button component or adapt Carousel controls to the existing Button props without changing Button visuals.

### Phase C: Desktop-Only Experimental Component

Scope:

- Create `AlbumCarouselDesktop.vue`.
- Use `AlbumCard.vue` only.
- Use same `folders` prop and `open-folder` emit pattern.
- Use shadcn Carousel primitives.
- Keep mobile/tablet untouched.
- Optionally guard with a local constant or feature flag while comparing native and Embla desktop behavior.

Checks:

- Desktop render with few albums and many albums.
- Edge controls disabled/hidden correctly.
- Card spacing matches current desktop row.
- No horizontal page overflow.
- Dark mode controls are neutral Stone.

### Phase D: Replace Desktop Branch

Scope:

- Keep `AlbumScroller.vue` as public wrapper.
- Branch desktop/wide to `AlbumCarouselDesktop.vue`.
- Branch mobile/tablet to `AlbumScrollerNative.vue`.
- Keep collapsed state and header in wrapper.
- Remove or isolate desktop-only `ResizeObserver`, `scrollBy`, and manual arrow state from desktop.
- Keep native logic only in mobile/tablet component.

Checks:

- Existing album click behavior.
- `localStorage` collapsed state.
- Empty folders behavior.
- Desktop keyboard navigation.
- Mobile and tablet unchanged.

### Phase E: Cleanup and Docs

Scope:

- Remove dead desktop `.album-scroll-btn` CSS.
- Keep native mobile/tablet CSS clearly scoped in `AlbumScrollerNative.vue`.
- Document why mobile/tablet remain native.
- Add direct Playwright coverage for desktop carousel and mobile/tablet regression.

Checks:

- Build passes.
- Playwright suite passes or scoped carousel tests pass plus documented residual risk.
- Visual smoke screenshots before/after desktop album row.

## Test Plan

### Unit or Component Tests if Available

Add focused tests if the project has or adds Vue component test infrastructure:

- collapsed state reads and writes `gallery-albums-collapsed`.
- album click emits the selected path.
- empty folders render no album section.
- desktop branch renders Carousel primitives.
- mobile branch renders native `.album-grid`.
- tablet branch renders native `.album-grid` and `AlbumCardTablet`.

### Playwright Desktop Tests

Add a folder-rich stubbed gallery fixture. Current responsive tests return `folders: []`, so they do not exercise AlbumScroller.

Required desktop checks:

- Albums section renders when folders exist and `gallery-albums-collapsed` is `"false"`.
- Carousel root exists on desktop.
- Previous/next controls exist when overflow exists.
- Next control moves the carousel forward.
- Previous control moves the carousel back.
- Controls are disabled or hidden correctly at the start/end.
- Album card click still opens/selects the album.
- Dark mode controls render with neutral Stone styles.
- No orange/gold focus ring on carousel controls.
- Keyboard tab order is reasonable.
- Arrow keys scroll when the Carousel root is focused.
- No native tooltip appears from carousel controls.

### Playwright Mobile and Tablet Regression

Required checks:

- Mobile still renders native `.album-grid`.
- Mobile `.album-grid` still has `scroll-snap-type`.
- Mobile arrows remain hidden if that is current behavior.
- Tablet still renders native `.album-grid`.
- Tablet still renders `AlbumCardTablet`.
- Tablet scroll behavior and arrows remain unchanged unless explicitly approved.
- No lightbox/mobile components are touched.

### Visual Smoke

Before/after compare:

- desktop album row at 1280px and 1920px
- dark mode desktop album row
- few albums with no overflow
- many albums with overflow
- mobile 375px album row
- tablet 768px and 834px album row

Check:

- card spacing
- card width
- arrow placement
- no layout shift
- no horizontal page overflow
- edge fades if retained or intentionally removed on desktop

## Implementation Acceptance Criteria

Future implementation is successful only if:

- Desktop AlbumScroller uses shadcn-vue Carousel/Embla.
- Mobile behavior is unchanged.
- Tablet behavior is unchanged.
- Manual desktop `scrollBy`, desktop `ResizeObserver`, and desktop arrow-state code are removed or isolated from desktop.
- Existing public `AlbumScroller.vue` API stays compatible.
- Collapsed state persists with `gallery-albums-collapsed`.
- Album card components and click behavior are preserved.
- No warm/orange standard UI control styling is introduced.
- Official Stone shadcn tokens remain intact.
- `[data-theme="dark"]` remains the dark mode selector.
- Typecheck passes.
- Build passes.
- Playwright or equivalent tests pass.
- No accessibility regression.
- No native browser tooltip leaks from carousel controls.

## Rollback Plan

Keep rollback simple:

1. Leave `AlbumScrollerNative.vue` as a faithful extraction of the current implementation.
2. Keep the public `AlbumScroller.vue` wrapper branch-based.
3. If desktop Carousel causes layout, accessibility, or interaction regressions, switch the desktop branch back to `AlbumScrollerNative.vue`.
4. Do not remove the native implementation until desktop Carousel passes all acceptance checks.
5. If the shadcn Carousel primitive installation causes type or import churn, revert only Phase B files and dependency changes before touching AlbumScroller runtime behavior.

Rollback should not affect mobile/tablet because those branches remain native throughout the migration.
