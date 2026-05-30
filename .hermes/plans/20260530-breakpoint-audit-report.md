# Breakpoint Audit Report — 2026-05-30

## 1. Centralized Breakpoint Definitions

### `useDevice.ts` (JS/TS Breakpoint Constants)
**File:** `/home/ubuntu/gallery-repo/frontend/src/composables/useDevice.ts`

| Constant | Value | Meaning |
|---|---|---|
| `BREAKPOINTS.compact` | 480 | Below this = compact (tiny phone) |
| `BREAKPOINTS.phone` | 768 | Below this = phone (480–767) |
| `BREAKPOINTS.tablet` | 1200 | Below this = tablet (768–1199) |
| `BREAKPOINTS.desktop` | Infinity | 1200+ |

**Derived device types:**
- `isMobile` = `isCompact || isPhone` → width < 768
- `isLargeScreen` = `isTablet || isDesktop` → width >= 768
- `isTablet` = 480 <= width < 1200 (BUG: overlaps with phone range; see §7)

**Breakpoint boundaries (derived from computed breakpoint logic):**
| Range | Type |
|---|---|
| 0 – 479 | compact |
| 480 – 767 | phone |
| 768 – 1199 | tablet |
| 1200+ | desktop |

### `main.scss` (CSS Comment Documentation)
**File:** `/home/ubuntu/gallery-repo/frontend/src/styles/main.scss` (lines 426–433)

```
Desktop:  >1024px
Tablet:   768-1024px
Phone:    <=767px
Small:    <480px (390px iPhone viewport)
```

**MISMATCH:** The CSS documentation says tablet goes up to 1024px, but `useDevice.ts` says tablet goes up to 1199px (since desktop starts at 1200). This is a **documentation vs. implementation discrepancy**.

---

## 2. All CSS @media Breakpoints Used in the Codebase

### Breakpoint: `max-width: 767px` (Phone / Mobile)
Used in **15 locations** across 7 files:

| File | Lines | Usage |
|---|---|---|
| `src/styles/tokens.css` | 231 | Mobile override: zero glow vars |
| `src/styles/_mobile-overrides.scss` | 8 | Mobile override: glow + shadow reduction |
| `src/styles/main.scss` | 445–449 | `.hide-phone`, `.show-phone`, `.hide-desktop` utilities |
| `src/App.vue` | 448 | Sidebar → fixed overlay, grid → 1fr, content padding |
| `src/components/AppHeader.vue` | 483 | Hamburger always visible, mobile search-bar layout |
| `src/components/GalleryGrid.vue` | 1138 | Grid gap 6px, hidden grid-header, 44px nav-btn, 120px bottom padding |
| `src/components/AlbumScroller.vue` | 322 | Zero glow bleed, scroll-snap, always-visible arrows, min-width 130px |
| `src/components/AlbumsTabView.vue` | 105 | Zero padding, 10px gap |

### Breakpoint: `max-width: 1024px` (Tablet and below)
Used in **5 locations** across 5 files:

| File | Lines | Usage |
|---|---|---|
| `src/styles/main.scss` | 440–443 | `.hide-tablet`, `.show-tablet` utilities |
| `src/App.vue` | 405 | Grid layout columns 240px 1fr, content padding, edge-toggle positioning |
| `src/components/AppHeader.vue` | 454 | Brand icon 48px, title clamp, search box min-width 180px |
| `src/components/GalleryGrid.vue` | 1127 | Grid header gap 8px, breadcrumb max-width 300px |
| `src/components/MobileHeader.vue` | 578 | Search focus input max-width 520px (combined with min: 481px) |

### Breakpoint: `min-width: 768px` + `max-width: 1024px` (Tablet-range lock)
Used in **2 locations**:

| File | Lines | Usage |
|---|---|---|
| `src/App.vue` | 428 | Sidebar 240px persistent, hamburger always visible, edge-toggle hidden |
| `src/components/AppHeader.vue` | 471 | Hamburger inline-flex, brand-hero scale(0.8) |

