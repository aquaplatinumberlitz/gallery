# Mobile-First Style Refactor Proposal — Gallery App

> **Date:** 2026-05-27
> **Based on:** Full code analysis of `frontend/src/` — 12 components, 4 SCSS files, composables, stores, and existing plans

---

## 1. Current Mobile Pain Points (Code-Level Evidence)

### 1.1 AlbumCard: 3D Hover Effects Run on Mobile (Wasteful)

**File:** `AlbumCard.vue` (lines 46-220)
- `perspective: 1000px` + `transform-style: preserve-3d` on every album card
- `.album-layer-back` rotates `-12deg`, `.album-layer-front` rotates `8deg`
- On `:hover`:
  - `translateY(-10px)` on diagonal wrapper
  - Layer back: `translate(-20px, 5px) rotate(-15deg)`
  - Layer front: `translate(10px, -5px) rotate(12deg) scale(1.05)`
  - Dark mode: 6-layer `box-shadow` glow (`--glow-card-hover-front`, 50px spread)
- On mobile: these all fire on `:active` but never visually settle → **wasted GPU cycles**
- The elastic bounce curve `cubic-bezier(0.34, 1.56, 0.64, 1)` on `.album-cover-diagonal` triggers layout thrash on scroll

### 1.2 PhotoCard: Unnecessary Hover Scale

**File:** `PhotoCard.vue` (lines 127-195)
- `:hover` state: `translateY(-2px) scale(1.02)` + `box-shadow` transition
- `.thumbnail-img` gets `scale(1.05)` with 280ms cubic-bezier
- On mobile: these fire on first tap (sticky hover) then remain until next tap → looks glitchy
- No `@media (hover: hover)` guard exists

### 1.3 GlowContainer: Negative Margin Layout Risk

**File:** `GlowContainer.vue` (lines 14-25)
- Uses negative margins + padding technique with `pointer-events: none`
- On mobile: values reduce to 16px bleed (AlbumScroller passes `bleed=16` when `isMobile`), but the negative margin arithmetic can still cause overflow clipping in WebView

### 1.4 No Touch-Optimized States

- Nowhere in the codebase uses `@media (hover: none)` or `@media (pointer: coarse)` to differentiate touch behavior
- Mobile hover animations are direct copies of desktop hover animations
- No active/tap state alternatives for touch devices

### 1.5 Brand Hero Still in DOM on Mobile

**File:** `AppHeader.vue` — `v-if="!isMobile"` controls visibility, but **the entire AppHeader is rendered as a separate component from MobileHeader**. This is fine (not in DOM), but the brand CSS animation keyframes in `main.scss` (lines 84-113 for `dark-title-shimmer`, `dark-title-glow`, `dark-underline-pulse`) still exist in global CSS and are parsed on mobile.

### 1.6 Breakpoint Inconsistency

| Location | Breakpoints Used |
|----------|-----------------|
| `useDevice.ts` | compact <480, phone <768, tablet <1024, desktop ≥1024 |
| `App.vue` styles | 1024px, 768-1024, 767px, 480px |
| `GalleryGrid.vue` | 1024px, 767px, 480px |
| `AlbumScroller.vue` | 767px, 480px |
| `AlbumCard.vue` | 767px, 480px |
| `_mobile_ux_plan.md` | 640px (outdated) |

**Problem:** `useDevice` composable is available but **not used** in any style-based logic — only in template conditionals. All responsive styles use raw media query pixel values.

---

## 2. Effects to Fix for Mobile ⚠️

### P0 — CRITICAL (Fix Now)

| Effect | Component | Why Remove | Replacement |
|--------|-----------|------------|-------------|
| **3D layer rotation** (`rotate(-12deg/8deg)`) | AlbumCard | No hover on touch; GPU compositing cost | Flat layering with subtle `box-shadow` depth (like Apple Photos album stack) |
| **Elastic bounce** (`.album-cover-diagonal` transform) | AlbumCard | Causes jank on scroll; `perspective: 1000px` forces 3D render layer | Remove entirely on mobile; keep only on `@media (hover: hover)` |
| **Hover scale** (`scale(1.02)` + `translateY(-2px)`) | PhotoCard | Sticky hover on mobile causes flicker; wastes GPU | Replace with `box-shadow` elevation only, activated on tap via `:active` |
| **Glow box-shadow** (6-layer, 50px spread) | AlbumCard + tokens.css | Expensive to paint; on low-end devices causes frame drops | Disable glow entirely on mobile; use tinted border (2px) instead |

