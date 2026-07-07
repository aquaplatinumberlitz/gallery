# Search Pattern Adaptation

Status: Implemented

Last reviewed: 2026-07-07

Implementation notes:

- `/api/search` now returns a bounded `media` stream with numeric cursor
  pagination while keeping legacy `albums`, `photos`, `videos`, and `prompt`
  fields.
- The frontend search composable uses infinite query paging and GalleryGrid
  appends search pages through a search-mode sentinel.
- Fielded search supports comma-AND prompt semantics and OR values for
  supported indexed fields.

## Summary

Adapt the useful search patterns from Immich and Diffusion Toolkit into
gallery-repo without copying their product-specific UI or architecture.

The main change is to move gallery search from "one request returns several
large sections, then the client virtualizes them" to "the server returns a
bounded page of results, the client appends pages, and virtualization remains a
rendering safety layer."

Use Immich as the model for incremental web search data flow. Use Diffusion
Toolkit as the model for structured query parsing and DB-layer paging.

## What To Adapt

### Adapt From Immich

- Add paginated search results with a `next_cursor` contract.
- Reset search results when `query`, `scope`, or `path` changes.
- Append additional search pages only when the search key is unchanged.
- Use one primary media stream for assets instead of forcing the UI to merge
  several result sections.
- Keep a shared virtualized gallery rendering path for search and browse where
  the existing gallery design allows it.

Reason: Immich avoids loading all matching assets into the browser at once. The
important pattern is incremental data loading, not the exact visual layout.

### Do Not Adapt From Immich

- Do not copy Immich's justified layout unless gallery-repo intentionally wants
  that visual design.
- Do not add smart search, vector search, or ML-backed ranking until gallery-repo
  has the required index and product requirements.
- Do not treat UI virtualization as the only performance control. The API must
  also bound each response.

Reason: gallery-repo already has a grid design and a local metadata index. The
performance issue is data shape and loading strategy, not a need to copy
Immich's whole search product.

### Adapt From Diffusion Toolkit

- Keep search parsing and filtering in a structured query layer.
- Extend the current fielded parser incrementally instead of replacing it.
- Apply pagination at the DB/query layer using a deterministic order.
- Dedupe asset paths before results reach the UI.
- Keep thumbnail loading tied to viewport visibility and bounded result pages.

Reason: Diffusion Toolkit handles large local libraries by querying a bounded
page and using a rich query model. Those ideas map well to gallery-repo's local
SQLite-backed metadata index.

### Do Not Adapt From Diffusion Toolkit

- Do not copy WPF paging controls or desktop-only UI flow.
- Do not switch gallery-repo search to Enter-only search. Keep live debounced
  search.
- Do not copy the full Diffusion Toolkit regex parser. Extend
  `fielded_search_parser.py` only where gallery-repo has indexed data.
- Do not add filters such as rating, favorite, or NSFW unless gallery-repo has
  stable indexed fields and UI semantics for them.

Reason: Diffusion Toolkit is a desktop app. Its query model is useful, but its
UI architecture is not a good fit for a browser gallery.

## Phase 1: Paginated Search API And Infinite Client Flow

### Backend

- Extend `GET /api/search` with `cursor?: int`.
- Keep `limit` bounded and use it as the page size for the media stream.
- Add these response fields:
  - `media: UnifiedSearchResult[]`
  - `next_cursor: number | null`
  - `has_more: boolean`
  - `returned: number`
  - `limit: number`
- Keep existing response fields during migration:
  - `albums`
  - `photos`
  - `videos`
  - `prompt`
- Return `albums` only on the first page. Cap album suggestions at 12.
- Build `media` by merging photo filename results, video filename results, and
  prompt metadata results, then dedupe by normalized path.
- Use deterministic ordering so page boundaries are stable for one query.
- Preserve existing stale-path filtering and cleanup behavior for both `albums`
  and `media`.

### Frontend

- Change `unifiedSearch()` to accept `cursor`.
- Convert `useUnifiedSearchQuery` from `useQuery` to `useInfiniteQuery`.
- Keep the composable name if that reduces callsite churn.
- Add a search infinite query key that includes normalized `query`, `scope`,
  `path`, and `limit`.
