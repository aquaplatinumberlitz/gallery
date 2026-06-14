# Tailwind Migration Plan — Animation & Visual Preservation

**Last reviewed:** 2026-06-13 (Preflight approved)
**Status:** Phase 0 complete — Preflight enabled, all tests pass
**Decision:** Hybrid Migration (see §14)

---

## 1. Executive Summary

This document presents a detailed migration plan for adopting Tailwind CSS in the gallery frontend, with the non-negotiable requirement that 100% of current animations, transitions, hover effects, layout polish, premium album/card styling, mobile quirks, and gallery-specific visual effects are preserved.

**The repo currently uses:**
- SCSS modules (7 files, ~1,700 lines)
- CSS custom properties in `tokens.css` (258 lines, 90+ design tokens)
- Scoped `<style>` blocks in 35 Vue SFCs
- 25 `@keyframes` animation definitions
- 129 `transition` property declarations
- 20+ `backdrop-filter` uses
- 20+ `color-mix(in srgb, ...)` for semi-transparent theme-aware surfaces
- 133 `transform` property uses
- PhotoSwipe 5 and vue-spring-bottom-sheet for lightbox/mobile sheets

**Recommendation:** Hybrid migration covering Phases 0-2. Tailwind for desktop-first common utilities, CSS variables as the semantic theme backbone, SCSS preserved for animations, complex effects, third-party overrides, and mobile/iOS quirks. shadcn-vue approved for selective, component-by-component adoption where it improves quality, accessibility, or maintainability — not for wholesale rewrite or mobile/tablet risky surfaces in Phase 1. **Phase 3 (Metadata/Admin Table) is deferred — not implementing now. Revisit when TanStack Table features are needed.**

---

## Tailwind Version Target

**Target version: Tailwind v4.**

When implementation begins:
- Vite integration through the `@tailwindcss/vite` plugin
- CSS-first configuration via `@import "tailwindcss"` and `@theme` blocks
- Semantic tokens defined through Tailwind v4 theme/CSS token approach
- No `tailwind.config.js` as the primary configuration path (Tailwind v3 alternative, not recommended for this repo)

### Why Tailwind v4

- **Current modern Tailwind direction**: Tailwind v4 is the stable, forward-looking version. v3 is in maintenance mode.
- **Vite plugin path is simpler**: The `@tailwindcss/vite` plugin requires no PostCSS config and integrates natively with Vite's pipeline.
- **CSS-first token mapping fits this repo**: Gallery already defines 90+ semantic tokens in `tokens.css` via CSS custom properties. v4's `@theme` block and CSS-first approach makes mapping these tokens to Tailwind's design system more natural than a JS config file.
- **Easier to keep semantic tokens close to existing SCSS/CSS variables**: v4 allows defining Tailwind theme values directly in CSS alongside existing variables, reducing the gap between the two systems.

### Tailwind v3 alternatives (not recommended for this repo)

The following patterns are Tailwind v3 conventions and should NOT be used unless specifically labeled as "Tailwind v3 alternative, not recommended for this repo":

- `tailwind.config.js` as the primary configuration path
- `@tailwind base; @tailwind components; @tailwind utilities;`
- `corePlugins: { preflight: false }`

Preferred Tailwind v4 direction:
- Use Tailwind v4 CSS-first setup with `@import "tailwindcss"`
- Import only the layers needed during early migration: theme layer, utilities layer
- Preflight/base layer was tested as a separate spike after initial foundation (completed — Preflight now enabled permanently after passing 25/25 `tailwind-preflight.spec.ts` tests on PC, iPad, iPhone)

---

## 2. Current Styling Architecture Audit

### 2.1 File Inventory

| File | Type | Lines | Role |
|---|---|---|---|
| `frontend/src/styles/tokens.css` | CSS | 258 | Semantic design tokens (90+ vars), warm-latte/premium theme, light/dark |
| `frontend/src/styles/main.scss` | SCSS | 472 | Global styles, brand animations, base resets, a11y, responsive base |
| `frontend/src/styles/_breakpoints.scss` | SCSS | 17 | Breakpoint mixins (compact, mobile, tablet, desktop, wide) |
| `frontend/src/styles/_mobile-overrides.scss` | SCSS | 103 | Touch hover fixes, safe-area, iOS Safari background anchor fixes |
| `frontend/src/styles/_lightbox-shared.scss` | SCSS | 352 | PhotoSwipe overrides, accordion, focus rings, badges, floating controls |
| `frontend/src/styles/_lightbox-desktop.scss` | SCSS | 252 | Desktop metadata panel (sidebar, prompt boxes, params grid) |
| `frontend/src/styles/_lightbox-mobile.scss` | SCSS | 272 | Mobile bottom sheet (tabs, copy buttons, compact) |
| `frontend/src/styles/_lightbox-tablet.scss` | SCSS | 269 | Tablet bottom sheet (2-column grid, iPad-specific) |
| `frontend/src/assets/fonts.css` | CSS | 31 | Google Fonts CDN imports (Inter, JetBrains Mono, Cinzel) |
| `frontend/src/App.vue` | Vue | 2 style lines | Layout moved to layout components |
| 35 Vue SFCs | Vue | ~6,500 | Scoped component styles |

### 2.2 Style Loading Order

1. `tokens.css` — CSS custom properties defined on `:root` and `[data-theme="dark"]`
2. `fonts.css` — Google Fonts CDN `@import`
3. `tailwind.css` — Tailwind v4 utilities/theme layer (imported in `main.ts` after `tokens.css` but before `main.scss`) **(added in Phase 0)**
4. `main.scss` — global resets, brand keyframes, a11y, responsive base, `_mobile-overrides`
5. Per-component scoped SCSS — each SFC imports relevant `_lightbox-*.scss` or `_breakpoints.scss` as needed

### 2.3 Technology Stack

- **SCSS**: `sass` v1.94.2 (Dart Sass)
- **Vue 3 SFC**: `<style scoped>` with `lang="scss"` or plain CSS
- **No PostCSS config present** — no existing Tailwind, no autoprefixer (handled by Vite)
- **No CSS-in-JS or CSS Modules**
- **Vite 7.2.4** with `@vitejs/plugin-vue`

---

## 3. Animation & Effect Inventory

### 3.1 `@keyframes` Registry (25 definitions found)

| # | Name | File | Trigger | CSS Properties | Duration/Easing | Device | Risk | Migration Decision |
|---|---|---|---|---|---|---|---|---|
| 1 | `iconFlicker` | `styles/main.scss:9` | Dark mode brand-icon | `box-shadow`, `filter: drop-shadow` | 1.5s infinite alternate | Desktop | **High** | Keep in SCSS |
| 2 | `dark-title-shimmer` | `styles/main.scss:54` | Dark mode brand-title | `background-position` | 4s linear infinite | Desktop | **High** | Keep in SCSS |
| 3 | `dark-title-glow` | `styles/main.scss:59` | Dark mode brand-title | `filter: drop-shadow` (3 layers) | 3s ease-in-out infinite | Desktop | **High** | Keep in SCSS |
| 4 | `dark-underline-pulse` | `styles/main.scss:74` | Dark mode brand-title `::after` | `opacity`, `box-shadow` | 3s ease-in-out infinite | Desktop | **High** | Keep in SCSS |
| 5 | `lucide-spin` | `styles/main.scss:419` | Global (any lucide icon) | `transform: rotate(360deg)` | 1.5s linear infinite | All | Low | **Custom Tailwind utility:** `animate-[spin_1.5s_linear_infinite]`. Default Tailwind `animate-spin` is 1s linear infinite, which differs from the existing CSS (1.5s). A custom duration utility preserves visual parity. |
| 6 | `shimmer` | `PhotoCard.vue:306` | Photo card loading | `transform: translateX` | 1.5s infinite | All | Medium | Keep in SCSS (complex gradient + dark mode override) |
| 7 | `shimmer` | `SkeletonLoader.vue:86` | Skeleton placeholder | `transform: translateX` | 1.5s infinite | All | Medium | Keep in SCSS (touch-device disable logic) |
| 8 | `searchBarExpand` | `MobileHeader.vue:408` | Mobile search focus | `opacity`, `transform: scaleX` | 200ms cubic-bezier | Mobile | **High** | Keep in SCSS — do not touch mobile |
| 9 | `backBtnIn` | `MobileHeader.vue:552` | Mobile search back button | `opacity`, `transform: translateX` | 200ms cubic-bezier | Mobile | **High** | Keep in SCSS — do not touch mobile |
| 10 | `thSearchBarIn` | `TabletHeader.vue:307` | Tablet search focus | `opacity`, `transform: scaleX` | 200ms cubic-bezier | Tablet | **High** | Keep in SCSS — do not touch tablet |
| 11 | `thBackBtnIn` | `TabletHeader.vue:424` | Tablet search back button | `opacity`, `transform: translateX` | 200ms cubic-bezier | Tablet | **High** | Keep in SCSS — do not touch tablet |
| 12 | `fadeSlideIn` | `GalleryGrid.vue:1245` | Non-mobile scroller mount | `opacity`, `transform: translateY` | 260ms ease | Desktop/Tablet | Low | Keep in SCSS (scoped to GalleryGrid) |
| 13 | `fadeIn` | `RootPathSheet.vue:346` | Sheet open | `opacity` | 0.2s ease | Mobile | Medium | Keep in SCSS — do not touch sheet |
| 14 | `slideUp` | `RootPathSheet.vue:351` | Sheet open | `transform: translateY` | 0.3s cubic-bezier | Mobile | Medium | Keep in SCSS — do not touch sheet |
| 15 | `fadeIn` | `SettingsModal.vue:404` | Modal open | `opacity` | 0.2s ease | Desktop | Low | Tailwind `@layer` possible |
| 16 | `slideUp` | `SettingsModal.vue:409` | Modal open | `transform: translateY`, `opacity` | 0.3s cubic-bezier | Desktop | Low | Tailwind `@layer` possible |
| 17 | `underline-grow` | `AppHeader.vue:420` | Brand title hover | `transform: scaleX` | Unused? | Desktop | Low | Remove (unused) or keep |
| 18 | `subtle-float` | `AppHeader.vue:425` | Brand title hover | `transform: translateY` | Unused? | Desktop | Low | Remove (unused) or keep |
| 19 | `icon-spin` | `EmptyState.vue` | Loading empty state | `transform: rotate` | 2s linear infinite | All | Low | Tailwind equivalent possible |
| 20 | `pulse-slow` | `EmptyState.vue` | Empty state | `opacity` | 3s ease-in-out infinite | All | Low | Tailwind equivalent possible |
| 21 | `float` | `EmptyState.vue` | Empty state decorative | `transform: translateY` | 3s ease-in-out infinite | All | Low | Keep in SCSS |
| 22 | `twinkle` | `EmptyState.vue` | Empty state decorative | `opacity` | 2s ease-in-out infinite | All | Low | Keep in SCSS |
| 23 | `rotate-gradient` | `IntroScreen.vue` | Intro screen background | `transform: rotate` | 20s linear infinite | Desktop | Low | Keep in SCSS |
| 24 | `subtle-pulse` | `IntroScreen.vue` | Intro screen UI | `opacity` | 2s ease-in-out infinite | Desktop | Low | Keep in SCSS |
| 25 | `shimmer-gold` | `IntroScreen.vue` | Intro screen CTA | `background-position` | 2s linear infinite | Desktop | Low | Keep in SCSS |

