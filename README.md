# Aetheris — AI Art Gallery

> A museum-grade gallery frontend for browsing AI-generated artwork collections. Browse, inspect, and manage thousands of AI-generated images with a polished, responsive interface inspired by museum aesthetics and Material Design 3.

---

## ✦ Overview

**Aetheris** (formerly Museum Art Gallery) is a Vue 3 + TypeScript single-page application that turns any local folder of AI-generated images into a beautiful, browsable gallery. Built for AI artists, model trainers, and collectors who need a fast, organized way to sift through large volumes of generated content — complete with LoRA highlighting, full generation metadata inspection, and a museum-quality dark/light theme.

The frontend communicates with a **FastAPI** backend (separate repository) that handles filesystem scanning, thumbnail generation, and AI metadata extraction.

---

## ✦ Features

### Gallery Grid
The core browsing experience. A responsive, virtualized grid of photo thumbnails powered by `vue-virtual-scroller` (RecycleScroller) for smooth scrolling through thousands of images. Features:
- **Virtual scrolling** — renders only visible rows, 200px buffer, handles large collections
- **Hybrid grid slider** — drag or click to adjust columns from **1 to 8**, persisted to `localStorage`
- **Adaptive defaults** — 5 columns on desktop (>1024px), 3 on tablet (641–1024px), 2 on phone (≤640px)
- **Section titles** — "Albums" and "Photos" with Cinzel serif font + gold gradient underline + count badge
- **Natural sort** — sort by name (natural order: `img2.jpg` before `img10.jpg`) or date modified, ascending/descending
- **Open folder button** — opens the current folder in the OS file explorer via backend API
- **Error recovery** — dismissible error banner with clear+retry flow
- **Loading skeletons** — shimmer placeholders during data fetch
- **Infinite scroll** — IntersectionObserver-based sentinel loads 200 images per page

### Photo Card
Grid thumbnail component for individual images:
- **Shimmer loading placeholder** — animated wave gradient until the thumbnail loads
- **Lazy loading** — `loading="lazy"` attribute on img elements
- **Animated preview on hover** — for GIF/WebP files, plays the full animated version on hover (150ms debounce)
- **Type badge** — shows "GIF" or "PLAYING" overlay on animated files
- **Subtle scale + translateY hover** — 1.02 scale, -2px translate with 280ms cubic-bezier
- **MD3 Elevation** — box-shadow states for default, hover, and active/pressed

### Album Card
Folder thumbnail card with a distinctive 3D cover-stack effect:
- **Dual-layer cover stack** — front and back layers with staggered rotation (-12° back, +8° front), creating a physical album look
- **Hover animation** — layers fan out: back shifts left (-20px, -15°), front shifts right (+10px, +12°, scale 1.05)
- **Elastic bounce** — 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) transition
- **Fallback placeholder SVG** — FontAwesome Pro-style image icon when no cover images exist
- **Dark mode neon glow** — multi-layer orange/gold glow on hover (6 box-shadow layers)
- **Active click state** — 3-layer orange glow, transforms back to neutral
- **Responsive height** — 280px standard, 200px on mobile ≤640px, 160px on small ≤480px

### Lightbox
Full-viewport image viewer with comprehensive AI metadata panel:
- **Full-viewport display** — image scaled to `object-fit: contain`, centered on dark radial-gradient background
- **Keyboard navigation** — ← → arrows, Escape to close, Tab-trapped focus
- **Mouse wheel navigation** — 60ms throttle between wheel-triggered prev/next
- **Swipe support** — touch-friendly navigation on mobile
- **Lazy high-res loading** — uses ~2K thumbnail by default, falls back to original on error or animation
- **Fullscreen mode** — native Fullscreen API, switches to original-resolution image in fullscreen
- **Metadata panel** — right sidebar (400px, 320px min) showing:
  - **Image info** — filename, dimensions, date, generation time, tool badge (e.g. SwarmUI, ComfyUI)
  - **Prompt** — positive prompt with **LoRA highlighting** (`<lora:name:weight>` tokens rendered as purple pills)
  - **Negative prompt** — collapsible, copy button with CheckCircle feedback
  - **Generation parameters** — collapsible group showing Seed, Steps, CFG, Sampler, Scheduler, Aspect Ratio
  - **Model & Resources** — collapsible group showing Checkpoint, LoRAs, and SwarmUI models with hash
