# Metadata Inspector Performance Plan

Last reviewed: 2026-06-16

Status: all phases implemented.

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

- Run `frontend/tests/e2e/metadata-performance.spec.ts`.
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

Status: implemented on 2026-06-16.

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

Implementation result:

- `LibraryInspector.vue` uses `@tanstack/vue-virtual` to render only the visible metadata rows plus overscan.
- Default rendered table rows dropped from the full 100-row response to about 15 DOM rows on the 1366x900 Playwright viewport.
- Latest `metadata-performance.spec.ts` run after Phase 1:
  - navigation: API response to first row 60ms, click to table ready 613ms, rendered rows 15
  - sort: API response to update 25ms, rendered rows 15, table not cleared during load
  - search: one debounced request, final API response to update 208ms, rendered rows 1

## Phase 2 - Navigation, Prefetch, and State Restore

Status: implemented on 2026-06-16.

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

Implementation result:

- `/metadata` route chunk is prefetched on browser idle from the app header.
- Metadata route chunk and the first inspector query are prefetched on metadata link hover/focus.
- Inspector server state uses a short `staleTime` so hover/focus prefetch can be reused during navigation.
- Inspector UI state is kept in the gallery store:
  - query
  - scope
  - sort
  - model filter
  - prompt filter
  - selected row
  - table scroll offset, scoped by current path
- Latest `metadata-performance.spec.ts` run after Phase 2:
  - navigation: click to table ready 442ms, rendered rows 15
  - sort: API response to update 42ms, rendered rows 15, table not cleared during load
  - search: one debounced request, final API response to update 209ms, rendered rows 1
  - state restore: sort and table scroll restore after metadata -> gallery -> metadata

## Phase 3 - List/Detail API Split and SQL Follow-Up

Status: implemented on 2026-06-16.

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

Implementation result:

- The list/detail API boundary is preserved:
  - `/api/library/inspector` returns bounded list rows only.
  - `/api/library/inspector/metadata` remains the full detail endpoint for prompt, negative prompt, raw metadata, LoRA resources, and copied metadata.
- The list SQL no longer uses `SELECT m.*`.
- The list query now projects only list fields and SQL-derived flags/previews:
  - path/name/folder/date/dimensions/model/tool/sampler/seed
  - `substr(prompt, 1, 141)` as prompt preview
  - boolean flags for prompt, negative prompt, and raw metadata availability
  - LoRA count/preview from the indexed resource summary added in Phase 3.1
- Full `metadata_json`, full prompt, negative prompt, and raw metadata are not hydrated into list rows.
- No SQLite index was added in this phase because current evidence still points to frontend render as the original bottleneck, and warm backend list timing remains low on the local DB.
- Latest verification:
  - backend inspector tests: `12 passed`
  - frontend inspector tests: `5 passed`
  - metadata performance tests: `4 passed`
  - frontend build: passed
  - warm direct `list_library_inspector_rows("", "all", None, 100, "date_desc")`: about 23ms after DB initialization

## Phase 3.1 - Indexed Resource Summary

Status: implemented on 2026-06-16.

Primary objective: keep LoRA/resource list/search accurate without parsing full raw metadata JSON during `/api/library/inspector`.

Implementation result:

- Added normalized `image_resources` storage for extracted resources.
- Metadata upsert now replaces resource rows for the indexed image path.
- Existing databases backfill `image_resources` during schema migration to `user_version = 2`.
- Resource extraction uses indexed metadata inputs:
  - `metadata_json` `loras` / `LoRA` style blocks
  - `metadata_json` `resources` / `Resources` blocks
  - fallback `lora_text` entries
- Library Inspector list rows now join a grouped LoRA summary from `image_resources`:
  - `lora_count`
  - `lora_preview`
  - `has_lora`
- The previous JSON keyword heuristic is no longer needed for list LoRA badges.
- Fielded search now uses `image_resources` for:
  - `lora:<name-or-hash>`
  - `resource_hash:<hash>`
- LoRA facets now read from `image_resources`, so metadata-json-only LoRAs are visible in facet output after indexing/backfill.

Edge case covered:

- If `lora_text` is empty but `metadata_json` contains a LoRA entry, the list still shows the LoRA badge/count/preview and `lora:<name>` search finds the row.

Latest verification:

- backend inspector tests: `13 passed`
- backend facets tests: `11 passed`
- fielded search parser tests: `91 passed`
- warm direct `list_library_inspector_rows("", "all", None, 100, "date_desc")`: about 24ms after DB initialization

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

## Appendix: Database Schema & Search Flow

### `image_metadata` vs `image_resources`

`image_metadata` and `image_resources` deliberately store related data at different shapes.

`image_metadata` is one row per indexed photo. It stores the main metadata payload used for display and direct filtering:

- `prompt`
- `negative_prompt`
- `model`
- `sampler`
- `seed`
- `steps`
- `cfg_scale`
- `metadata_json` as the raw JSON blob
- `lora_text`

`image_resources` is many rows per photo. It flattens resource information extracted from `metadata_json` and `lora_text` into separate indexed rows. Each extracted resource can carry:

- `kind`
- `name`
- `hash`
- `resource_hash`
- `weight`
- `strength`

Both tables exist because they serve different query paths. `image_metadata` keeps the original per-photo metadata intact, including the raw JSON needed for detail display and future extraction. `image_resources` is the pre-extracted search structure.

Searching directly inside `metadata_json` would require parsing JSON at query time for every candidate row. That is too slow for interactive search and facets, especially as libraries grow. `image_resources` avoids that by storing the extracted resource values in normal indexed columns, so fielded search can use an `EXISTS` subquery against the flattened rows.

Analogy: `image_metadata` is the book; `image_resources` is the index at the back of the book.

### Gallery Search vs Library Inspector Search

Gallery Search and Library Inspector Search share the same fielded-query condition builder. Queries such as `lora:add_detail`, `model:pony`, and `seed:12345` go through `build_fielded_conditions()` in `fielded_search_parser.py`. For resource-backed fields, the SQL subquery into `image_resources` via `EXISTS` is identical.

The surrounding flow is different.

Gallery Search (`/api/search`):

- Plain text goes through `search_index()`.
- Plain text uses FTS5 on `file_index_fts` and `image_metadata_fts`.
- Plain text returns three sections: `albums[]`, `photos[]`, and `prompt[]`.
- Fielded queries go through `search_index_fielded()`.
- Fielded search uses `build_fielded_search_sql()`.
- Fielded search builds a CTE with field conditions joined with the FTS5 filename match.
- Fielded search returns photo and prompt sections; albums still come from residual text FTS.
- Results return `file_index` columns (`fi.*`).
- There is no overscan and no stale row filtering.
- The limit defaults to 50 per section.

Library Inspector Search (`/api/library/inspector`):

- All requests go through `list_library_inspector_rows()`.
- The `q` parameter always uses `parse_fielded_query()` plus `build_fielded_conditions()` for search conditions.
- There is no separate filename FTS path; the `q` parameter is the search.
- Results return `image_metadata`-derived columns (`m.*`) as flat `rows[]`.
- The inspector has overscan plus stale row filtering. If the DB returns rows pointing to deleted files, it re-queries with a larger limit to fill the page.
- Sort options include `date_asc`, `date_desc`, `name_asc`, and `name_desc`, not only `mtime DESC`.
- The limit defaults to 200.

### Data Source Table Mapping

| Table | Content | Schema row count | Used by |
|---|---|---|---|
| `file_index` | 1 row per file/folder: path, name, type, parent_path, mtime, size, width, height | 1-to-1 | Scan, gallery browse, gallery search (photos/albums) |
| `file_index_fts` | FTS5 index over `file_index` filename | 1-to-1 with `file_index` | Gallery search filename matching |
| `image_metadata` | 1 row per photo: path, prompt, negative_prompt, model, sampler, seed, steps, cfg_scale, metadata_json (raw), lora_text | 1-to-1 with indexed photos | Metadata display, Library Inspector, fielded search, gallery prompt search |
| `image_metadata_fts` | FTS5 unicode61 over prompt/negative/model/sampler/raw_metadata_text | 1-to-1 with `image_metadata` | Gallery prompt search, metadata search |
| `image_metadata_fts_trigram` | FTS5 trigram over same fields (CJK support) | 1-to-1 with `image_metadata` | CJK/substring search |
| `image_resources` | N rows per photo: kind, name, hash, resource_hash, weight, strength (flattened from metadata_json/loras/lora_text) | 1-to-many | Fielded search `lora:`/`resource_hash:`, LoRA facets, Library Inspector list LoRA badges |