### P1 — HIGH (Do Next)

| Effect | Component | Why Change | Replacement |
|--------|-----------|------------|-------------|
| **Shimmer animation** (`.shimmer-wave`) | PhotoCard | Infinite `@keyframes shimmer` runs even off-screen; CPU cost | Only animate when `isLoaded === false` and card is in viewport (use `content-visibility: auto`) |
| **3D preserve** (`transform-style: preserve-3d`) | AlbumCard | Forces GPU layer; mobile GPUs are bandwidth-limited | Remove entirely on mobile |
| **Dark mode multi-glow** (6 `box-shadow` layers) | AlbumCard + tokens.css | 6 shadows × 2 layers × N cards = massive overdraw | Reduce to 1-2 shadow layers on mobile |
| **Hover border glow** | GalleryGrid (nav-btn, sort-trigger, grid-slider) | All hover shadows (`box-shadow: 0 4px 12px color-mix(...)`) | Reduce opacity/remove shadow on mobile hover |

### P2 — MEDIUM (Polish)

| Effect | Component | Why Change |
|--------|-----------|-------------|
| `.brand-title` shimmer keyframes | main.scss | Loaded in global CSS even if AppHeader isn't rendered |
| `.album-scroll-btn` hover scale | AlbumScroller | Hover shows/hides arrows; on mobile arrows always visible but hover stays |
| `fadeSlideIn` animation | GalleryGrid | Runs on every image row mount; on slow devices causes repaint |

---

## 3. Proposed Mobile-First Style Architecture

### 3.1 Recommendation: Hybrid — Media Queries in Component + Global Mobile Override File

**Strategy:** Use **co-located media queries** inside each component's `<style scoped>` for component-specific overrides (animations, layout), PLUS a single `_mobile-overrides.scss` partial for global touch/hover/glow resets.

**Rationale:**
- Component-scoped overrides keep styles isolated (Vue SFC best practice)
- Global overrides handle cross-cutting concerns: `@media (hover: none)` resets, `@media (pointer: coarse)` touch target tweaks, glow disabling
- Avoids file-hopping for simple changes

**File structure addition:**

```
src/styles/
  tokens.css              ← (existing) design tokens
  main.scss               ← (existing) global styles
  _mobile-overrides.scss  ← (NEW) cross-cutting mobile resets
  _lightbox-desktop.scss  ← (existing)
  _lightbox-mobile.scss   ← (existing)
  _lightbox-shared.scss   ← (existing)
  _lightbox-tablet.scss   ← (existing)
```

**`_mobile-overrides.scss` contents:**
```scss
// ============================================
// Mobile Overrides — Cross-Cutting Resets
// ============================================

// 1. Disable all hover effects on touch devices
@media (hover: none) and (pointer: coarse) {
  * {
    &:hover {
      // Kill sticky hover on all elements
      animation: none !important;
      transform: none !important;
    }
  }
}

// 2. Disable heavy glow effects on mobile (poor GPU)
@media (max-width: 767px) {
  :root[data-theme="dark"] {
    --glow-card-hover: none;
    --glow-card-hover-front: none;
    --glow-card-hover-back: none;
    --glow-card-active: none;
  }
}

// 3. Touch target expansion (44px minimum)
@media (pointer: coarse) {
  .mh-btn, .mbb-btn, .nav-btn,
  [class*="btn"], [role="button"] {
    &::before {
      content: '';
      position: absolute;
      inset: -8px;
    }
  }
}

// 4. Reduced shadow complexity on mobile
@media (max-width: 767px) {
  --shadow-card: 0 1px 2px rgba(0,0,0,0.15);
  --shadow-card-hover: 0 2px 6px rgba(0,0,0,0.15);
}
```

### 3.2 Use `useDevice` Composable for Reactive Style Logic

Currently `useDevice` is used only for `v-if` in templates. It should also drive:
- `columnCount` default (3 on mobile, 5 on desktop) — already in `useColumnResize`
- `GlowContainer` bleed value (already done via `bleed` prop)
- Conditional CSS classes via computed refs:
  ```vue
  <div :class="['album-card', { 'is-touch': isMobile }]">
  ```

### 3.3 Standardize Breakpoints

Align all media queries with `useDevice.ts` constants:

```scss
// Semantic breakpoint map
$breakpoints: (
  'compact': 480px,
  'phone': 768px,
  'tablet': 1024px,
);

@mixin respond-below($bp) {
  $max: map-get($breakpoints, $bp);
  @if $max {
    @media (max-width: $max) { @content; }
  }
}

// Usage:
// @include respond-below('phone') { ... }
```

Or simplest approach: use the existing pixel values (480, 767, 1024) consistently everywhere. The current plan.md uses 640px which is wrong — align to 767px and 480px.

---

## 4. 2025-2026 Mobile UX Trends — Applicability

| Trend | Apply? | Notes |
|-------|--------|-------|
| **Bottom sheet** (sort, filter, overflow) | ✅ YES | Already in LightboxMobileSheet; extend to GalleryGrid sort menu |
| **Swipe gestures** (nav, dismiss) | ✅ YES | Phase 4 of existing plan; start with lightbox swipe horizontal |
| **Spring animations** | ⚠️ PARTIAL | Use for sheet open/close (cubic-bezier already good); avoid on grid items (jank) |
| **Glassmorphism** (backdrop-filter) | ⚠️ CAREFUL | `backdrop-filter: blur()` is expensive on mobile; use sparingly only on floating bars (MobileHeader, MobileFloatingBottomBar already use it with 85% opacity to reduce paint) |
| **Pull-to-refresh** | ✅ YES | Already in plan (Phase 4.1); use translateY with spring easing |
| **Collapsible header** (scroll hide) | ✅ YES | Already implemented via `useScrollVisibility` composable |
| **Pinch-to-zoom grid** | ❌ DEFER | High complexity, conflicts with scroll; defer to Phase 4 |
| **Haptic feedback** | ✅ YES | Low effort; use `navigator.vibrate()` for tab switches, pull-to-refresh trigger |

---

## 5. Performance Considerations

### 5.1 GPU / Paint Cost Analysis

| Operation | Mobile GPU Impact | Recommendation |
|-----------|------------------|----------------|
| `box-shadow` (6-layer glow, 50px spread) | 🔴 EXTREME — 6× paint passes per card | Disable entirely on mobile |
| `backdrop-filter: blur(12px)` | 🟡 MODERATE — GPU composition; okay if 1-2 elements | Keep on header/bars only (2 instances max) |
| `transform: translateY/scale` with `perspective: 1000px` | 🟡 MODERATE — forces 3D layer; memory | Remove `perspective` on mobile; use 2D transforms only |
| `@keyframes shimmer` (infinite) | 🟡 MODERATE — repaint even off-screen | Add `content-visibility: auto` to grid items |
| Opacity transitions | 🟢 LOW — composited by GPU | Keep as-is |
| CSS `filter: drop-shadow()` (brand icon, title) | 🟢 LOW — GPU-friendly if few elements | Keep but limit to 2-3 elements max |

### 5.2 Quick Performance Wins

1. **Add `content-visibility: auto`** to all `.virtual-row` and `.album-grid > *` items
2. **Wrap glow box-shadows in `@media (hover: hover) and (pointer: fine)`** — desktop only
3. **Replace `@keyframes shimmer` with `content-visibility: auto` + opacity transition** — off-screen cards skip paint
4. **Limit `backdrop-filter`** to max 2 elements on screen (header + bottom bar)

---

## 6. Files to Change — Prioritized

### Phase 1 — CSS Quick Fixes (1-2h)

| # | File | Change | Effort |
|---|------|--------|--------|
| 1 | `AlbumCard.vue` | Wrap `:hover` + `perspective` in `@media (hover: hover)` | 30min |
| 2 | `PhotoCard.vue` | Wrap `:hover scale` in `@media (hover: hover)`; add `:active` tap state | 20min |
| 3 | `tokens.css` | Add `--glow-disabled: none` token; override on mobile | 15min |
| 4 | `AlbumScroller.vue` | Remove elastic bounce on mobile; simplify arrow visibility | 15min |
| 5 | `GalleryGrid.vue` | Add `content-visibility: auto` to virtual rows | 10min |

### Phase 2 — Architecture Changes (2-4h)

| # | File | Change | Effort |
|---|------|--------|--------|
| 6 | `src/styles/_mobile-overrides.scss` (NEW) | Global hover: none + glow disable + touch targets | 1h |
| 7 | `AlbumCard.vue` | Mobile-specific template: remove `perspective`, add flat stack with shadow | 1.5h |
| 8 | `AlbumScroller.vue` | Use `useDevice` to drive `bleed` prop directly (already partially done) | 30min |
| 9 | `main.scss` | Remove shimmer-related global styles; add `@media (prefers-reduced-motion)` checks | 30min |