- **Copy to clipboard** — prompt, negative prompt, and seed each have individual copy buttons
- **Preload neighbors** — adjacent images preloaded for instant navigation
- **Request dedup** — metadata request counter prevents stale responses
- **Responsive** — on mobile (≤640px) metadata becomes a bottom sheet (max 45vh), hidden in non-fullscreen

### Breadcrumb
Path navigation bar with smart collapsing for deep paths:
- **Home icon** — styled with `--primary-color` and drop-shadow glow
- **Smart collapse** — when path exceeds `maxVisible` (default: 4 segments), intermediate folders are hidden behind an `[...]` ellipsis button
- **Ellipsis dropdown** — click shows hidden segments as a menu with Folder icons + "Show full path" option
- **Collapse button** — when manually expanded, a Minimize icon restores collapsed state
- **Chevron separators** — between each breadcrumb segment
- **Last segment active** — disabled, bold, full-color, acts as current location indicator
- **Click to navigate** — clicking any non-last segment navigates to that folder path
- **Custom scrollbar** — 6px thin scrollbar in the path container

### Sidebar & Folder Tree
Collapsible sidebar with recursive folder navigation:
- **Root path input** — text field with FolderOpen icon, Enter to load, RotateCcw reset button
- **Loading pill** — inline "Loading" indicator with spinning Loader icon
- **FolderTreeItem (recursive)** — lazy-loads children on expand, supports indefinite nesting
- **Expand/collapse** — ChevronRight/ChevronDown arrows, only enabled for folders with children
- **Active state** — gold accent background (`rgba(214, 161, 93, 0.16)`) + left indicator bar
- **Empty children display** — "(Empty)" text shown when opened folder has no subfolders
- **Keyboard navigation** — WAI-ARIA TreeView pattern: Enter/Space to select, ArrowRight to expand, ArrowLeft to collapse
- **Compact design** — 13px font, 3px 6px padding, bronze folder icon
- **Sidebar edge toggle** — fixed-position button at sidebar edge, ChevronLeft/ChevronRight, neon glow in dark mode
- **Mobile overlay** — transparent backdrop with Escape-key dismiss, auto-closes on mobile

### Sort Controls
Google Photos-inspired sort dropdown:
- **Sort trigger** — ArrowUpDown icon + current sort label + chevron
- **Sort options** — "Name" (Type icon) and "Date modified" (Clock icon)
- **Direction indicator** — ArrowUp (ascending) or ArrowDown (descending) next to active sort
- **Keyboard accessible** — ArrowUp/Down/Escape navigation inside dropdown
- **Persisted preference** — sort field and order saved to localStorage
- **Natural name sorting** — handles `img2.jpg` < `img10.jpg` correctly via digit-aware comparison

### Search
Global search filtering across both folders and images:
- **Desktop search** — inline input in the header, part of `.header-actions`
- **Mobile search** — expandable Search icon button with backdrop overlay
- **Case-insensitive** — `toLowerCase().includes()` matching
- **Clear button** — X icon when query is non-empty
- **Search-aware empty states** — "No results" state with "Clear search" action button when search yields no matches
- **Persisted query** — bound to `galleryStore.searchQuery`