### 3.2 Transition Inventory (129 declarations)

**Categories and count:**
- Theme transitions (color, background-color): ~30 uses
- Transform transitions (hover lift, scale): ~35 uses
- Opacity transitions (fade, loading states): ~20 uses
- Box-shadow transitions (hover glow): ~12 uses
- Border-color transitions (focus/hover rings): ~15 uses
- Layout transitions (sidebar width, header show/hide): ~10 uses
- Vue `<Transition>` component animations: ~7 uses

### 3.3 Backdrop-Filter Uses (20+ occurrences)

| Location | Value | Device |
|---|---|---|
| Mobile header background | `blur(12px)` | Mobile |
| Mobile search overlay | `blur(4px)` | Mobile |
| Desktop lightbox sidebar | `blur(20px)` | Desktop |
| Lightbox mobile photo counter | `blur(8px)` | All |
| Lightbox desktop counter | `blur(8px)` | Desktop |
| Lightbox floating controls | `blur(8px)` | All |
| Settings modal backdrop | `blur(4px)` | Desktop |
| Root path sheet backdrop | `blur(2px)` | Mobile |
| Mobile sidebar backdrop | `blur(2px)` | Mobile |
| Photo card type badge | `blur(4px)` | All |
| Tablet/search header background | `blur(12px)` | Tablet |
| Tablet search overlay | `blur(4px)` | Tablet |

All `backdrop-filter` uses must include `-webkit-backdrop-filter` prefix for Safari compatibility.

### 3.4 color-mix() Uses (20+ occurrences)

Used extensively for semi-transparent theme-aware backgrounds:
- `var(--surface-color) 85%, transparent` (mobile/tablet headers)
- `var(--text-color) 8%, transparent` (button hover states)
- `var(--primary-color) 10%, transparent` (active option backgrounds)
- `var(--muted-text) 4%, var(--surface-color)` (scope selector backgrounds)
- `var(--border-color) 50%, transparent` (mobile header borders)

`color-mix()` is not available in Tailwind utilities and must remain in SCSS or be expressed via CSS variable opacity hacks. Tailwind's opacity utilities cannot replicate `color-mix(in srgb, ...)` because they work on the entire element, not a single color channel relative to a theme variable.

### 3.5 Third-Party Library Override Zones

| Library | Override Files | Risk |
|---|---|---|
| **PhotoSwipe 5** | `_lightbox-shared.scss:10-24`, `Lightbox.vue:438-458` | **High** — PhotoSwipe CSS classes (`.pswp__*`) must be overridden exactly as-is |
| **vue-spring-bottom-sheet** | `LightboxMobileSheet.vue:398-489` | **High** — VSBS uses `[data-vsbs-*]` attribute selectors with custom properties |
| **@tanstack/vue-virtual** | `GalleryGrid.vue` (inline styles for virtual items) | Medium — position calculations must not be affected |
| **Lucide icons** | Various (size/color via CSS vars and inline styles) | Low — sizing already uses `--gallery-icon-*` tokens |

---

## 4. CSS Classification

### 4.1 Group A — Safe to Migrate to Tailwind Utilities

These are simple, non-animated layout/spacing/sizing properties that Tailwind handles natively:

| Category | Current Approach | Tailwind Equivalent |
|---|---|---|
| **display** properties (`flex`, `grid`, `inline-flex`) | Custom classes | `flex`, `grid`, `inline-flex` |
| **flex-direction** | `flex-direction: column` | `flex-col` |
| **align-items** | `align-items: center` | `items-center` |
| **justify-content** | `justify-content: space-between` | `justify-between` |
| **gap** | `gap: 8px` | `gap-2` (if configured) |
| **padding** | `padding: 16px` | `p-4` |
| **margin** | `margin-top: 12px` | `mt-3` |
| **font-size** (simple, non-responsive) | `font-size: 14px` | `text-sm` |
| **font-weight** | `font-weight: 600` | `font-semibold` |
| **border-radius** | `border-radius: 8px` | `rounded-lg` |
| **border** (basic 1px solid) | `border: 1px solid ...` | `border` + `border-color-*` |
| **overflow** | `overflow: hidden` | `overflow-hidden` |
| **width/height** (fixed) | `width: 38px; height: 38px` | `w-[38px] h-[38px]` or token |
| **position** | `position: relative` | `relative` |
| **z-index** | `z-index: 80` | `z-80` (if configured) |
| **cursor** | `cursor: pointer` | `cursor-pointer` |
| **white-space** | `white-space: nowrap` | `whitespace-nowrap` |
| **text-align** | `text-align: center` | `text-center` |
| **min-width: 0** | Used extensively for flex truncation | `min-w-0` |

**Risk: Low.** These are straightforward 1:1 mappings. No visual change expected.

### 4.2 Group B — Better Migrated to Tailwind `@layer components`

These are repeated patterns across **desktop** components that benefit from a component-level abstraction. Mobile and tablet variants are explicitly excluded during early migration.

**Allowed early candidates (desktop only):**

| Pattern | Current Locations | Tailwind Approach | Scope Notes |
|---|---|---|---|
| **Icon button** | Desktop AppHeader `.nav-btn`, `.hamburger-btn`, `.settings-btn` | `@layer components { .btn-icon { ... } }` combining 8-10 utilities | desktop AppHeader button/icon-button variants only. MobileHeader and TabletHeader are excluded. |
| **Navigation button** | GalleryGrid nav buttons (desktop) | Component class | desktop-only |
| **Badge/Chip/Status pill** | Desktop toast badges, loading badge, desktop status indicators | Semantic component class using gallery tokens | desktop Badge/Chip primitives |
| **Input shell/pill** | Desktop search box layout only | Component class for the pill-shaped input wrapper | desktop search/input only. mobile/tablet search excluded. |
| **Dropdown menu** (sort, density) | GalleryGrid sort/density dropdowns (desktop) | Component class with transition | desktop toolbar pieces only |
| **Modal shell** (backdrop + content + header/body/footer) | SettingsModal (desktop) | Component class pattern | SettingsModal desktop-safe only. RootPathSheet excluded. |
| **Toast shell** | ToastItem (desktop) | Component class with variants (success/error/warning/info) | desktop Toast shell only if behavior is unchanged |
| **Dialog/Sheet overlay** | Desktop Dialog/Popover only | Shared overlay component class | desktop Dialog/Popover only. mobile Sheet and RootPathSheet excluded. |

**Explicitly excluded from Group B during early migration:**
- MobileHeader
- TabletHeader
- MobileLayout
- TabletLayout
- RootPathSheet
- LightboxMobileSheet
- mobile/tablet sheet behavior
- mobile/tablet search/sort/theme/sidebar behavior
- GalleryGrid virtualization internals
- image loading behavior
- lightbox behavior

**Risk: Low-Medium.** Must ensure Tailwind component classes produce identical computed CSS. Test with Playwright screenshot comparison.

### 4.3 Group C — Must Remain in SCSS

These cannot be safely migrated to Tailwind utilities or components:

| Category | Examples | Reason |
|---|---|---|
| **Complex keyframe animations** | `iconFlicker`, `dark-title-shimmer`, `dark-title-glow` | Tailwind's `@keyframes` support is limited; these use multi-layer `filter: drop-shadow()` and complex gradient compositions |
| **PhotoSwipe overrides** | `.pswp__button--arrow--next`, `.pswp__top-bar` | Third-party CSS class names; must override as-is |
| **vue-spring-bottom-sheet overrides** | `[data-vsbs-sheet]`, `[data-vsbs-backdrop]`, `[data-vsbs-scroll]` | Third-party attribute selectors; must override as-is |
| **`color-mix(in srgb, ...)` rules** | 20+ occurrences | Tailwind has no `color-mix` utility; cannot be replaced by `bg-*` or opacity |
| **`backdrop-filter` with specific blur values** | Mobile headers, lightbox panels | Tailwind's `backdrop-blur-*` may work but must also output `-webkit-backdrop-filter` |
| **iOS Safari safe-area fixes** | `env(safe-area-inset-top)`, `env(safe-area-inset-bottom)` | Tailwind's `safe` prefix is limited; mobile headers need exact pixel behavior |
| **Album card 3D perspective transforms** | `perspective: 1000px`, `transform-style: preserve-3d`, `translateZ()` | Tailwind has no 3D transform utilities |
| **Album card dark mode neon glow composites** | `--glow-card-hover`, `--glow-card-hover-front` with 4-5 box-shadow layers | Beyond Tailwind's shadow scale |
| **Brand title gradient text** | `background-clip: text`, `-webkit-text-fill-color: transparent`, `filter: drop-shadow()` (multi-layer) | Tailwind's gradient text utilities cannot replicate the multi-layer drop-shadow |
| **Custom scrollbar styling** | 38 occurrences of `::-webkit-scrollbar` | Tailwind has no scrollbar utility; needs SCSS |
| **Touch device hover disables** | `@media (hover: none)` resetting hover states | Critical for avoiding sticky hover on iOS |
| **Reduced motion overrides** | `@media (prefers-reduced-motion: reduce)` | System-level a11y; must remain |
| **High contrast mode** | `@media (prefers-contrast: high)` | System-level a11y; must remain |
| **Theme toggle track/thumb animation** | Multi-step `cubic-bezier` with gradient backgrounds | Complex multi-element orchestration |

### 4.4 Group D — Do Not Touch During Initial Tailwind Migration

These files and their behaviors are **frozen** during phases 0-2. Any change to these requires a separate mobile/tablet design spec, real iPhone/iPad testing, and explicit approval.

| File | Reason Frozen |
|---|---|
| **`MobileHeader.vue`** | Previous Phase 1 attempt showed real iPhone Safari regressions when mobile header was touched. Complex search expand/collapse animation, backdrop-filter, safe-area, overlay management. |
| **`TabletHeader.vue`** | Same risk profile as MobileHeader. Search expand animation, breadcrumb integration, overlay. |
| **`MobileLayout.vue`** | Sidebar behavior, backdrop, padding transitions tied to header/bottom bar visibility. |
| **`TabletLayout.vue`** | Sidebar overlay behavior, backdrop transition, tablet-specific grid. |
| **`LightboxMobileSheet.vue`** | vue-spring-bottom-sheet integration, 200+ lines of VSBS CSS overrides with `[data-vsbs-*]` selectors, mobile tabs, copy interactions. |
| **`RootPathSheet.vue`** | Mobile bottom sheet with paste, iOS textarea focus quirks, safe-area awareness. |
| **`MobileFloatingBottomBar.vue`** | Fixed bottom nav tied to `safe-area-inset-bottom`, scroll visibility sync. |
| **`MobilePhotoSwipe.vue`** | PhotoSwipe + safe-area positioning, mobile gesture handling. |
| **`TabletPhotoSwipe.vue`** | Tablet-specific PhotoSwipe integration. |
| **`AlbumCardMobile.vue`** | Mobile-specific card styling with compact layout, mobile hover overrides. |
| **`AlbumCardTablet.vue`** | Tablet-specific card styling. |

**Also frozen during initial phases:**
- GalleryGrid virtualization (`@tanstack/vue-virtual` row virtualization logic)
- GalleryGrid image loading behavior (IntersectionObserver, load-more sentinel)
- Lightbox open/close behavior
- Theme toggle event chain (`App.vue` `toggleTheme()` and `watchEffect`)
- Header button order on all layouts
- Mobile/tablet search/sort/theme/sidebar behavior
- Any `@media (hover: none)` or `@media (pointer: coarse)` rules

---

## 5. Tailwind Token Strategy

### 5.1 CSS Variable to Tailwind Token Mapping

Rather than hardcoding Tailwind palette colors (e.g., `bg-stone-100`), we map the existing `--gallery-*` CSS custom properties into Tailwind's theme as semantic tokens:

```js
// Tailwind v3 tailwind.config.js alternative — NOT recommended for this repo.
// This is provided as a reference only. Target is Tailwind v4 CSS-first @theme.
// module.exports = {
//   theme: {
//     extend: {
//       colors: {
        // Semantic surface colors (do NOT use raw Tailwind palette)
        background: 'var(--bg-color)',
        foreground: 'var(--text-color)',
        surface: 'var(--surface-color)',
        'surface-elevated': 'var(--gallery-surface-elevated)',
        'surface-hover': 'var(--gallery-surface-hover)',
        'surface-dim': 'var(--gallery-surface-dim)',

        // Semantic text colors
        'text-primary': 'var(--gallery-text-primary)',
        'text-secondary': 'var(--gallery-text-secondary)',
        'text-tertiary': 'var(--gallery-text-tertiary)',
        'text-disabled': 'var(--gallery-text-disabled)',
        'text-inverse': 'var(--gallery-text-inverse)',
        'text-placeholder': 'var(--gallery-text-placeholder)',

        // Legacy text tokens (used by components)
        title: 'var(--title-color)',
        muted: 'var(--muted-text)',
        'muted-foreground': 'var(--muted-text)',

        // Semantic border colors
        border: 'var(--gallery-border-default)',
        'border-subtle': 'var(--gallery-border-subtle)',
        'border-hover': 'var(--gallery-border-hover)',

        // Accent/primary
        primary: 'var(--primary-color)',
        'primary-hover': 'var(--gallery-accent-hover)',
        'primary-muted': 'var(--gallery-accent-muted)',
        'primary-text': 'var(--gallery-accent-text)',
        'primary-border': 'var(--gallery-accent-border)',

        // Semantic status
        success: 'var(--gallery-success)',
        'success-bg': 'var(--gallery-success-bg)',
        warning: 'var(--gallery-warning)',
        'warning-bg': 'var(--gallery-warning-bg)',
        error: 'var(--gallery-error)',
        'error-bg': 'var(--gallery-error-bg)',
        info: 'var(--gallery-info)',
        'info-bg': 'var(--gallery-info-bg)',

        // Neon (brand icon, dark mode search)
        neon: 'var(--neon-color)',
        'neon-border': 'var(--neon-border-color)',

        // Folder icon
        folder: 'var(--folder-color)',
      },
      borderRadius: {
        sm: 'var(--gallery-radius-sm)',
        md: 'var(--gallery-radius-md)',
        lg: 'var(--gallery-radius-lg)',
        xl: 'var(--gallery-radius-xl)',
        full: 'var(--gallery-radius-full)',
      },
      boxShadow: {
        sm: 'var(--gallery-shadow-sm)',
        md: 'var(--gallery-shadow-md)',
        lg: 'var(--gallery-shadow-lg)',
        xl: 'var(--gallery-shadow-xl)',
        // Legacy shadow tokens
        card: 'var(--shadow-card)',
        'card-hover': 'var(--shadow-card-hover)',
        'card-level2': 'var(--shadow-card-level2)',
        'card-level4': 'var(--shadow-card-level4)',
        // Focus ring
        'focus-ring': 'var(--focus-ring-shadow)',
      },
      fontFamily: {
        body: 'var(--font-body)',
        code: 'var(--font-code)',
        // Also support the gallery-specific fonts directly
        cinzel: ['Cinzel', 'serif'],
        inter: ['InterVariable', 'Segoe UI', 'SF Pro Display', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      transitionTimingFunction: {
        'gallery': 'cubic-bezier(0.4, 0, 0.2, 1)',
        'gallery-bounce': 'cubic-bezier(0.34, 1.56, 0.64, 1)',
        'gallery-spring': 'cubic-bezier(0.68, -0.15, 0.265, 1.35)',
      },
      transitionDuration: {
        fast: 'var(--gallery-timing-fast)',    // 80ms
        normal: 'var(--gallery-timing-normal)', // 200ms
        slow: 'var(--gallery-timing-slow)',     // 400ms
      },
//     },
//   },
// };
```
This is a Tailwind v3 alternative. The target is Tailwind v4 CSS-first configuration via `@theme`.

### 5.2 Class Naming Strategy

**All component classes use semantic tokens, NEVER raw Tailwind palette colors:**

```
✅ bg-background text-foreground border-border
✅ bg-surface hover:bg-surface-hover
✅ text-muted-foreground text-primary
✅ shadow-md hover:shadow-lg
✅ rounded-lg border-border

❌ bg-stone-100 text-gray-900 border-gray-200  (hardcoded palette)
❌ dark:bg-zinc-900 dark:text-zinc-100          (would break when tokens change)
```

### 5.3 Dark Mode Strategy

