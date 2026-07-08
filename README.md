# AI Art Gallery

Last reviewed: 2026-07-08

A local-first web gallery for browsing AI-generated image and video collections. It pairs a FastAPI backend for registered-library management, mixed-media scanning, image derivatives, video streaming/posters, indexed metadata search, and read-only metadata inspection with a Vue 3 frontend that provides a responsive TanStack Virtual gallery, PhotoSwipe-based image lightbox, native video player, and virtualized desktop Library Inspector.

Designed for local/personal use. It is not intended as a hardened public deployment.

## Features

- Responsive desktop, tablet, and mobile layouts
- Registered libraries with multiple import paths, exclusion patterns, scan/repair jobs, and responsive management UI
- TanStack Virtual-scrolled mixed-media grid for large folders
- Native video playback with HTTP Range streaming and cached WebP posters
- PhotoSwipe 5 lightbox with device-specific metadata panels
- Derivative-first lightbox — 1440px WebP preview as the main PhotoSwipe source; original `/api/image` only on zoom, fullscreen, download, or animated images
- AI metadata parsing for A1111, SwarmUI, ComfyUI, NovelAI, and EasyDiffusion
- WebP thumbnail generation with diskcache persistent caching
- Light and dark themes using gallery design tokens
- Mobile/tablet debugging helpers for Safari and icon sizing
- Durable background metadata indexer with coalesced SQLite jobs and lifecycle/runtime status in library and maintenance status APIs
- Fielded metadata search (`prompt:`, `seed:`, `model:`, `steps:`, etc.) with a dedicated parser; warm metadata reads from SQLite without re-parsing PNG chunks
- Warm indexed folder listing (SQLite-first, `os.stat` + SQLite only) with optional scheduled refresh and file-watcher support
- DB-derived faceted aggregation endpoint (`/api/facets`) for tool, model, sampler, and other metadata dimensions
- Desktop Library Inspector at `/metadata` for read-only AI photo metadata inspection with prompt/negative/LoRA search, DB-first detail popovers, copy actions, shadcn-vue Select toolbar filters/sort, TanStack Table returned-row sorting, and TanStack Virtual table rows

## Tech Stack

| Layer                     | Technology                                                               |
| ------------------------- | ------------------------------------------------------------------------ |
| Backend                   | FastAPI, Uvicorn, Pydantic, Pillow, diskcache, cachetools, SQLite FTS5   |
| Backend Modules           | metadata_store, fielded_search_parser, indexer, facets, refresh, watcher |
| Frontend                  | Vue 3, TypeScript, Vite, Vue Router, Pinia                               |
| Lightbox                  | PhotoSwipe 5                                                             |
| Grid/Table Virtualization | @tanstack/vue-virtual                                                    |
| Server Cache              | @tanstack/vue-query                                                      |
| Advanced Search Form      | @tanstack/vue-form                                                       |
| Metadata Table            | @tanstack/vue-table                                                      |
| Local Reactive DB         | @tanstack/vue-db, @tanstack/query-db-collection                          |
| UI Components             | Local shadcn-vue-style components, Reka UI, CVA, clsx, tailwind-merge    |
| Styling                   | Tailwind CSS 4, SCSS, CSS custom properties                              |
| HTTP Client               | Axios                                                                    |
| Icons                     | lucide-vue-next                                                          |

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
./test.sh lint
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
./test.sh fast
```

Full CI-equivalent validation, including docs/test-catalog checks, deterministic functional E2E, and performance tests:

```bash
./test.sh full
```

All Ruff, ESLint, and Prettier gates scan the full codebase.
Run `./test.sh help` for focused commands such as `lint`, `unit`, `e2e`, and `perf`.

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
│   ├── libraries.py
│   ├── library_events.py
│   ├── metadata_extract.py
│   ├── metadata_parse.py
│   ├── metadata_store/
│   ├── models.py
│   ├── paths.py
│   ├── refresh.py
│   ├── requirements-dev.txt
│   ├── requirements.txt
│   ├── scan.py
│   ├── search.py
│   ├── static_files.py
│   ├── thumbnails.py
│   ├── video.py
│   ├── watcher.py
│   └── tests/
│       ├── conftest.py
│       ├── test_api_integration_derivatives.py
│       ├── test_api_integration_health_and_safety.py
│       ├── test_api_integration_metadata_search_facets.py
│       ├── test_app.py
│       ├── test_derivatives.py
│       ├── test_facets.py
│       ├── test_fielded_search_parser.py
│       ├── test_indexer_staging.py
│       ├── test_library_inspector.py
│       ├── test_metadata_binary_sanitizer.py
│       ├── test_scan_folder_counts.py
│       ├── test_scan_worker.py
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
│   ├── internal/
│   │   ├── perf-smoke.sh
│   │   └── test-playwright.sh
│   └── *.py
├── test.sh
└── docs/
```

