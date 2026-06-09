Update the README.md and docs to reflect current project state after recent migrations.

Repo: /home/ubuntu/gallery-repo (branch main, already at latest)

## What changed recently (needs doc updates):

1. vue-virtual-scroller → @tanstack/vue-virtual (row-based virtual scroll in GalleryGrid)
2. LRU thumbnail cache → diskcache persistent cache (already in backend)
3. TanStack Query installed and partially used (scan API cache)
4. @tanstack/vue-form installed (foundation, not yet in use)
5. @tanstack/vue-table installed (foundation, not yet in use)
6. @tanstack/vue-query-devtools installed (dev-only)
7. nginx production mode (VPS serves dist/ instead of Vite proxy)
8. src/lib/tanstack/README.md exists with documentation

## Files to update:

### README.md

Line 12: "Virtual-scrolled image grid" → "TanStack Virtual-scrolled image grid"
Line 15: "LRU caching" → "diskcache persistent caching"

Update the tech stack table (lines 19-28) to include all current TanStack packages:

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Uvicorn, Pillow, diskcache, cachetools |
| Frontend | Vue 3, TypeScript, Vite, Pinia |
| Lightbox | PhotoSwipe 5 |
| Grid | @tanstack/vue-virtual |
| Server Cache | @tanstack/vue-query |
| Styling | SCSS, CSS custom properties |
| Icons | Lucide Vue Next |

Update the API Summary table: add the search endpoints that exist but aren't listed:
- GET /api/search — unified photo/album/prompt search
- GET /api/search-metadata — legacy metadata search (deprecated)

Update the Documentation section (lines 104-110) to add a reference to the library usage guide:
- [Library Usage](docs/THIRD_PARTY_LIBRARIES.md) — third-party library integration notes
- [TanStack Guide](src/lib/tanstack/README.md) — TanStack Query, Virtual, Form, Table usage

### docs/THIRD_PARTY_LIBRARIES.md

Add @tanstack/vue-form and @tanstack/vue-table to the Quick Index table (around line 9-23):

| @tanstack/vue-form | Future: metadata forms, batch editor, settings | foundation only; not yet in use |
| @tanstack/vue-table | Future: metadata management table, admin views | foundation only; not yet in use |

Add detail sections for each (after the @tanstack/vue-virtual section, around line 204-205):

#### @tanstack/vue-form

- Library: TanStack Form (type-safe Vue form validation)
- Official Vue docs: https://tanstack.com/form/latest/docs/framework/vue
- Status: Foundation installed, not yet used in any component
- Planned use: photo metadata editing, batch editor, import settings
- See src/lib/tanstack/README.md for details

#### @tanstack/vue-table

- Library: TanStack Table (headless datagrid/table)
- Official Vue docs: https://tanstack.com/table/latest/docs/framework/vue
- Status: Foundation installed, not yet used in any component
- Planned use: metadata management table, duplicate/broken image audit, import history
- See src/lib/tanstack/README.md for details

#### @tanstack/vue-query-devtools

- Library: TanStack Query Devtools
- npm: @tanstack/vue-query-devtools
- Status: Installed as devDependency, active in dev mode only
- Usage: Floating devtools panel visible in browser during development; tree-shaken in production

### docs/ARCHITECTURE.md

No changes needed — already mentions TanStack Virtual correctly ("virtualizes large grids"). But verify line 9-10 mentions "TanStack Virtual" or "virtual scroll" correctly. If it still says "vue-virtual-scroller" anywhere, fix it.

## HARD RULES
- ONLY modify README.md, docs/THIRD_PARTY_LIBRARIES.md, docs/ARCHITECTURE.md
- Do NOT touch any .vue/.ts/.scss source code
- No git operations
- Keep descriptions concise and factual
