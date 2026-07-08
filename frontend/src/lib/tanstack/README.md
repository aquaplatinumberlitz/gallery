# TanStack Usage Guide

This frontend uses TanStack libraries for state management, data display, and form handling.

## Installed Packages

| Package | Version | Status: Active \| Foundation \| Planned | Purpose |
|---------|---------|--------------------------------------|---------|
| `@tanstack/vue-query` | ^5.x | ✅ Active | Server-state caching for scan/infinite pages, folder children, search, metadata, and background refetch. Setup in `src/query/index.ts`. |
| `@tanstack/vue-virtual` | ^3.x | ✅ Active | Row-based virtual scrolling for desktop/tablet photo grid. Uses `useVirtualizer` in `GalleryGrid.vue`. |
| `@tanstack/vue-form` | latest | ✅ Active | Advanced fielded search form in `src/components/search/AdvancedSearchDrawer.vue`. See notes below. |
| `@tanstack/vue-table` | latest | ✅ Active | Sortable metadata table in `LibraryInspector.vue`. Uses `useVueTable`, `createColumnHelper`, `getCoreRowModel`, `getSortedRowModel` with shadcn-vue `<Table>` primitives. Paired with `@tanstack/vue-virtual` for virtual scrolling. See notes below for planned expansions. |
| `@tanstack/vue-query-devtools` | ^6.x | ✅ Active | Lazy-loaded in dev mode only (`isDev` guard in `App.vue`). Not bundled in production build. Provides Query dev panel for inspecting cache, mutations, and refetch triggers. |

## @tanstack/vue-form — Active in Advanced Search

Currently used in `AdvancedSearchDrawer.vue` to manage fielded-search form state and validation, then serialize structured controls to the backend fielded query syntax.

### Planned components
- **Add/Edit photo metadata form** — title, description, tags, source URL, album selection, AI metadata fields
- **Batch metadata editor** — apply tags/title/description to multiple images at once
- **Import settings form** — root path config, search API keys, cron schedule
- **Validation** — use TanStack Form's built-in validation for required fields, URL format, tag constraints

### Migration rule
Do NOT replace every small `v-model` form by default. Use TanStack Form when validation, touched/dirty state, submit modes, or structured serialization would otherwise become bespoke component state.

## @tanstack/vue-table — Active in LibraryInspector, Planned Expansions

Currently used in `LibraryInspector.vue` for a sortable, virtual-scrolling metadata table.
shadcn-vue `<Table>` primitives serve as the UI layer on top of `useVueTable`.

### Planned expansions (not yet implemented)
- **Metadata management table** — sort/filter by filename, album, size, type, date, status
- **Duplicate image finder** — list suspected duplicates with match score
- **Broken image audit** — show files that failed thumbnail generation or have missing originals
- **Import history** — table of crawl/import jobs with status, count, timestamps
- **All photos management** — full scrollable table with batch selection, move, delete

### Migration rule
Do NOT replace the current card/grid gallery view with a table. Table is for admin/management screens, not browsing.

## Resources

- @tanstack/vue-query: https://tanstack.com/query/latest/docs/framework/vue
- @tanstack/vue-virtual: https://tanstack.com/virtual/latest/docs/framework/vue
- @tanstack/vue-form: https://tanstack.com/form/latest/docs/framework/vue
- @tanstack/vue-table: https://tanstack.com/table/latest/docs/framework/vue
