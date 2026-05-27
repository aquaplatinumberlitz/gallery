# Mobile UI/UX Implementation Plan — Gallery Vue App

> **Created:** 2026-05-25  
> **Based on:** Web research (Material Design 3, iOS HIG, UX blogs), existing `_ux_research.md`, and full code analysis  
> **Target:** `/home/ubuntu/gallery-repo/gallery/frontend/`

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [Phase 1 — CSS-Only Quick Wins (High Impact, Low Effort)](#2-phase-1--css-only-quick-wins)
3. [Phase 2 — Structural HTML/Component Changes (Medium Impact, Medium Effort)](#3-phase-2--structural-changes)
4. [Phase 3 — Bottom Navigation & Header Redesign (High Impact, High Effort)](#4-phase-3--bottom-navigation--header-redesign)
5. [Phase 4 — Gestures, Animations & Enhancements](#5-phase-4--gestures-animations--enhancements)
6. [Risks & Mitigations](#6-risks--mitigations)
7. [Testing & Verification](#7-testing--verification)

---

## 1. Current State Analysis

### 1.1 Current Mobile User Flow

```
┌──────────────────────────────────────┐
│ [☰] [⚙️]        [🌙] [🔍]           │  ← Header (hamburger, settings, theme, search)
├──────────────────────────────────────┤
│ [◀] [▶] [📂]   Sort ▼  [≡ Grid]    │  ← Grid header (nav, sort, grid slider)
│ Current Folder Name → 12 photos     │  ← Mobile folder bar
├──────────────────────────────────────┤
│                                      │
│  ┌─────┐ ┌─────┐ ┌─────┐           │
│  │ 📸  │ │ 📸  │ │ 📸  │           │  ← Gallery grid (2-3 columns)
│  └─────┘ └─────┘ └─────┘           │
│  ...                                │
│                                      │
└──────────────────────────────────────┘
```

### 1.2 Files Analyzed

| File | Lines | Role |
|------|-------|------|
| `src/App.vue` | 1114 | Shell layout, header, sidebar, theme toggle, search, settings modal |
| `src/components/GalleryGrid.vue` | 1383 | Grid header, nav buttons, breadcrumb, sort, grid slider, folder bar |
| `src/components/Lightbox.vue` | 1571 | Lightbox + mobile bottom sheet with metadata |
| `src/components/SidebarHeader.vue` | 186 | Sidebar root path input |
| `src/components/FolderTreeItem.vue` | 221 | Folder tree with keyboard nav |
| `src/styles/main.scss` | 525 | Global styles, animations, dark mode |

### 1.3 Mobile Breakpoints Currently Used

- **Phone:** `<=640px` (primary mobile breakpoint)
- **Small phone:** `<=480px` (compact layout)
- **Tablet:** `641-1024px` (sidebar persistent + hamburger)

### 1.4 Pain Points Summary

| # | Issue | Severity | Location |
|---|-------|----------|----------|
| 1 | No bottom navigation — hamburger menu is outdated pattern | 🔴 Critical | App.vue |
| 2 | Search UX: icon→expand overlay with backdrop is clunky | 🔴 Critical | App.vue |
| 3 | Theme toggle wastes precious header space on mobile | 🟡 Medium | App.vue |
| 4 | Settings button in header (should be in bottom nav tab) | 🟡 Medium | App.vue |
| 5 | Brand hero hidden via display:none but still in DOM | 🟢 Low | App.vue |
| 6 | Grid slider on mobile is unnecessary (pinch-to-zoom better) | 🟡 Medium | GalleryGrid.vue |
| 7 | No pull-to-refresh for gallery | 🟡 Medium | GalleryGrid.vue |
| 8 | No collapsible header on scroll | 🟢 Low | App.vue |
| 9 | Sort dropdown in grid header awkward on mobile | 🟡 Medium | GalleryGrid.vue |
| 10 | No swipe gestures for navigation | 🟢 Low | GalleryGrid.vue |
| 11 | No haptic feedback for touch actions | 🟢 Low | All |

### 1.5 Gap Analysis vs. Best Practices

| Criteria | Gallery Vue (mobile) | Google Photos | Apple Photos | MD3/iOS HIG |
|----------|---------------------|---------------|--------------|-------------|
| **Bottom Navigation** | ❌ Hamburger menu | ✅ 4 tabs | ✅ 4 tabs | ✅ Standard |
| **Search UX** | ⚠️ Icon→Overlay | ✅ Full-width bar | ✅ Tab in bottom nav | ✅ Full-width or tab |
| **Header height** | ~48px | ~56dp | ~44pt | 48-56px |
| **Header layout** | 3-4 icons | Search + avatar | Title + buttons | Single row |
| **Theme toggle** | In header | In settings | System auto | Settings |
| **Grid control** | Slider widget | Pinch-to-zoom | Pinch-to-zoom | Gesture-based |
| **Pull-to-refresh** | ❌ | ✅ | ✅ | Recommended |
| **Collapsible header** | ❌ | ✅ | ❌ | Optional |
| **Touch targets** | ⚠️ 28-30px icons | ✅ 44px min | ✅ 44pt min | 44px/48dp min |

---

## 2. Phase 1 — CSS-Only Quick Wins

> **Goal:** Immediate mobile UX improvements without changing HTML/JS structure.  
> **Effort:** ~2-3 hours total.  
> **Risk:** Very low — CSS changes only, easy to revert.

### 2.1 Remove Brand Hero from DOM on Mobile (not just hide)

- **Description:** The `.brand-hero` block is currently `display: none` on mobile but still 
  rendered in DOM. Remove it entirely on mobile via a conditional or use CSS to skip it.
- **File:** `src/App.vue` (template + scoped styles)
- **CSS change:** Replace `display: none` in `@media (max-width: 640px)` with `content-visibility: hidden` 
  and `position: absolute` to reduce layout cost. Alternatively, add `v-if="!isMobile"` in template 
  for a cleaner approach (this touches template — see Phase 2).
- **Effort:** 15 min
- **Risk:** Minimal
- **Test:** Verify brand hero absent on mobile viewport

### 2.2 Increase Touch Target Minimums for Header Buttons

- **Description:** Currently mobile header buttons (hamburger, search, settings) are 28-30px, 
  below the recommended 44px minimum. Use CSS `::before` pseudo-elements to expand hit areas 
  without changing visual size.
- **File:** `src/App.vue` — `@media (max-width: 640px)` section
- **CSS change:**
  ```css
  .hamburger-btn, .settings-btn, .search-box {
    position: relative;
  }
  .hamburger-btn::before, .settings-btn::before, .search-box::before {
    content: '';
    position: absolute;
    inset: -8px; /* expand hit area to ~44px */
  }
  ```
- **Effort:** 20 min
- **Risk:** Very low
- **Test:** Tap around each button — should register clicks 8px outside visible area

### 2.3 Optimize Grid Gap & Padding for Content Density

- **Description:** On mobile, reduce spacing between photo grid items and content padding 
  to maximize viewport usage. Currently `gap: 8px` on virtual rows, padding 6px on content.
- **File:** `src/components/GalleryGrid.vue` — `@media (max-width: 640px)`
- **Changes:**
  - Reduce `virtual-row` gap from `8px` to `4px` on very small screens (<400px)
  - Reduce `.content-body` padding from `4px` to `2px`
  - Reduce `.scroller-header` padding-bottom
- **Effort:** 15 min
- **Risk:** Low — visual density preference
- **Test:** Verify grid items not overlapping, no clipping

### 2.4 Simplify Sort Dropdown to Bottom Sheet on Mobile

- **Description:** Currently on mobile the sort trigger becomes icon-only (hides label text). 
  Add a bottom-sheet style menu (using CSS `position: fixed; bottom: 0;` transform instead of 
  absolute positioning) for easier one-handed use.
- **File:** `src/components/GalleryGrid.vue` — `.sort-menu` styles for mobile
- **Changes:** Override `.sort-menu` on mobile to:
  ```css
  @media (max-width: 640px) {
    .sort-menu {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      top: auto;
      border-radius: 16px 16px 0 0;
      box-shadow: 0 -4px 20px rgba(0,0,0,0.15);
    }
  }
  ```
- **Effort:** 20 min
- **Risk:** Low
- **Test:** Verify sort options accessible, no overlap with bottom of screen

### 2.5 Add Safe Area Padding for Notched Phones

- **Description:** Current layout doesn't account for `safe-area-inset-*` constants used by 
  iOS notched devices and Android display cutouts.
- **File:** `src/styles/main.scss` + `src/App.vue`
- **Changes:** Add `env(safe-area-inset-top)` and `env(safe-area-inset-bottom)` to header/content:
  ```css
  @supports (padding: env(safe-area-inset-bottom)) {
    .content { 
      padding-bottom: calc(8px + env(safe-area-inset-bottom)); 
    }
  }
  ```
- **Effort:** 15 min
- **Risk:** Very low
- **Test:** Verify on device with notch (or browser DevTools notch emulation)

### 2.6 Hide Grid Slider on Mobile, Show Column Count as Static Badge

- **Description:** The grid slider (range input) takes up space and is hard to use on mobile. 
  Pinch-to-zoom is the standard pattern (Phase 4). For now, hide the slider track and show a 
  static column count badge.
- **File:** `src/components/GalleryGrid.vue` — `@media (max-width: 640px)`
- **Changes:**
  ```css
  @media (max-width: 640px) {
    .grid-slider {
      pointer-events: none; /* prevent interaction */
      opacity: 0.5;
      border: none;
      background: transparent;
      padding: 0;
    }
    .slider-track-wrapper { display: none; }
    .slider-icon { display: none; }
    .slider-count-badge { 
      position: static; 
      margin: 0;
    }
  }
  ```
- **Effort:** 15 min
- **Risk:** Low
- **Test:** Verify grid slider still visible but non-interactive

### 2.7 Mobile Header — Hide Settings Icon on Mobile

- **Description:** Settings button is unnecessary in the mobile header. Settings belong in a 
  bottom nav tab or profile screen. Hide it on mobile for now.
- **File:** `src/App.vue` — scoped styles
- **Changes:** 
  ```css
  @media (max-width: 640px) {
    .settings-btn { display: none; }
  }
  ```
- **Effort:** 5 min
- **Risk:** Low — settings still accessible via hamburger → sidebar
- **Test:** Verify settings button absent on mobile

---

## 3. Phase 2 — Structural HTML/Component Changes

> **Goal:** Component restructuring and UX improvements that require template changes.  
> **Effort:** ~6-8 hours total.  
> **Risk:** Medium — template changes may affect tests.

### 3.1 Full-Width Search Bar (Replace Icon→Expand Pattern)

- **Description:** Replace the current icon-only search that expands to overlay with a 
  persistent full-width search bar in the mobile header (Google Photos pattern). 
  On focus, it should push down content and show recent searches.
- **Files:** `src/App.vue` (template + styles), `src/styles/main.scss`
- **Changes:**
  - Remove `isSearchExpanded` toggle logic
  - Make `.search-box` always show the `<input>` field on mobile
  - Make search bar the dominant header element (take `flex: 1`)
  - Add placeholder text "Search photos..."
  - On focus: keyboard opens, optionally show suggestions overlay
  - Add search backdrop for overlay results (on mobile only)
- **Template change (App.vue line ~235):**
  ```diff
  - <div class="search-box" :class="{ expanded: isSearchExpanded }">
  + <div class="search-box mobile-search">
  -   <Search :size="18" class="search-icon-btn" @click.stop="toggleMobileSearch" />
  +   <Search :size="16" class="search-icon" />
  ```
- **CSS change:** Remove the icon-only compact styles, make search bar always full-width
- **Effort:** 1.5 hours
- **Risk:** Medium — changes how users interact with search
- **Test:** Verify search input always visible on mobile, keyboard works, search results filter

### 3.2 Move Theme Toggle to Settings Screen

- **Description:** Remove the theme toggle button from mobile header. Add theme setting 
  inside `SettingsModal.vue` instead. On desktop, the theme toggle can stay (or also move).
- **Files:** `src/App.vue` (template), `SettingsModal.vue` (needs investigation)
- **Changes:**
  - Add `display:none` on `.theme-toggle` for mobile
  - Add a theme toggle in Settings modal (radio switch or toggle)
  - Keep the `toggleTheme()` function in App.vue but callable from SettingsModal
- **Effort:** 1 hour
- **Risk:** Low
- **Test:** Verify theme setting accessible from Settings, theme persists

### 3.3 Breadcrumb → Simple Back Button + Folder Name

- **Description:** Currently on mobile, breadcrumb is hidden entirely. Replace with a 
  simple "Back" chevron + current folder name in the grid header area.
- **Files:** `src/components/GalleryGrid.vue` (template)
- **Changes:**
  - Show `.mobile-folder-bar` as the primary navigation indicator
  - Add a "Back" button in the mobile folder bar (replaces breadcrumb)
  - Keep the current folder name display
  - Remove the separate `.mobile-folder-bar` — merge into grid header
- **Effort:** 1 hour
- **Risk:** Low
- **Test:** Verify back navigation works, folder name displays correctly

### 3.4 Combine Nav Buttons into Compact Row

- **Description:** The nav group (back/forward/open-folder) takes 3 button slots. 
  On mobile, reduce to just back (when available) and forward, move open-folder 
  into an overflow menu or remove it.
- **Files:** `src/components/GalleryGrid.vue` (template)
- **Changes:**
  - Show only back/forward nav buttons on mobile (already done partially)
  - Remove `.nav-btn.open-folder` from mobile grid header entirely
- **Effort:** 30 min
- **Risk:** Low
- **Test:** Verify nav works, open-folder still accessible from desktop

### 3.5 Improve Search UX with Instant Results Overlay

- **Description:** On mobile, when search is focused, show a dedicated search results 
  overlay with recent searches, suggestions, and matched results. Currently search just 
  filters items inline.
- **Files:** `src/App.vue` (template), possibly new `SearchOverlay.vue` component
- **Changes:**
  - When search input is focused on mobile, show an overlay with:
    - Recent searches (localStorage)
    - Number of matches
    - "Clear" button
  - Close on blur/escape
- **Effort:** 2 hours
- **Risk:** Medium
- **Test:** Verify overlay shows on focus, closes properly, recent searches persist

---

## 4. Phase 3 — Bottom Navigation & Header Redesign

> **Goal:** Complete mobile navigation overhaul — replace hamburger with bottom nav bar.  
> **Effort:** ~16-20 hours total.  
> **Risk:** High — requires significant component restructuring.

### 4.1 Create BottomNavigationBar.vue Component

- **Description:** New Vue 3 component implementing MD3-style bottom navigation bar.
  - 4 tabs: Photos, Albums, Search, More/Settings
  - Icon + label (label visible, icon on active)
  - Height: 56px (MD3 spec)
  - Safe area aware (padding-bottom for notched phones)
  - Active state indicator (MD3 pill-style or line)
  - Smooth transitions between tabs
- **File:** `src/components/BottomNavigationBar.vue` (new)
- **Props:**
  - `activeTab: string`
  - `tabs: TabItem[]`
- **Events:**
  - `@select(tabId: string)`
- **Specification:**
  ```ts
  interface TabItem {
    id: string;
    label: string;
    icon: string; // lucide icon name
    badge?: number;
  }
  ```
- **Tab definitions:**
  | Tab | Icon | Purpose |
  |-----|------|---------|
  | Photos | Image | Grid view (current default) |
  | Albums | FolderOpen | Folder tree/album view |
  | Search | Search | Search-focused view |
  | More | Settings | Settings, theme, about |
- **Effort:** 4 hours
- **CSS Details:** MD3 spec — `position: fixed; bottom: 0; z-index: 1000;` with safe area
- **Risk:** Medium — new component, needs to integrate with existing state

### 4.2 Implement Bottom Nav in App.vue

- **Description:** Replace hamburger menu + sidebar overlay with bottom navigation bar. 
  The sidebar becomes a full-page "Albums" tab view instead of an overlay drawer.
- **Files:** `src/App.vue` (template + script + styles)
- **Changes:**
  - **Template:**
    ```diff
    - <aside id="sidebar" class="sidebar" :class="{ open: isSidebarOpen, mobile: isMobile }">
    -   <SidebarHeader />
    -   <FolderTreeItem ... />
    - </aside>
    - <button class="sidebar-edge-toggle" ... />
    - <div v-if="isSidebarOpen && isMobile" class="sidebar-backdrop" ... />
    + <BottomNavigationBar v-if="isMobile" :active-tab="activeTab" @select="switchTab" />
    ```
  - Remove `isSidebarOpen`, `closeSidebar()`, `toggleSidebar()` logic
  - Add `activeTab` ref ('photos' | 'albums' | 'search' | 'more')
  - Add `switchTab(tabId)` method
  - Conditionally render content based on active tab
  - Add padding-bottom to `.content` to account for bottom nav height (56px + safe-area)
- **Effort:** 4 hours
- **Risk:** High — fundamental navigation change
- **Test:** Verify all 4 tabs work, content area not obscured by bottom nav

### 4.3 Create AlbumsTabView.vue (Replaces Sidebar on Mobile)

- **Description:** The sidebar folder tree becomes a full-page "Albums" tab. This is 
  triggered when user taps the "Albums" bottom nav tab. Contains:
  - SidebarHeader (root path input)
  - FolderTreeItem (recursive folder tree)
  - Full height, scrollable
- **File:** `src/components/AlbumsTabView.vue` (new)
- **Changes:**
  - Extract sidebar content (SidebarHeader + FolderTreeItem) into AlbumsTabView
  - Show on mobile when `activeTab === 'albums'`
  - Keep sidebar on desktop as-is
- **Effort:** 3 hours
- **Risk:** Medium — code extraction, verify desktop sidebar unchanged
- **Test:** Verify albums tab shows folder tree, navigation works

### 4.4 Collapsible Header on Scroll

- **Description:** Header automatically hides when scrolling down to maximize content 
  viewing area. Shows when scrolling up (Google Photos pattern).
- **Files:** `src/App.vue` (script + styles), `src/components/GalleryGrid.vue` (scroll events)
- **Changes:**
  - Track scroll position in GalleryGrid scroller
  - Emit scroll direction (`@scrolling` event with direction up/down)
  - In App.vue, add CSS class to hide/show header based on scroll direction
  - Animate with CSS `transform: translateY(-100%)` for hide
  - Bottom nav bar also hides/shows in sync (optional — "immersive" mode)
- **Implementation approach:**
  ```ts
  // GalleryGrid emits
  let lastScrollY = 0;
  const handleScroll = (e: Event) => {
    const target = e.target as HTMLElement;
    const delta = target.scrollTop - lastScrollY;
    if (delta > 20) emit('scrollDown');
    else if (delta < -20) emit('scrollUp');
    lastScrollY = target.scrollTop;
  };
  ```
- **Effort:** 2 hours
- **Risk:** Medium — scroll event performance, timing with virtual scroller
- **Test:** Scroll down/up, verify header hides/shows smoothly

### 4.5 Remove Hamburger Menu and Sidebar (Mobile)

- **Description:** Once bottom nav is implemented, remove the hamburger menu, sidebar 
  overlay, and backdrop from mobile view. Keep sidebar for desktop.
- **Files:** `src/App.vue` (template + styles)
- **Changes:**
  - Remove `isSidebarOpen`, `closeSidebar()`, `toggleSidebar()` from script
  - Remove sidebar HTML block when on mobile
  - Remove sidebar-backdrop
  - Remove hamburger button from header
  - Keep sidebar on desktop (>1024px)
- **Effort:** 1 hour
- **Risk:** Medium — ensure desktop sidebar still works
- **Test:** Desktop sidebar functions, mobile shows no sidebar

### 4.6 New Mobile Header (Single Row, Search-Dominant)

- **Description:** After removing hamburger + theme toggle + settings, the mobile header 
  becomes clean and minimal:
  ```
  ┌──────────────────────────────────────┐
  │ [🔍 Search photos...      ] [👤]     │  ← ~48px
  └──────────────────────────────────────┘
  ```
- **Files:** `src/App.vue` (template + styles)
- **Changes:**
  - Header has only: full-width search bar + profile/avatar icon
  - Remove `header-left` div entirely on mobile
  - Remove `header-actions` div (search and theme were in here)
  - Search is the star — always visible, full width
  - Profile icon opens "More" tab or triggers settings
- **Effort:** 2 hours
- **Risk:** Medium
- **Test:** Verify clean header, search works, profile icon responds

---

## 5. Phase 4 — Gestures, Animations & Enhancements

> **Goal:** Polish, gestures, and interactions that make the app feel native.  
> **Effort:** ~12-16 hours total.  
> **Risk:** Medium-High — gesture handling can be tricky on web.

### 5.1 Pull-to-Refresh Gallery Grid

- **Description:** Swipe down at top of gallery to reload current folder contents. 
  Show a pull indicator with refresh icon that transforms into a spinner.
- **Files:** `src/components/GalleryGrid.vue` (template + script)
- **Approach:**
  - Use touch events (`touchstart`, `touchmove`, `touchend`) on scroller
  - Track pull distance, show visual indicator
  - When pull exceeds threshold (~80px), trigger `galleryStore.refresh()`
  - Show spinner during refresh
  - Use `transform: translateY()` for smooth pull animation
  - Respect `prefers-reduced-motion`
- **Effort:** 3 hours
- **Risk:** Medium — conflicts with virtual scroller touch handling
- **Test:** Pull down, verify refresh triggers, no conflict with scrolling

### 5.2 Pinch-to-Zoom Grid

- **Description:** Pinch gesture on gallery grid changes column count (replaces grid slider).
  - Pinch in (zoom out) → more columns (smaller thumbnails)
  - Pinch out (zoom in) → fewer columns (larger thumbnails)
  - Smooth visual transition
- **Files:** `src/components/GalleryGrid.vue` (script)
- **Approach:**
  - Track `touchstart` with 2 touches → record distance
  - On `touchmove` with 2 touches → compute distance delta
  - Delta > threshold → change `columnCount` by ±1
  - Debounce to prevent rapid changes
  - Visual feedback: subtle scale animation on grid items
- **Effort:** 4 hours
- **Risk:** High — multi-touch handling is complex, conflicts with scroll/click
- **Test:** Pinch on grid, verify column count changes smoothly

### 5.3 Swipe to Navigate Between Folders

- **Description:** Horizontal swipe on grid area navigates between sibling folders 
  (folders at the same level in the folder tree). Left → next sibling, Right → previous.
- **Files:** `src/components/GalleryGrid.vue` (script)
- **Approach:**
  - Track horizontal touch gestures
  - If horizontal distance > 80px and vertical distance < 30px, trigger navigation
  - Animate: slide out current content, slide in new content
  - Works best for sibling folders at same tree level
- **Effort:** 3 hours
- **Risk:** High — conflicts with vertical scroll, accidental triggers
- **Test:** Swipe left/right, verify navigation to sibling folders

### 5.4 Lightbox Swipe Gestures

- **Description:** In lightbox, swipe horizontally to navigate between images, 
  swipe down to close. Currently uses button clicks only.
- **Files:** `src/components/Lightbox.vue` (script)
- **Changes:**
  - Add touch event handlers for swipe gestures
  - Left/right swipe → prev/next image
  - Down swipe on image → close lightbox
  - Track velocity for natural feel (fast swipe = go to next, slow = stay)
  - Add drag indicator (image follows finger slightly)
- **Effort:** 3 hours
- **Risk:** Medium — must not conflict with pinch-to-zoom on image
- **Test:** Swipe through images, verify smooth navigation

### 5.5 Haptic Feedback

- **Description:** Use Vibration API (`navigator.vibrate()`) for subtle haptic 
  feedback on key interactions:
  - Long press on photo (select mode)
  - Swipe to navigate
  - Pull-to-refresh threshold reached
  - Tab switch in bottom nav
  - Respect `prefers-reduced-motion`
- **Files:** New composable `src/composables/useHaptic.ts`
- **Implementation:**
  ```ts
  export function useHaptic() {
    const isSupported = typeof navigator !== 'undefined' && 'vibrate' in navigator;
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const light = () => { if (isSupported && !prefersReduced) navigator.vibrate(10); };
    const medium = () => { if (isSupported && !prefersReduced) navigator.vibrate(20); };
    const heavy = () => { if (isSupported && !prefersReduced) navigator.vibrate([30, 50, 30]); };
    return { light, medium, heavy };
  }
  ```
- **Effort:** 1 hour
- **Risk:** Low
- **Test:** Verify vibration on supported devices, no-op on desktop

### 5.6 Smooth Page Transitions & Micro-Animations

- **Description:** Add Vue `<Transition>` and CSS animations for:
  - Tab switching in bottom nav (slide content)
  - Folder navigation (fade + slide)
  - Search results appearing (stagger)
  - Image loading in grid (opacity fade-in)
  - Bottom sheet open/close (slide up/down)
- **Files:** `src/App.vue`, `src/components/GalleryGrid.vue`, `src/components/Lightbox.vue`
- **Changes:**
  - Wrap tab content in `<Transition name="tab-slide">`
  - Add `tab-slide-enter-active / leave-active` CSS classes
  - Stagger animation for grid items (CSS `animation-delay` with `nth-child`)
  - Respect `prefers-reduced-motion`
- **Effort:** 2 hours
- **Risk:** Low
- **Test:** Verify transitions smooth, no jank, not nauseating

### 5.7 iOS-Style Bottom Sheet for Sort & Filter

- **Description:** Replace current dropdown sort menu with iOS-style bottom sheet 
  that slides up from the bottom. Already partially done in Lightbox.vue (mobile-sheet).
- **Files:** New `src/components/BottomSheet.vue` (reusable) + GalleryGrid.vue
- **Changes:**
  - Create reusable BottomSheet component (uses Teleport + Transition)
  - Pull logic from Lightbox.vue's mobile-sheet
  - Use for: sort options, filter options, overflow menu items
  - Drag handle to dismiss (swipe down)
- **Effort:** 3 hours
- **Risk:** Medium
- **Test:** Verify bottom sheet opens/closes smoothly, drag to dismiss works

---

## 6. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Bottom nav breaks desktop layout | Medium | High | Use `v-if="isMobile"` exclusively for nav bar |
| Sidebar removal breaks folder tree access | High | High | AlbumsTabView must be fully functional first |
| Collapsible header conflicts with virtual scroller | Medium | High | Test thoroughly with RecycleScroller |
| Pinch-to-zoom conflicts with scroll on mobile | High | Medium | Implement gesture priority: scroll > pinch on single axis |
| Swipe navigation triggers when scrolling | High | Medium | Use angle threshold (>30° horizontal to trigger) |
| Pull-to-refresh conflicts with native scroll bounce | Medium | Low | Disable overscroll-behavior on scroller |
| CSS-only changes in Phase 1 don't improve UX enough | Low | Low | Acceptable — Phase 1 is interim improvements |
| Haptic vibration not respected by all browsers | Low | Low | Graceful degradation — no-op on unsupported |
| Safe area CSS not rendering correctly on some devices | Medium | Low | Use `env()` with fallback values |
| Reduced motion preferences not respected | Low | Medium | Add `@media (prefers-reduced-motion: reduce)` to all animations |

---

## 7. Testing & Verification

### 7.1 Device Testing Matrix

| Device | Viewport | Browser | What to Test |
|--------|----------|---------|-------------|
| iPhone 14 Pro | 390×844 | Safari | All phases, notch safe area, bottom nav |
| iPhone SE | 375×667 | Safari | Compact layout, smallest viewport |
| Samsung Galaxy S24 | 360×780 | Chrome | Android bottom nav, gesture nav |
| Google Pixel 7 | 412×915 | Chrome | MD3 compliance, touch targets |
| iPad Mini | 744×1133 | Safari | Tablet mode (sidebar persistent) |
| Desktop Chrome | 1920×1080 | Chrome | Verify desktop unaffected by mobile changes |
| Desktop Firefox | 1280×800 | Firefox | Cross-browser consistency |

### 7.2 Verification Checklist Per Phase

**Phase 1 (CSS-only):**
- [ ] Brand hero not visible on mobile (no empty space)
- [ ] Touch targets feel responsive (tapping near buttons works)
- [ ] Grid density improved — more photos visible
- [ ] Sort menu appears as bottom sheet on mobile
- [ ] No horizontal overflow on iPhone SE viewport
- [ ] Safe area padding visible on notched devices

**Phase 2 (Structural):**
- [ ] Search bar always visible on mobile, keyboard opens on tap
- [ ] Search results filter correctly, clear button works
- [ ] Theme toggle absent from mobile header
- [ ] Theme toggle present in Settings modal
- [ ] Mobile folder bar shows current folder + back navigation
- [ ] Nav buttons (back/forward) work correctly

**Phase 3 (Bottom Nav):**
- [ ] Bottom nav visible with 4 tabs on mobile
- [ ] Tabs switch content correctly (Photos, Albums, Search, More)
- [ ] Content area not obscured by bottom nav
- [ ] Desktop sidebar still works as before
- [ ] Albums tab shows folder tree
- [ ] Header is clean: search + profile icon only
- [ ] Collapsible header hides on scroll down, shows on scroll up

**Phase 4 (Gestures):**
- [ ] Pull-to-refresh works on gallery grid
- [ ] Pinch-to-zoom changes grid column count
- [ ] Swipe left/right navigates sibling folders
- [ ] Lightbox swipe gestures work
- [ ] Haptic feedback on key interactions (supported devices)
- [ ] Transitions are smooth and not jarring
- [ ] `prefers-reduced-motion` respected everywhere

### 7.3 Automated Test Considerations

- **Cypress/Playwright:** Test responsive layouts at 390×844 and 375×667 viewports
- **Component tests:** Test BottomNavigationBar tab switching
- **Integration tests:** Ensure bottom nav dispatches correct actions to gallery store
- **Visual regression:** Percy-style screenshot comparison for each phase

---

## Appendix A: File Change Summary

| File | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|------|---------|---------|---------|---------|
| `App.vue` | 2.1, 2.2, 2.7 | 3.1, 3.2, 3.5 | 4.2, 4.4, 4.5, 4.6 | 5.6 |
| `GalleryGrid.vue` | 2.3, 2.4, 2.6 | 3.3, 3.4 | — | 5.1, 5.2, 5.3 |
| `Lightbox.vue` | — | — | — | 5.4, 5.7 |
| `main.scss` | 2.5 | — | — | 5.6 |
| `BottomNavigationBar.vue` (new) | — | — | 4.1 | — |
| `AlbumsTabView.vue` (new) | — | — | 4.3 | — |
| `SearchOverlay.vue` (new) | — | 3.5 | — | — |
| `BottomSheet.vue` (new) | — | — | — | 5.7 |
| `useHaptic.ts` (new) | — | — | — | 5.5 |

## Appendix B: Estimated Total Effort

| Phase | Hours | Calendar Days (1 dev) |
|-------|-------|----------------------|
| Phase 1 — CSS Quick Wins | 2-3h | 1 day |
| Phase 2 — Structural Changes | 6-8h | 1-2 days |
| Phase 3 — Bottom Nav & Header | 16-20h | 3-4 days |
| Phase 4 — Gestures & Enhancements | 12-16h | 2-3 days |
| **Total** | **36-47h** | **7-10 days** |

## Appendix C: Key Design References

- **Material Design 3 — Navigation Bar:** Bottom navigation with 4-5 items, icon + label, active indicator pill
- **Material Design 3 — Search:** Persistent search bar or search tab in bottom nav
- **iOS HIG — Tab Bars:** Bottom tabs with icon + label, 44pt height minimum
- **Google Photos (2025):** Single-row collapsible header with search bar dominant, 4 tab bottom nav
- **Apple Photos (iOS 18):** Navigation bar with title + edit buttons, 4 tab bottom nav, search as tab
- **UX Best Practices:** 44px touch targets, bottom nav over hamburger, full-width search, collapsible headers on scroll, gesture navigation