### Empty States
10 context-aware empty state variants, each with custom FA Pro SVG icons:
| Type | Icon | Title | Description |
|------|------|-------|-------------|
| `empty-folder` | FolderOpen | This folder is empty | No images or subfolders found here |
| `no-results` | Search | No results found | Try adjusting your search or filters |
| `no-images` | Images | No images here | This folder only contains subfolders |
| `error` | TriangleAlert | Something went wrong | Unable to load content |
| `no-path` | FolderTree | Welcome to Gallery | Enter a folder path to start browsing |
| `loading` | Loader (spinning) | Loading... | Please wait while we fetch your content |
| `default` | Box | Nothing here | — |

Each state includes: animated background circles (pulse-slow), icon ring with accent-color border, floating dot elements, sparkle decorations, optional action button with configurable label + FA icon.

### Toast Notifications
Bottom-right notification system with auto-dismiss and progress bar:
- **4 types** — success (green), error (red), warning (amber), info (blue)
- **Duration tiers** — SHORT 3000ms, DEFAULT 4000ms, MEDIUM 6000ms, LONG 10000ms
- **Progress bar** — animated via `requestAnimationFrame`, pauses on hover/focus
- **Max visible** — limited to 3 simultaneous toasts
- **Action button** — e.g. "Retry" with configurable callback
- **Dismissible** — X button on each toast, closes on action click
- **HTML support** — `toast-stat` styled spans for colored album/image count displays
- **TransitionGroup animation** — slide-in from right with scale
- **Promise-based helper** — `toast.promise()` shows loading → success/error flow

### Intro Screen
Full-viewport entry experience with seasonal themes:
- **Iframe-based** — loads a landing page HTML from the backend (`/api/landing-pages`)
- **Seasonal detection** — automatically selects Birthday (Sep 3), Christmas (Dec 24-25), Lunar New Year themes
- **Random fallback** — picks a random landing page from available options
- **Cinzel ENTER button** — frosted glass + gold animated border (conic-gradient rotation) + shine sweep effect
- **Settings modal** — configure intro mode: Automatic, Disabled, or Manual (select specific theme with Preview)

### Settings Modal
Intro page configuration with focus-trapped dialog:
- **3 modes** — Automatic (random + holiday-aware), Disabled (skip intro), Manual (always show specific theme)
- **Theme selector** — dropdown populated from backend landing pages, formatted names (e.g. "birthday" → "Birthday")
- **Preview button** — opens the selected theme in the intro screen without closing settings
- **Focus trap** — Tab/Shift+Tab cycles within modal, Escape closes, returns focus to trigger
- **Frosted backdrop** — `backdrop-filter: blur(4px)`, smooth fadeIn + slideUp animation

### Theme System
Dual light/dark mode with automatic and manual control:
- **System preference detection** — `prefers-color-scheme: dark` media query on first load
- **Persisted choice** — saved to `localStorage` under `gallery-theme` key
- **Data attribute** — `data-theme="dark|light"` on `<html>` element
- **Theme toggle** — animated pill-shaped button with sliding thumb, sun/moon SVG icons
- **Light mode** — clean minimal aesthetic, navy #143d60 titles, warm cream #f5eee6 background
- **Dark mode** — museum-inspired: black #080808 background, gold #d6a15d accents, neon glow effects
- **Gradient toggle** — light: `#667eea → #764ba2`, dark: `#f093fb → #f5576c`

### Accessibility (a11y)
Built following WCAG 2.1 AA and Apple HIG guidelines:
- **Focus-visible** — custom `box-shadow` focus ring using `--primary-color`
- **Skip link** — hidden skip-to-content link appears on Tab
- **Screen reader** — `.sr-only` utility class for visually hidden text
- **Touch targets** — `@media (pointer: coarse)` enforces 44×44px minimum
- **Reduced motion** — `@media (prefers-reduced-motion: reduce)` disables all animations
- **High contrast** — `@media (prefers-contrast: high)` increases border widths and contrast ratios
- **ARIA** — WAI-ARIA TreeView pattern for folder tree, `aria-label` and `title` attributes throughout
- **Focus trap** — custom composable for modal dialogs (Lightbox, Settings)

