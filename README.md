# ࿓ Aetheris — AI Art Gallery

A refined gallery interface for browsing, curating, and presenting AI-generated artwork. Designed for artists who work with generative models — browse thousands of generations across folder hierarchies, inspect LORA metadata at a glance, and navigate your collection in a lightbox experience that puts the art first.

Built with **Vue 3 + TypeScript + Pinia** on a responsive grid layout, served via a FastAPI backend that scans local directories and streams thumbnails on demand.

---

## Features

- **Gallery Grid** — Responsive album cards with cover-image thumbnails, infinite scroll, and slideshow playback.
- **Lightbox** — Full-viewport image inspection with keyboard navigation (← →), swipe support, and LORA metadata overlay.
- **Folder Tree + Breadcrumb** — Recursive sidebar file browser with lazy-loaded children, breadcrumb path navigation, and back/forward history.
- **Search & Sort** — Real-time filename filtering, sort by name or date (ascending/descending).
- **Metadata Viewer** — Extracts and highlights generation parameters: model, sampler, CFG scale, seed, steps, and LORA identifiers.
- **Dark / Light Theme** — Dual pastel-dreamscape palettes with neon glow effects in dark mode.
- **Empty States** — Context-aware illustrations for empty folders, no search results, errors, and loading.
- **Toast Notifications** — Success/error feedback with retry actions and album/image count summaries.
- **Accessible** — WCAG 2.1 AA focus indicators, skip-link navigation, reduced-motion support, high-contrast mode, and 44 px minimum touch targets.
- **Responsive** — Adaptive 1–8 column grid (desktop 5, tablet 3, phone 2) with horizontal top bar + sidebar on desktop and 2-row toolbar on mobile.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Vue 3, TypeScript, Pinia, Vite 7 |
| **Styling** | SCSS custom properties, pastel dreamscape palette |
| **UI Icons** | Lucide-vue-next (chevrons, loaders, close, settings) |
| **Brand Icons** | FontAwesome Pro SVGs (metadata-stripped) for empty states |
| **API Client** | Axios with typed error classification |
| **Backend** | FastAPI (Python) — local file scanning, thumbnail streaming |
| **Fonts** | Cinzel (brand), InterVariable (UI), JetBrains Mono (code) |
| **Deployment** | Static build served via Python HTTP server on Oracle Cloud VPS |
| **Orchestration** | pnpm, vue-tsc type checking |

---

## Getting Started

### Prerequisites

- **Node.js** ≥ 18
- **pnpm** (recommended) or npm
- **Python** ≥ 3.10 (for the backend API)

### Local Development

```bash
# 1. Clone & install frontend dependencies
cd gallery/frontend
pnpm install

# 2. Start Vite dev server (port 5173 by default)
pnpm dev

# 3. In a separate terminal, start the FastAPI backend
#    (pointing to your image directory)
cd gallery/backend  # or wherever your API lives
uvicorn main:app --reload --port 8000
```

The frontend expects the API at `http://localhost:8000` by default. Override via the `VITE_API_URL` environment variable.

### Production Build

```bash
cd gallery/frontend
pnpm build          # outputs to dist/
```

Serve the `dist/` directory with any HTTP server:

```bash
python3 -m http.server 4173 --directory dist/
```

The production instance runs on **Oracle Cloud VPS** (`150.230.56.153:4173`) behind iptables port range `4170–4180`.

---

## Theme & Design

The visual identity takes inspiration from **museum exhibition catalogues** — sparing ornament, generous whitespace, and deliberate typographic hierarchy.

### Dark Mode
- **Primary palette:** Gold `#d6a15d`, bronze `#b97845`, deep charcoal background (`#080808`)
- **Title treatment:** Warm gold-to-cream gradient with multi-layer `drop-shadow` glow and shimmer animation
- **Neon accents:** Cyan `#08f` border glow on brand icons, gold-border search fields with inset glow on focus
- **Interactive states:** Hover intensifies glow layers and speeds up shimmer

### Light Mode
- **Primary palette:** Burnt orange `#ff6b35`, cream `#f5eee6` background, navy `#143d60` text
- **Clean, minimal:** No glow effects; subtle radial-gradient ambient tint at viewport top
- **Sparkle icon:** Hidden by default, fades in on brand title hover with gold drop-shadow

### Grid System
- **Desktop (≥1024 px):** 5 columns + persistent sidebar
- **Tablet (640–1024 px):** 3 columns, collapsible sidebar
- **Phone (<640 px):** 2 columns, 2-row toolbar, folder bar (Row3)

### Hybrid Slider
Grid density slider with 28 px thumb, 48 px hit area, and tooltip label.

---

## Credits

- **Design & Development** — Built for AI artists who generate at scale and need a curator's lens over their collections.
- **Icons** — Lucide (MIT) for UI elements; FontAwesome Pro (license required) for brand/empty-state SVGs.
- **Fonts** — Cinzel by Natanael Gama (OFL), Inter by Rasmus Andersson (OFL), JetBrains Mono (OFL).
- **Framework** — Vue.js ecosystem, Pinia state management, Vite bundler.
