# AI Art Gallery

Last reviewed: 2026-06-10

A local-first web gallery for browsing AI-generated artwork collections. It pairs a FastAPI backend for scanning, thumbnails, and metadata parsing with a Vue 3 frontend that provides a responsive TanStack Virtual gallery and PhotoSwipe-based lightbox.

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

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Uvicorn, Pillow, diskcache, cachetools, SQLite |
| Backend Modules | metadata_store, fielded_search_parser, indexer, facets, refresh, watcher |
| Frontend | Vue 3, TypeScript, Vite, Pinia |
| Lightbox | PhotoSwipe 5 |
| Grid | @tanstack/vue-virtual |
| Server Cache | @tanstack/vue-query |
| Local Reactive DB | @tanstack/vue-db, @tanstack/query-db-collection |
| Styling | SCSS, CSS custom properties |
| Icons | Lucide Vue Next |

## Quick Start

Backend:

```bash
cd backend
python3 -m venv .venv_linux
source .venv_linux/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
VITE_API_URL=http://127.0.0.1:8000 npm run dev
```

Open `http://localhost:5173`.

All-in-one launcher:

```bash
python3 start.py
```

Production:

```bash
cd frontend
npm run build
cd ../backend
PRODUCTION=1 uvicorn main:app --host 0.0.0.0 --port 8000
```

In production mode the backend serves `frontend/dist/` as a static SPA with client-side routing fallback.

## Project Structure

```text
gallery-repo/
├── start.py
├── backend/
│   ├── main.py
│   ├── app.py
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
│       ├── test_scan_folder_counts.py
│       ├── test_scan_hot_path.py
│       ├── test_scheduled_refresh.py
│       ├── test_warm_folder_listing.py
│       └── test_watcher.py
├── frontend/
│   ├── package.json
│   ├── public/landpage/
│   ├── tests/
│   │   ├── gallery-cache-revisit.spec.ts
│   │   ├── gallery-no-reload.spec.ts
│   │   ├── gallery-no-reload-real-backend.spec.ts
│   │   ├── lightbox-loading-policy.spec.ts
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
│       ├── composables/
│       ├── layouts/
│       ├── services/
│       ├── stores/
│       ├── styles/
│       └── types/
├── scripts/
│   ├── test_all.sh
│   ├── test_backend_api_integration.sh
│   ├── test_frontend_contract.sh
│   └── test_perf_smoke.sh
└── docs/
```

## API Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/scan?path=...&scope=...` | Scan folders and paginated images; scope controls scan depth |
| `GET` | `/api/image?path=...` | Serve an original image |
| `GET` | `/api/thumbnail?path=...` | Serve a cached WebP thumbnail (max 512px) |
| `GET` | `/api/preview?path=...` | Serve a cached WebP preview (max 1440px) |
| `GET` | `/api/metadata?path=...` | Parse AI generation metadata |
| `GET` | `/api/search` | Unified photo/album/prompt search |
| `GET` | `/api/search-metadata` | Legacy metadata text search (prompt/model/filename) |
| `GET` | `/api/facets` | Faceted aggregation counts (tool, model, sampler, etc.) |
| `GET` | `/api/index/status` | Metadata indexer queue/runtime status |
| `POST` | `/api/open-folder` | Open a folder in the OS file explorer when enabled |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/landing-pages` | List intro page templates |

## Documentation

- [Test Strategy](docs/TEST_STRATEGY.md) - 325 tests across backend API integration, Playwright contract, and perf tiers
- [API Integration Testing](docs/API_INTEGRATION_TESTING.md) - isolated backend integration test fixtures and patterns
- [Architecture](docs/ARCHITECTURE.md) - frontend/backend architecture, data flow, lightbox design
- [Development](docs/DEVELOPMENT.md) - setup, commands, debugging tools, maintenance practices
- [UI/UX Guidelines](docs/UI_UX_GUIDELINES.md) - breakpoints, layout rules, mobile behavior, theme rules
- [Troubleshooting](docs/TROUBLESHOOTING.md) - known issues, Safari/iOS gotchas, regression checks
- [Metadata Parsing](docs/METADATA_PARSING.md) - backend scan, thumbnail, metadata, and dimension pipelines
- [Evolution Master Plan](docs/GALLERY_REPO_EVOLUTION_MASTER_PLAN_codex.md) - phased roadmap (Phases 0-3 done)
- [Lightbox Loading Policy](docs/LIGHTBOX_IMAGE_LOADING_POLICY.md) - derivative-first lightbox rules and guarantees
- [Performance Testing](docs/PERFORMANCE_TESTING.md) - perf budgets, test methodology, results
- [Performance Comparison Report](docs/perf_compare_report.md) - Phase 2A lightbox perf comparison
- [DiffusionToolkit Pipeline Audit](docs/DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md) - comparison with DiffusionToolkit metadata, indexing, thumbnail, and lightbox pipeline
- [DiffusionToolkit Metadata Parse Analysis](docs/DIFFUSIONTOOLKIT_METADATA_PARSE_ANALYSIS.md) - parser-specific lessons and proposed gallery metadata parser improvements
- [DiffusionToolkit Metadata Search Analysis](docs/DIFFUSIONTOOLKIT_METADATA_SEARCH_ANALYSIS.md) - search-query lessons and proposed fielded metadata search backlog
- [Immich Pipeline Audit](docs/IMMICH_PIPELINE_AUDIT.md) - comparison with Immich pipeline
- [Media Pipeline Comparison](docs/MEDIA_PIPELINE_COMPARISON.md) - gallery-repo vs DT vs Immich pipeline comparison
- [Backend Library Research](docs/BACKEND_LIBRARY_REPLACEMENT_RESEARCH.md) - library replacement analysis
- [TanStack Migration Plan](docs/TANSTACK_MIGRATION_PLAN.md) - incremental TanStack Query migration
- [Library Usage](docs/THIRD_PARTY_LIBRARIES.md) - third-party library integration notes
- [TanStack Guide](frontend/src/lib/tanstack/README.md) - TanStack Query + Virtual usage (Form + Table: foundation only)

## License

Personal Use Only.
