# TanStack Migration Plan

Last reviewed: 2026-06-09

This plan keeps the TanStack migration incremental. It documents the ownership boundary first, then limits each phase to one behavioral surface.

## Current Installation and Runtime Use

Installed TanStack libraries:

- `@tanstack/vue-query`
- `@tanstack/vue-virtual`
- `@tanstack/db`
- `@tanstack/query-db-collection`
- `@tanstack/vue-db`
- `@tanstack/vue-form`
- `@tanstack/vue-table`
- `@tanstack/vue-query-devtools`

Runtime use today:

- TanStack Query is installed through `frontend/src/query/index.ts` and caches first-page `/api/scan` responses.
- TanStack Virtual is used by `GalleryGrid.vue` for desktop/tablet row virtualization.
- TanStack DB, Query Collection, and Vue DB are present as a beta foundation with a landing-pages pilot collection wired into Settings theme selection.
- Query Devtools are rendered from the app root in development mode.
- TanStack Form and Table are installed foundations only and are not used in runtime UI.

## State Ownership

Pinia owns:

- UI/navigation state
- `rootPath` and `currentPath`
- history/back-forward
- selected folder/open state
- sort/view preferences
- search input/scope
- lightbox open/index/UI state
- mobile sheet/UI state

TanStack Query owns:

- API/server state
- loading/error/fetching state
- cache, `staleTime`, and `gcTime`
- refetch/invalidate
- `/api/scan`
- `/api/search`
- `/api/metadata` if migrated
- `/api/landing-pages` if using Query directly
- future mutations

TanStack DB owns only:

- collection/live-query layer when data has stable keys
- local reactive querying across loaded collection data
- Query Collection only when endpoint semantics are compatible
- landing pages pilot if kept

## Current Boundary

The current gallery scan flow is hybrid for compatibility. TanStack Query caches the first scan page by deterministic key, and the active gallery grid reads first-page folders/photos from Query. The Pinia gallery store still copies scan data for navigation, initial root-load compatibility, and infinite-load append behavior.

Infinite image loading and folder tree loading still call the API from Pinia/store code directly. Search results and lightbox metadata now use plain TanStack Query as their active source of truth, while deprecated Pinia search result fields remain temporarily for compatibility.

TanStack DB currently wraps only `/api/landing-pages` into a Query Collection. The API response is normalized from `string[]` to landing-page rows keyed by `url`, with an index retained to preserve API order in live queries.

## Why Query Is the Default

Plain TanStack Query matches this app's REST/API data model directly:

- request identity is explicit in the query key
- loading, fetching, error, stale, cache, and garbage-collection state stay with the server response
- refetching and invalidation are endpoint-oriented
- future writes can use Query mutations without requiring a local collection model first

Use Query by default for API/server state. Add DB only when a collection/live-query layer has stable keys and a clear definition of the complete collection state for its scope.

## Query Collection Warning

Query Collection treats the query result as the synced collection state for that scope. That is a good fit when the endpoint returns the complete set of rows for a stable collection scope.

Endpoint subsets, search results, and cursor pages can be wrong if modeled as full collection sync. A search response is a filtered subset, a scan response is scoped to a path and may contain only the first image page, and infinite loading returns cursor pages that are intentionally partial. Modeling those as complete collection state can create replacement or deletion semantics that do not match the backend.

Therefore search, scan, and infinite load stay with plain TanStack Query first. Do not use TanStack DB for those flows until collection scope, stable keys, and full-state semantics are designed.

## Approved Phase Order

0. Standardize queryKeys/queryOptions

1. Landing pages: finish DB pilot or use Query directly

2. Search: plain TanStack Query, not DB

3. Metadata: plain TanStack Query if needed

4. First scan page: TanStack Query source of truth, not DB

5. Infinite load: useInfiniteQuery, not DB

6. Folder tree: query-ify later

7. DB only for collection/live-query cases with stable keys and clear full-state semantics

## Phase 0 Scope

Phase 0 creates a centralized query key module and refactors existing Query/DB pilot code to use it.

Status: complete. Query path normalization is shared through `normalizeQueryPath`, scan/search/metadata query keys use that normalizer, and `queryKeys.scanPath(path)` is available for broad scan-path invalidation while exact scan fetch/cache keys remain `queryKeys.scan(path, IMAGE_PAGE_SIZE)`.

Allowed:

- centralize keys in `frontend/src/query/keys.ts`
- update existing `/api/scan` Query helpers to use `queryKeys.scan(...)`
- update the landing-pages Query Collection to use `queryKeys.landingPages()`

Not allowed:

- migrate search to Query
- migrate metadata to Query
- migrate `/api/scan` source of truth
- migrate infinite load
- migrate folder tree
- wire landing pages UI differently
- change backend behavior
- change UI/UX

## Phase 1 Scope

Phase 1 landing pages are complete for Settings theme selection. The existing landing-pages Query Collection still uses `url` as the collection key, defensively ignores duplicate URLs, preserves API order with an index, and `SettingsModal.vue` reads it through `useLandingPagesLiveQuery()` with a pending-data guard. `IntroScreen.vue` keeps its direct conditional `fetchLandingPages()` call so disabled, manual, and forced-preview flows do not start an eager landing-pages query.

## Phase 2 Scope

Status: complete. Active unified search UI uses `useUnifiedSearchQuery()` with plain TanStack Query and `queryKeys.search(trimmedQuery, scope, path)`. Pinia keeps search input text, search scope, and navigation state. TanStack Query owns `/api/search` results, loading/fetching, errors, and cache. The legacy Pinia `unifiedSearchResults`, `searchLoading`, `searchError`, and `unifiedSearch()` action remain only as deprecated compatibility state and are not the active UI source of truth.

## Phase 3 Scope

Status: complete. Lightbox metadata uses `usePhotoMetadataQuery()` with plain TanStack Query and `queryKeys.metadata(path)`. The query is enabled only while the lightbox is open and a current image path exists, with a 10-minute stale time and 30-minute garbage-collection time. Pinia lightbox state keeps open/current-index/gallery-item navigation and current item path/name only; TanStack Query owns `/api/metadata` response, loading, errors, and cache.

## Phase 4 Scope

Status: partial. `useCurrentScanQuery()` exposes the current path's first `/api/scan` page through plain TanStack Query and `queryKeys.scan(path, IMAGE_PAGE_SIZE)`. `GalleryGrid.vue` reads active first-page folders and photos from Query, while Pinia remains as compatibility state for root-load loading, copied scan metadata/cursors, and images appended by the existing `loadMoreImages()` path. Phase 5 infinite loading has not started, so Pinia still participates in the rendered image list after page one.

## Hard Rules

- Do not add new Query -> Pinia duplicated server-state flows unless needed for compatibility.
- Do not use TanStack DB for search results.
- Do not use TanStack DB for infinite/cursor pagination yet.
- Do not use TanStack DB for `/api/scan` until collection scope and full-state semantics are designed.
- Plain TanStack Query is the default for REST/API data.
- Query Collection is only for stable collection endpoints where the response represents the complete state for that collection scope.
- Pinia should not become a second cache for server data.
- Thumbnails should remain browser/server cached; no Query needed.
