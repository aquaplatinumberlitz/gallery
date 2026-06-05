# AI Art Gallery — Local Collection Browser

<p align="center">
  <img src="https://img.shields.io/badge/Vue.js-3.5-4FC08D?style=flat-square&logo=vue.js" alt="Vue 3.5">
  <img src="https://img.shields.io/badge/FastAPI-0.124-009688?style=flat-square&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Vite-7.2-646CFF?style=flat-square&logo=vite" alt="Vite 7">
  <img src="https://img.shields.io/badge/TypeScript-5.9-3178C6?style=flat-square&logo=typescript" alt="TypeScript 5.9">
  <img src="https://img.shields.io/badge/PhotoSwipe-5.4-000?style=flat-square&logo=photoswipe" alt="PhotoSwipe 5">
  <img src="https://img.shields.io/badge/License-Personal_Use-orange?style=flat-square" alt="License">
</p>

A responsive, local-first web gallery for browsing AI-generated artwork collections (Stable Diffusion, SwarmUI, ComfyUI, NovelAI, EasyDiffusion). Features a virtual-scrolled photo grid, PhotoSwipe 5 lightbox with device-specific metadata panels, and deep AI metadata parsing.

> ⚠️ Designed for **local/personal use** — not intended for public deployment.

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Backend** | FastAPI (Python) | 0.124 |
| **Server** | Uvicorn | 0.38 |
| **Image Processing** | Pillow | 12.0 |
| **Cache** | cachetools (LRU) | 6.2 |
| **Frontend** | Vue 3 (Composition API) | 3.5.24 |
| **Language** | TypeScript | 5.9.3 |
| **Build Tool** | Vite | 7.2.4 |
| **State** | Pinia | 3.0.4 |
| **Lightbox** | PhotoSwipe | 5.4.4 |
| **Virtual Scroll** | vue-virtual-scroller | 3.0.4 |
| **Styling** | SCSS (Dart Sass) | 1.94.2 |
| **Icons** | Lucide Vue Next | 1.0 |
| **HTTP Client** | Axios | 1.13 |

---

## Quick Start

### Development

**Terminal 1 — Backend:**
```bash
cd backend
python3 -m venv .venv_linux
source .venv_linux/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm install   # or: pnpm install
VITE_API_URL=http://127.0.0.1:8000 npm run dev
```

Open **http://localhost:5173**

### Production

Build the frontend, then run the backend in production mode to serve the SPA:

```bash
cd frontend
npm run build
cd ../backend
PRODUCTION=1 uvicorn main:app --host 0.0.0.0 --port 8000
```

The backend serves `frontend/dist/` as a static SPA (with catch-all for client-side routing).

### Auto-Launch (All-in-One)

```bash
python3 start.py
```

Creates venv, installs all dependencies (pip + npm), and starts both servers.

---

## Project Structure

