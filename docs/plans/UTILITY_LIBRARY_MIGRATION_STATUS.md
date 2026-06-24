# Utility / Library Migration Status

Last updated: 2026-06-24

## Legend
- ✅ Done
- 🔄 In progress
- ⏳ Pending
- 🚫 Deferred
- ❌ Blocked

## Phase 1 — Low-risk wins

| # | Item | Commit | Status | Notes |
|---|------|--------|--------|-------|
| 1 | Raw clipboard callsite cleanup | [66d77e2](../..//commit/66d77e2) | ✅ | Routes raw clipboard copy through shared helper in `LibraryDetailPage.vue` |
| 2 | Debounced search refs | [4f7ebf8](../..//commit/4f7ebf8) | ✅ | Replaced manual setTimeout/clearTimeout with VueUse in `useUnifiedSearchQuery` and `useInfiniteLibraryInspectorQuery` |
| 3 | `useClipboard.ts` → VueUse | [ad9fea8](../..//commit/ad9fea8) | ✅ | Wrapped `@vueuse/core` `useClipboard` in Gallery's wrapper, preserving toast/copied-id/label behavior |

## Phase 2 — Standard API / central cleanup

| # | Item | Commit | Status | Notes |
|---|------|--------|--------|-------|
| 4 | Natural sort → `Intl.Collator` | [97894a3](../..//commit/97894a3) | ✅ | Replaced regex-based numeric splitting with `Intl.Collator({ numeric: true, sensitivity: "base" })` |
| 5 | Axios interceptor | [a252e82](../..//commit/a252e82) | ✅ | Added response interceptor, removed duplicate try/catch patterns from 25 API functions |

## Phase 3 — Responsive/layout plumbing

| # | Item | Commit | Status | Notes |
|--|------|--------|--------|-------|
| 6 | `useDevice.ts` → VueUse breakpoints | [1ceac2a](../..//commit/1ceac2a) | ✅ | Replaced custom singleton resize listener with `useWindowSize()` from @vueuse/core. Added boundary tests. |
| 7 | Simple manual listeners → `useEventListener` | [4b8109b](../..//commit/4b8109b) | ✅ | Migrated keydown/resize/visibilitychange/focus listeners in App.vue, AlbumScrollerNative.vue, useCatalogStatusQuery.ts, useLibraryStatusBatchQuery.ts |

## Phase 4 — Observer/storage plumbing

| # | Item | Commit | Status | Notes |
|---|------|--------|--------|-------|
| 8 | `useColumnResize.ts` partial VueUse migration | d86ddbf | ✅ | Replaced manual ResizeObserver/lifecycle + localStorage/loadGridSize/saveGridSize with useResizeObserver + useLocalStorage |
| 9 | Simple `ResizeObserver` callsites | ea93bbf | ✅ | Migrated ExpandableText.vue and AlbumScrollerNative.vue to useResizeObserver |
| 10 | Simple localStorage callsites | f82236d | ✅ | Migrated App.vue sidebar state and AlbumScroller.vue collapse state to useStorage |

## Phase 5 — Accessibility-sensitive migration

| # | Item | Commit | Status | Notes |
|---|------|--------|--------|-------|
| 11 | `useFocusTrap.ts` → Reka FocusScope | — | ⏳ | Not started |

## Phase 6 — Small DRY cleanup

| # | Item | Commit | Status | Notes |
|---|------|--------|--------|-------|
| 12 | `formatBytes` dedup | — | ⏳ | Not started |

## Deferred / Conditional

| Item | Status | Notes |
|------|--------|-------|
| `useScrollVisibility.ts` | 🚫 | Keep. Optional partial VueUse plumbing only. |
| `usePullToRefresh.ts` | 🚫 | Keep. Domain UX. |
| GalleryGrid IntersectionObserver | 🚫 | Defer. Only if simple + test-covered. |
| Toast store | 🚫 | Keep. Feature-complete. |
| Admin Library Table/Form | 🚫 | Defer until sort/filter/bulk feature required. |
| Backend pipeline | 🚫 | Keep current architecture. |
