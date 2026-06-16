# Metadata Inspector Performance Plan

Last reviewed: 2026-06-16

Status: proposed.

This plan targets the `/metadata` navigation and `LibraryInspector.vue` interaction delay. Recent profiling showed that the default `/api/library/inspector` request is not the main source of the perceived 800ms delay on the tested local dataset. The expensive path is frontend main-thread work after the API body is already available: mounting and updating 100 rich table rows with thumbnails, popovers, dropdown menus, and long metadata cells.

The plan is intentionally phased so fixes are measurable and reversible. Do not make broad SQL, state-management, or UI rewrites before the render bottleneck is addressed and measured.

## Goals

- Make opening `/metadata` feel responsive from the gallery metadata button.
- Keep sort and search interactions responsive when the result set has many rows.
- Keep the table useful for metadata inspection without mounting heavy controls for every row.
- Preserve current behavior unless a phase explicitly changes the API contract or UI behavior.
- Use measurements to prove each phase before moving to the next one.

## Non-Goals

- Do not redesign the whole metadata page.
- Do not replace the gallery grid.
- Do not add advanced DAM features such as tags, ratings, batch editing, or saved searches.
- Do not start with backend rewrites. SQL/index work is a follow-up unless new profiling contradicts the current finding.
- Do not remove prompt, LoRA, or action features; defer their heavy rendering until the user asks for them.

## Baseline to Keep

Before changing runtime behavior, preserve a repeatable baseline:

- Run `frontend/tests/metadata-performance.spec.ts`.
- Record click-to-first-row-visible for gallery to metadata navigation.
- Record API headers/body-ready timing separately from UI-ready timing.
- Record long tasks after the `/api/library/inspector` body is ready.
- Record sort and search update latency for a high-row response.
- Keep one direct backend timing sample for `/api/library/inspector` so backend regressions are visible.

Recommended performance budget after all phases:

- API duration for default inspector request: keep under 150ms p95 on the local test dataset.
- Click metadata button to first useful table paint: under 300ms after route chunk is cached.
- Sort/search UI update after API body ready: under 200ms for the default result size.
- Main-thread long task after API body ready: no single task above 150ms during default table render.

## Phase 1 - Virtualized Cheap Rows

Primary objective: reduce mount/update cost by rendering only rows in or near the viewport and by making each visible row cheap.

Scope:

- Add row virtualization to `LibraryInspector.vue`.
- Render only visible rows plus a small overscan window.
- Use a stable row height so virtualization math does not shift during scroll.
- Keep the visible row layout close to the current table: thumbnail, name, folder, model, sampler, seed, dimensions, date, and one actions entry point.
- Replace always-mounted row popovers/dropdowns with lazy-mounted content.
- Keep prompt and LoRA summary text cheap in the row; move full prompt/LoRA content behind a lazy popover or detail action.
- Keep thumbnails in fixed-size containers with `loading="lazy"` where possible.

Implementation notes:

- Prefer the existing TanStack stack. The repo already uses `@tanstack/vue-virtual` and `@tanstack/vue-table`.
- Avoid variable-height table rows in this phase. Long names, paths, prompts, and LoRA lists should truncate inside fixed-height cells.
- Use plain elements where possible inside repeated row markup. Avoid mounting complex component trees per row unless the row is visible and the control is open.
- Keep server-side sorting and search as-is. Do not add SQL indexes in this phase unless profiling shows backend time has become the bottleneck after virtualization.

Acceptance criteria:

- Default 100-row metadata navigation no longer mounts 100 full rich rows at once.
- The number of active row component trees is bounded by viewport rows plus overscan.
- The same `metadata-performance.spec.ts` or an added companion spec shows a meaningful drop in post-API long-task time.
- Sort and search updates repaint only the virtualized window, not the entire result set.
- No functional regression in row click, thumbnail display, copy actions, prompt/LoRA inspection, or action menu behavior.

Risks:

- Virtualized tables require stable row geometry. If rows expand for long content, scroll positions can become inaccurate.
- Sticky headers and table semantics can be tricky with virtualized rows. Validate desktop and narrow viewport layouts.
- Lazy popovers must still be keyboard-accessible and must not lose focus unexpectedly.

Exit condition:

- The measured delay from API body-ready to first visible row is no longer the dominant part of the `/metadata` navigation.

## Phase 2 - Navigation, Prefetch, and State Restore

Primary objective: make entering and returning to `/metadata` feel instant when data and code are already known.

Scope:

- Prefetch the `/metadata` route chunk when the metadata button is hovered, focused, or when the app is idle after gallery load.
- Prefetch or warm the first `/api/library/inspector` query only when the user is likely to enter metadata and the current path/scope are known.
- Preserve inspector UI state across gallery/metadata navigation:
  - search query
  - scope
  - sort
  - selected row if applicable
  - scroll offset
  - current path
- Restore scroll position after returning to `/metadata`.
- Keep previous data visible during sort/search refetch where it improves perceived responsiveness, with a clear pending/fetching state.

Implementation notes:

- Keep ownership boundaries clear:
  - Pinia or route state owns UI/navigation state.
  - TanStack Query owns server response, loading, fetching, stale, and cache state.
- Use deterministic query keys for inspector requests.
- Avoid mutating API response objects for UI-only state.
- Use a bounded cache lifetime so metadata responses do not grow without limit.

Acceptance criteria:

- First navigation after app load is faster when the route chunk has been prefetched.
- Back/forward between gallery and metadata restores previous metadata state and scroll position.
- Returning from metadata to gallery remains fast.
- Search and sort do not clear the entire table to an empty state unless the request truly has no results.
- No stale state leak between different folder paths or scopes.

Risks:

- Over-eager prefetch can waste backend and thumbnail requests. Trigger route prefetch broadly, but data prefetch only when path/scope are stable.
- State restore can confuse users if it survives too long across unrelated folders. Scope restore keys by route plus path plus inspector params.
- Cached data must not mask indexing changes forever. Keep an explicit stale time and allow refetch.

Exit condition:

- After one metadata visit, gallery to metadata and metadata to gallery transitions both feel cached and stable.
- Sort/search perceived latency is dominated by actual backend response only when the backend is slow, not by remounting the whole table.

## Phase 3 - List/Detail API Split and SQL Follow-Up

Primary objective: reduce payload and processing for large libraries after the frontend render bottleneck is fixed.

Scope:

- Split the API contract into:
  - list rows: fields needed to scan, sort, search, and display the table
  - detail rows: long prompt, negative prompt, LoRA list, raw metadata, and other expensive fields loaded on demand
- Load detail data when:
  - a row detail panel opens
  - a prompt/LoRA popover opens
  - an existing preview/detail surface needs full metadata
- Re-measure `/api/library/inspector` after the list DTO is smaller.
- Add SQLite indexes only after capturing query plans on realistic data.

Candidate list DTO fields:

- path
- name
- folder
- thumbnail path or thumbnail URL inputs
- model summary
- sampler summary
- seed
- width
- height
- modified time
- stale/index state if needed for UI

Candidate detail DTO fields:

- full prompt
- negative prompt
- full LoRA entries
- raw parsed metadata
- generation parameters not visible in the list
- extended file/index metadata

SQL follow-up checklist:

- Capture `EXPLAIN QUERY PLAN` for default date sort, name sort, search, and scoped folder filter.
- If `ORDER BY COALESCE(m.mtime, fi.mtime)` still forces temp sort and backend time becomes material, consider a stored normalized sort column such as `effective_mtime`.
- If natural name sort is slow at larger row counts, consider a stored normalized/natural-sort key rather than relying on runtime `GALLERY_NATURAL` collation for large sorts.
- Add or validate indexes for hot filters and joins:
  - `image_metadata(path)` should already be covered by primary/unique path.
  - `file_index(path)` for the join.
  - `file_index(type, path)` or equivalent if type filtering remains hot.
  - path-prefix/scope indexes only if SQLite query plans can use them for the current prefix pattern.
  - generated or stored sort-key indexes only after the schema supports indexed `ORDER BY`.
- Avoid adding indexes blindly; every index increases write/update cost during indexing.

Acceptance criteria:

- Default list response is materially smaller than the current full row response.
- Opening prompt/LoRA/detail remains fast because detail fetch is scoped to one row.
- Backend p95 remains comfortably under budget on realistic large-library data.
- Query plans and timings justify every new index.

Risks:

- Splitting DTOs creates extra network requests for detail interactions. Use cache by path and prefetch detail only for selected/hovered rows if needed.
- A stored `effective_mtime` or natural sort key introduces consistency requirements when metadata or file index rows update.
- SQLite expression/index behavior depends on exact query shape. Verify with `EXPLAIN QUERY PLAN`, not assumptions.

Exit condition:

- The app can scale past the default 100-row request without reintroducing frontend long tasks or backend sort/search spikes.

## Phase Order Rules

1. Do Phase 1 first because current evidence points to frontend row rendering as the 800ms delay.
2. Do Phase 2 after Phase 1 so route/data prefetch does not hide an expensive render path.
3. Do Phase 3 after re-measuring. Backend/index work is valid only when the new bottleneck is proven.

## Test Plan

For every phase:

- Run the metadata performance spec.
- Capture browser long tasks around gallery to metadata navigation.
- Capture API timing separately from UI-ready timing.
- Test default sort, name sort, search with many results, search with few results, and back/forward navigation.
- Test at least one narrow viewport because virtualization and fixed row height can expose layout issues.

Manual checks:

- Open metadata from the gallery button.
- Sort date ascending/descending and name ascending/descending.
- Search with a broad query that returns many rows.
- Search with a narrow query that returns one or a few rows.
- Open row actions.
- Open prompt/LoRA inspection.
- Navigate back to gallery, then return to metadata.

## Stop Conditions

Pause and re-profile before continuing if:

- Backend API timing rises above the frontend render time after Phase 1.
- Virtualization causes row misalignment, broken keyboard focus, or incorrect action targets.
- State restore shows rows from the wrong folder/scope.
- Detail DTO splitting creates visible delay every time a user opens common row information.