- Use page param as the search cursor.
- Aggregate `media` from all loaded pages.
- Use first-page `albums` as album suggestions.
- Remove stale `placeholderData` behavior for search query changes. A new query
  should not keep old result cards on screen as if they belong to the new query.
- Add a search-mode sentinel in `GalleryGrid.vue` that calls `fetchNextPage()`
  when the user nears the bottom of search results.

### Acceptance Criteria

- Typing a new query fetches only the first bounded page.
- Scrolling search results fetches more pages.
- Search results do not duplicate assets across pages.
- Existing non-search browse infinite loading keeps working unchanged.

## Phase 2: Query Semantics From Diffusion Toolkit

- Keep the current fielded syntax as the compatibility base.
- Add comma-separated residual prompt terms:
  - `cat, dog` means both terms must match prompt or metadata text.
  - Quoted values can contain commas.
- Add `|` OR values only for fields with stable existing support:
  - `model:a|b`
  - `sampler:euler|ddim`
  - `seed:1|2`
  - `path:foo|bar`
- Keep field filters scoped to media results.
- Keep album suggestions based on residual text only.
- Do not change `model_or_hash`, `raw`, `param`, or advanced field behavior
  without dedicated tests.

### Acceptance Criteria

- Existing fielded queries still return the same expected assets.
- New comma-AND prompt searches work for prompt metadata.
- New OR field values work only for explicitly supported fields.
- Album suggestions remain navigation aids, not strict field-filtered results.

## Phase 3: Render And Thumbnail Hardening

- Keep TanStack row virtualization for search results.
- Render search as:
  - optional album suggestion rows from the first page
  - one media section from the aggregated `media` stream
  - bottom loading row while fetching the next page
- Keep search thumbnail policy:
  - 256px thumbnail edge
  - `fetch-priority="low"`
  - `decoding="async"`
  - staggered visible thumbnail loading
- Keep existing browse virtualization and browse infinite scrolling unchanged.
- After the UI uses `media`, reduce duplicated search computed state for
  `photos`, `videos`, and `prompt`, but do not remove API compatibility fields
  in the same phase.

### Acceptance Criteria

- Desktop search does not produce visible browser jank when typing common
  queries such as `a`, `ab`, `test`, and `mika`.
- The DOM only mounts visible virtual rows plus overscan.
- Thumbnail requests are bounded by visible rows and incremental search pages.

## Test Plan

### Backend

- Empty query returns empty `albums`, empty `media`, and `next_cursor: null`.
- First page can return album suggestions; later pages return no album
  suggestions.
- Page 1 and page 2 return no duplicate media paths.
- `next_cursor` and `has_more` are correct when results exceed `limit`.
- `next_cursor` is `null` when the final page is reached.
- Fielded media queries still apply metadata filters.
- Stale paths are filtered and still trigger cleanup.

### Frontend Unit Tests

- `useUnifiedSearchQuery` fetches the first page with cursor `0`.
- `fetchNextPage()` sends the previous page's `next_cursor`.
- Aggregated media includes all loaded pages.
- Changing `query`, `scope`, or `path` resets loaded pages.
- The search sentinel does not call `fetchNextPage()` when already fetching or
  when there is no next page.

### E2E And Performance

- Use a fixture with many albums, photos, videos, and prompt matches.
- Type `a`, `ab`, `test`, and `mika` in the main gallery search box.
- Verify the first response is bounded by the search page size.
- Verify scrolling search results fetches the next page.
- Verify no duplicate cards appear after additional pages load.
- Verify no long render task is introduced when search results settle.

## Assumptions And Defaults

- Keep live debounced search at 300ms.
- Use `SEARCH_PAGE_SIZE = 60` on the frontend unless product testing shows a
  better value.
- Use numeric offset cursor for phase 1 to match the current browse pattern.
- Consider keyset cursors later if result ordering drift or very large result
  sets become a measured problem.
- Keep album suggestions capped at 12 and first-page only.
- Keep legacy `albums/photos/videos/prompt` API fields during the migration.
- Do not remove the current virtualization and thumbnail-jank fixes.
