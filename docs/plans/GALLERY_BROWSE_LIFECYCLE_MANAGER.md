# Gallery Browse Lifecycle Manager

Status: Proposed tech debt note

Last reviewed: 2026-07-02

## Context

The gallery currently spreads browse lifecycle state across `galleryStore`,
`GalleryGrid.vue`, `useInfiniteBrowseQuery`, sidebar tree queries, virtualizer
state, and search mode. The current targeted cache reactivation fix is
intentionally small and should remain in place.

This note tracks a possible future refactor only if gallery browse lifecycle
needs broader hardening.

## Goal

Introduce a focused browse lifecycle composable or manager, for example
`useGalleryBrowseViewState`, that owns active browse scope and derived UI
lifecycle state.

## Invariants To Centralize

- Active browse scope is keyed by `libraryId`, `importPathId`, normalized
  browse path, include-offline mode, and relevant view mode.
- Cached browse data is considered active only when the first page matches the
  current scope.
- Loading, refreshing, empty, error, and loaded states are derived from query
  data for the active scope, not from stale component-local flags.
- Gallery scroll reset and restore are scoped by active library and browse path.
- Virtualizer measurement and scroll correction run when dataset identity,
  column count, row height, or scope changes.
- Infinite-scroll sentinel fetches only against the current active scope.
- Search mode and browse mode do not leak placeholder or cached rows into each
  other.
- Sidebar tree root and expanded-folder state stay scoped to active library and
  import path.
- Back/forward browse history is clamped to the active import root.

## Consider When

- More cache reactivation bugs appear after switching library, folder, or search
  modes.
- Per-library or per-folder scroll memory becomes a product requirement.
- Gallery folder/library deep links are introduced.
- Virtualizer measurement or blank-grid regressions recur.
- Browse, sidebar, and search state become harder to test independently.

## Non-Goals For Now

- Do not replace the current targeted fix just to make the architecture look
  cleaner.
- Do not clear TanStack Query cache broadly to paper over lifecycle bugs.
- Do not remount the entire gallery grid on every small state change unless a
  measured virtualizer bug requires it.

## Suggested Test Coverage

- Library A -> library B -> library A with cached pages.
- Root folder -> nested folder -> browser back with cached pages.
- Browse mode -> search mode -> browse mode without duplicate first-page
  requests.
- Desktop and tablet virtualized grids after column count changes.
- Mobile native grid with pull-to-refresh and bottom-bar visibility.