### Breakpoint: `max-width: 480px` (Compact / Small phone)
Used in **9 locations** across 6 files:

| File | Lines | Usage |
|---|---|---|
| `src/styles/_lightbox-mobile.scss` | 246 | Sheet height 40dvh, tighter spacing |
| `src/components/GalleryGrid.vue` | 1234 | Grid header gap 4px, nav-btn 30px |
| `src/components/AlbumScroller.vue` | 351 | Album card min-width 110px, gap 6px |
| `src/components/AlbumsTabView.vue` | 143 | Grid gap 8px |
| `src/components/SidebarHeader.vue` | 170 | Reduced sidebar padding, input height 36px |
| `src/components/MobileFloatingBottomBar.vue` | 134 | Pill size reduction, icon 22px |
| `src/components/BottomNavigationBar.vue` | 108 | Labels hidden (see below for 360px) |

### Breakpoint: `max-width: 360px` (Very small phone)
Used in **2 locations**:

| File | Lines | Usage |
|---|---|---|
| `src/components/BottomNavigationBar.vue` | 108 | `.nav-label { display: none }` |
| `src/components/AlbumsTabView.vue` | 150 | Album cards use `calc((100vw - 24px) / 2)` |

### Breakpoint: `min-width: 900px` (Tablet landscape)
Used in **1 location**:

| File | Lines | Usage |
|---|---|---|
| `src/styles/_lightbox-tablet.scss` | 264 | Tablet panel margins 0 32px |

### Breakpoint: `max-height: 800px` (Short viewport)
Used in **1 location**:

| File | Lines | Usage |
|---|---|---|
| `src/styles/_lightbox-tablet.scss` | 271 | Tablet panel max-height 55vh, min-height 22vh |

### Breakpoint: `min-width: 481px` + `max-width: 1024px` (Tablet-specific, 481+)
Used in **1 location**:

| File | Lines | Usage |
|---|---|---|
| `src/components/MobileHeader.vue` | 578 | Search focus input max-width 520px |

---

## 3. JavaScript `matchMedia` / `innerWidth` Usage

### `useDevice.ts` — Singleton resize listener
- **Line 14:** Initializes `currentWidth` from `window.innerWidth`
- **Line 37:** Updates `currentWidth.value = window.innerWidth` on resize
- **Lines 19–23:** Computes breakpoint from `currentWidth` against `BREAKPOINTS` constants
- **Line 38:** Adds `resize` listener with `{ passive: true }`

### `useColumnResize.ts` — Grid column count logic
- **Line 9–16 (`getDefaultCols()`):** Uses `window.innerWidth` with hardcoded numeric values:
  - `w >= 1200` → 4 columns (uses `BREAKPOINTS.tablet`)
  - `w >= 768` → 3 columns (uses `BREAKPOINTS.phone`)
  - `w >= 460` → 3 columns (hardcoded — NOT a BREAKPOINTS constant)
  - `w >= 480` → 2 columns (uses `BREAKPOINTS.compact`)
  - `< 480` → 2 columns
- **Note:** The hardcoded `460` is a **0-width gap** between 460 and 480 (BREAKPOINTS.compact). If width is 465–479, `getDefaultCols()` returns 3, but the `useDevice()` breakpoint considers it `phone` (480–767). This is intentional (iPhone Plus/Pro Max), but creates a subtle inconsistency.

### `AlbumScroller.vue` — Duplicate mobile detection
- **Line 42:** `const isMobile = ref(false)` — local ref, not from `useDevice`
- **Line 69:** `window.matchMedia("(max-width: 767px)").matches` — hardcoded string, NOT using `BREAKPOINTS` constant
- **Lines 124–132:** Adds/removes its own `resize` event listener (duplicate of `useDevice`)