```
gallery-repo/
├── start.py                  # Auto-launch script
├── backend/
│   ├── main.py               # FastAPI server + all API endpoints
│   └── requirements.txt
├── frontend/
│   ├── package.json
│   ├── public/landpage/      # Intro screen HTML templates
│   ├── dist/                 # Production build output
│   └── src/
│       ├── App.vue           # Root orchestrator (dispatches to layout components + Lightbox + modals)
│       ├── main.ts           # Entry point (Pinia + global styles + eruda debug + mount)
│       ├── components/       # GalleryGrid, Lightbox, PhotoSwipeViewer, TabletPhotoSwipe, MobilePhotoSwipe, etc.
│       ├── stores/           # Pinia: gallery.ts, lightbox.ts, toast.ts
│       ├── composables/      # useDevice.ts, useColumnResize.ts, useScrollVisibility.ts, usePhotoSwipe.ts, etc.
│       ├── layouts/          # DesktopLayout.vue, TabletLayout.vue, MobileLayout.vue
│       ├── styles/           # main.scss, tokens.css, _breakpoints.scss, lightbox variants
│       ├── types/index.ts    # TypeScript interfaces
│       └── services/api.ts   # Axios client
└── docs/                     # Architecture & maintenance guides
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/scan?path=...` | Scan directory (folders + paginated images) |
| `GET` | `/api/image?path=...` | Serve original image |
| `GET` | `/api/thumbnail?path=...` | WebP thumbnail (LRU-cached, 1GB) |
| `GET` | `/api/metadata?path=...` | Parse AI generation metadata |
| `POST` | `/api/open-folder` | Open folder in OS file explorer |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/landing-pages` | List intro page templates |

### Metadata Parsing

Auto-detects A1111, SwarmUI, ComfyUI, NovelAI, and EasyDiffusion from PNG chunks (`parameters`, `prompt`, `workflow`) and EXIF. Falls back to `.txt` sidecar files.

---

## Responsive Breakpoints

| Tier | Width | Grid (level 3 default) | Grid range (levels 1–5) | Lightbox | Sidebar |
|------|-------|------------------------|-------------------------|----------|---------|
| **Compact** | <480px | 2 col | 2–3 col | MobilePhotoSwipe + MobileSheet | Overlay |
| **Mobile** | 480–767px | 2 col | 2–3 col | MobilePhotoSwipe + MobileSheet | Overlay |
| **Tablet** | 768–1199px | 4 col | 3–5 col | TabletPhotoSwipe + TabletPanel | 280px drawer |
| **Desktop** | 1200–1439px | 6 col | 4–8 col | PhotoSwipeViewer + DesktopPanel | 280px persistent |
| **Wide** | ≥1440px | 6 col | 4–8 col | PhotoSwipeViewer + DesktopPanel | 280px persistent |

Grid columns are responsive by device category via `GRID_COLUMN_MAP` in `useColumnResize.ts`. The slider controls density level (1–5), which maps to different column counts per device (e.g., level 3 = 6 cols on desktop, 4 on tablet, 2 on mobile).

---

## Architecture Docs

For detailed information about the codebase, data flow, and maintenance, see:

- **[Codebase Architecture & Data Flow](docs/CODEBASE_ARCHITECTURE_AND_DATA_FLOW_MAINTENANCE.md)** — Backend internals, frontend stores/composables, component tree, API endpoints, data flow diagrams, known regression risks.
- **[Frontend UI Interactions & Mobile Maintenance](docs/FRONTEND_UI_INTERACTIONS_AND_MOBILE_MAINTENANCE.md)** — Device-specific UI behavior, PhotoSwipe integration, virtual scroll, scroll visibility, mobile quirks (Safari, touch targets), debug checklist.
- **[Frontend Lightbox Architecture](docs/frontend-lightbox-architecture.md)** — Per-device PhotoSwipe wrappers, shared composable, metadata panels, index/close/toggle flows, regression boundaries.
- **[Responsive Layout & Breakpoints](docs/responsive-layout-and-breakpoints.md)** — Device detection, layout components, grid column mapping, breakpoint sync.
- **[Image Scan & Dimensions](docs/image-scan-and-dimensions.md)** — EXIF handling, dimension extraction, thumbnail pipeline.
- **[UI Components Maintenance](docs/ui-components-maintenance.md)** — EmptyState, sidebar/drawer, toolbar, icon tokens.
- **[Debugging iPad Safari & Eruda](docs/debugging-ipad-safari-eruda.md)** — Debug tools, icon overlay, eruda console.

---

## Key Features

- **Virtual Scrolling** — RecycleScroller handles thousands of images efficiently
- **PhotoSwipe 5 Lightbox** — Device-specific wrappers (PhotoSwipeViewer / TabletPhotoSwipe / MobilePhotoSwipe) with dedicated metadata panels and zoom controls
- **AI Metadata** — Deep parsing of generation parameters (prompt, seed, CFG, LoRAs, etc.) across 5 app formats
- **Dual Theme** — Light (warm cream) + Dark (warm near-black with gold accents)
- **Design Tokens v2** — Primer-inspired `--gallery-*` CSS custom properties with icon size tokens
- **Responsive** — 5 breakpoints, 3 layout components (DesktopLayout / TabletLayout / MobileLayout), per-device grid column mapping
- **Mobile UX** — Hide/show bars on scroll, pull-to-refresh, haptic feedback, 44×44px touch targets, full Ionic compatibility
- **Tablet UX** — Animated drawer sidebar (transform + inert), dedicated TabletPhotoSwipe with bottom toolbar, TabletGalleryToolbar
- **LRU Caching** — 1GB thumbnails, 100MB metadata
- **Accessibility** — WCAG 2.1 with keyboard nav, focus traps, ARIA labels, inert on closed drawers
- **FOUC Prevention** — Inline theme detection before CSS render
- **Dev Debug Tools** — Eruda mobile console (`?eruda=1`), icon debug overlay (`?iconDebug=1`), dev-only safety guards

---

## License

Personal Use Only.