---

## ✦ Architecture

```
gallery/
└── frontend/
    ├── dist/                       # Production build output
    ├── src/
    │   ├── assets/
    │   │   └── fonts.css           # Google Fonts imports (Cinzel, Inter, JetBrains Mono)
    │   ├── components/
    │   │   ├── AlbumCard.vue       # Folder cover card with 3D layer stack
    │   │   ├── Breadcrumb.vue      # Smart-collapsing path navigation
    │   │   ├── EmptyState.vue      # 10-variant context-aware empty state
    │   │   ├── FolderTreeItem.vue  # Recursive folder tree node
    │   │   ├── GalleryGrid.vue     # Main grid: virtual scroller, sort, grid slider
    │   │   ├── IntroScreen.vue     # Full-viewport entry with seasonal themes
    │   │   ├── Lightbox.vue        # Full metadata image viewer
    │   │   ├── PhotoCard.vue       # Grid thumbnail with hover animation
    │   │   ├── SettingsModal.vue   # Intro screen configuration dialog
    │   │   ├── SidebarHeader.vue   # Root path input + load controls
    │   │   ├── SkeletonLoader.vue  # Shimmer loading placeholder
    │   │   ├── ToastContainer.vue  # Toast notification stack
    │   │   └── ToastItem.vue       # Individual toast with progress bar
    │   ├── composables/
    │   │   ├── useFocusTrap.ts     # Modal focus trap (WCAG compliant)
    │   │   └── useToast.ts         # Toast notification convenience wrapper
    │   ├── directives/
    │   │   └── clickOutside.ts     # Click-outside detection directive
    │   ├── services/
    │   │   └── api.ts              # Axios API client with error handling
    │   ├── stores/
    │   │   ├── gallery.ts          # Pinia store: albums, images, navigation, search
    │   │   ├── lightbox.ts         # Pinia store: lightbox state, metadata, navigation
    │   │   └── toast.ts            # Pinia store: toast queue management
    │   ├── styles/
    │   │   └── main.scss           # CSS variables, theme, animations, a11y, responsive
    │   ├── types/
    │   │   ├── index.ts            # TypeScript interfaces (FileNode, Metadata, etc.)
    │   │   └── vue-virtual-scroller.d.ts  # Module declaration for virtual scroller
    │   ├── App.vue                 # Root component: layout, sidebar, header, theme
    │   ├── constants.ts            # IMAGE_PAGE_SIZE = 200
    │   ├── env.d.ts                # Vite client type declarations
    │   └── main.ts                 # App entry: createApp, Pinia, global CSS
    ├── package.json                # Dependencies and scripts
    ├── vite.config.ts              # Vite config with API proxy
    ├── tsconfig.json               # TypeScript configuration
    └── .gitignore                  # node_modules, dist, .env
```

---

## ✦ Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Frontend Framework** | Vue 3 (Composition API + `<script setup>`) | ^3.5.24 |
| **State Management** | Pinia | ^3.0.4 |
| **Build Tool** | Vite | ^7.2.4 |
| **Language** | TypeScript | ~5.9.3 |
| **Styling** | SCSS (Sass) | ^1.94.2 |
| **Icons** | Lucide Vue Next | ^1.0.0 |
| **Virtual Scroller** | vue-virtual-scroller | ^3.0.4 |
| **HTTP Client** | Axios | ^1.13.2 |
| **Type Checking** | vue-tsc | ^3.1.4 |
| **Vue Plugin** | @vitejs/plugin-vue | ^6.0.2 |

### Fonts
| Font | Usage | Source |
|------|-------|--------|
| **Cinzel** | Brand titles, section headers, ENTER button | Google Fonts (serif, display) |
| **InterVariable** | UI text, labels, buttons, body copy | Google Fonts (sans-serif) |
| **JetBrains Mono** | Code, metadata, generation params, badges | Google Fonts (monospace) |

