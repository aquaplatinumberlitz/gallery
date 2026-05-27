# Mobile UX Refactor — Final Approved Proposal

> **Date:** 2026-05-27  
> **Status:** ✅ Approved by user after Codex–OpenCode debate  
> **Scope:** 3 phases — CSS quick fixes (Phase 1), component polish (Phase 2), testing + perf (Phase 3)

---

## Architecture Decisions (Approved)

| Decision | Outcome | Source |
|---|---|---|
| Architecture | Hybrid: media queries in SFC + global `_mobile-overrides.scss` | Codex wins |
| Component splitting | No new components — keep existing SFCs | Codex wins |
| Color palette | Hex palette retained | Codex wins |
| Mobile glow | **Zero glow on mobile** (Codex wins, OpenCode conceded) | Codex wins |
| Breakpoint | `max-width: 767px` for layout; `(hover: none)` for hover independently | Codex wins |
| GlowContainer | Uses existing `disabled` prop — `:disabled="isMobile"` | Codex wins |
| PhotoCard JS guard | `matchMedia('(hover: none)')` guard on `onMouseEnter` — animated path only (Alternative B) | OpenCode influence |
| Skeleton shimmer | Add `@media (hover: none)` block to disable shimmer | OpenCode influence |
| `prefers-reduced-motion` | Global `main.scss` already sufficient — per-component not needed | OpenCode influence |
| `albumScrollerIn` animation | Add `will-change: transform, opacity` | OpenCode influence |
| Shadow opacity | Light: 0.20 / Dark: 0.50 | OpenCode influence |
| BottomNavigationBar | Cross-fade 200ms, icon scale, scroll-to-top | OpenCode influence |

---

## Phase 1 — CSS Quick Fixes (NOW)

### Files to modify:

| # | File | Changes |
|---|---|---|
| 1 | `_mobile-overrides.scss` **(NEW)** | Global hover/glow/touch resets |
| 2 | `main.scss` | Import `_mobile-overrides.scss` |
| 3 | `AlbumCard.vue` | Wrap hover in `@media (hover: hover)`, perspective:none on mobile, :active scale(0.97) |
| 4 | `PhotoCard.vue` | JS `matchMedia` guard + CSS hover wrap + mobile :active scale |
| 5 | `AlbumScroller.vue` | Zero glow bleed on mobile, always-visible arrows, `will-change` on grid items |
| 6 | `GalleryGrid.vue` | 4px gaps, 44px touch targets, 120px bottom padding, `content-visibility: auto` |
| 7 | `GlowContainer.vue` / `GalleryGrid.vue` | Change `:bleed="isMobile ? 16 : 50"` → `:disabled="isMobile"` |
| 8 | `SkeletonLoader.vue` | `@media (hover: none)` block to disable shimmer animation |
| 9 | `tokens.css` | Add CSS variable overrides for mobile glow (override by `_mobile-overrides.scss`) |

### Details:

#### 1. `_mobile-overrides.scss` — Global resets

```scss
// ============================================================
// MOBILE OVERRIDES — Global resets for touch/hover/glow
// This file is imported last in main.scss to override all vars
// ============================================================

// --- Disable glow on mobile (max-width: 767px) ---
@media (max-width: 767px) {
  :root {
    --glow-color: transparent;
    --glow-card-hover: none !important;
    --glow-card-active: none !important;
    --glow-card-hover-front: none !important;
    --glow-card-hover-back: none !important;
  }

  // Override shadow opacity: light 0.20 / dark 0.50
  :root {
    --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.20), 0 1px 3px 1px rgba(0, 0, 0, 0.10);
    --shadow-card-hover: 0 1px 3px rgba(0, 0, 0, 0.20), 0 4px 8px 3px rgba(0, 0, 0, 0.10);
    --shadow-card-level2: 0 1px 2px rgba(0, 0, 0, 0.20), 0 2px 6px 2px rgba(0, 0, 0, 0.10);
    --shadow-card-level4: 0 2px 3px rgba(0, 0, 0, 0.20), 0 6px 10px 4px rgba(0, 0, 0, 0.10);
  }

  :root[data-theme="dark"] {
    --shadow-card: 0 1px 3px 1px rgba(0, 0, 0, 0.50), 0 1px 2px rgba(0, 0, 0, 0.70);
    --shadow-card-level2: 0 2px 6px 2px rgba(0, 0, 0, 0.50), 0 1px 2px rgba(0, 0, 0, 0.70);
  }
}

// --- Kill all sticky hover on touch devices ---
@media (hover: none) {
  *:hover {
    // Reset sticky hover junk
    transform: none !important;
    box-shadow: none !important;
    border-color: var(--border-color) !important;
    background: transparent !important;
  }

  // But allow :active to work
  *:active {
    -webkit-tap-highlight-color: transparent;
  }
}

// --- Touch target expansion (pointer: coarse) ---
@media (pointer: coarse) {
  button, [role="button"], a, input, select, textarea {
    min-height: 44px;
    min-width: 44px;
  }
}
```

#### 3. AlbumCard.vue changes

- Wrap `:hover` + `perspective: 1000px` in `@media (hover: hover)`
- Mobile: `perspective: none`, flat card
- Mobile: `:active { scale(0.97) }`, 2px border, zero glow
- Dark mode glow removed on mobile

#### 4. PhotoCard.vue changes

- **CSS**: Wrap `:hover` scale in `@media (hover: hover)`
- **JS**: `onMouseEnter` — add guard `if (window.matchMedia('(hover: none)').matches) return;`
- Mobile: `:active { scale(0.97) }`

#### 5. AlbumScroller.vue changes

- Zero glow bleed on mobile (glow-disabled approach via parent)
- Simplify arrows — always visible on mobile
- Add `will-change: transform, opacity` to `album-grid > *`

#### 6. GalleryGrid.vue changes

- 4px gaps on mobile (already 6px, reduce to 4px)
- 44px touch targets for nav buttons on mobile
- 120px bottom padding (currently 90px, increase to 120px)
- `content-visibility: auto` on `.virtual-row`

#### 7. GalleryGrid.vue GlowContainer usage

- Change `:bleed="props.isMobile ? 16 : 50"` → `:disabled="props.isMobile"`
- Same for line 411 fallback

#### 8. SkeletonLoader.vue changes

- Add `@media (hover: none)` block to disable shimmer animation
- Use static gradient instead of animated wave

#### 9. tokens.css changes

- No structural changes — `_mobile-overrides.scss` will override glow CSS variables globally

---

## Phase 2 — Component Polish (Next)

| Component | Changes |
|---|---|
| BottomNavigationBar | Cross-fade 200ms, icon scale on active, scroll-to-top |
| MobileHeader | Spacing, touch targets, animation tweaks |
| LightboxMobileSheet | Swipe gesture polish, close button sizing |
| Breadcrumb | Tap target 44px on pointer:coarse |
| EmptyState | Reduce padding on mobile, center alignment |

---

## Phase 3 — Testing + Perf (Final)

- `npm run build` — ensure clean build
- Lighthouse mobile audit (target >85 perf)
- DeviceLab testing (iPhone SE, Pixel 7, iPad Mini)
- Touch responsiveness validation
- Reduced motion verification
- Keyboard nav on desktop regression check