## API Summary

| Method                 | Endpoint                                        | Purpose                                                                                         |
| ---------------------- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `GET`                  | `/api/browse?library_id=...&path=...`           | Read-only catalog listing for a library root or folder with cursor pagination                   |
| `GET`                  | `/api/folders?path=...`                         | Return direct child folders for sidebar expansion                                               |
| `GET`                  | `/api/image?path=...`                           | Serve an original image                                                                         |
| `GET`                  | `/api/thumbnail?path=...`                       | Serve a cached WebP thumbnail (max 512px)                                                       |
| `GET`                  | `/api/preview?path=...`                         | Serve a cached WebP preview (max 1440px)                                                        |
| `GET`                  | `/api/video?path=...`                           | Stream an original video with HTTP Range support                                                |
| `GET`                  | `/api/video/poster?path=...`                    | Serve a cached WebP video poster                                                                |
| `GET`                  | `/api/metadata?path=...`                        | Parse AI generation metadata                                                                    |
| `GET`                  | `/api/search`                                   | Unified photo/album/prompt search                                                               |
| `GET`                  | `/api/search-metadata`                          | Legacy metadata text search (prompt/model/filename)                                             |
| `GET`                  | `/api/library/inspector`                        | Bounded read-only metadata inspection rows; empty `q` returns latest indexed metadata           |
| `GET`                  | `/api/library/inspector/metadata?path=...`      | DB-first full prompt/negative/LoRA/resource metadata detail for inspector popovers/copy actions |
| `GET`                  | `/api/facets`                                   | Faceted aggregation counts (tool, model, sampler, etc.)                                         |
| `GET`                  | `/api/maintenance/runtime`                      | Global catalog, metadata, watcher, refresh, and lifecycle runtime diagnostics                    |
| `POST`                 | `/api/open-folder`                              | Open a folder in the OS file explorer when enabled                                              |
| `GET`                  | `/api/health`                                   | Health check                                                                                    |
| `GET`                  | `/api/landing-pages`                            | List intro page templates                                                                       |
| `GET/POST`             | `/api/libraries`                                | List or register libraries                                                                      |
| `GET`                  | `/api/libraries/{id}/status`                    | Unified catalog status for a library or scoped path                                             |
| `POST`                 | `/api/libraries/{id}/scan`                      | Queue a background update for a registered library                                              |
| `GET/PATCH/PUT/DELETE` | `/api/libraries/{id}`                           | Read, update, or unregister a library                                                           |

`GET /api/browse` accepts only `library_id`, `path`, `cursor`, `limit`, and
`include_offline`. It returns `folders`, `media`, `next_media_cursor`,
`total_images`, `total_videos`, `total_assets`, and `index_source`. Undeclared
query parameters return `422`.

## Documentation

- [AI Agent Handoff](AGENTS.md) - repo working rules, reading order, source-of-truth guardrails, and test minimums for AI agents
- [Documentation Index](docs/README.md) - maintained references, testing, research, reports, plans, and archived context
- [Architecture](docs/ARCHITECTURE.md) - frontend/backend boundaries, data flow, and runtime contracts
- [Testing Guide](docs/testing/README.md) - test selection, performance testing, catalog, and debug tools
- [TanStack Guide](frontend/src/lib/tanstack/README.md) - TanStack Query, Virtual, Form, and Table usage

## License

Personal Use Only.
