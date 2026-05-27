# Extended Mobile UX Proposal — Gallery App

> **Date:** 2026-05-27
> **Based on:** Full code-level analysis of all 22 Vue components, 5 SCSS/CSS files, composables, stores, and the existing `_mobile_refactor_proposal.md`
> **Goal:** Define a **completely separate mobile style** — zero glow, zero hover carryover, flat design, touch-native — while keeping the Pastel Dreamscape color palette (tone only).

---

## Table of Contents

1. [Guiding Philosophy](#1-guiding-philosophy)
2. [Architecture Decision: Separate Component vs Media Queries](#2-architecture-decision-separate-component-vs-media-queries)
3. [Component-by-Component Mobile Spec](#3-component-by-component-mobile-spec)
   - 3.1 [AlbumCard.vue — Flat Stack Card](#31-albumcardvue--flat-stack-card)
   - 3.2 [PhotoCard.vue — Tap-to-Reveal](#32-photocardvue--tap-to-reveal)
   - 3.3 [AlbumScroller.vue — Snap Scroller](#33-albumscrollervue--snap-scroller)
   - 3.4 [GalleryGrid.vue — Unified Mobile Layout](#34-gallerygridvue--unified-mobile-layout)
   - 3.5 [GlowContainer.vue — Disabled on Mobile](#35-glowcontainervue--disabled-on-mobile)
   - 3.6 [MobileHeader.vue — Redefined](#36-mobileheadervue--redefined)
   - 3.7 [MobileFloatingBottomBar.vue — Evolution to Bottom Nav](#37-mobilefloatingbottombarvue--evolution-to-bottom-nav)
   - 3.8 [BottomNavigationBar.vue — Integration Spec](#38-bottomnavigationbarvue--integration-spec)
4. [Mobile Color Palette — Pastel Dreamscape Variant](#4-mobile-color-palette--pastel-dreamscape-variant)
5. [Mobile Animation System — Spring & Flat](#5-mobile-animation-system--spring--flat)
6. [CSS Architecture Changes](#6-css-architecture-changes)
7. [Touch Gesture Specs](#7-touch-gesture-specs)
8. [Performance Checklist](#8-performance-checklist)
9. [Implementation Priority & Effort](#9-implementation-priority--effort)
10. [CSS Code Snippets — Ready to Copy](#10-css-code-snippets--ready-to-copy)

---

## 1. Guiding Philosophy

**"Mobile is not 'desktop but smaller.' Mobile is its own medium."**

| Principle | Desktop (Existing) | Mobile (New) |
|-----------|-------------------|--------------|
| Card style | 3D layers, `perspective: 1000px`, `rotate(-12deg)` | Flat 2-layer stack, no perspective, no rotation |
| Hover | `translateY(-10px)`, `scale(1.05)`, glow shadows | **No hover.** `:active` only. Tap feedback via `opacity` or `scale(0.97)` |
| Glow | 6-layer `box-shadow`, 50px spread, neon color | **Zero glow.** Use `border` accent or `background` tint instead |
| Animation | `cubic-bezier(0.34, 1.56, 0.64, 1)` (elastic bounce) | `cubic-bezier(0.4, 0, 0.2, 1)` (MD3 standard easing) or `spring(Stiffness=300, Damping=20)` for sheet |
| Shadows | `--shadow-card-level4` with `color-mix` | MD3 Elevation Level 1 max (`0 1px 2px rgba(0,0,0,0.15)`) |
| Shimmer | Infinite `@keyframes shimmer` | Use `content-visibility: auto` + static skeleton color; animate only when in viewport + `isLoading` |
| Touch targets | 32-40px buttons | 44px minimum (`@media (pointer: coarse)`) |
| Scroll | Scrollbar-based, pagination arrows | `scroll-snap-type: x mandatory`, spring scroll, hide arrows |
| Sort/Filter | Dropdown menu | Bottom sheet (reuse `LightboxMobileSheet` pattern) |

---

## 2. Architecture Decision: Separate Component vs Media Queries

### Recommendation: **Media Queries + Mobile Override Module (Hybrid)**

Do **NOT** create separate `MobileAlbumCard.vue` / `MobilePhotoCard.vue` files. Rationale:

1. **Template is mostly shared** — the data binding, props, emits, and accessibility attributes are identical. Only CSS + a few conditional attributes change.
2. **Vue SFC scoped styles + media queries** give clean separation within one file.
3. **Maintenance cost doubles** with separate components — every prop change needs updates in 2 files.
4. **Bundle size** — separate components would be tree-shaken (good), but the template duplication isn't worth it.

### What to do instead:

```vue
<template>
  <!-- Same template for both -->
  <div class="album-card" :class="{ 'is-touch': isMobile }" ...>
```

```scss
// DESKTOP styles (default)
.album-card {
  perspective: 1000px;
  // ... all existing desktop CSS
}

// MOBILE overrides (at end of <style scoped>)
@media (hover: none) and (pointer: coarse),
       (max-width: 767px) {
  .album-card {
    perspective: none;                   // Kill 3D
    padding-top: 0;                      // Remove hover space
    padding-left: 0;                     // Remove hover space
    transform: none !important;          // Kill all hover transforms
    
    .album-cover-diagonal {
      transform-style: flat;
      transition: none;                  // Kill elastic bounce
      transform: none !important;
    }
    
    .album-layer {
      transition: none;                  // Kill layer animation
    }
    
    .album-layer-back {
      transform: none;                   // Flat position
      top: 0; left: 0;
    }
    
    .album-layer-front {
      transform: none;                   // Flat position
      top: 0; right: 0;
    }
  }
}
```

### Global mobile override file still recommended:

`src/styles/_mobile-overrides.scss` — imported once in `main.scss` — handles cross-cutting concerns that would be repetitive in every component:

- `@media (hover: none)` → kill all sticky hovers globally
- `@media (pointer: coarse)` → 44px touch targets
- `[data-theme="dark"] @media (max-width: 767px)` → disable all glow CSS variables

---

## 3. Component-by-Component Mobile Spec

### 3.1 AlbumCard.vue — Flat Stack Card

#### Current Mobile Pain
- `perspective: 1000px` forces 3D render layer on every card
- `.album-layer-back` rotated `-12deg`, `.album-layer-front` rotated `8deg` — looks chaotic on mobile
- Hover fires `translateY(-10px)` on diagonal, fans layers apart
- Dark mode: 6-layer `box-shadow` glow — GPU nightmare on OLED mobile
- `padding-top: 20px; padding-left: 20px` — waste of space for hover animation that never works on touch

#### Proposed Mobile Design: **Flat Stack Card**

```
┌──────────────────────────────┐
│ ┌─────────┐  ┌─────────┐   │
│ │ BACK    │  │ FRONT   │   │   ← Both layers flat, no rotation
│ │ layer   │  │ layer   │   │      Back shifted 6px down/right
│ │         │  │         │   │      Front on top
│ └─────────┘  └─────────┘   │
│                              │
│  Album Name                 │   ← Title
│  📁 Album · 42 photos       │   ← Meta
└──────────────────────────────┘
```

#### Concrete CSS Changes

```scss
// --- FILE: AlbumCard.vue, at end of <style scoped> ---

// MOBILE: completely kill 3D, glow, hover, elastic bounce
@media (hover: none) and (pointer: coarse),
       (max-width: 767px) {
  
  .album-card {
    perspective: none;                       // REMOVE 3D CONTEXT
    transform-style: flat;
    padding-top: 0;                          // Remove hover space padding
    padding-left: 0;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.10); // MD3 Level 1 max
    border-radius: 8px;                      // Smaller radius for mobile
    transition: 
      transform 150ms ease,                  // Only for active state
      box-shadow 150ms ease;
    
    // TAP: subtle press feedback (replaces hover)
    &:active {
      transform: scale(0.97);
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
    }
  }
  
  .album-cover-diagonal {
    height: 130px;                           // Fixed height for mobile
    transform-style: flat;
    transition: none;
    transform: none !important;              // Override all hover transforms
    
    // Only animate on mount if we want a subtle reveal
    animation: albumCardIn 300ms ease both;
  }
  
  @keyframes albumCardIn {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: none; }
  }
  
  // Both layers: flat, no rotation
  .album-layer {
    width: 65%;
    height: 70%;
    transition: none;                        // No hover animation
    border-width: 2px;                       // Thinner border for mobile
    border-radius: 4px;                      // Slightly rounded layers
  }
  
  .album-layer-back {
    top: 6px;
    left: 6px;
    transform: none;                         // FLAT — no rotate(-12deg)
    opacity: 0.85;
    z-index: 1;
    box-shadow: none;                        // No shadow on back layer
    border-color: color-mix(in srgb, var(--primary-color) 20%, transparent);
  }
  
  .album-layer-front {
    top: 0;
    right: unset;
    left: 20px;                              // Layer front sits 20px right of left edge
    transform: none;                         // FLAT — no rotate(8deg)
    z-index: 10;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
    border-color: var(--album-border-color);
  }
  
  .album-info {
    margin-top: 6px;                         // Less gap on mobile
    padding: 0 6px 6px;
    
    .album-name {
      font-size: 13px;                       // Smaller
      font-weight: 500;                      // Lighter weight for mobile
    }
    
    .album-meta {
      font-size: 10px;
      gap: 3px;
    }
  }
  
  // --- Dark mode mobile: NO GLOW ---
  html[data-theme="dark"] & {
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
    
    .album-layer-front {
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
      border-color: rgba(255, 255, 255, 0.15);
    }
    
    .album-layer-back {
      border-color: rgba(255, 255, 255, 0.08);
    }
    
    .album-name {
      color: var(--neon-color);              // Keep accent color for title
    }
    
    // ABSOLUTELY NO GLOW SHADOWS
    &:hover, &:active {
      box-shadow: none !important;
      .album-layer-front {
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3) !important;
      }
      .album-layer-back {
        box-shadow: none !important;
      }
    }
  }
}

// Even smaller screens
@media (max-width: 480px) {
  .album-cover-diagonal { height: 90px; }
  .album-layer { width: 60%; height: 65%; }
  .album-layer-front { left: 16px; }
  .album-name { font-size: 12px; }
  .album-meta { font-size: 9px; }
}
```

#### Key Properties Summary

| Property | Desktop (Keep) | Mobile (New) |
|----------|---------------|--------------|
| `perspective` | `1000px` | `none` |
| `transform-style` | `preserve-3d` | `flat` |
| `padding-top` | `20px` | `0` |
| `box-shadow` (dark hover) | 6-layer glow | `0 1px 2px rgba(0,0,0,0.3)` |
| `.album-layer-back transform` | `rotate(-12deg)` | `none` (use `top:6px; left:6px`) |
| `.album-layer-front transform` | `rotate(8deg)` | `none` (use `top:0; left:20px`) |
| Transition duration | `280ms` / `400ms` (elastic) | `150ms` (only `:active`) |
| Easing | `cubic-bezier(0.34, 1.56, 0.64, 1)` | `ease` |
| Border width | `4px` | `2px` |
| Border-radius | `12px` | `8px` |
| Layer border-radius | `1px` | `4px` |

---

### 3.2 PhotoCard.vue — Tap-to-Reveal

#### Current Mobile Pain
- `:hover` fires `translateY(-2px) scale(1.02)` — sticky hover means card stays "hovered" until next tap
- `.thumbnail-img scale(1.05)` — remains scaled up on tapped cards
- `@keyframes shimmer` runs infinitely even on off-screen cards
- `backdrop-filter: blur(4px)` on `.type-badge` — moderate GPU cost

#### Proposed Mobile Design: **Bare Square with Tap Lift**

```
┌──────┐
│      │
│  🖼  │   ← Image fills card, 1:1 aspect ratio
│      │
│      │   ← On tap: subtle scale(0.97) + border accent
└──────┘
```

#### Concrete CSS Changes

```scss
// --- FILE: PhotoCard.vue, at end of <style scoped> ---

@media (hover: none) and (pointer: coarse),
       (max-width: 767px) {
  
  .photo-card {
    border-radius: 8px;                      // Smaller radius
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.10); // MD3 Level 1
    transition:
      transform 120ms ease,                  // Fast, no hover delay
      box-shadow 120ms ease;
    
    // NO HOVER — only active state via tap
    &:active {
      transform: scale(0.97);
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
    }
    
    // Sticky hover protection: if hover somehow fires, do nothing
    &:hover {
      transform: none !important;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.10) !important;
      .thumbnail-img { transform: none !important; }
    }
  }
  
  .thumbnail-img {
    transition: opacity 300ms ease;          // Fade-in only
    // Remove transform transition — no hover scale on mobile
    transform: none !important;
  }
  
  // Shimmer: only on loading + in viewport
  .shimmer-placeholder {
    // Use a static gradient instead of animated shimmer on mobile
    background: linear-gradient(90deg, 
      rgba(0, 0, 0, 0.04), 
      rgba(0, 0, 0, 0.06), 
      rgba(0, 0, 0, 0.04));
    html[data-theme="dark"] & {
      background: linear-gradient(90deg,
        rgba(255, 255, 255, 0.04),
        rgba(255, 255, 255, 0.06),
        rgba(255, 255, 255, 0.04));
    }
  }
  
  .shimmer-wave {
    display: none;                           // Remove shimmer animation entirely
  }
  
  // Type badge: reduce blur
  .type-badge {
    backdrop-filter: none;                   // Remove expensive blur
    background: rgba(0, 0, 0, 0.7);
    font-size: 9px;
    padding: 1px 5px;
    top: 6px;
    right: 6px;
  }
  
  // Dark mode mobile: NO GLOW, minimal border
  html[data-theme="dark"] & {
    background: #181818;
    border: 1px solid rgba(255, 255, 255, 0.06);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
    
    &:hover {
      border-color: rgba(255, 255, 255, 0.06); // Same as default
      transform: none !important;
    }
    
    &:active {
      border-color: rgba(255, 255, 255, 0.15); // Slightly brighter on tap
      transform: scale(0.97);
    }
    
    // Remove hover transition — too expensive
    transition: transform 120ms ease, border-color 120ms ease;
  }
}

// Even smaller screens
@media (max-width: 480px) {
  .photo-card {
    border-radius: 6px;
    box-shadow: 0 1px 1px rgba(0, 0, 0, 0.08);
  }
}
```

#### Key Properties Summary

| Property | Desktop (Keep) | Mobile (New) |
|----------|---------------|--------------|
| `border-radius` | `12px` | `8px` (480px: `6px`) |
| `:hover` transform | `translateY(-2px) scale(1.02)` | `none !important` (disabled) |
| `:active` transform | `translateY(0) scale(1.01)` | `scale(0.97)` |
| `box-shadow` | `--shadow-card-hover` | `0 1px 2px rgba(0,0,0,0.10)` |
| `.thumbnail-img:hover scale` | `scale(1.05)` | `none !important` |
| Shimmer animation | `@keyframes shimmer 1.5s infinite` | `display: none` (static gradient) |
| `backdrop-filter` (type-badge) | `blur(4px)` | `none` |
| Transition duration | `280ms` / `400ms` | `120ms` |
| Transition easing | `cubic-bezier(0.4, 0, 0.2, 1)` / `cubic-bezier(0.25, 0.46, 0.45, 0.94)` | `ease` |

---

### 3.3 AlbumScroller.vue — Snap Scroller

#### Current Mobile Pain
- At `max-width: 767px`: `scroll-snap-type: x mandatory` already set ✓
- But arrow buttons don't hide (`.album-arrows` hides ✓ already at line 397-399)
- The `album-grid-wrapper` still has `--glow-bleed-x: 12px` / `--glow-bleed-y: 12px` — should be 0
- Section title "Albums" still uses Cinzel serif + underline gradient — fine to keep
- The collapse animation `max-height: 0 → 600px` is still desktop-style; mobile should use shorter/faster collapse

#### Proposed Mobile Design: **Native Snap Scroll**

```
  Albums  📁 3
┌──────────────────────────────────────────┐
│ ┌──────┐ ┌──────┐ ┌──────┐              │
│ │ Card │ │ Card │ │ Card │  → snap       │
│ │   1  │ │   2  │ │   3  │    scroll     │
│ └──────┘ └──────┘ └──────┘              │
│                                          │
│  ← snap align start                      │
└──────────────────────────────────────────┘
```

#### Concrete CSS Changes

```scss
// --- FILE: AlbumScroller.vue — replace existing @media (max-width: 767px) block ---

@media (max-width: 767px) {
  .album-grid-wrapper {
    --glow-bleed-x: 0;                      // ZERO bleed on mobile — no glow
    --glow-bleed-y: 0;
    --glow-bleed-bottom: 0;
    padding: 0;                              // Remove all glow padding
    margin: 0;                               // Remove all glow negative margin
  }
  
  .album-grid {
    gap: 10px;                               // Reduced gap
    padding: 4px 10px 8px;                  // Padding only for content, not glow
    scroll-snap-type: x mandatory;
    scroll-behavior: smooth;
    // Friction scroll for iOS feel
    -webkit-overflow-scrolling: touch;
  }
  
  .album-grid > * {
    min-width: 140px;                        // Slightly larger than before
    max-width: 180px;
    scroll-snap-align: start;
    // Add a small animation on scroll entry
    animation: albumScrollerIn 350ms ease both;
  }
  
  @keyframes albumScrollerIn {
    from { opacity: 0; transform: translateX(12px); }
    to { opacity: 1; transform: translateX(0); }
  }
  
  // Hide arrows on mobile (already set, keep)
  .album-arrows { display: none; }
  
  // Section title: keep but smaller
  .section-title {
    margin-bottom: 6px;
    h3 {
      font-size: 14px;
    }
  }
  
  .album-count-badge {
    font-size: 11px;
    padding: 2px 8px 2px 6px;
  }
  
  // Collapse animation: faster on mobile
  .album-collapse-enter-active,
  .album-collapse-leave-active {
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  }
  
  .album-collapse-enter-to,
  .album-collapse-leave-from {
    max-height: 400px;                       // Smaller max for mobile
  }
}

@media (max-width: 480px) {
  .album-grid-wrapper {
    --glow-bleed-x: 0;
    --glow-bleed-y: 0;
    --glow-bleed-bottom: 0;
    padding: 0;
    margin: 0;
  }
  .album-grid { 
    gap: 8px; 
    padding: 2px 8px 6px;
  }
  .album-grid > * { 
    min-width: 120px; 
    max-width: 150px; 
  }
}
```

#### Key Properties Summary

| Property | Desktop (Keep) | Mobile (New) |
|----------|---------------|--------------|
| `--glow-bleed-x` | `50px` (768+), `12px` (480-767) | `0` |
| `--glow-bleed-y` | same | `0` |
| Grid padding | `24px 50px` | `4px 10px 8px` |
| Grid gap | `24px` | `10px` (480: `8px`) |
| Card min-width | `180px` | `140px` (480: `120px`) |
| Arrows | Visible on hover | `display: none` |
| Scroll behavior | `smooth` | `smooth` + `-webkit-overflow-scrolling: touch` |
| Collapse duration | `0.35s` | `0.2s` |
| Collapse max-height | `600px` | `400px` |

---

### 3.4 GalleryGrid.vue — Unified Mobile Layout

#### Current Mobile Pain
- Sort dropdown: `display: none` at 767px — fine, no sort on mobile
- Grid slider: `display: none` at 767px — fine
- Breadcrumb: `display: none` at 767px — fine, handled by MobileFloatingBottomBar
- Nav buttons: `width: 32px; height: 32px` at 767px — **below 44px spec**
- `.virtual-row` gap: reduced to `6px` at 767px — okay
- Bottom padding: `90px` at 767px for floating bar clearance — okay
- **Missing:** Sort/filter bottom sheet, pull-to-refresh, no touch area for 44px

#### Proposed Mobile Design

```
┌──────────────────────────────┐
│  ← [Photos · 42]  ⠇        │  ← Section header
├──────────────────────────────┤
│ ┌──┐ ┌──┐ ┌──┐             │
│ │P1│ │P2│ │P3│             │  ← 3 columns, gap 6px
│ └──┘ └──┘ └──┘             │
│ ┌──┐ ┌──┐ ┌──┐             │
│ │P4│ │P5│ │P6│             │
│ └──┘ └──┘ └──┘             │
│           ...               │
├──────────────────────────────┤
│  ← Sort by: Name ∨           │  ← Bottom sheet trigger
└──────────────────────────────┘
```

#### Concrete CSS Changes

```scss
// --- FILE: GalleryGrid.vue — modify existing @media (max-width: 767px) block ---

@media (max-width: 767px) {
  .gallery-grid {
    gap: 4px;                               // Tighter vertical gap
  }
  
  .grid-header {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: nowrap;
    padding: 8px 12px 4px;                 // More top padding for safe area
    padding-top: max(8px, env(safe-area-inset-top));
    
    // Mobile section title
    .photos-count {
      font-size: 13px;
      font-weight: 500;
    }
  }
  
  // Nav buttons: meet 44px but visually compact
  .nav-btn {
    width: 40px;                             // Visual size
    height: 40px;
    min-width: 44px;                         // Touch target (::before expansion)
    min-height: 44px;
    border-radius: 10px;
    border: none;                            // Remove border on mobile
    background: transparent;
    color: var(--text-color);
    
    &:active {
      background: rgba(0, 0, 0, 0.06);      // Subtle tap feedback
      transform: scale(0.95);
    }
    
    // No glow hover on mobile
    &:hover {
      border: none;
      box-shadow: none;
      background: transparent;
      transform: none;
    }
  }
  
  // Open-folder button: hidden (already set)
  .nav-btn.open-folder { display: none; }
  
  // Sort: hidden as dropdown (already set)
  .sort-dropdown { display: none; }
  
  // SORT BOTTOM SHEET (NEW)
  .mobile-sort-trigger {
    display: flex;                           // Show on mobile
    align-items: center;
    justify-content: flex-end;
    padding: 8px 12px;
    font-size: 12px;
    color: var(--muted-text);
    cursor: pointer;
    // Expand touch target
    &::before {
      content: '';
      position: absolute;
      inset: -8px;
    }
    
    &:active {
      color: var(--primary-color);
    }
  }
  
  // Grid slider: hidden (already set)
  .grid-slider { display: none; }
  
  // Virtual row: tighter gap
  .virtual-row {
    gap: 4px;                                // Even tighter than 6px
    padding: 0 2px;                          // Minimal side padding
  }
  
  // Scroller: remove right padding (narrow screen)
  .scroller {
    padding-right: 0;
    padding-left: 0;
  }
  
  // Breadcrumb: hidden (already set)
  .breadcrumb-wrap { display: none; }
  
  // Nav group: hidden on mobile (handled by bottom bar)
  .nav-group { display: none; }
  
  // Section title: mobile version
  .section-title {
    margin-bottom: 4px;
    padding: 0 12px;
    h3 { font-size: 14px; }
    span { font-size: 11px; }
  }
  
  // Albums section: tighter
  .albums-section { margin-bottom: 4px; }
  
  // Footer: more bottom space for bottom nav
  .scroller-footer {
    padding-top: 4px;
    padding-bottom: 120px;                   // More space for bottom nav bar
  }
  
  // Error banner: compact on mobile
  .error-banner {
    margin: 4px 8px;
    padding: 8px 10px;
    font-size: 12px;
  }
}

// Dark mode mobile: no glow on anything
@media (pointer: coarse) and (max-width: 767px) {
  html[data-theme="dark"] .nav-btn:not(:disabled) {
    &:hover {
      box-shadow: none;
      background: transparent;
    }
    &:active {
      background: rgba(255, 255, 255, 0.08);
    }
  }
}
```

#### Key Properties Summary

| Property | Desktop (Keep) | Mobile (New) |
|----------|---------------|--------------|
| Grid gap | `20px` | `4px` |
| Row gap | `20px` | `4px` |
| Row padding | `0 8px` | `0 2px` |
| Nav button size | `40px` | `40px` (visual) / `44px` (touch) |
| Sort UI | Dropdown | Bottom sheet (NEW) |
| Footer padding-bottom | `40px` | `120px` |
| Error banner padding | `10px 12px` | `8px 10px` |
| Section title font | `16px` | `14px` |

---

### 3.5 GlowContainer.vue — Disabled on Mobile

#### Current Mobile Pain
- Even with `bleed=16` on mobile, the component still renders `padding` + negative `margin` + `overflow: visible`
- This can cause horizontal scroll on narrow viewports
- The `disabled` prop exists but is not used by any mobile code path

#### Proposed Change

In `GalleryGrid.vue` template, pass `disabled` when mobile:

```vue
<!-- Current -->
<GlowContainer :bleed="props.isMobile ? 16 : 50">

<!-- Proposed -->
<GlowContainer :bleed="0" :disabled="props.isMobile">
```

Or simpler: make `GlowContainer` auto-disable based on `useDevice`:

```vue
<!-- In GlowContainer.vue script -->
import { useDevice } from '../composables/useDevice'
const { isMobile } = useDevice()

const containerStyle = computed(() => {
  if (props.disabled || isMobile.value) return {}
  // ... rest of style logic
})
```

#### Concrete CSS Changes

```scss
// GlowContainer.vue already has .glow-disabled class:
// .glow-disabled { padding: 0 !important; margin: 0 !important; }

// Ensure it also doesn't cause overflow
.glow-disabled {
  overflow: visible;          // Keep visible (no overflow:hidden)
  pointer-events: auto;       // Re-enable pointer events
}
```

---

### 3.6 MobileHeader.vue — Redefined

#### Current Issues
- `mh-btn` is 38px — below 44px spec (`min-width: auto` excluded in `main.scss` line 512-518)
- Glassmorphism `backdrop-filter: blur()` used — acceptable (only 1 instance)
- Content behind header gets clipped by `position: fixed`

#### Changes Required

```scss
.mh-btn {
  width: 40px;                  // Visual 40px
  height: 40px;
  min-width: 44px;              // Touch target expansion
  min-height: 44px;
  // Remove ::before approach — just use min-width/min-height on the button itself
}

// Remove exclusion in main.scss for .hamburger-btn, .settings-btn
// Currently at line 437-443:
//   .theme-toggle, .search-box, .hamburger-btn, .settings-btn { min-width: auto; min-height: auto; }
// Change to: only exclude .search-box and .theme-toggle
@media (pointer: coarse) {
  .theme-toggle, .search-box {
    min-width: auto;
    min-height: auto;
  }
  // .hamburger-btn and .settings-btn get 44px minimum
}
```

---

### 3.7 MobileFloatingBottomBar.vue — Evolution to Bottom Nav

#### Current Issues
- `mbb-btn` is 36px — below 44px spec
- Floating pill style looks like a prototype, not production
- No label on buttons — unclear navigation

#### Changes Required

```scss
.mbb-btn {
  width: 40px;                  // Visual
  height: 40px;
  min-width: 44px;
  min-height: 44px;
}
```

**But the bigger architectural change** (Phase 3 in original proposal): integrate `BottomNavigationBar.vue` and replace this floating bar + hamburger sidebar.

---

### 3.8 BottomNavigationBar.vue — Integration Spec

The file exists at `frontend/src/components/BottomNavigationBar.vue`. It has MD3-style 4-tab layout. Currently **not integrated** into `App.vue`.

#### Integration Requirements

1. **App.vue**: Add `BottomNavigationBar` as a sibling of `<router-view>` / main content
2. **Visibility**: Show only on mobile (`v-if="isMobile"`)
3. **Tabs**: Photos, Albums, Search, More
4. **Tab 1 (Photos)**: Same as current grid view
5. **Tab 2 (Albums)**: Extract sidebar content → dedicated `AlbumsTabView.vue`
6. **Tab 3 (Search)**: Expand search input (reuse MobileHeader search)
7. **Tab 4 (More)**: Settings, theme toggle, about

#### CSS for Bottom Nav

```scss
// Minimal, flat, no glow
.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 90;
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 6px 0;
  padding-bottom: max(6px, env(safe-area-inset-bottom, 0px));
  background: color-mix(in srgb, var(--surface-color) 92%, transparent);
  border-top: 1px solid var(--border-color);
  
  .nav-tab {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    min-width: 44px;
    min-height: 44px;
    background: transparent;
    border: none;
    color: var(--muted-text);
    font-size: 10px;
    cursor: pointer;
    transition: color 150ms ease;
    padding: 4px 12px;
    
    &.active {
      color: var(--primary-color);
    }
    
    &:active {
      opacity: 0.7;
    }
  }
}
```

---

## 4. Mobile Color Palette — Pastel Dreamscape Variant

**Keep the same hex values** from `main.scss` and `tokens.css`. The palette is already well-suited for mobile (high contrast, soft pastels). Do NOT create separate mobile color tokens.

| Token | Hex (Light) | Hex (Dark) | Mobile Notes |
|-------|-------------|-------------|--------------|
| `--bg-color` | `#f5eee6` | `#080808` | Keep — warm cream / true black |
| `--text-color` | `#143d60` | `#eaeaea` | Keep — readable on mobile |
| `--primary-color` | `#ff6b35` | `#d6a15d` | Keep — accent for active states |
| `--surface-color` | `#ffffff` | `#11100f` | Keep — card backgrounds |
| `--neon-color` | `#ff6b35` | `#d6a15d` | Keep — title color on dark mobile (no glow) |
| `--muted-text` | `#4a6587` | `#b3b3b3` | Keep — secondary labels |

### The only change: How colors are APPLIED

| Context | Desktop | Mobile |
|---------|---------|--------|
| Card border (dark mode) | Glow shadow `0 0 50px var(--glow-color-25)` | `1px solid rgba(255, 255, 255, 0.15)` (no glow) |
| Card shadow | `--shadow-card-level4` (deep) | `0 1px 2px rgba(0,0,0,0.10)` (shallow) |
| Active state feedback | Box-shadow + transform | `background: rgba(0,0,0,0.06)` (simple tint) |
| Title accent | `drop-shadow(0 0 12px rgba(214,161,93,0.5))` | `color: var(--neon-color)` (flat color only) |
| Section underline | Gradient + glow animation | `1px solid var(--primary-color)` (static line) |

---

## 5. Mobile Animation System — Spring & Flat

### 5.1 No Elastic Bounces on Mobile

The existing elastic curve `cubic-bezier(0.34, 1.56, 0.64, 1)` is completely replaced on mobile with:

```scss
// MD3 Standard easing (deceleration)
--mobile-ease-standard: cubic-bezier(0.4, 0, 0.2, 1);

// MD3 Accelerate easing (for exit animations)
--mobile-ease-accelerate: cubic-bezier(0.4, 0, 1, 1);

// Fast tap feedback
--mobile-ease-tap: cubic-bezier(0.2, 0, 0, 1);
```

### 5.2 Animation Inventory

| Animation | Where | Desktop | Mobile | Mobile Timing |
|-----------|-------|---------|--------|---------------|
| Card mount | AlbumCard / PhotoCard | `fadeSlideIn 260ms ease` | Same animation, faster | `200ms ease` |
| Card tap | AlbumCard | `:hover 280ms` → `:active 150ms` | `:active scale(0.97)` | `120ms ease` |
| Card press | PhotoCard | `280ms` elastic | `:active scale(0.97)` | `120ms ease` |
| Scroll snap | AlbumScroller | N/A (no snap on desktop) | `scroll-snap-type: x mandatory` | CSS native |
| Sheet open | LightboxMobileSheet | (desktop uses panel) | Spring `cubic-bezier(0.32, 0.72, 0, 1)` | `350ms` |
| Sheet close | LightboxMobileSheet | (desktop uses panel) | MD3 Accelerate | `200ms` |
| Collapse albums | AlbumScroller | `0.35s` | `0.2s` | `200ms` |
| Shimmer | PhotoCard | Infinite keyframe | Static gradient | No animation |
| Brand title | main.scss | `dark-title-shimmer 4s linear infinite` | No animation | Removed on mobile |
| Pull-to-refresh | GalleryGrid (future) | N/A | Spring `translateY` | `300ms` |
| Fade-slide row | GalleryGrid | `fadeSlideIn 260ms ease` | `200ms ease`, faster | `200ms` |

### 5.3 `prefers-reduced-motion` Additions

Add to ALL mobile overrides:

```scss
@media (prefers-reduced-motion: reduce) {
  .album-card:active,
  .photo-card:active {
    transform: none !important;
    transition: none !important;
  }
  .album-grid > * {
    animation: none !important;
  }
}
```

---

## 6. CSS Architecture Changes

### 6.1 New File: `_mobile-overrides.scss`

```scss
// ============================================
// _mobile-overrides.scss — Global Mobile Resets
// ============================================
// Imported once in main.scss via @use

// 1. GLOBAL: Kill all hover effects on touch devices
@media (hover: none) and (pointer: coarse) {
  * {
    &:hover {
      animation: none !important;
      transform: none !important;
      // Exceptions: allow transform on .album-grid > * (mount animation)
      // and :active states
    }
  }
}

// 2. GLOBAL: Disable all glow CSS variables on mobile
@media (pointer: coarse) and (max-width: 767px) {
  :root[data-theme="dark"] {
    --glow-card-hover: none;
    --glow-card-hover-front: none;
    --glow-card-hover-back: none;
    --glow-card-active: none;
    --glow-color: transparent;
  }
}

// 3. GLOBAL: Reduce all shadow variables on mobile
@media (max-width: 767px) {
  :root {
    --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.10);
    --shadow-card-hover: 0 1px 2px rgba(0, 0, 0, 0.10);
    --shadow-card-level2: 0 1px 2px rgba(0, 0, 0, 0.10);
    --shadow-card-level4: 0 1px 2px rgba(0, 0, 0, 0.10);
    
    // Also kill the radial gradient on body background
    --bg-gradient-opacity: 0%; // or remove the background-image in main.scss
  }
  :root[data-theme="dark"] {
    --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.3);
    --shadow-card-hover: 0 1px 2px rgba(0, 0, 0, 0.3);
    --shadow-card-level2: 0 1px 2px rgba(0, 0, 0, 0.3);
    --shadow-card-level4: 0 1px 2px rgba(0, 0, 0, 0.3);
  }
}

// 4. GLOBAL: Touch target expansion (44px minimum)
@media (pointer: coarse) {
  button, [role="button"], a {
    min-height: 44px;
    min-width: 44px;
  }
  // Exceptions
  .theme-toggle, .search-box {
    min-width: auto;
    min-height: auto;
  }
}

// 5. GLOBAL: Disable body gradient on mobile (GPU savings)
@media (max-width: 767px) {
  body {
    background-image: none;
  }
}

// 6. GLOBAL: Remove all brand-title animations on mobile
@media (max-width: 767px) {
  .brand-title {
    // !important needed to override main.scss specificity
    animation: none !important;
    filter: none !important;
    background: none !important;
    -webkit-text-fill-color: var(--neon-color) !important;
    color: var(--neon-color) !important;
  }
  .brand-title::after {
    animation: none !important;
    box-shadow: none !important;
  }
  .brand-icon {
    animation: none !important;
    filter: none !important;
    box-shadow: none !important;
  }
}
```

### 6.2 Modified File: `tokens.css`

Add a data-attribute toggle for mobile glow:

```css
/* At the bottom of tokens.css */
@media (hover: none) and (pointer: coarse) {
  :root {
    --glow-card-hover: none;
    --glow-card-hover-front: none;
    --glow-card-hover-back: none;
    --glow-card-active: none;
  }
}
```

Or better: just handle it in `_mobile-overrides.scss` as shown above.

### 6.3 Modified File: `main.scss`

- Remove `body { background-image: radial-gradient(...) }` on mobile (already proposed above)
- Add `@use './mobile-overrides'` at top
- Move the `@media (pointer: coarse)` block (lines 425-519) into `_mobile-overrides.scss` to keep all mobile-related resets in one file
- Remove the exclusion of `.hamburger-btn` and `.settings-btn` from the touch-target rules

---

## 7. Touch Gesture Specs

### 7.1 Swipe to Dismiss (Lightbox)

Already planned in Phase 4. Implementation note:

```typescript
// In Lightbox.vue or a useSwipeDismiss composable
const onTouchStart = (e: TouchEvent) => { /* record startX, startY */ }
const onTouchMove = (e: TouchEvent) => {
  const deltaX = e.touches[0].clientX - startX
  // Apply transform: translateX(deltaX) with opacity fade
  // If deltaX > threshold (80px), trigger dismiss
}
const onTouchEnd = (e: TouchEvent) => {
  // Spring back (snap) or complete dismiss
  // Use spring animation: cubic-bezier(0.32, 0.72, 0, 1)
}
```

### 7.2 Pull-to-Refresh

```typescript
// In GalleryGrid.vue
const onTouchStart = (e: TouchEvent) => {
  if (scroller.scrollTop <= 0) {
    // Start tracking pull
    pullStartY = e.touches[0].clientY
    isPulling = true
  }
}
const onTouchMove = (e: TouchEvent) => {
  if (!isPulling) return
  const delta = e.touches[0].clientY - pullStartY
  // Clamp: max 80px
  // Apply transform to grid content
}
const onTouchEnd = () => {
  if (pullDistance > 60) {
    // Refresh
    galleryStore.refresh()
    // Spring back animation
  } else {
    // Snap back
  }
}
```

### 7.3 Tap → Scale Animation (Touch Ripple Alternative)

Instead of Material ripple effect (complex, expensive), use a simple scale-down:

```scss
// Global touch feedback
@media (pointer: coarse) {
  .album-card:active,
  .photo-card:active,
  .nav-btn:active,
  .mbb-btn:active,
  .mh-btn:active {
    transform: scale(0.95);
    transition: transform 100ms ease;
  }
}
```

---

## 8. Performance Checklist

### Must-Fix on Mobile

| # | Item | Impact | File |
|---|------|--------|------|
| 1 | `perspective: 1000px` → `none` | Frees GPU layer per card | AlbumCard.vue |
| 2 | `transform-style: preserve-3d` → `flat` | Frees GPU layer | AlbumCard.vue |
| 3 | 6-layer `box-shadow` → `none` | Eliminates 6x paint passes per card | tokens.css / _mobile-overrides.scss |
| 4 | `@keyframes shimmer` → static gradient | Eliminates infinite repaint | PhotoCard.vue |
| 5 | `backdrop-filter: blur(4px)` → `none` (on type-badge) | Saves GPU composition | PhotoCard.vue |
| 6 | `body { background-image: radial-gradient(...) }` → `none` | Saves background paint | main.scss / _mobile-overrides.scss |
| 7 | `content-visibility: auto` on `.virtual-row > *` | Skips layout/paint off-screen | GalleryGrid.vue |
| 8 | 3D `rotate(-12deg/8deg)` → flat position | Eliminates expensive composite | AlbumCard.vue |
| 9 | `::before` touch target expansion | Better tap accuracy, fewer mis-clicks | _mobile-overrides.scss |
| 10 | Remove glow bleed padding/margin from GlowContainer | Prevents horizontal scroll | GlowContainer.vue |

### Nice-to-Have

| # | Item | Impact | File |
|---|------|--------|------|
| 11 | Limit brand-title animations to desktop only | Minor CSS parse savings | main.scss |
| 12 | Remove `drop-shadow()` filters from brand elements | Minor GPU savings | main.scss |
| 13 | Use `will-change: transform` on AlbumScroller items | Optimizes scroll compositing | AlbumScroller.vue |
| 14 | `-webkit-overflow-scrolling: touch` on scrollers | Enables iOS friction scroll | AlbumScroller.vue, GalleryGrid.vue |

---

## 9. Implementation Priority & Effort

### Phase 1 — Zero-Touch Resets (CSS only, ~2 hours)

| # | File | Change | Approx Time |
|---|------|--------|-------------|
| 1 | Create `_mobile-overrides.scss` | Global hover/glow/touch resets | 45min |
| 2 | `main.scss` | Import overrides, remove body gradient on mobile | 15min |
| 3 | `AlbumCard.vue` | Add mobile media query block — kill 3D, glow, hover | 30min |
| 4 | `PhotoCard.vue` | Add mobile media query block — kill hover, shimmer | 20min |
| 5 | `AlbumScroller.vue` | Replace mobile media query — zero glow bleed, snap refine | 15min |
| 6 | `GalleryGrid.vue` | Fix mobile nav-btn touch targets, footer padding | 15min |
| 7 | `GlowContainer.vue` | Auto-disable on mobile | 10min |

### Phase 2 — UX Enhancement (~4-6 hours)

| # | File | Change | Approx Time |
|---|------|--------|-------------|
| 8 | `BottomNavigationBar.vue` | Integrate into App.vue, replace hamburger | 2h |
| 9 | `AlbumsTabView.vue` (NEW) | Extract albums sidebar for mobile tab | 1.5h |
| 10 | `GalleryGrid.vue` | Add sort bottom sheet (reuse LightboxMobileSheet) | 1.5h |
| 11 | `main.scss` | Clean up excluded touch-target classes | 30min |

### Phase 3 — Polish (~4-6 hours)

| # | File | Change | Approx Time |
|---|------|--------|-------------|
| 12 | `LightboxMobileSheet.vue` | Spring animation on open/close | 1h |
| 13 | `GalleryGrid.vue` | Pull-to-refresh gesture | 2h |
| 14 | `Lightbox.vue` | Swipe to dismiss gesture | 2h |
| 15 | All components | `prefers-reduced-motion` coverage audit | 1h |

---

## 10. CSS Code Snippets — Ready to Copy

### 10.1 Complete AlbumCard Mobile Override

```scss
// Paste at end of AlbumCard.vue <style scoped>, before closing </style>

// ── MOBILE: Complete reset, no 3D, no glow, no hover ──
@media (hover: none) and (pointer: coarse),
       (max-width: 767px) {

  .album-card {
    perspective: none;
    transform-style: flat;
    padding-top: 0;
    padding-left: 0;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.10);
    border-radius: 8px;
    transition: transform 150ms ease, box-shadow 150ms ease;

    &:hover {
      transform: none !important;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.10) !important;
    }

    &:active {
      transform: scale(0.97);
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
    }
  }

  .album-cover-diagonal {
    height: 130px;
    transform-style: flat;
    transition: none;
    transform: none !important;
    animation: albumCardIn 300ms ease both;
  }

  @keyframes albumCardIn {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: none; }
  }

  .album-layer {
    width: 65%;
    height: 70%;
    transition: none;
    border-width: 2px;
    border-radius: 4px;
  }

  .album-layer-back {
    top: 6px;
    left: 6px;
    transform: none;
    opacity: 0.85;
    z-index: 1;
    box-shadow: none;
    border-color: color-mix(in srgb, var(--primary-color) 20%, transparent);
  }

  .album-layer-front {
    top: 0;
    right: unset;
    left: 20px;
    transform: none;
    z-index: 10;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
  }

  .album-info {
    margin-top: 6px;
    padding: 0 6px 6px;
    .album-name { font-size: 13px; font-weight: 500; }
    .album-meta { font-size: 10px; gap: 3px; }
  }

  // Dark mode mobile — NO GLOW
  html[data-theme="dark"] & {
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
    .album-layer-front {
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
      border-color: rgba(255, 255, 255, 0.15);
    }
    .album-layer-back {
      border-color: rgba(255, 255, 255, 0.08);
    }
    .album-name { color: var(--neon-color); }
    &:hover, &:active {
      box-shadow: none !important;
      .album-layer-front { box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3) !important; }
    }
  }

  @media (max-width: 480px) {
    .album-cover-diagonal { height: 90px; }
    .album-layer { width: 60%; height: 65%; }
    .album-layer-front { left: 16px; }
    .album-name { font-size: 12px; }
    .album-meta { font-size: 9px; }
  }
}
```

### 10.2 Complete PhotoCard Mobile Override

```scss
// Paste at end of PhotoCard.vue <style scoped>

@media (hover: none) and (pointer: coarse),
       (max-width: 767px) {

  .photo-card {
    border-radius: 8px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.10);
    transition: transform 120ms ease, box-shadow 120ms ease;

    &:hover {
      transform: none !important;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.10) !important;
      .thumbnail-img { transform: none !important; }
    }

    &:active { transform: scale(0.97); box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06); }
  }

  .thumbnail-img {
    transition: opacity 300ms ease;
    transform: none !important;
  }

  .shimmer-placeholder {
    background: linear-gradient(90deg, rgba(0,0,0,0.04), rgba(0,0,0,0.06), rgba(0,0,0,0.04));
    html[data-theme="dark"] & {
      background: linear-gradient(90deg, rgba(255,255,255,0.04), rgba(255,255,255,0.06), rgba(255,255,255,0.04));
    }
  }

  .shimmer-wave { display: none; }

  .type-badge {
    backdrop-filter: none;
    background: rgba(0, 0, 0, 0.7);
    font-size: 9px;
    padding: 1px 5px;
    top: 6px; right: 6px;
  }

  html[data-theme="dark"] & {
    background: #181818;
    border: 1px solid rgba(255, 255, 255, 0.06);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
    &:hover { border-color: rgba(255, 255, 255, 0.06); transform: none !important; }
    &:active { border-color: rgba(255, 255, 255, 0.15); transform: scale(0.97); }
    transition: transform 120ms ease, border-color 120ms ease;
  }

  @media (max-width: 480px) {
    .photo-card { border-radius: 6px; box-shadow: 0 1px 1px rgba(0,0,0,0.08); }
  }
}
```

### 10.3 Complete AlbumScroller Mobile Override

```scss
// Replace the existing @media (max-width: 767px) block in AlbumScroller.vue entirely

@media (max-width: 767px) {
  .album-grid-wrapper {
    --glow-bleed-x: 0;
    --glow-bleed-y: 0;
    --glow-bleed-bottom: 0;
    padding: 0;
    margin: 0;
  }

  .album-grid {
    gap: 10px;
    padding: 4px 10px 8px;
    scroll-snap-type: x mandatory;
    scroll-behavior: smooth;
    -webkit-overflow-scrolling: touch;
  }

  .album-grid > * {
    min-width: 140px;
    max-width: 180px;
    scroll-snap-align: start;
    animation: albumScrollerIn 350ms ease both;
  }

  @keyframes albumScrollerIn {
    from { opacity: 0; transform: translateX(12px); }
    to { opacity: 1; transform: translateX(0); }
  }

  .album-arrows { display: none; }

  .section-title { margin-bottom: 6px; h3 { font-size: 14px; } }
  .album-count-badge { font-size: 11px; padding: 2px 8px 2px 6px; }

  .album-collapse-enter-active,
  .album-collapse-leave-active {
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  }
  .album-collapse-enter-to,
  .album-collapse-leave-from {
    max-height: 400px;
  }

  @media (max-width: 480px) {
    .album-grid-wrapper { --glow-bleed-x: 0; --glow-bleed-y: 0; --glow-bleed-bottom: 0; padding: 0; margin: 0; }
    .album-grid { gap: 8px; padding: 2px 8px 6px; }
    .album-grid > * { min-width: 120px; max-width: 150px; }
  }
}
```

### 10.4 `_mobile-overrides.scss` — Ready to Create

```scss
// ============================================
// _mobile-overrides.scss
// Cross-cutting mobile resets — imported once
// in main.scss via @use
// ============================================

// 1. Kill all hover effects on touch devices
@media (hover: none) and (pointer: coarse) {
  * {
    &:hover {
      animation: none !important;
      transform: none !important;
    }
  }
}

// 2. Disable all glow CSS variables on mobile
@media (pointer: coarse) and (max-width: 767px) {
  :root[data-theme="dark"] {
    --glow-card-hover: none;
    --glow-card-hover-front: none;
    --glow-card-hover-back: none;
    --glow-card-active: none;
    --glow-color: transparent;
  }
}

// 3. Reduce all shadow variables on mobile
@media (max-width: 767px) {
  :root {
    --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.10);
    --shadow-card-hover: 0 1px 2px rgba(0, 0, 0, 0.10);
    --shadow-card-level2: 0 1px 2px rgba(0, 0, 0, 0.10);
    --shadow-card-level4: 0 1px 2px rgba(0, 0, 0, 0.10);
  }
  :root[data-theme="dark"] {
    --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.3);
    --shadow-card-hover: 0 1px 2px rgba(0, 0, 0, 0.3);
    --shadow-card-level2: 0 1px 2px rgba(0, 0, 0, 0.3);
    --shadow-card-level4: 0 1px 2px rgba(0, 0, 0, 0.3);
  }

  // Remove body radial gradient (GPU savings)
  body {
    background-image: none !important;
  }

  // Kill brand animations (parsed but not visible on mobile)
  .brand-title {
    animation: none !important;
    filter: none !important;
    background: none !important;
    -webkit-text-fill-color: var(--neon-color) !important;
    color: var(--neon-color) !important;
  }
  .brand-title::after {
    animation: none !important;
    box-shadow: none !important;
  }
}

// 4. Touch target expansion (44px minimum)
@media (pointer: coarse) {
  button, [role="button"], a {
    min-height: 44px;
    min-width: 44px;
  }
  // Exceptions for visually compact controls
  .theme-toggle,
  .search-box {
    min-width: auto;
    min-height: auto;
  }
}

// 5. Reduced motion
@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; }
}
```

---

## Summary: Files to Create / Modify

| Action | File | Description |
|--------|------|-------------|
| **CREATE** | `frontend/src/styles/_mobile-overrides.scss` | Global mobile resets for hover, glow, shadows, touch targets |
| **MODIFY** | `frontend/src/styles/main.scss` | Add `@use './mobile-overrides'`, remove body gradient on mobile, fix touch-target exclusions |
| **MODIFY** | `frontend/src/styles/tokens.css` | (Optional) Add mobile `@media` block disabling glow — or rely on overrides file |
| **MODIFY** | `frontend/src/components/AlbumCard.vue` | Add mobile media query block at end of `<style scoped>` |
| **MODIFY** | `frontend/src/components/PhotoCard.vue` | Add mobile media query block at end of `<style scoped>` |
| **MODIFY** | `frontend/src/components/AlbumScroller.vue` | Replace `@media (max-width: 767px)` block with zero-glow version |
| **MODIFY** | `frontend/src/components/GalleryGrid.vue` | Fix nav-btn touch targets, footer padding, section header spacing |
| **MODIFY** | `frontend/src/components/GlowContainer.vue` | Auto-disable on mobile via `useDevice` or `isMobile` prop |

**Total estimated effort:** Phase 1 (~2h CSS only) + Phase 2 (~4-6h structural) + Phase 3 (~4-6h polish) = **~10-14 hours total**
