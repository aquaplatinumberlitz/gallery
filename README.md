# AI Art Gallery

Last reviewed: 2026-06-16

A local-first web gallery for browsing AI-generated artwork collections. It pairs a FastAPI backend for scanning, thumbnails, indexed metadata search, and read-only metadata inspection with a Vue 3 frontend that provides a responsive TanStack Virtual gallery, PhotoSwipe-based lightbox, and virtualized desktop Library Inspector.

Designed for local/personal use. It is not intended as a hardened public deployment.

## Features

- Responsive desktop, tablet, and mobile layouts
- TanStack Virtual-scrolled image grid for large folders
- PhotoSwipe 5 lightbox with device-specific metadata panels
- Derivative-first lightbox — 1440px WebP preview as the main PhotoSwipe source; original `/api/image` only on zoom, fullscreen, download, or animated images
- AI metadata parsing for A1111, SwarmUI, ComfyUI, NovelAI, and EasyDiffusion
- WebP thumbnail generation with diskcache persistent caching
- Light and dark themes using gallery design tokens
- Mobile/tablet debugging helpers for Safari and icon sizing
- Background metadata indexer with coalesced job queue and batched SQLite writer, exposing an index status endpoint
- Fielded metadata search (`prompt:`, `seed:`, `model:`, `steps:`, etc.) with a dedicated parser; warm metadata reads from SQLite without re-parsing PNG chunks
- Warm indexed folder listing (SQLite-first, `os.stat` + SQLite only) with optional scheduled refresh and file-watcher support
- DB-derived faceted aggregation endpoint (`/api/facets`) for tool, model, sampler, and other metadata dimensions
- Desktop Library Inspector at `/metadata` for read-only AI photo metadata inspection with prompt/negative/LoRA search, DB-first detail popovers, copy actions, shadcn-vue Select toolbar filters/sort, TanStack Table returned-row sorting, and TanStack Virtual table rows

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Uvicorn, Pydantic, Pillow, diskcache, cachetools, SQLite FTS5 |
| Backend Modules | metadata_store, fielded_search_parser, indexer, facets, refresh, watcher |
| Frontend | Vue 3, TypeScript, Vite, Vue Router, Pinia |
| Lightbox | PhotoSwipe 5 |
| Grid/Table Virtualization | @tanstack/vue-virtual |
| Server Cache | @tanstack/vue-query |
| Advanced Search Form | @tanstack/vue-form |
| Metadata Table | @tanstack/vue-table |
| Local Reactive DB | @tanstack/vue-db, @tanstack/query-db-collection |
| UI Components | Local shadcn-vue-style components, Reka UI, CVA, clsx, tailwind-merge |
| Styling | Tailwind CSS 4, SCSS, CSS custom properties |
| HTTP Client | Axios |
| Icons | lucide-vue-next |

## Quick Start

Backend:

```bash
python3 -m venv backend/.venv_linux
source backend/.venv_linux/bin/activate
pip install -r backend/requirements.txt
python3 -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Backend development tools:

```bash
pip install -r backend/requirements-dev.txt
scripts/lint_backend.sh
scripts/format_backend_check.sh
```

Frontend:

```bash
cd frontend
corepack pnpm install
VITE_API_URL=http://127.0.0.1:8000 corepack pnpm run dev
```

Open `http://localhost:5173`.

All-in-one launcher:

```bash
python3 start.py
```

Production:

```bash
cd frontend
corepack pnpm run build
cd ..
PRODUCTION=1 python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

In production mode the backend serves `frontend/dist/` as a static SPA with client-side routing fallback.

Quality checks:

```bash
scripts/lint_backend.sh
scripts/format_backend_check.sh
cd frontend
corepack pnpm run lint
corepack pnpm run format:check
corepack pnpm run typecheck
```

Backend Ruff checks and frontend Prettier checks run against changed files by default, using `origin/main` as the base when available. This avoids forcing a full historical reformat while still protecting new changes.

## Project Structure

```text
gallery-repo/
├── start.py
├── backend/
│   ├── main.py
│   ├── app.py
│   ├── albums.py
│   ├── config.py
│   ├── errors.py
│   ├── facets.py
│   ├── fielded_search_parser.py
│   ├── files.py
│   ├── folders.py
│   ├── health.py
│   ├── images.py
│   ├── indexer.py
│   ├── metadata_extract.py
│   ├── metadata_parse.py
│   ├── metadata_store.py
│   ├── models.py
│   ├── paths.py
│   ├── refresh.py
│   ├── requirements-dev.txt
│   ├── requirements.txt
│   ├── scan.py
│   ├── search.py
│   ├── static_files.py
│   ├── thumbnails.py
│   ├── watcher.py
│   └── tests/
│       ├── conftest.py
│       ├── test_api_integration_derivatives.py
│       ├── test_api_integration_health_and_safety.py
│       ├── test_api_integration_index_status.py
│       ├── test_api_integration_metadata_search_facets.py
│       ├── test_api_integration_scan.py
│       ├── test_app.py
│       ├── test_derivatives.py
│       ├── test_facets.py
│       ├── test_fielded_search_parser.py
│       ├── test_indexer_staging.py
│       ├── test_library_inspector.py
│       ├── test_metadata_binary_sanitizer.py
│       ├── test_scan_folder_counts.py
│       ├── test_scan_hot_path.py
│       ├── test_scheduled_refresh.py
│       ├── test_warm_folder_listing.py
│       └── test_watcher.py
├── frontend/
│   ├── eslint.config.js
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── public/landpage/
│   ├── scripts/
│   ├── tests/
│   │   ├── gallery-cache-revisit.spec.ts
│   │   ├── gallery-no-reload.spec.ts
│   │   ├── gallery-no-reload-real-backend.spec.ts
│   │   ├── lightbox-loading-policy.spec.ts
│   │   ├── library-inspector.spec.ts
│   │   ├── metadata-performance.spec.ts
│   │   ├── mobile-lightbox-sheet.spec.ts
│   │   ├── responsive-breakpoints.spec.ts
│   │   ├── search-fielded-ui.spec.ts
│   │   └── perf/
│   │       ├── album-open.perf.spec.ts
│   │       ├── lightbox.perf.spec.ts
│   │       └── perf-utils.ts
│   └── src/
│       ├── App.vue
│       ├── components/
│       ├── db/
│       ├── composables/
│       ├── layouts/
│       ├── query/
│       ├── router/
│       ├── services/
│       ├── stores/
│       ├── styles/
│       └── types/
├── scripts/
│   ├── format_backend_check.sh
│   ├── lint_backend.sh
│   ├── test-all.sh
│   ├── test-backend.sh
│   ├── test-frontend.sh
│   ├── test_backend_api_integration.sh
│   ├── test-e2e.sh
│   └── test_perf_smoke.sh
└── docs/
```

## API Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/scan?path=...&image_limit=...&image_cursor=...` | Scan a folder and return albums plus paginated images |
| `GET` | `/api/folders?path=...` | Return direct child folders for sidebar expansion |
| `GET` | `/api/image?path=...` | Serve an original image |
| `GET` | `/api/thumbnail?path=...` | Serve a cached WebP thumbnail (max 512px) |
| `GET` | `/api/preview?path=...` | Serve a cached WebP preview (max 1440px) |
| `GET` | `/api/metadata?path=...` | Parse AI generation metadata |
| `GET` | `/api/search` | Unified photo/album/prompt search |
| `GET` | `/api/search-metadata` | Legacy metadata text search (prompt/model/filename) |
| `GET` | `/api/library/inspector` | Bounded read-only metadata inspection rows; empty `q` returns latest indexed metadata |
| `GET` | `/api/library/inspector/metadata?path=...` | DB-first full prompt/negative/LoRA/resource metadata detail for inspector popovers/copy actions |
| `GET` | `/api/facets` | Faceted aggregation counts (tool, model, sampler, etc.) |
| `GET` | `/api/index/status` | Metadata indexer queue/runtime status |
| `POST` | `/api/open-folder` | Open a folder in the OS file explorer when enabled |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/landing-pages` | List intro page templates |

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - frontend/backend architecture, data flow, lightbox design
- [Library Usage](docs/THIRD_PARTY_LIBRARIES.md) - third-party library integration notes
- [UI/UX Guidelines](docs/UI_UX_GUIDELINES.md) - breakpoints, layout rules, mobile behavior, theme rules
- [Test Strategy](docs/test-debug-perf/TEST_STRATEGY.md) - backend, Playwright contract, and perf tiers
- [Performance Testing](docs/test-debug-perf/PERFORMANCE_TESTING.md) - perf budgets, test methodology, results
- [Performance Comparison Report](docs/test-debug-perf/perf_compare_report.md) - lightbox perf comparison notes
- [Evolution Master Plan](docs/plan/GALLERY_REPO_EVOLUTION_MASTER_PLAN_codex.md) - phased roadmap
- [TanStack Migration Plan](docs/plan/TANSTACK_MIGRATION_PLAN.md) - incremental TanStack Query migration
- [Shadcn Sidebar Migration Plan](docs/plan/SHADCN_SIDEBAR_MIGRATION_PLAN.md) - sidebar migration notes
- [Tailwind Migration Plan](docs/plan/TAILWIND_MIGRATION_ANIMATION_PRESERVATION_PLAN.md) - Tailwind migration and animation preservation notes
- [Shadcn Component Audit](docs/reports/SHADCN_COMPONENT_AUDIT.md) - local UI component audit
- [Library Inspector UX Research](docs/research/library-inspector-ux-patterns.md) - metadata inspector UX references
- [DiffusionToolkit Pipeline Audit](<docs/DT&IMMICH analysis/DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md>) - comparison with DiffusionToolkit metadata, indexing, thumbnail, and lightbox pipeline
- [DiffusionToolkit Metadata Parse Analysis](<docs/DT&IMMICH analysis/DIFFUSIONTOOLKIT_METADATA_PARSE_ANALYSIS.md>) - parser-specific lessons and proposed metadata parser improvements
- [DiffusionToolkit Metadata Search Analysis](<docs/DT&IMMICH analysis/DIFFUSIONTOOLKIT_METADATA_SEARCH_ANALYSIS.md>) - search-query lessons and fielded metadata search backlog
- [Immich Pipeline Audit](<docs/DT&IMMICH analysis/IMMICH_PIPELINE_AUDIT.md>) - comparison with Immich pipeline
- [Media Pipeline Comparison](<docs/DT&IMMICH analysis/MEDIA_PIPELINE_COMPARISON.md>) - gallery-repo vs DiffusionToolkit vs Immich pipeline comparison
- [TanStack Guide](frontend/src/lib/tanstack/README.md) - TanStack Query, Virtual, Form, and Table usage

## License

Personal Use Only.