### `PhotoCard.vue` — Touch device guard
- **Line 36:** `window.matchMedia('(hover: none)').matches` — guards against sticky hover on touch devices

### `App.vue` — Theme detection
- **Line 50:** `window.matchMedia("(prefers-color-scheme: dark)").matches` — system theme
- **Line 105:** Same call in `onMounted`
- **Line 110:** Same call in catch block
- **Line 118:** `window.matchMedia("(prefers-color-scheme: dark)")` — creates MediaQueryList for listener

---

## 4. Resize Listeners / Observers

| Component | Mechanism | What it tracks |
|---|---|---|
| `useDevice.ts` | `window.addEventListener('resize')` | `window.innerWidth` for breakpoint |
| `useColumnResize.ts` | `new ResizeObserver()` on grid element | Grid container width for column count |
| `AlbumScroller.vue` | `window.addEventListener('resize')` + `new ResizeObserver()` | Overflow arrows + mobile detection |
| `App.vue` | `window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change')` | Theme change |

---

## 5. Media Feature Queries (Non-Width)

| Query | Files | Purpose |
|---|---|---|
| `(hover: none)` | `_mobile-overrides.scss` (line 37), `PhotoCard.vue` (line 36), `main.scss` (—) | Kill sticky hover on touch devices |
| `(hover: hover) and (pointer: fine)` | `_mobile-overrides.scss` (line 87) | Desktop-specific hover (reserved) |
| `(pointer: coarse)` | `_mobile-overrides.scss` (line 92), `main.scss` (line 394) | 44px touch targets |
| `(prefers-color-scheme: dark)` | `App.vue` (multiple) | System dark mode detection |
| `(prefers-reduced-motion: reduce)` | `_lightbox-shared.scss`, `_lightbox-mobile.scss`, `GalleryGrid.vue`, `main.scss` | Reduced motion |
| `(prefers-contrast: high)` | `_lightbox-shared.scss`, `main.scss` | High contrast mode |

---

## 6. Component-Level Device Logic

### Components using `useDevice()`:
| Component | Props/Computed Used | Behavior |
|---|---|---|
| `App.vue` | `isMobile` | Close sidebar on Escape, pass to GalleryGrid |
| `Lightbox.vue` | `isDesktop`, `isTablet`, `isMobile` | Three distinct rendering templates for lightbox |
| `GalleryGrid.vue` | `props.isMobile` (passed from App) | RecycleScroller vs native scroll, GlowContainer disabled |

### Components with standalone mobile logic:
| Component | Mechanism | Breakpoint |
|---|---|---|
| `AlbumScroller.vue` | `window.matchMedia("max-width: 767px")` | 767px (not using BREAKPOINTS) |
| `GlowContainer.vue` | `:disabled="props.isMobile"` | Uses `isMobile` from device detection |

---

## 7. Issues & Inconsistencies

### ISSUE 1: CSS Documentation vs. JS Implementation (MISMATCH)
- **CSS docs** (`main.scss` line 429–432): Tablet = 768–1024px, Desktop = >1024px
- **JS implementation** (`useDevice.ts`): Tablet = 768–1199px, Desktop = 1200+
- **Impact:** Media queries in `.vue` scoped styles use 1024px as the tablet→desktop boundary, while the JS composable treats 1024–1199px as "tablet." A user at 1100px width would get `isTablet=true` from JS but tablet CSS rules from `@media (max-width: 1024px)`. This creates a **gap zone (1025–1199px)** where JS says "tablet" but CSS applies no tablet-specific rules.

### ISSUE 2: Hardcoded value `460` in `useColumnResize.ts`
- Line 14: `if (w >= 460) return 3` — not derived from `BREAKPOINTS`
- Creates division between 460 (3 cols) and 480 (2 cols) that is not documented
- No comment explaining why 460 was chosen vs. the compact breakpoint of 480