Gallery uses `html[data-theme="dark"]` attribute selector (NOT Tailwind's `dark:` class strategy).

Tailwind v4 CSS-first approach: Use `@custom-variant` to register the `[data-theme="dark"]` selector so that `dark:bg-background` resolves correctly against our existing `data-theme="dark"` attribute.

Tailwind v3 alternative (not recommended):
```js
darkMode: ['selector', '[data-theme="dark"]'],
```

---

## 6. shadcn-vue Selective Adoption Strategy

### 6.1 User-Approved Strategy

**Decision:** shadcn-vue may be adopted **selectively** for standard desktop UI primitives and behavior-heavy desktop components when it provides better accessibility, keyboard handling, focus management, or maintainability than our hand-rolled implementation.

**Constraints (hard):**
- shadcn-vue is NOT a wholesale replacement framework.
- shadcn-vue must NOT override gallery design identity.
- shadcn-vue must NOT force a parallel token system unless tokens are explicitly bridged to existing gallery semantic tokens (see §6.4).
- Every adoption step is component-by-component, individually tested, and individually reviewed.
- Mobile/tablet risky surfaces remain frozen during Phase 1 (see §6.3 Group C).

**What changed from the earlier approach:**
The original plan treated shadcn-vue strictly as a "pattern reference only — never installed." That prohibition is now lifted. shadcn-vue may be installed, and individual component code may be adopted, **provided** the constraints above are met for each component.

---

### 6.2 Component Grouping

#### Group A — Replace with shadcn-vue early where practical

These are standard UI primitives that are reasonable candidates for early shadcn-vue adoption:

- Button / IconButton
- Badge / Chip
- Input
- Select
- Dropdown Menu
- Tooltip
- Popover
- Dialog (desktop only)
- Breadcrumb
- Tabs (if needed)
- Separator

**Guidance:**
- Prefer shadcn-vue or shadcn-vue-inspired internal wrappers for these.
- **Keep gallery tokens and visual identity.** Do not accept default shadcn styling blindly. Adapt the component styling to use `--gallery-*` tokens via Tailwind semantic utilities or CSS variable references.
- Avoid introducing unnecessary behavior dependencies for purely static layout unless the component benefit is clear (e.g., Dropdown Menu brings keyboard nav and focus management that a plain `<div>` does not).
- Start with the **smallest safe candidates first**: Button/IconButton, Badge/Chip, Input, Separator, Breadcrumb. These have minimal behavior surface and are easiest to verify.

#### Group B — Replace carefully after audit

These are possible shadcn-vue replacements, but they require careful behavior and visual parity review:

| Current Component | shadcn-vue Candidate | Notes |
|---|---|---|
| SettingsModal | Dialog | Dialog may improve focus trap and accessibility. Existing animations and UX must be preserved or explicitly reviewed. |
| Sort/density menu | Dropdown Menu / Select | Behavior-heavy; must preserve existing sort/density logic and dropdown animation feel. |
| Toast system | Sonner or Toast | Do NOT replace the toast manager unless there is a clear behavior benefit and tests prove parity. |
| Sidebar/Folder tree | Sidebar / Collapsible / Button pattern | The existing folder tree is app-specific. Only use Collapsible/Button patterns if they reduce complexity. Do not force a full shadcn Sidebar. |
| GalleryGrid toolbar | Button / Dropdown / Slider only | Only migrate toolbar controls. Never touch GalleryGrid virtualization, image loading, sentinel logic, skeleton logic, or lightbox trigger behavior. |

**Guidance:**
- Migration must be incremental. Do not rewrite the whole feature.
- Before/after Playwright screenshot comparison is mandatory (see §10).
- Keyboard navigation, focus trap, Escape key, outside click, and dark/light theme must be tested per component.

#### Group C — Do not replace in Phase 1

These must stay frozen. Do not migrate to shadcn-vue in Phase 1:

- MobileHeader
- TabletHeader
- RootPathSheet
- LightboxMobileSheet
- PhotoSwipe / lightbox core
- GalleryGrid virtualization / image loading
- Album hover premium animation
- iOS Safari safe-area / gesture fixes

**Guidance:**
- Do not rewrite gesture, safe-area, or mobile behavior.
- Do not replace PhotoSwipe or lightbox internals.
- Do not migrate animation-heavy premium gallery effects.
- These areas require separate future specs and real-device testing.

---

### 6.4 Dependency and Token Bridge Audit

**Before installing shadcn-vue or adding any shadcn component**, run a dependency and token bridge audit. The audit must answer:

1. Which exact shadcn-vue component(s) are needed?
2. Which npm dependencies will be added? (e.g., `shadcn-vue`, `radix-vue` / `reka-ui`, `vue-sonner`, `clsx`, `class-variance-authority`, `tailwind-merge`, `tailwindcss-animate`)
3. Does the component require Reka UI (formerly Radix-Vue)?
4. Does it require `vue-sonner`?
5. Does it require class utilities such as `clsx` / `cva` / `tailwind-merge`?
6. How will shadcn CSS variables (e.g., `--background`, `--foreground`, `--primary`) map to existing gallery tokens (e.g., `--bg-color`, `--text-color`, `--primary-color`)?
7. How will dark mode work with the existing `[data-theme="dark"]` attribute? (See §5.3 for the `@custom-variant dark` strategy.)
8. Does this component work cleanly with Tailwind v4 and the current `@theme inline` setup?
9. What tests will prove no visual or behavior regression?

**Rule:** Do not allow a large dependency install without a specific component adoption target. Every added dependency must be justified by at least one concrete component replacement.

---

### 6.5 Token Bridging

shadcn-vue components typically reference CSS variables from a shadcn theme (defined on `:root` in a `globals.css` — e.g., `--background`, `--foreground`, `--primary`, `--muted`, `--accent`, `--border`, `--ring`, `--radius`). Gallery uses its own semantic tokens in `tokens.css`.

**Bridging approach:**
- Do NOT duplicate the shadcn theme variables in gallery. Instead, create an alias layer that maps shadcn variable names to gallery token values.
- Example: `--background: var(--bg-color); --foreground: var(--text-color); --primary: var(--primary-color); --border: var(--gallery-border-default); --radius: var(--gallery-radius-md);`
- This alias layer should live in a new file (e.g., `frontend/src/styles/_shadcn-token-bridge.css`) imported after `tokens.css` and before Tailwind.
- The bridge must work for both light and dark modes via `[data-theme="dark"]`.

**Guidance:**
- Token bridging is a **pre-requisite** to any shadcn component adoption.
- Do not write a full shadcn theme from scratch. Only bridge the variables actually used by adopted components.
- Document each bridged variable with its gallery source and the shadcn component(s) that consume it.

---

### 6.6 Testing Requirements

Every shadcn-vue adoption step must run:

**Type and build:**
- `vue-tsc --noEmit`
- `npm run build`

**Existing regression tests:**
- All existing Playwright tests, including active `tailwind-preflight.spec.ts` (25 tests)

**New component-specific tests:**
- Visual regression screenshot for the affected component (light + dark) — pixel diff is informational, use manual inspection

**For mobile/tablet freeze verification:**
- Verify MobileHeader still renders and functions
- Verify TabletHeader still renders and functions
- Verify RootPathSheet and LightboxMobileSheet are untouched if not in scope

**For desktop behavior-heavy components (Dialog, Popover, Dropdown Menu):**
- Test keyboard navigation (Tab, Arrow keys, Enter, Space)
- Test focus trap (if Dialog or Popover)
- Test Escape key dismiss
- Test outside click dismiss
- Test dark/light theme toggle inside the open component
- Test no console errors during open/close lifecycle
- Test scroll lock behavior (Dialog should lock body scroll; Popover may or may not)

**For mobile/tablet safety gates:**
- Grep the diff for any changes to files listed in Group C. If any found, block the PR until they are reverted.

---

### 6.7 Hard Rules

1. **shadcn-vue is approved for selective, component-by-component adoption** where it improves quality, accessibility, or maintainability. It is **not** approved for wholesale rewrite or mobile/tablet risky surfaces in Phase 1.
2. **`npx shadcn-vue@latest add ...`** is allowed for specific components, but only after a dependency/token audit (see §6.4) and only targeting Group A or Group B components.
3. **Gallery semantic tokens and visual identity always take precedence** over shadcn defaults.
4. **Every adoption must be individually tested** with type-checks, builds, and Playwright before/after screenshots.
5. **Mobile/tablet Group C components must not be touched** in Phase 1. Any accidental change to these files is a blocker.
6. **Do not install shadcn dependencies globally without a specific component target.** Each dependency must map to at least one concrete component replacement.

---

## 7. Tailwind Preflight Risk Analysis

### 7.1 What Tailwind Preflight Does

Tailwind's Preflight (based on modern-normalize) resets:
- `*` box-sizing to `border-box`
- Removes default margins from `body`, `h1-h6`, `blockquote`, `dl`, `dd`, etc.
- Resets heading font sizes/weights
- Removes list styles
- Makes images block-level
- Resets button font inheritance
- Resets input/textarea appearance
- Removes default `border-style` from horizontal rules
- Sets `-webkit-tap-highlight-color: transparent`

### 7.2 Risk Assessment for This Repo

| Preflight Reset | Gallery Already Handles? | Risk | Notes |
|---|---|---|---|
| `box-sizing: border-box` | ✅ Yes (`main.scss:237-241`) | **None** — already applied |
| Body margin reset | ✅ Yes (`main.scss:243`) | **None** |
| Heading size reset | ⚠️ Partial — `h1-h6` set to `font-family: var(--font-body)` but sizes are per-component | **Medium** — Preflight would remove browser-default heading sizes. Gallery Card titles use explicit `font-size`. AppHeader `h1` uses explicit `font-size: clamp(22px, 3vw, 30px)`. Safe. |
| Image block display | ⚠️ Gallery images use `object-fit: cover` with `display: block` explicitly | **Low** — PhotoCard sets `img { display: block }`. Preflight's `img { display: block }` is compatible. |
| Button font inheritance | ✅ Yes (`main.scss:261-263`) | **None** |
| Input/textarea reset | ⚠️ Gallery inputs use explicit `border: none; background: transparent` in scoped styles | **Medium** — Preflight removes native `appearance` which may change select element rendering. Must test `<select>` elements (search scope, theme select). |
| List style reset | ⚠️ Not used in gallery currently | **None** |
| `-webkit-tap-highlight-color` | Already handled in `_mobile-overrides.scss:58` | **None** |

### 7.3 PhotoSwipe & Third-Party Impact

**Critical concern:** Preflight's `img { display: block }` and button resets could affect PhotoSwipe's internal DOM structure. PhotoSwipe generates its own HTML with inline styles — Preflight would cascade into PhotoSwipe's shadow-like DOM (it's not actually shadow DOM).

