# Development

Last reviewed: 2026-06-07

## Local Setup

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

All-in-one:

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

## Environment

| Variable | Purpose |
|----------|---------|
| `VITE_API_URL` | Frontend API base URL in development |
| `PRODUCTION=1` | Backend serves the built SPA |
| `GALLERY_ROOT` | Filesystem root allowed by backend path checks |
| `GALLERY_OPEN_FOLDER=true` | Enables `/api/open-folder` |
| `FRONTEND_ORIGIN` / `FRONTEND_PORT` | CORS origin configuration |

If `VITE_API_URL` is empty in development, API calls use the frontend origin. That requires a Vite proxy; otherwise requests such as `/api/scan` hit the Vite dev server instead of FastAPI.

## Debug Tools

### Eruda

Mobile/tablet debug console:

```text
http://<host>/?eruda=1
http://<host>/?eruda=0
```

Implemented in `frontend/src/utils/erudaDebug.ts`. It is dev-only, lazy-loads from CDN, and persists through localStorage until disabled.

Useful checks:

| Check | Where |
|-------|-------|
| Viewport width | Elements or console: `document.documentElement.clientWidth` |
| Network calls | Eruda Network tab for `/api/scan`, `/api/thumbnail`, `/api/metadata` |
| Storage | Eruda Storage tab for `gallery-root-path`, `gallery-grid-size`, `gallery-sort` |
| PhotoSwipe dimensions | Select `.pswp__img` and inspect rendered dimensions |

### Icon Debug Overlay

```text
http://<host>/?iconDebug=1
```

Implemented in `frontend/src/utils/iconDebugOverlay.ts`. It is dev-only and URL-only, with no localStorage persistence. Use it to inspect Lucide rendered sizes, copy a JSON report, and force toolbar/header SVG dimensions during debugging.

## Common Maintenance Checks

Before changing layout or lightbox behavior:

- Test widths around `767/768px` and `1199/1200px`.
- Verify desktop lightbox image, counter, and next arrow remain outside the metadata sidebar.
- Verify tablet drawer opens/closes with hamburger, backdrop, Escape, and successful path submit.
- Verify mobile header/bottom bar hide/show behavior during scroll.
- Verify mobile metadata sheet drag/snap/scroll is owned by VSBS and content still scrolls normally.
- For mobile lightbox sheet changes, run the full checklist in [Troubleshooting](TROUBLESHOOTING.md#mobile-lightbox-sheet-checklist).

Before changing metadata or thumbnail code:

- Test PNG metadata from at least one supported generator.
- Test an image with EXIF orientation.
- Test an image large enough to exercise thumbnail generation.
- Confirm cache keys still include file mtime and size.

## Useful Files

| Concern | Files |
|---------|-------|
| API calls | `frontend/src/services/api.ts`, `backend/app.py`, `backend/main.py` |
| Device detection | `frontend/src/composables/useDevice.ts` |
| Breakpoint mixins | `frontend/src/styles/_breakpoints.scss` |
| Grid density | `frontend/src/composables/useColumnResize.ts` |
| Virtual grid | `frontend/src/components/GalleryGrid.vue` |
| Lightbox orchestration | `frontend/src/components/Lightbox.vue` |
| PhotoSwipe lifecycle | `frontend/src/composables/usePhotoSwipe.ts` |
| Mobile lightbox sheet | `frontend/src/components/LightboxMobileSheet.vue`, `frontend/src/styles/_lightbox-mobile.scss` |
| Metadata parsing | `backend/metadata_parse.py`, `backend/metadata_extract.py` |

## Documentation Maintenance

- Keep root `README.md` short: overview, quick start, feature list, and links.
- Put durable system behavior in `docs/ARCHITECTURE.md`.
- Put setup and debugging commands here.
- Put visual and interaction rules in `docs/UI_UX_GUIDELINES.md`.
- Put symptoms, gotchas, and regression checks in `docs/TROUBLESHOOTING.md`.
- Put backend scan, dimension, thumbnail, and metadata parser details in `docs/METADATA_PARSING.md`.