### Backend (separate repository)
|- **FastAPI** — Python backend serving images, thumbnails, metadata, and directory scanning
|- **Metadata Parser** — AI image metadata extraction engine, inspired by [DiffusionToolkit](https://github.com/RupertAvery/DiffusionToolkit), with **~95% feature adoption**:
|  - **6 formats**: SwarmUI, A1111/WebUI, ComfyUI, NovelAI, EasyDiffusion, + `.txt` sidecar fallback
|  - **15+ A1111 fields**: Steps, Sampler, CFG, Seed, Model, Scheduler, model_hash, clip_skip, hires_upscale, hires_steps, denoising_strength, VAE, Size (→Width/Height), ENSD, Aesthetic Score
|  - **ComfyUI**: 8+ node types parsed (CLIPTextEncode, KSampler, CheckpointLoader, VAELoader, ControlNetLoader, LoraLoader, UpscaleModelLoader, CLIPSetLastLayer) with node reference resolution
|  - **LoRA extraction**: 2 patterns (`<lora:name:weight>`, `LoRA: [name]`) + SwarmUI object/string lists, dedup, strip `.safetensors`
|  - **Cache**: LRU 100MB size-based with Future-based dedup (tránh parse trùng)
|- **Endpoints**: `/api/scan`, `/api/image`, `/api/thumbnail`, `/api/metadata`, `/api/open-folder`, `/api/landing-pages`

---

## ✦ Theme & Design

### CSS Custom Properties (Design Tokens)

| Token | Dark Mode | Light Mode | Description |
|-------|-----------|------------|-------------|
| `--bg-color` | `#080808` | `#f5eee6` | Page background |
| `--surface-color` | `#11100f` | `#ffffff` | Card/surface background |
| `--text-color` | `#eaeaea` | `#143d60` | Primary text |
| `--title-color` | `#d6a15d` | `#143d60` | Headings and titles |
| `--primary-color` | `#d6a15d` | `#ff6b35` | Primary accent (gold / orange) |
| `--neon-color` | `#d6a15d` | `#ff6b35` | Neon glow accent |
| `--folder-color` | `#f2a007` | `#f2a007` | Folder icon (bronze/gold) |
| `--muted-text` | `#b3b3b3` | `#4a6587` | Secondary/muted text |
| `--border-color` | `rgba(255,255,255,0.075)` | `rgba(0,0,0,0.12)` | Dividers and borders |
| `--album-border-color` | `#eaeaea` | `#ffffff` | Album card layer borders |
| `--font-body` | InterVariable, Segoe UI, SF Pro Display, system-ui | Body text |
| `--font-code` | JetBrains Mono, monospace | Code/metadata |
| `--focus-ring-shadow` | `0 0 0 2px #fff, 0 0 0 4px var(--primary-color)` | Focus indicator |

### Typography

- **Cinzel** — Used for brand hero title ("Museum Art Gallery"), section headers ("Albums", "Photos"), and the intro ENTER button. In dark mode, the brand title features a gold gradient shimmer with multi-layer `drop-shadow` glow.
- **InterVariable** — Primary UI font. Body text, buttons, inputs, breadcrumbs, sidebar, toasts. Weights 100–900 with variable axes.
- **JetBrains Mono** — Code blocks, metadata values (seed, steps, CFG), generation parameters, grid column count badge, folder count badges, album count badge.

### Responsive Breakpoints

| Layout | Grid Columns | Top Bar | Sidebar | Lightbox Panel |
|--------|:---:|:---:|:---:|:---:|
| Desktop >1024px | 5 (default) | Horizontal full | Visible (280px) | 400px sidebar |
| Tablet 641–1024px | 3 (default) | Compact nav | Visible | 320px sidebar |
| Phone ≤640px | 2 (default) | Mini 2-row + folder bar | Overlay (toggle) | Bottom sheet ≤45vh |

### Grid Slider

- **Hybrid control**: click the range track (positioned absolutely over a styled progress bar) or drag the thumb — both change the column count from 1 to 8
- **Thumb size**: 28×28px circle with white border and primary-color background
- **Hit area**: 48px min-height for touch devices (via `@media (pointer: coarse)`)
- **Track**: 100px wide, 6px tall with gradient progress fill
- **Tooltip**: shows current column count above the thumb on hover, hidden on mobile
- **Persistence**: column count saved to `localStorage` key `gallery-grid-size`

### Glow Effects (Dark Mode Only)

- **Album card hover**: 6-layer neon glow — white core (2px, 5px) + gold/orange layers (10px, 20px, 35px, 50px at decreasing opacity)
- **Album card front layer hover**: 5-layer glow — white core (2px, 4px) + orange layers (8px, 15px, 25px)
- **Album card active/pressed**: 3-layer orange glow (3px, 8px, 15px)
- **Brand title**: 3-layer `drop-shadow` gold glow that intensifies on hover
- **Search box**: `box-shadow` neon gold on focus-within
- **Sidebar field container**: neon gold border + glow on focus-within
- **Sidebar edge toggle**: gold border + subtle glow
- **Theme toggle (dark)**: gold thumb glow with `box-shadow`
- **Section title underline**: gold gradient line with animated pulse

### Empty States

10 FA Pro SVG icon strings embedded directly in `EmptyState.vue`:

| # | Icon Name | SVG Path Description | Used In |
|---|-----------|---------------------|---------|
| 1 | `FolderOpen` | Classic open folder shape | Empty folder, no content |
| 2 | `Search` | Magnifying glass + document | No search results |
| 3 | `Images` | Picture frame with landscape | Folder has no images, only subfolders |
| 4 | `TriangleAlert` | Warning triangle with exclamation | Error states |
| 5 | `FolderTree` | Hierarchical folders with checkmark | No path selected (welcome) |
| 6 | `Loader` | 4 arrows in diamond pattern (spinning) | Loading state |
| 7 | `Box` | Simple circle/box | Default fallback |
| 8 | `X` | X mark | Close/clear action button |
| 9 | `ArrowLeft` | Left arrow | Go back action button |
| 10 | `Sparkle` | 3 sparkle stars | Decorative floating elements |

Each state renders: animated pulsing background circles, a gradient icon ring with accent-color border, floating dots, sparkle decorations, and optional action button.

---

## ✦ Components in Detail

### AlbumCard.vue
- **Props**: `node: FileNode` (with `cover_images` array, `name`)
- **Emits**: `click`
- **State**: hover/active CSS-only (no JS state)
- **Key styles**: `perspective: 1000px` on card, `transform-style: preserve-3d` on cover diagonal, `.album-layer-back` rotated -12deg with `translateZ(0)`, `.album-layer-front` rotated +8deg with `translateZ(20px)`, hover fans layers out to -15deg/+12deg with translate offsets

### Breadcrumb.vue
- **Props**: `path?: string`, `maxVisible?: number` (default 4)
- **Emits**: `navigate(path)`
- **State**: `isExpanded`, `ellipsisMenuOpen`
- **Directives**: `v-click-outside` for closing ellipsis menu
- **Logic**: splits path by `/` or `\`, computes visible vs hidden segments, shows ellipsis dropdown with "Show full path" expand option

### EmptyState.vue
- **Props**: `type`, `title?`, `description?`, `actionLabel?`, `actionIcon?`, `compact?`
- **Emits**: `action`
- **State**: computed defaults based on type
- **Icons**: 10 inline SVG strings matching FA Pro shapes
- **Animations**: `pulse-slow` (4s), `float` (3-4s), `twinkle` (2-2.5s), `icon-spin` (1.5s for loading)

### FolderTreeItem.vue
- **Props**: `node: FileNode`, `activePath?`, `level?` (default 1)
- **Emits**: none (uses galleryStore directly)
- **State**: `isActive` (computed), `isLoading` (from store `loadingMap`)
- **Recursive**: self-references in template for children
- **WAI-ARIA**: keyboard navigation with ArrowRight (expand), ArrowLeft (collapse), Enter/Space (select)

### GalleryGrid.vue
- **Props**: none (uses stores)
- **State**: `columnCount` (local + persisted), `rowHeight` (ResizeObserver-computed), `showSortMenu`, `loadMoreSentinel`
- **Virtual scroller**: `RecycleScroller` from `vue-virtual-scroller` with dynamic row height
- **Infinite scroll**: IntersectionObserver with 400px root margin
- **Sort**: natural sort with digit-aware comparison, persisted to localStorage
- **Grid slider**: range input 1-8 with custom styled track, thumb, tooltip, badge
- **Error handling**: error banner, retry via store, clear error button
- **Empty states**: 6 distinct states (no path, error, no results, empty folder, no images, loading)

### Lightbox.vue
- **Props**: none (uses lightboxStore)
- **State**: `isFullscreen`, `imageError`, `manualOriginal`, `fallbackOriginal`, `showGenParams`, `showResources`, `copyStatus`, focus trap
- **Keyboard**: ← → for nav, Escape to close, Tab trapped in modal
- **Mouse wheel**: throttle to 60ms, deltaY > 0 = next, < 0 = prev
- **Fullscreen**: Fullscreen API with `requestFullscreen()` / `exitFullscreen()`, switches to original image
- **Metadata**: fetched from `/api/metadata`, LoRA tokens parsed via regex and highlighted as pills
- **Copy**: `navigator.clipboard.writeText()` with 1500ms visual feedback
- **Image fallback**: tries thumbnail → original on error; animated files (GIF/WebP) load original directly

### PhotoCard.vue
- **Props**: `src?: string`, `name?: string`
- **Emits**: `click`
- **State**: `isLoaded`, `hasError`, `isHovering`, `shouldPlay`, `previewSrc`
- **Hover**: 150ms debounced timer before loading full animated preview
- **Shimmer**: absolute-positioned gradient wave with `translateX` animation
- **Badge**: "GIF" or "PLAYING" overlay for animated files

### SidebarHeader.vue
- **Props**: none
- **State**: `pathInput` (bound to store `rootPath`)
- **Events**: Enter key triggers `setRootPath`, RotateCcw resets
- **Label**: "ROOT PATH" with FolderOpen icon, hint text "Press Enter to load"

### ToastItem.vue
- **Props**: `toast: Toast`
- **Emits**: `dismiss`
- **State**: `progress` (0-100), `isPaused`, `startTime`
- **Progress animation**: `requestAnimationFrame` driven, pauses on mouseenter/focusin
- **Types**: success (green #22c55e), error (red #ef4444), warning (amber #f59e0b), info (blue #3b82f6)
- **Dark mode**: dark surface #1f2937, lighter text

### IntroScreen.vue
- **Props**: `visible`, `forceUrl?`
- **Emits**: `update:visible`, `enter`
- **State**: `introUrl`
- **Seasonal detection**: Intl Chinese calendar for Lunar New Year, date checks for birthday (Sep 3) and Christmas (Dec 24-25)
- **Storage**: reads `intro_mode` and `intro_theme` from localStorage

### SettingsModal.vue
- **Props**: `isOpen`
- **Emits**: `close`, `preview(url)`
- **State**: `introMode`, `selectedTheme`, `availableThemes`, `isLoadingThemes`
- **Focus trap**: uses `useFocusTrap` composable, activates on open, deactivates on close

---

## ✦ Getting Started

### Prerequisites

- **Node.js** >= 18 (tested with v22+)
- **pnpm** (recommended) or npm
- **FastAPI backend** running (see separate repository)

### Local Development

```bash
# Navigate to frontend directory
cd gallery/frontend

# Install dependencies
pnpm install

# Start dev server (default: http://127.0.0.1:5173)
pnpm dev

# Or specify a custom port and API URL
VITE_PORT=3000 VITE_API_URL=http://localhost:8000 pnpm dev
```

The Vite dev server proxies `/api/*` requests to the backend (default `http://localhost:8000`), configurable via `VITE_API_URL` environment variable.

### Production Build

```bash
pnpm build
```

Output is written to `gallery/frontend/dist/`. This static build can be served by any web server (Nginx, Apache, or the FastAPI backend itself).

### Deployment (VPS)

```nginx
# Example Nginx configuration
server {
    listen 80;
    server_name gallery.yourdomain.com;

    root /var/www/gallery/frontend/dist;
    index index.html;

    # Proxy API requests to FastAPI backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

---

## ✦ API Endpoints

The frontend communicates with the backend through these endpoints:

| Method | Endpoint | Description | Parameters |
|--------|----------|-------------|------------|
| `GET` | `/api/scan` | Scan a directory for folders and images | `path`, `image_limit`, `image_cursor` |
| `GET` | `/api/image` | Serve a full-resolution image | `path` |
| `GET` | `/api/thumbnail` | Serve a thumbnail (with optional max_size) | `path`, `max_size` |
| `GET` | `/api/metadata` | Fetch AI generation metadata (tool, prompt, params, models) | `path` |
| `POST` | `/api/open-folder` | Open a folder in the OS file explorer | `path` |
| `GET` | `/api/landing-pages` | List available intro/landing page URLs | — |

### Backend Error Responses

All endpoints return structured errors in FastAPI's standard `{"detail": {"error": "...", "message": "..."}}` format:

| Error Type | HTTP Status | Description |
|-----------|:---------:|-------------|
| `not_found` | 404 | Path does not exist |
| `not_directory` | 400 | Path is not a directory |
| `permission` | 403 | No filesystem permission |
| `invalid_file` | 400 | Unsupported file type |
| `timeout` | 504 | Scan timed out |
| `server_error` | 500 | Unexpected server error |
| `network` | — | Client cannot reach server |

---

## ✦ Color Palette Philosophy

The gallery's color system is designed to evoke **museum-grade sophistication** while remaining functional for high-volume image browsing.

### Light Mode: "The Archive"
- **Background** `#f5eee6` — warm cream, reminiscent of archival paper and gallery walls
- **Text** `#143d60` — deep navy, professional and authoritative
- **Accent** `#ff6b35` — vibrant coral-orange, provides energetic contrast against the warm background
- **Surface** `#ffffff` — clean white for cards and panels

### Dark Mode: "The Gallery at Night"
- **Background** `#080808` — near-black, eliminates visual noise and makes images pop
- **Text** `#eaeaea` — warm off-white for readability without eye strain
- **Accent** `#d6a15d` — aged gold, evokes museum lighting, prestige, and warmth
- **Glow** Multi-layer `#ff6b35` (orange) neon — draws attention to interactive elements in the dark

### The Gold-Orange Connection
The dual accent system (gold in dark, orange in light) is intentional: gold reads as elegant and warm against black, while orange provides high-contrast actionability against a cream background. The theme toggle smoothly transitions between these identities.

---

## ✦ Credits

- **Vue 3** + **Pinia** — reactive frontend framework and state management
- **Lucide Icons** — beautiful, consistent icon set for Vue
- **vue-virtual-scroller** — performant virtual rendering for large image sets
- **Google Fonts** — Cinzel (brand), Inter (UI), JetBrains Mono (code)
- **FontAwesome Pro** — SVG icons used for empty state illustrations
- **Vite** — fast, modern build tooling
- **FastAPI** — Python backend serving the gallery API
- **Material Design 3** — elevation and interaction pattern inspiration
- **Apple HIG** — focus management and accessibility patterns

---

## ✦ License

MIT — feel free to use, modify, and distribute.

---

*Built with ❤️ for the AI art community.*