Similarly, vue-spring-bottom-sheet generates `[data-vsbs-*]` elements with its own CSS. Preflight might reset margins or box-sizing on VSBS internal elements.

### 7.4 Recommendation: Staged Preflight Approach

**Default recommendation: Do not enable Preflight by default during the first migration step.** Preflight is an optional later spike, not the default first move. Tailwind utilities can still be used without Preflight, but some utilities may need small base patches (e.g., border defaults must be documented if Preflight is disabled).

**Rationale:** Tailwind Preflight is based on modern-normalize and applies broad CSS resets that can silently change buttons, inputs, images, `html`/`body`/`#app` sizing, focus outlines, PhotoSwipe internals, vue-spring-bottom-sheet elements, and mobile Safari behavior. This repo has existing base resets in `main.scss` that already cover many of the same concerns without the risk of cascading into third-party DOM.

**Staged approach:**

**Phase 0A — Start without Preflight (initial)**
- Started with Tailwind v4 utilities and theme layer only.
- Phase 0A initially omitted Preflight during initial foundation (commit `90e6623`).

**Phase 0B — Screenshot baselines**
- Desktop/mobile/tablet screenshot baselines captured with Preflight disabled.
- 23 Playwright smoke tests added — all passed, no regressions found (commit `b2dde0b`).
- ✅ Phase 0B complete.

**Phase 0C — Preflight enabled — testing passed**
- Preflight enabled at commit `6eb447d` + `@import "tailwindcss/preflight.css" layer(base);`
- Deployed to VPS for real-device testing on PC, iPad, iPhone.
- ✅ User tested on PC, iPad, iPhone — 25/25 `tailwind-preflight.spec.ts` tests pass
- ✅ Preflight stays enabled permanently
- ✅ No `_tailwind-patches.scss` patches required for Preflight (no regressions found)

**Historical disabled-Preflight compatibility notes:**
- Tailwind utilities are fully functional without Preflight. Most utilities do not depend on Preflight resets.
- A few utilities (notably `border`, `border-*`) assume Preflight has reset `border-style` to `solid`. When Preflight was disabled, explicit `border-style: solid` could be needed alongside `border` utility in rare cases.
- No other Tailwind utility requires Preflight to function correctly.

**Preflight-enabled safeguard patches considered during Phase 0C:**

During Phase 0C Preflight verification, the following patches were candidate safeguards to verify against Playwright screenshot baselines (see §10). Any required patch must be applied AFTER Tailwind in the CSS cascade:

```css
/* In _tailwind-patches.scss, loaded AFTER Tailwind */

/* Protect PhotoSwipe internal elements from Preflight */
.pswp img {
  display: revert; /* Undo Preflight's img { display: block } */
}

/* Protect vue-spring-bottom-sheet from Preflight */
[data-vsbs-sheet] h1,
[data-vsbs-sheet] h2,
[data-vsbs-sheet] h3,
[data-vsbs-sheet] h4,
[data-vsbs-sheet] h5,
[data-vsbs-sheet] h6,
[data-vsbs-sheet] p,
[data-vsbs-sheet] blockquote {
  font-size: revert;
  font-weight: revert;
  margin: revert;
}

/* Ensure #app sizing is preserved */
#app {
  height: 100%;
  overflow: hidden;
}

/* Preserve html/body height */
html, body {
  height: 100%;
}
```

**Specific Preflight patches for gallery components (if Preflight is enabled):**

| Affected Element | Patch | Reason |
|---|---|---|
| `select` elements (scope selector, theme select) | Set explicit `appearance: auto` or style as custom | Preflight removes native OS styling |
| PhotoSwipe images | `img { display: revert }` inside `.pswp` | Preflight `display: block` may break swipe layout |
| VSBS header elements | Revert heading resets inside `[data-vsbs-*]` | VSBS uses its own heading styles |
| `#app` height | Explicit `height: 100%` | Preflight may not set this |

**Safety verification:**
1. Phase 0C Preflight verification: Run full Playwright screenshot tests on desktop/mobile/tablet
2. With Preflight enabled: Run same tests, compare pixel diff
3. Investigate any deviations manually; pixel diff is informational, not a blocker

---

## 8. Migration Phases

### Phase 0 — Tailwind Foundation (No Visual Changes) ✅ COMPLETED

**Goal:** Install and configure Tailwind without changing any component styling.

**Preflight tasks completed:**
- ✅ Playwright is configured in the repo
- ✅ Baseline capture commands defined
- ✅ Baseline captures run before Tailwind install

**Tasks completed (commit 90e6623):**
- ✅ `npm install -D tailwindcss @tailwindcss/vite`
- ✅ Tailwind v4 Vite plugin added to `vite.config.ts`
- ✅ No `tailwind.config.js` — CSS-first configuration used
- ✅ Created `frontend/src/styles/tailwind.css` with `@theme inline` + `@custom-variant dark` (+ section headers)
- ✅ Semantic token mapping defined: 33 colors, 5 radii, 9 shadows, 5 fonts, 3 easings, 3 durations
- ✅ `tailwind.css` imported in `main.ts` AFTER `tokens.css` but BEFORE `main.scss`
- ✅ Dark mode configured via `@custom-variant dark (&:where([data-theme=\"dark\"], [data-theme=\"dark\"] *))`
- ✅ Created `frontend/src/styles/_tailwind-patches.scss` (placeholder, unimported)
- ✅ Phase 0A initially omitted Preflight (commit `90e6623`); enabled in Phase 0C and approved after user testing (commit `6eb447d+`). 25/25 `tailwind-preflight.spec.ts` tests pass. Preflight stays enabled permanently.
- ✅ `vue-tsc --noEmit` passes
- ✅ `npm run build` passes
- ✅ 23 Playwright smoke tests pass — no regressions found (commit `b2dde0b`)
- ✅ No visual changes confirmed during the disabled-Preflight Phase 0A/B baseline; Preflight tested on PC, iPad, iPhone — 25/25 `tailwind-preflight.spec.ts` tests pass, Preflight stays enabled permanently (Phase 0C)

> **Status:** Phase 0 complete. Tailwind v4 is available. Preflight enabled, tested on PC/iPad/iPhone. 25/25 `tailwind-preflight.spec.ts` tests pass. No regressions found. No `_tailwind-patches.scss` patches required. Preflight stays enabled permanently. Desktop Phase 1 migration is ready to proceed.

### Phase 1 — Desktop Primitive Adoption

**Goal:** Introduce selected shadcn-vue-compatible primitives or internal wrappers for low-risk desktop UI. Start with the smallest, safest candidates first.

**Group A candidates (earliest targets):**
- Button / IconButton — replace hand-rolled icon button patterns with shadcn Button, adapted to gallery tokens
- Badge / Chip — replace hand-rolled badge styles with shadcn Badge, using gallery semantic colors
- Input — standardize input styling with shadcn Input, adapted to gallery tokens
- Separator — trivial layout element; low risk
- Breadcrumb — simple flex layout with separators; shadcn or internal wrapper

**Group A candidates (second wave, same phase):**
- Select — desktop scope selector, sort dropdown trigger
- Dropdown Menu — sort/density menus
- Tooltip — hover info on desktop controls
- Popover — index status panel, quick-info panels
- Dialog — SettingsModal shell (behavior audit first — see Phase 1.5)
- Tabs — if needed for future admin UI

**Guidance:**
- Prefer shadcn-vue or shadcn-vue-inspired internal wrappers for these.
- Keep gallery tokens and visual identity. Do not accept default shadcn styling blindly.
- Avoid introducing unnecessary behavior dependencies for purely static layout unless the component benefit is clear.
- Every adoption step runs `vue-tsc`, `npm run build`, and existing Playwright tests (see §6.6).

**Desktop-only Tailwind utilities (non-shadcn, safe to do in parallel):**

| Component | Migration | Risk |
|---|---|---|
| AppHeader `hb-brand-hero` static layout (flex, gap, padding) | Tailwind utilities | Low |
| Desktop toast shell (container, item layout, not colors) | Tailwind utilities | Low |
| GalleryGrid toolbar layout (grid, gap, alignment) | Tailwind utilities | Low — desktop toolbar/control wrapper styles only. Do not touch scroller, virtual rows, sentinels, image loading states, skeleton behavior, virtualization logic, lightbox trigger behavior, or image sizing policy. |
| SidebarHeader layout | Tailwind utilities | Low |
| FolderTreeItem layout | Tailwind utilities | Low |