### Phase 3 — Enhanced Mobile UX (4-8h)

| # | File | Change | Effort |
|---|------|--------|--------|
| 10 | `GalleryGrid.vue` | Sort menu → bottom sheet on mobile (reuse LightboxMobileSheet pattern) | 2h |
| 11 | `BottomNavigationBar.vue` | Integrate with App.vue as primary mobile nav | 3h |
| 12 | `AlbumsTabView.vue` (NEW) | Extract sidebar content for mobile albums tab | 2h |
| 13 | `LightboxMobileSheet.vue` | Add spring animation on open/close | 1h |

---

## 7. Special Notes

### 7.1 Glow Bleed Without `overflow: hidden`

Current approach: `GlowContainer` uses negative margins + padding to allow glow to bleed. On mobile, the `bleed` prop reduces to 16px. **This is fine** — the `overflow: visible` approach works. Just ensure:
- Parent containers (`scroller-container`, `folders-only-container`) have `overflow: visible` (they do — lines 529-601)
- The `vue-recycle-scroller__item-wrapper` has `overflow: visible` (line 552 — already set via `:deep()`)

### 7.2 Touch Target 44px Minimum

Current state:
- `MobileHeader` buttons: 38px (`mh-btn`) → **below spec**
- `MobileFloatingBottomBar` buttons: 36px (`mbb-btn`) → **below spec**
- `GalleryGrid` nav buttons on mobile: 32px → **below spec**
- `AlbumScroller` arrows: 42px → borderline

**Fix:** Add `::before` pseudo-element approach or increase button sizes to 44px. The `@media (pointer: coarse)` block in `main.scss` (lines 425-519) already sets `min-height: 44px; min-width: 44px` on buttons but has exclusion rules for compact controls. Ensure mobile nav buttons are NOT excluded.

### 7.3 `prefers-reduced-motion` Coverage

Current: Only GalleryGrid has `prefers-reduced-motion: reduce` query (lines 1116-1125). Need to add to:
- `AlbumCard.vue` — disable hover transforms
- `PhotoCard.vue` — disable hover scale
- `AlbumScroller.vue` — disable scroll animation
- `LightboxMobileSheet.vue` — disable slide transitions

### 7.4 Dark Mode Glow vs Mobile Battery

The dark mode glow effects use 6-layer `box-shadow` declarations. On OLED screens, heavy glow compositing can prevent GPU from entering low-power state. **Disable all glow effects on battery-powered mobile devices** via `@media (max-width: 767px)` override in tokens.

### 7.5 Bottom Nav Implementation Status

**Good news:** `BottomNavigationBar.vue` already exists (lines 1-76) with MD3-style layout (4 tabs: Photos, Albums, Search, More). However, it's **not yet integrated** into `App.vue`. The existing `_mobile_ux_plan.md` correctly identifies this as Phase 3 (~16-20h). The current mobile uses:
- `MobileHeader.vue` (top fixed bar with hamburger + search + theme + settings)
- `MobileFloatingBottomBar.vue` (floating pill with nav buttons)
- Hamburger-based sidebar overlay

**Recommendation:** Implement bottom nav integration as the highest-priority UX structural change. It replaces 3 separate mobile UI pieces with one cohesive pattern.

---

## 8. Summary: What to Do (Ordered by Impact)

1. **Immediate (CSS only, 2h):** Wrap all hover effects in `@media (hover: hover)` across AlbumCard, PhotoCard, AlbumScroller, GalleryGrid — immediately fixes sticky hover jank on mobile
2. **Quick (CSS only, 1h):** Add `_mobile-overrides.scss` with global touch/hover/glow resets
3. **Quick (CSS, 30min):** Disable glow tokens on mobile in `tokens.css`
4. **Structural (4h):** Integrate `BottomNavigationBar.vue` into `App.vue`; replace hamburger + sidebar overlay on mobile
5. **Structural (2h):** Create `AlbumsTabView.vue` for the Albums bottom nav tab
6. **Enhanced (2h):** Convert GalleryGrid sort dropdown to bottom sheet on mobile
7. **Polish (1h):** Add gesture support to Lightbox (swipe between images)
8. **Performance (1h):** Add `content-visibility: auto` to virtual grid rows; limit `backdrop-filter` usage
