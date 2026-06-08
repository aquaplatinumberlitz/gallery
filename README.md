# AI Art Gallery

Last reviewed: 2026-06-08

A local-first web gallery for browsing AI-generated artwork collections. It pairs a FastAPI backend for scanning, thumbnails, and metadata parsing with a Vue 3 frontend that provides a responsive TanStack Virtual gallery and PhotoSwipe-based lightbox.

Designed for local/personal use. It is not intended as a hardened public deployment.

## Features

- Responsive desktop, tablet, and mobile layouts
- Virtual-scrolled image grid for large folders
- PhotoSwipe 5 lightbox with device-specific metadata panels
- AI metadata parsing for A1111, SwarmUI, ComfyUI, NovelAI, and EasyDiffusion
- WebP thumbnail generation with LRU caching
- Light and dark themes using gallery design tokens
- Mobile/tablet debugging helpers for Safari and icon sizing

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Uvicorn, Pillow, cachetools |
| Frontend | Vue 3, TypeScript, Vite, Pinia |
| Lightbox | PhotoSwipe 5 |
| Grid | @tanstack/vue-virtual |
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
│   └── requirements.txt
├── frontend/
│   ├── package.json
│   ├── public/landpage/
│   └── src/
│       ├── App.vue
│       ├── components/
│       ├── composables/
│       ├── layouts/
│       ├── services/
│       ├── stores/
│       ├── styles/
│       └── types/
└── docs/
```

## API Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/scan?path=...` | Scan folders and paginated images |
| `GET` | `/api/image?path=...` | Serve an original image |
| `GET` | `/api/thumbnail?path=...` | Serve a cached WebP thumbnail |
| `GET` | `/api/metadata?path=...` | Parse AI generation metadata |
| `POST` | `/api/open-folder` | Open a folder in the OS file explorer when enabled |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/landing-pages` | List intro page templates |

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - frontend/backend architecture, data flow, lightbox design
- [Development](docs/DEVELOPMENT.md) - setup, commands, debugging tools, maintenance practices
- [UI/UX Guidelines](docs/UI_UX_GUIDELINES.md) - breakpoints, layout rules, mobile behavior, theme rules
- [Troubleshooting](docs/TROUBLESHOOTING.md) - known issues, Safari/iOS gotchas, regression checks
- [Metadata Parsing](docs/METADATA_PARSING.md) - backend scan, thumbnail, metadata, and dimension pipelines

## License

Personal Use Only.