**Not allowed in Phase 1 (confirming):**
- ❌ No MobileHeader, TabletHeader
- ❌ No RootPathSheet, LightboxMobileSheet
- ❌ No mobile/tablet layout components
- ❌ No GalleryGrid virtualization
- ❌ No mobile/tablet header/search/sort/theme behavior
- ❌ No album card animations
- ❌ No brand title animations
- ❌ No theme toggle or brand icon (animation-heavy)

### Phase 1.5 — Behavior-Heavy Desktop Primitives

**Goal:** Evaluate and adopt shadcn-vue behavior-heavy components for desktop where they improve accessibility, keyboard handling, or focus management.

**Candidates:**
- **Dialog** — SettingsModal replacement. Studied for focus trap, Escape-key dismiss, outside-click dismiss, `aria-modal`, body scroll lock.
- **Dropdown Menu** — GalleryGrid sort/density menus. Studied for keyboard nav, typeahead, focus management.
- **Select** — Desktop scope/theming selectors. Studied for native vs. custom select behavior parity.
- **Tooltip** — Hover info labels on desktop controls. Studied for delay, positioning, and touch-device suppression.
- **Popover** — Index status panel, quick-info overlays. Studied for focus trap, positioning, and click-outside dismiss.
- **Tabs** — If introduced for admin or settings UI.

**Pre-requisites:**
- Dependency and token bridge audit completed (see §6.4).
- Token bridging file created and verified in both light and dark modes (see §6.5).
- Phase 1 Group A lightweight candidates (Button, Badge, Input, Separator, Breadcrumb) already adopted and proven stable.

**Guidance:**
- Each component must pass the full testing checklist in §6.6 before being considered "adopted."
- Do not replace SettingsModal wholesale in one commit — adopt Dialog as the shell first, then migrate internal panels incrementally.

### Phase 2 — Desktop Search/Filter/Admin Primitives

**Allowed candidates:**
- Desktop AdvancedSearch layout (future component, Tailwind-first, shadcn-vue Input/Badge/Button as building blocks)
- Desktop filter chips (future SearchFilterChips, Tailwind + gallery tokens, shadcn Badge for chip base)
- Desktop popover/dialog shell (future components, Tailwind `@layer`, shadcn Popover/Dialog where behavior/a11y benefits are clear)
- Desktop status panel (IndexStatusPanel, shadcn Tooltip/Popover for detail overlays)
- Desktop command/search palette shell (shadcn Command pattern where keyboard navigation adds value)

**Guidance:**
- shadcn-vue may be used where behavior or accessibility benefits are clear.
- Do not override gallery visual identity — all shadcn components must use bridged gallery tokens (see §6.4, §6.5).
- New components built in this phase should be Tailwind-first with gallery tokens, using shadcn-vue primitives where they reduce boilerplate for standard interaction patterns.

### Phase 3 (Future — deferred) — Metadata/Admin Table

**Not implementing now. Revisit when TanStack Table features are needed.**

**Allowed candidates (deferred):**
- TanStack Table integration (new MetadataTable component, Tailwind-first)
- TanStack Table toolbar/action menu (Tailwind utilities; shadcn Button, Dropdown Menu, Dialog, Badge, Tooltip for table controls)
- Column visibility / pagination UI

**Guidance:**
- shadcn-vue can be considered for table controls, dropdowns, dialogs, badges, and tooltips.
- shadcn-vue must NOT be used for replacing gallery browsing UI (GalleryGrid, PhotoCard, lightbox).
- Table-specific UI must still use gallery semantic tokens via the token bridge.

### Phase 4 — Mobile/Tablet (Future Spec Only)

- Requires separate mobile/tablet design spec
- Requires real iPhone Safari testing
- Requires real iPad/tablet testing
- Requires rollback plan with explicit approval
- Not planned in this document beyond the "do not touch" classification

---

## 9. Animation Preservation Rules

### 9.1 Strict Rules

1. **Animations are not migrated unless visual parity is proven.** No exceptions.
2. **Existing @keyframes stay in SCSS first.** They may be duplicated to `tailwind.config.js` `keyframes` extension only after visual parity is confirmed.
3. **Complex hover effects stay in SCSS first.** Album card 3D transforms, brand title glow, theme toggle animation, etc.
4. **Tailwind may only replace static layout/spacing around the animation, not the animation itself.**
5. **Every animation migration must have before/after screenshots or video capture.**
6. **Any difference in timing/easing/transform/opacity/shadow is a regression.**
7. **If an animation uses `color-mix()`, `backdrop-filter`, `filter: drop-shadow()` with multiple layers, or `background-clip: text` — it stays in SCSS permanently.**

### 9.2 Animation Classification by Migration Treatment

| Animation | Treatment | Justification |
|---|---|---|
| `iconFlicker` (brand icon) | **Never migrate** | Multi-layer box-shadow animation with neon variables |
| `dark-title-shimmer` (brand title) | **Never migrate** | Gradient background-position animation with `background-clip: text` |
| `dark-title-glow` (brand title) | **Never migrate** | Multi-layer `filter: drop-shadow()` with specific rgba values |
| `dark-underline-pulse` (brand title ::after) | **Never migrate** | Box-shadow pulse tied to theme variables |
| `shimmer` (PhotoCard/SkeletonLoader) | **Possible future migration** | Could use Tailwind keyframe extension, but must preserve dark mode override and touch-device disable |
| `searchBarExpand` (MobileHeader) | **Never migrate** | Mobile-header frozen; complex cubic-bezier with scaleX |
| `thSearchBarIn` (TabletHeader) | **Never migrate** | Tablet-header frozen |
| `fadeIn` / `slideUp` (SettingsModal) | **Keep in SCSS during Phase 1.** Defer animation migration to later phase after visual parity is proven. | Desktop-safe only, but animations must stay SCSS-first per §9.1 rule 2 (animations are not migrated unless visual parity is proven). |
| `fadeIn` / `slideUp` (RootPathSheet) | **Keep in SCSS — do not touch** | Mobile-sensitive bottom sheet behavior, iOS textarea/focus quirks, previous mobile regressions. Deferred to future Mobile/Tablet Spec. |
| `fadeSlideIn` (GalleryGrid scroller) | **Keep in SCSS** | Scoped to GalleryGrid; must not change |
| `lucide-spin` | **Custom Tailwind utility:** `animate-[spin_1.5s_linear_infinite]` | Simple rotation; Tailwind equivalent exists, but default `animate-spin` duration is 1s instead of the existing 1.5s, so a custom duration utility is required for visual parity. |
| Vue `<Transition>` animations (toast, sort dropdown, overlay) | **Preserve as-is** | Vue transition classes already handled; only surround markup can use Tailwind |

### 9.3 Per-Effect Preservation Examples

**Example 1: Album Card 3D Hover (Desktop)**

```scss
// Current (AlbumCard.vue:237-256)
@media (hover: hover) {
  &:hover {
    transform: translateY(-4px);
    box-shadow: var(--album-hover-shadow);
    .album-cover-diagonal { transform: translateY(-10px); }
    .album-layer-back { transform: translate(-20px, 5px) rotate(-15deg); }
    .album-layer-front { transform: translate(10px, -5px) rotate(12deg) scale(1.05); }
  }
}
```

**Migration verdict: Keep 100% in SCSS.** Nested child transforms with `perspective` and `transform-style: preserve-3d` cannot be expressed as Tailwind utilities. Only the outer card's static layout (padding, border-radius) can safely use Tailwind utilities.

**Example 2: Brand Title Dark Mode**

```scss
// Current (main.scss:89-131)
html[data-theme="dark"] .brand-title {
  background: linear-gradient(90deg, #d6a15d 0%, ...);
  background-size: 200% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  filter: drop-shadow(0 0 4px ...) drop-shadow(0 0 12px ...) drop-shadow(0 0 20px ...);
  animation: dark-title-shimmer 4s linear infinite, dark-title-glow 3s ease-in-out infinite;
}
```

**Migration verdict: Never migrate.** This is the most complex animation in the codebase. It combines gradient text fill, multi-layer drop-shadow, and two simultaneous keyframe animations. No Tailwind utility or theme extension can replicate this faithfully.

**Example 3: Mobile Header Background**

```scss
// Current (MobileHeader.vue:297)
background: color-mix(in srgb, var(--surface-color) 85%, transparent);
backdrop-filter: blur(12px);
-webkit-backdrop-filter: blur(12px);
```

**Migration verdict: Keep in SCSS.** `color-mix()` has no Tailwind equivalent. `backdrop-filter` could use Tailwind's `backdrop-blur-xl`, but the `color-mix` dependency means the entire rule must stay SCSS. Also, MobileHeader is a do-not-touch zone.

---

## 10. Visual Regression Testing Plan

### 10.1 Automated Playwright Screenshot Tests

Required test captures (all at 2x DPR for retina accuracy):

