# TanStack Usage Guide

This frontend uses TanStack libraries for state management, data display, and form handling.

## Installed Packages

| Package | Version | Status | Purpose |
|---------|---------|--------|---------|
| `@tanstack/vue-query` | ^5.x | ✅ Active | Server-state caching for gallery scans, thumbnail cache invalidation, background refetch. Setup in `src/query/index.ts`. |
| `@tanstack/vue-virtual` | ^3.x | ✅ Active | Row-based virtual scrolling for desktop/tablet photo grid. Uses `useVirtualizer` in `GalleryGrid.vue`. |
| `@tanstack/vue-form` | latest | 🟡 Foundation | Future: metadata forms (title, description, tags), batch editor, settings. See notes below. |
| `@tanstack/vue-table` | latest | 🟡 Foundation | Future: metadata management table, duplicate/broken image audit, import history. See notes below. |

## @tanstack/vue-form — Future Use

### Planned components
- **Add/Edit photo metadata form** — title, description, tags, source URL, album selection, AI metadata fields
- **Batch metadata editor** — apply tags/title/description to multiple images at once
- **Import settings form** — root path config, search API keys, cron schedule
- **Validation** — use TanStack Form's built-in validation for required fields, URL format, tag constraints

### Migration rule
Do NOT replace current v-model forms until a dedicated metadata editing feature is being built. Current forms are minimal (search, path entry) and work fine with v-model.

## @tanstack/vue-table — Future Use

### Planned components
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