### ISSUE 3: Duplicate mobile detection in `AlbumScroller.vue`
- `AlbumScroller.vue` creates its own `isMobile` ref with `window.matchMedia("(max-width: 767px)")`
- Ignores `useDevice().isMobile` which uses `BREAKPOINTS.phone` (768)
- The hardcoded string `"(max-width: 767px)"` is not synchronized with the BREAKPOINTS constant
- Adds its own resize listener even though `useDevice()` already tracks resize

### ISSUE 4: `isTablet` overlap with `phone` in `useDevice.ts`
- `isTablet = breakpoint === 'tablet'` means width is between 480 and 1199
- But `isPhone` is between 480 and 767
- So `isTablet` actually covers 480–1199, which includes the phone range (480–767)
- This is technically correct (the computed returns the first match), but the naming is misleading — values at 500px width are classified as "phone" not "tablet"

### ISSUE 5: Three different "tablet" definitions
1. **JS (`useDevice.ts`):** tablet = 768–1199px
2. **CSS docs (`main.scss`):** tablet = 768–1024px
3. **Component CSS (`@media` queries):** uses 1024px as the boundary, creating a gap of 1025–1199px of undefined behavior

### ISSUE 6: Missing breakpoints `min-width: 768px` without upper bound
- Several components use `@media (min-width: 768px)` only in pair with `max-width: 1024px`
- No component uses `@media (min-width: 1200px)` or `@media (min-width: 1025px)` for desktop-specific rules — desktop is the default (no media query wrapping)

### ISSUE 7: No CSS custom properties for breakpoints
- All breakpoint values in CSS are hardcoded as magic numbers (767, 1024, 480, 360, 900, 800)
- No SCSS variables or CSS custom properties define breakpoints centrally
- Changing a breakpoint value requires editing every `@media` query individually

---

## 8. Complete Breakpoint Value Inventory

| Value | Used In | Type |
|---|---|---|
| 360 | `BottomNavigationBar.vue`, `AlbumsTabView.vue` | CSS @media |
| 460 | `useColumnResize.ts` | JS hardcoded |
| 480 | `BREAKPOINTS.compact`, 6 CSS files | JS constant + CSS @media |
| 481 | `MobileHeader.vue` | CSS @media (paired with 1024) |
| 767 | 15 locations across 7 files | CSS @media + JS matchMedia |
| 768 | `BREAKPOINTS.phone`, 2 lock queries | JS constant + CSS @media |
| 800 | `_lightbox-tablet.scss` | CSS @media (max-height) |
| 900 | `_lightbox-tablet.scss` | CSS @media (min-width) |
| 1024 | 6 CSS files | CSS @media |
| 1200 | `BREAKPOINTS.tablet` | JS constant |
| Infinity | `BREAKPOINTS.desktop` | JS constant |

---

## 9. Summary of Architecture

The app uses a **hybrid responsive approach**:
1. **JS composable** (`useDevice.ts`) tracks window width via `resize` listener and computes device type
2. **CSS media queries** apply styling changes at specific breakpoints
3. **Component templates** use `v-if` with `isMobile`/`isTablet`/`isDesktop` for structural rendering changes

The primary layout breakpoint is **768px** (phone vs. tablet/desktop), with secondary refinements at **1024px** (tablet vs. desktop), **480px** (compact), and **360px** (very small phone).

### Recommendations (for reference, not action):
1. Align CSS docs with JS: change `main.scss` comment to say "Desktop: 1200+"
2. Consider adding a CSS custom property `--breakpoint-tablet: 1024px` or using SCSS variables
3. Make `AlbumScroller.vue` use `useDevice().isMobile` instead of its own matchMedia
4. Add a `BREAKPOINTS.largePhone` (e.g. 460) or document the 460 hardcoded value
5. Ensure all `@media (max-width: 1024px)` blocks are paired with `@media (min-width: 1200px)` for desktop rules, or explicitly handle the 1025–1199px gap