| # | Test | Devices | Views |
|---|---|---|---|
| 1 | Desktop gallery grid (light) | Chromium desktop 1440×900 | Full page |
| 2 | Desktop gallery grid (dark) | Chromium desktop 1440×900 | Full page |
| 3 | Desktop album card hover (light) | Chromium desktop 1440×900 | Single card close-up |
| 4 | Desktop album card hover (dark) | Chromium desktop 1440×900 | Single card close-up |
| 5 | Desktop photo card hover | Chromium desktop 1440×900 | Single card close-up |
| 6 | Desktop AppHeader (brand icon + title + theme toggle + search) | Chromium desktop 1440×900 | Header region |
| 7 | Desktop lightbox open (dark overlay) | Chromium desktop 1440×900 | Full viewport |
| 8 | Desktop lightbox sidebar | Chromium desktop 1440×900 | Sidebar region |
| 9 | Desktop SettingsModal open | Chromium desktop 1440×900 | Modal close-up |
| 10 | Desktop toast notification | Chromium desktop 1440×900 | Toast region |
| 11 | Desktop sort dropdown open | Chromium desktop 1440×900 | Dropdown close-up |
| 12 | Desktop skeleton loading | Chromium desktop 1440×900 | Grid region |
| 13 | Desktop empty state | Chromium desktop 1440×900 | Content region |
| 14 | Mobile gallery grid (light) | iPhone 15 Pro (393×852) | Full page |
| 15 | Mobile gallery grid (dark) | iPhone 15 Pro (393×852) | Full page |
| 16 | Mobile header (collapsed) | iPhone 15 Pro (393×852) | Header region |
| 17 | Mobile header (search active) | iPhone 15 Pro (393×852) | Header region |
| 18 | Mobile sidebar open | iPhone 15 Pro (393×852) | Full viewport |
| 19 | Mobile sort popover | iPhone 15 Pro (393×852) | Popover close-up |
| 20 | Mobile lightbox + bottom sheet | iPhone 15 Pro (393×852) | Full viewport |
| 21 | Mobile floating bottom bar | iPhone 15 Pro (393×852) | Bottom region |
| 22 | Tablet gallery grid (light) | iPad Pro 11" (834×1194) | Full page |
| 23 | Tablet header | iPad Pro 11" (834×1194) | Header region |
| 24 | Tablet lightbox + panel | iPad Pro 11" (834×1194) | Full viewport |

### 10.2 Manual Real-Device Checklist

| # | Check | Device |
|---|---|---|
| 1 | Header buttons: hamburger, search, sort, theme toggle all functional | iPhone (Safari) |
| 2 | Search expand/collapse animation smooth | iPhone (Safari) |
| 3 | Sidebar overlay opens/closes correctly | iPhone (Safari) |
| 4 | Album cards tappable with press feedback | iPhone (Safari) |
| 5 | Photo cards tappable (no sticky hover) | iPhone (Safari) |
| 6 | Lightbox opens, swipes between images, sheet expands | iPhone (Safari) |
| 7 | Safe-area: header below notch, bottom bar above home indicator | iPhone (Safari) |
| 8 | No white background bleeding in dark mode | iPhone (Safari) |
| 9 | Theme toggle works, dark/light transition smooth | iPhone (Safari) |
| 10 | Same checks on iPad | iPad (Safari) |
| 11 | Sidebar toggle, breadcrumb, all desktop controls | Desktop Chrome |
| 12 | Album card 3D hover effect (desktop) | Desktop Chrome |
| 13 | Brand title shimmer+glow (desktop dark) | Desktop Chrome |
| 14 | Theme toggle animation (desktop) | Desktop Chrome |

### 10.3 Before/After Comparison Protocol

1. **Baseline capture** — Before any Tailwind migration, capture all 24 Playwright screenshots + record manual checks
2. **Post-Phase 0 capture** — After Tailwind v4 foundation install, repeat all baseline captures. Expected result: no visual changes.
3. **Post-migration capture** — After each Phase 1/2 migration step, run Playwright screenshot tests against the baseline.
4. **Pixel diff is informational, not a blocker** — Automated pixel comparison provides a signal, but deviations should be **investigated manually** rather than auto-failing the PR. Use visual inspection + manual checklist to evaluate whether any differences are acceptable or require fixes.
5. **Manual visual inspection checklist:**
   - Are layout, spacing, and alignment visually identical?
   - Are colors, borders, shadows, and radii unchanged?
   - Are animations, transitions, and hover effects preserved?
   - Are dark/light theme renders correct?
   - Are third-party components (PhotoSwipe, VSBS) unaffected?
6. **Animation frame capture** — For animated elements, capture at 0ms, 500ms, and 1000ms of the animation cycle
7. **Video recording** — Record 5-second videos of key interactions (lightbox open, header search expand, album hover)

---

## 11. Rollback Strategy

### 11.1 Rollback Points

| Phase | Rollback Action | Recovery Time |
|---|---|---|
| Phase 0 | Remove Tailwind import, remove `tailwind.css`, remove Vite plugin, `npm uninstall tailwindcss` | ~5 min |
| Phase 1 | Git revert affected component files to pre-migration commit | ~2 min |
| Phase 2 | Git revert search/filter component files | ~5 min |
| Phase 3 (Future / Deferred) | Git revert metadata/table component files | ~5 min |

### 11.2 Git Strategy

- **Dedicated branch:** `tailwind-migration` branched from `main`
- **Commit per component:** One commit per migrated component for granular rollback
- **Pre-migration tag:** `pre-tailwind-baseline` on `main` before any Tailwind work
- **Post-Phase-0 tag:** `tailwind-foundation` after Phase 0 verified zero visual changes
- **Never squash merge** — preserve individual component migration commits

### 11.3 Emergency Rollback Procedure

If a critical visual regression is discovered in production after Tailwind migration:

1. **Immediate:** Revert the merge commit that introduced Tailwind
2. **Verify:** Run all 24 Playwright screenshot tests against the reverted code
3. **Root cause:** Isolate which specific migration caused the regression
4. **Fix:** Address the specific issue on the migration branch
5. **Re-test:** Full Playwright suite + manual device checklist
6. **Re-merge:** Only after all tests pass

---

## 12. File-by-File Migration Map

### SCSS/CSS Files

| File | Current Role | Risk | Phase | Recommendation | Reason |
|---|---|---|---|---|---|
| `styles/tokens.css` | Design tokens (90+ vars) | **High** | 0 | **Keep as-is**, map to Tailwind theme | Tokens must remain as CSS variables; Tailwind references them via `var()` |
| `styles/main.scss` | Global resets, brand animations, base styles, a11y | **High** | 0 | **Keep in SCSS**, strip only Preflight-overlapping resets | Brand animations, scrollbar styles, focus-visible, high-contrast, reduced-motion must stay SCSS |
| `styles/_breakpoints.scss` | SCSS breakpoint mixins | Low | 0 | **Keep in SCSS** but mark as deprecated | Tailwind has its own breakpoint system; SCSS mixins needed only for legacy components |
| `styles/_mobile-overrides.scss` | Touch hover fixes, iOS Safari background, safe-area | **Critical** | 0 | **Keep 100% as-is — do not touch** | This file fixes real iOS Safari bugs. Any change = potential regression |
| `styles/_lightbox-shared.scss` | PhotoSwipe overrides, accordion, focus rings | **High** | 0 | **Keep in SCSS** | PhotoSwipe class overrides + third-party selectors must stay |
| `styles/_lightbox-desktop.scss` | Desktop metadata panel | Medium | 0 | **Keep in SCSS** | Complex lightbox styling with backdrop-filter, scrollbar, nested selectors |
| `styles/_lightbox-mobile.scss` | Mobile bottom sheet | **High** | 0 | **Keep in SCSS — do not touch** | Mobile lightbox sheet is frozen |
| `styles/_lightbox-tablet.scss` | Tablet bottom sheet | **High** | 0 | **Keep in SCSS — do not touch** | Tablet lightbox sheet is frozen |
| `assets/fonts.css` | Google Fonts import | Low | 0 | **Keep as-is** | Font imports are orthogonal to Tailwind |

### Vue Components — Desktop (Safe to Migrate)

| File | Risk | Phase | Recommendation | Notes |
|---|---|---|---|---|
| `AppHeader.vue` | **High** | 1 | **Partial migration** — static layout (flex, gap, padding) to Tailwind. Animations (brand-icon, brand-title, theme toggle, search neon) keep in SCSS. | Dark mode neon effects on `.search-box`, `.theme-toggle` must stay SCSS. |
| `SettingsModal.vue` | Medium | 2+ | **Partial migration** — shell structure (backdrop, content, header/body/footer) to Tailwind `@layer`. Animations (`fadeIn`, `slideUp`) stay in SCSS and are deferred to Phase 2+ until visual parity is proven. | animation migration deferred — SCSS-first per §9.1 |
| `ToastContainer.vue` | Low | 1 | **Full migration** — positioning, layout, TransitionGroup classes to Tailwind. | Keep ToastItem color variants in SCSS (color-mix dependencies). |
| `ToastItem.vue` | Low | 1 | **Partial migration** — layout (flex, gap, padding) to Tailwind. Type variants (success/error/warning/info) keep in SCSS. | Color tokens via CSS variables are safe. |
| `GalleryGrid.vue` | **High** | 1 | **Partial migration** — toolbar/control wrapper layout (grid, gap, buttons) to Tailwind. Only desktop toolbar/control wrapper styles may be considered. Do not touch scroller, virtual rows, sentinels, image loading states, skeleton behavior, virtualization logic, lightbox trigger behavior, or image sizing policy. | Do NOT touch `.scroller`, `.virtual-row`, `.tanstack-virtual-*`, `.skeleton-grid`. |
| `DesktopLayout.vue` | Medium | 1 | **Partial migration** — grid layout, sidebar static styles. Sidebar open/close transition keep in SCSS. | |
| `Breadcrumb.vue` | Low | 1 | **Full migration** possible | Simple flex layout with text and separators. |
| `SidebarHeader.vue` | Low | 1 | **Full migration** possible | Simple layout with form elements. |
| `FolderTreeItem.vue` | Low | 1 | **Full migration** possible | Recursive flex layout; scoped styles are simple. |
| `EmptyState.vue` | Low | 1 | **Partial migration** — layout to Tailwind, decorative animations (icon-spin, pulse-slow, float, twinkle) keep in SCSS. | |
| `SkeletonLoader.vue` | Medium | 1 | **Partial migration** — layout to Tailwind, shimmer animation keep in SCSS. | Shimmer has touch-device disable logic. |
| `GlowContainer.vue` | Low | 1 | **Keep in SCSS** — the negative margin overflow hack must not be changed. | |
| `GallerySectionHeader.vue` | Low | 1 | **Full migration** possible | Simple flex layout with text and badge. |
| `AlbumScroller.vue` | Medium | 1 | **Keep in SCSS** — uses `@supports (background: color-mix(...))` progressive enhancement pattern. | |
| `ExpandableText.vue` | Low | 1 | **Keep in SCSS** — text clipping and expand logic depend on computed styles. | |
| `IntroScreen.vue` | Medium | 0 | **Keep in SCSS** — complex gradient, shimmer, and pulse animations. | |

### Vue Components — Do Not Touch (All Phases)

| File | Reason |
|---|---|
| `MobileHeader.vue` | Frozen — complex search expand/backdrop/overlay logic with mobile-specific CSS |
| `TabletHeader.vue` | Frozen — same risk profile, tablet-specific breadcrumb integration |
| `MobileLayout.vue` | Frozen — sidebar behavior, backdrop, padding transitions |
| `TabletLayout.vue` | Frozen — sidebar overlay, backdrop transition, grid layout |
| `LightboxMobileSheet.vue` | Frozen — VSBS integration, 200+ lines of `[data-vsbs-*]` overrides |
| `RootPathSheet.vue` | Frozen — mobile bottom sheet with iOS textarea quirks |
| `MobileFloatingBottomBar.vue` | Frozen — safe-area-inset-bottom, scroll visibility sync |
| `MobilePhotoSwipe.vue` | Frozen — mobile PhotoSwipe + safe-area positioning |
| `TabletPhotoSwipe.vue` | Frozen — tablet-specific PhotoSwipe integration |
| `LightboxTabletPanel.vue` | Frozen — tablet metadata panel with 2-column grid |
| `LightboxDesktopPanel.vue` | Frozen — complex metadata panel with collapsible sections |
| `Lightbox.vue` | Frozen — device-adaptive lightbox orchestration |
| `PhotoSwipeViewer.vue` | Frozen — core PhotoSwipe wrapper with paddingFn |
| `AlbumCardMobile.vue` | Frozen — mobile-specific, compact, hover overrides |
| `AlbumCardTablet.vue` | Frozen — tablet-specific card styling |
| `AlbumCard.vue` | **Partial freeze** — static layout (padding, border-radius, info section) can use Tailwind; 3D hover/perspective/dark glow keep in SCSS |
| `PhotoCard.vue` | **Partial freeze** — static layout can use Tailwind; hover transform, thumbnail opacity, shimmer animation, type badge keep in SCSS |
| `TabletGalleryToolbar.vue` | Frozen — tablet-specific toolbar component |
| `App.vue` | Frozen — theme toggle logic, layout switching |
| `GalleryGrid.vue` | Frozen for virtualization/internals — only the desktop toolbar wrapper may be considered |
| All mobile/tablet sheet behavior files | Frozen — includes `RootPathSheet.vue`, `LightboxMobileSheet.vue`, `LightboxTabletPanel.vue`, and any VSBS/sheet orchestration |

---

## 13. Final Recommendation

### Recommendation: **Hybrid Migration**

**Do not pursue a full Tailwind migration.** The gallery's animation density, `color-mix()` usage, 3D transforms, multi-layer drop-shadows, third-party overrides, and iOS Safari quirks make a full migration impractical without losing visual fidelity.

**Do pursue a hybrid approach:**

| Layer | Technology | Scope |
|---|---|---|
| **Semantic tokens** | CSS custom properties (`tokens.css`) | All colors, shadows, radii, timing, sizing. Single source of truth. |
| **Layout utilities** | Tailwind CSS | Spacing, flex/grid, sizing, typography, borders, simple hover states on desktop-safe components. |
| **Component abstractions** | Tailwind `@layer components` | Repeated patterns: icon buttons, input shells, badges, modals, dropdowns. |
| **Animations** | SCSS | All keyframes, complex hover effects, 3D transforms, gradient animations, multi-layer shadows. |
| **Visual effects** | SCSS | Dark mode neon glows, album card 3D, brand title shimmer, backdrop-filter compositions, `color-mix()` rules. |
| **Third-party overrides** | SCSS | PhotoSwipe, vue-spring-bottom-sheet, scrollbar styles. |
| **Mobile/iOS fixes** | SCSS | Safe-area, touch hover disables, rubber-band, viewport hacks. |
| **New components (future)** | Tailwind-first + gallery tokens | AdvancedSearch, IndexPanel — built with Tailwind from the start. MetadataTable deferred to Phase 3 (Future). |

### Why Not Full Migration

1. **25 @keyframes** — 18 of 25 are too complex for Tailwind keyframe extension
2. **20+ `color-mix()` uses** — no Tailwind equivalent; fundamental to the header glass-morphism design
3. **20+ `backdrop-filter` uses** — Safari requires `-webkit-` prefix; Tailwind output must be verified per browser
4. **Album card 3D transforms** — `perspective`, `transform-style: preserve-3d`, `translateZ()` are outside Tailwind's capabilities
5. **Multi-layer `filter: drop-shadow()`** — Brand title glow uses 3 simultaneous drop-shadow layers; Tailwind cannot compose filter chains
6. **Third-party overrides** — PhotoSwipe and VSBS require exact CSS class/attribute selectors; Tailwind cannot target `.pswp__button--arrow--next` or `[data-vsbs-sheet]`
7. **iOS Safari-specific fixes** — `_mobile-overrides.scss` fixes real bugs that only reproduce on physical iOS devices; no Tailwind utility can reproduce these context-dependent fixes
8. **38 custom scrollbar styles** — Tailwind has no scrollbar utility system

### Why Hybrid Works

1. Candidate estimate: Tailwind may cover a large portion of static layout/spacing styles, but the actual SCSS reduction must be proven by migration diffs. Do not commit to a 60-70% SCSS reduction until Phase 1 migration proves it without visual regressions.
2. Semantic tokens via CSS variables keep the warm-latte/premium theme intact
3. If migration diffs prove safe, SCSS may eventually shrink toward animation/effect/override concerns. Do not assume a fixed percentage before Phase 1 evidence.
4. New components are Tailwind-first, avoiding accumulation of new SCSS
5. Mobile/tablet code is untouched and safe
6. Every existing animation is preserved byte-for-byte

### Decision Criteria

- **Full migration:** ❌ — Too many `color-mix()`, 3D transforms, multi-layer filters, and iOS quirks that Tailwind cannot replicate
- **No migration:** ❌ — Misses opportunity to standardize layout/spacing and improve developer experience for new components
- **Hybrid migration:** ✅ — Preserves 100% of animations/effects while modernizing layout approach. Lowest risk, highest confidence.

---

## 14. Summary of Key Numbers

| Metric | Count |
|---|---|
| Vue SFC files audited | 35 |
| SCSS files audited | 7 |
| CSS files audited | 2 |
| `@keyframes` definitions found | 25 |
| `transition` declarations | 129 |
| `backdrop-filter` uses | 20+ |
| `color-mix()` uses | 20+ |
| `transform` uses | 133 |
| Custom scrollbar styles | 38 |
| `safe-area-inset` references | 6 |
| PhotoSwipe references | 20+ |
| vue-spring-bottom-sheet references | 30+ |
| Design tokens defined | 90+ |
| Components classified "do not touch" | 18 |
| Components safe for partial Tailwind migration | 10 |
| Components safe for full Tailwind migration | 5 |

---

## 15. Confirmation

This document was created as a research + planning exercise only. Updated as Phase 0 progressed.

- ✅ Tailwind v4 installed (`tailwindcss`, `@tailwindcss/vite`)
- ✅ Vite config updated (`tailwindcss()` plugin added)
- ✅ `tailwind.css` created with `@theme inline` + `@custom-variant dark`
- ✅ Preflight enabled — 25/25 `tailwind-preflight.spec.ts` tests pass, stays enabled permanently
- ❌ No Tailwind packages installed — now installed (Phase 0A)
- ❌ No package.json edited — now edited (Phase 0A)
- ❌ No Vite config edited — now edited (Phase 0A)
- ✅ No PostCSS config edited (not needed with Tailwind v4 Vite plugin)
- ✅ No Vue components modified — confirmed after Phase 0 testing
- ✅ No SCSS files modified — confirmed after Phase 0 testing
- ✅ No runtime behavior changed — confirmed after Phase 0 testing (23 Playwright smoke tests pass)
- ✅ No mobile/tablet code changed (frozen)
- ✅ shadcn-vue approved for selective, component-by-component adoption (see §6); not yet installed; no components migrated yet

All counts above were verified via `grep` commands against the actual repo at commit time. Results were included inline in each section.
