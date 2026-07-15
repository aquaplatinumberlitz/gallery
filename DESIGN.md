---
name: AI Art Gallery
description: A local-first web gallery for browsing AI-generated image and video collections
colors:
  surface: oklch(0.995 0.008 75)
  foreground: oklch(0.2 0.02 50)
  primary: oklch(0.22 0.02 50)
  primary-foreground: oklch(0.985 0.008 75)
  secondary: oklch(0.96 0.012 75)
  secondary-foreground: oklch(0.22 0.02 50)
  muted: oklch(0.96 0.012 75)
  muted-foreground: oklch(0.52 0.02 55)
  accent: oklch(0.95 0.025 60)
  accent-foreground: oklch(0.22 0.02 50)
  destructive: oklch(0.577 0.245 27.325)
  border: oklch(0.9 0.012 72)
  ring: oklch(0.709 0.01 56.259)
  success: "#22c55e"
  warning: "#f59e0b"
  error: "#ef4444"
  info: "#3b82f6"
  brand-accent: "#ff6b35"
  sidebar-surface: oklch(0.98 0.01 75)
typography:
  body:
    fontFamily: InterVariable, Segoe UI, SF Pro Display, system-ui, -apple-system, sans-serif
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
  code:
    fontFamily: JetBrains Mono, monospace
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  h1:
    fontFamily: InterVariable, Segoe UI, SF Pro Display, system-ui, -apple-system, sans-serif
    fontSize: 32px
    fontWeight: 600
    lineHeight: 1.25
  h2:
    fontFamily: InterVariable, Segoe UI, SF Pro Display, system-ui, -apple-system, sans-serif
    fontSize: 24px
    fontWeight: 600
    lineHeight: 1.25
  h3:
    fontFamily: InterVariable, Segoe UI, SF Pro Display, system-ui, -apple-system, sans-serif
    fontSize: 20px
    fontWeight: 500
    lineHeight: 1.25
  caption:
    fontFamily: InterVariable, Segoe UI, SF Pro Display, system-ui, -apple-system, sans-serif
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: 4px
  md: 8px
  lg: 12px
  xl: 16px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 32px
  xl: 64px
  gutter: 24px
  sidebar: 280px
  sidebar-mobile: 240px
---

## Overview

A focused, calm, technical gallery for AI-generated media. AI Art Gallery is a local-first tool for AI image/video collectors who browse, inspect, search, and manage personal generated-media libraries on desktop, tablet, and mobile. The interface is dense enough for repeat workflows, restrained in styling, and clear about filesystem effects. No marketing ornament, no decorative dashboards, no over-bright accent colors. The dominant feature is a virtual-scrolled mixed-media grid (TanStack Virtual) that fills the viewport — it establishes the page's weight before anything else. Everything serves browsing speed, metadata inspection, and catalog maintenance.

## Colors

The palette is built from warm-tinted neutrals using OKLCH color space, paired with a single orange brand accent. Semantic gallery tokens supplement the shadcn-vue base for status and feedback.

- **Surface (oklch(0.995 0.008 75)):** Page background. A warm off-white that avoids the clinical feel of pure white.
- **Foreground (oklch(0.2 0.02 50)):** Primary text. Deep warm-ink for maximum readability.
- **Primary (oklch(0.22 0.02 50)):** Interactive element text and emphasized content.
- **Secondary (oklch(0.96 0.012 75)):** Subtle container surfaces — hovered rows, pressed states.
- **Muted (oklch(0.96 0.012 75)):** Secondary surface fills — sidebar, card backgrounds.
- **Muted Foreground (oklch(0.52 0.02 55)):** Secondary text, metadata descriptions, timestamps.
- **Accent (oklch(0.95 0.025 60)):** Gentle warm highlight for hover states and subtle emphasis.
- **Border (oklch(0.9 0.012 72)):** Card borders, structural dividers, input outlines.
- **Ring (oklch(0.709 0.01 56.259)):** Focus indicator halo — 3px external shadow at 50% opacity in light mode, 70% in dark.
- **Brand Acccent (#ff6b35):** A restrained orange used sparingly for decorative hero text, section labels, and album card accents. Not used for primary actions.
- **Success (#22c55e):** Status indicators for healthy catalogs, completed jobs, indexed metadata.
- **Warning (#f59e0b):** Degraded state indicators, stale indexes, partial coverage.
- **Error (#ef4444):** Failure states, scan errors, broken derivative paths.
- **Sidebar Surface (oklch(0.98 0.01 75)):** Slightly distinct from page surface to frame navigation.

Dark mode inverts: surface becomes oklch(0.145 0.008 60) with warm-tinted depth, primary shifts to oklch(0.72 0.14 75), and the brand accent warms to golden (#d6a15d). All lightbox surfaces are always-dark: overlay at rgba(0,0,0,0.95), panel surface at #1a1a1a, text at #e0e0e0.

## Typography

The type system uses a single system-UI font stack (InterVariable with Segoe UI, SF Pro Display, and system-ui fallbacks) to keep the interface fast and familiar. JetBrains Mono is reserved for code, metadata keys, and data-display contexts.

- **Body (16px, 400 weight, 1.5 leading):** Default text. Relaxed line height for scanability in dense grid metadata and list rows.
- **Headings (h1: 32px/600, h2: 24px/600, h3: 20px/500):** Section titles, admin page headings, modal titles. Weight-driven hierarchy rather than massive size.
- **Caption (12px, 400 weight):** Secondary metadata, timestamps, file sizes, status labels. Subtle and compact.
- **Code/Mono (14px, JetBrains Mono):** Prompt text, parameter values, seed numbers, file paths, search queries. Set in monospace for precise scanning and copy-paste accuracy.
- **Metadata Labels:** Lightbox prompt labels use colored semantic tokens — positive prompt in green (#86efac dark), negative in red (#fca5a5 dark), tool labels in pink (#fb7185 dark).
- **Line length:** Body content constrained to 65 characters max for readability. Gallery metadata chips and table columns remain compact.

## Layout

The layout is organized around a persistent or collapsible sidebar (280px desktop, 240px mobile) plus a full-height virtual-scrolled gallery grid. Three distinct layout shells dispatch by viewport:

- **Desktop (>=1200px):** `DesktopLayout.vue` — persistent 280px sidebar using shadcn Sidebar components (SidebarProvider, Sidebar, SidebarInset, SidebarRail), AppHeader across the top, and the GalleryGrid filling the remaining viewport. Sidebar is collapsible via edge toggle.
- **Tablet (768–1199px):** `TabletLayout.vue` — 280px sidebar as a transform-based drawer kept in the DOM with inert + aria-hidden when closed. TabletHeader plus a separate compact TabletGalleryToolbar. Gallery content is not wrapped in an additional card.
- **Mobile (<768px):** `MobileLayout.vue` — 240px overlay sidebar with backdrop close. Native scroll instead of virtual. Fixed header + bottom bar with safe-area awareness. Bottom dock carries back/forward history and current folder label.

### Grid Density

The gallery grid uses a density slider with 5 levels. The same slider level produces different column counts per device:

| Level | Desktop | Tablet | Mobile |
|-------|---------|--------|--------|
| 1 (densest) | 8 | 5 | 3 |
| 2 | 7 | 5 | 3 |
| 3 (default) | 6 | 4 | 2 |
| 4 | 5 | 3 | 2 |
| 5 (sparsest) | 4 | 3 | 2 |

Density level is persisted to localStorage under `gallery-grid-size`.

### Breakpoints

| Category | Width | Layout | Default columns |
|----------|-------|--------|-----------------|
| Compact | <480px | Mobile | 2 |
| Mobile | 480–767px | Mobile | 2 |
| Tablet | 768–1199px | Tablet | 4 |
| Desktop | 1200–1439px | Desktop | 6 |
| Wide | >=1440px | Desktop | 6 |

### Routes

| Path | Page | Purpose |
|------|------|---------|
| `/` | GalleryRoute | Main virtual-scrolled gallery grid — the app's dominant surface |
| `/metadata` | LibraryInspector | Desktop read-only AI photo metadata inspection with TanStack Table |
| `/admin/libraries` | LibraryListPage | Registered library management |
| `/admin/libraries/:id` | LibraryDetailPage | Single library config, import paths, scan controls |
| `/admin/libraries/:id/jobs` | LibraryJobsPage | Job history for a library |
| `/admin/jobs` | JobsPage | Cross-library job history |
| `/admin/maintenance` | MaintenancePage | Catalog runtime status, index progress, integrity checks |

## Elevation & Depth

Depth is achieved through layered shadows with warm-tinted diffusion rather than aggressive drop shadows. Light mode uses low-opacity dark shadows; dark mode uses higher-opacity dark shadows for equivalent depth perception.

- **Card shadow (default):** `0 1px 2px rgba(0,0,0,0.3), 0 1px 3px 1px rgba(0,0,0,0.15)` — subtle elevation for sidebar items, album cards.
- **Card hover:** `0 1px 3px rgba(0,0,0,0.3), 0 4px 8px 3px rgba(0,0,0,0.15)` — lifted state for interactive cards.
- **Modal/drawer:** `--gallery-shadow-xl` — `0 8px 16px rgba(0,0,0,0.08), 0 16px 32px rgba(0,0,0,0.06)` light, deeper in dark mode.
- **Lightbox:** Full-screen overlay at `rgba(0,0,0,0.95)` with always-dark surfaces. No shadow needed — the overlay provides depth.
- **Focus ring:** A 3px external shadow using `color-mix(in srgb, var(--ring) 50%, transparent)` light / `70%` dark. Never an inset outline or thinner ring.

Interactive elements use a `-1px` translateY on active press for tactile feedback.

## Shapes

- **Small radius (4px):** Input fields, compact chips, metadata badges, small UI elements.
- **Medium radius (8px):** Cards, buttons, dropdowns, dialog corners. This is the default component radius (0.625rem via shadcn).
- **Large radius (12px):** Album cards, larger containers, search panels.
- **Extra large (16px):** Modal dialogs, drawer panels, floating sheets.
- **Full (9999px):** Notification badges, status dots, circular avatars, icon buttons.

Album cards use generous 12px rounded corners with a layered paper aesthetic (layer border overlays on the card edge). Lightbox panels are flat rectangles with no rounding — the dark overlay surface has straight corners at 0px.

## Components

- **Photo Card (`PhotoCard.vue`):** Fixed-aspect thumbnail card with rounded corners (8px), subtle shadow, and a hover lift effect. Shows file type badge (image/video), resolution, and file size overlaid at bottom. Click opens lightbox. Video cards (`VideoCard.vue`) add a play overlay icon centered on the thumbnail.
- **Album Card (`AlbumCard.vue`, `AlbumCardMobile.vue`, `AlbumCardTablet.vue`):** Device-specific card family. Desktop uses a layered paper composition with a decorative glow container (`GlowContainer.vue`) and an orange accent. Mobile/tablet use flattened two-column cards. All show cover thumbnail, album title, asset count, and date.
- **Album Scroller (`AlbumScroller.vue`, `AlbumScrollerNative.vue`):** Horizontal scroll strip of album cards below the AppHeader and above the gallery grid. Native scroll with momentum on mobile; custom scroll container on desktop.
- **App Header (`AppHeader.vue`):** Desktop top bar holding breadcrumb navigation, search input (`HeaderSearchBox.vue`), density slider, sort dropdown, and theme toggle. Fixed height with safe-area support.
- **Sidebar (`FolderTree.vue`, `FolderTreeRow.vue`):** Library tree with collapsible folders. Each row shows folder name and media count. Active path is highlighted. Root nodes show library name with scan status indicators.
- **Lightbox (`Lightbox.vue`):** Device-dispatch orchestrator. Desktop uses `PhotoSwipeViewer.vue` + `LightboxDesktopPanel.vue` (400px right sidebar metadata). Tablet uses `TabletPhotoSwipe.vue` + `LightboxTabletPanel.vue` (2-column grid drawer). Mobile uses `MobilePhotoSwipe.vue` + `LightboxMobileSheet.vue` (spring bottom sheet with 44%/80% snap points via `@douxcode/vue-spring-bottom-sheet`).
- **Lightbox Metadata Panel:** Three tabs — Prompt, Params, Model. Uses `ExpandableText.vue` for prompt/negative prompt with fade overlay and "Show more" button. Colored label chips for prompt types (green=positive, red=negative, pink=tool). Copy buttons on every copyable field. Desktop shows params in a compact 2-column table. Mobile tabs follow WAI-ARIA tabs pattern with roving tabindex.
- **PhotoSwipe Viewer (`PhotoSwipeViewer.vue`):** Derivative-first — 1440px WebP preview is the main PhotoSwipe source. Original image loads only on zoom, fullscreen, download, or animated images. Counter centered over image viewport via `--lightbox-sidebar-width`. Next-arrow placed outside metadata sidebar.
- **Buttons (shadcn-vue base):** Primary (filled `--primary` background), Secondary (outline `--border`), Ghost (transparent, `--accent` on hover). Destructive variant for irreversible actions. No neon glows, no custom cursors. Active state: `-1px` translateY and darker background.
- **Inputs/Forms:** Label above input. Error message below. Focus ring uses `--focus-ring-shadow` token. Helper text in `--muted-foreground`. No floating labels. Touch targets minimum 44x44px on mobile.
- **Search (`HeaderSearchBox.vue`, `AdvancedSearchDrawer.vue`):** Expanded search state in header with input, scope selector, and Advanced Search trigger. Fielded search syntax (`prompt:`, `seed:`, `model:`, `steps:`). Advanced Search is a 560px right-side sheet with filter sections, validation counts, and footer — one shared instance at the app shell.
- **Search Results (`SearchResultsPanel.vue`, `SearchResultMetadata.vue`):** Full-width results panel with photo cards in grid layout. Shows matched metadata chips per result. Supports cursor pagination.
- **Index Status (`IndexProgressBar.vue`, `IndexStatusBadge.vue`, `IndexStatusPanel.vue`):** Composite progress indicators with per-state labels: ready, usable-stale/building, degraded, failed, unavailable, disabled. Rebuild controls confirm before queueing.
- **Related Assets (`RelatedAssetsPanel.vue`, `RelationReasonList.vue`):** Image-level overflow action with one unified result grid. Backend-ranked metadata/recipe/visual evidence is deduplicated by asset ID and shown only as concise typed reason badges on each image. No match-type tabs, recorded-generation comparison summary, probability, confidence percentage, or inferred lineage.
- **Empty States (`EmptyState.vue`):** Six distinguished states — No path selected, Not loaded yet, Loading, Empty folder, Folders only, Has images. Each renders a distinct message and visual without decorative illustration.
- **Breadcrumb (`Breadcrumb.vue`):** Path navigation with clickable segments and a separator chevron. Each segment links to that path level in the gallery.
- **Video Player (`VideoPlayerDialog.vue`):** Modal video dialog with native `<video>` element, HTTP Range streaming via `/api/video`, cached WebP poster via `/api/video/poster`. Play overlay on video cards.
- **Skeleton Loader (`SkeletonLoader.vue`):** Shimmer-based loading placeholders matching exact card and row dimensions.
- **Gallery Toaster (`GalleryToaster.vue`):** Desktop toast notifications for job completion, errors, and status updates. Positioned bottom-right.
- **Settings Modal (`SettingsModal.vue`):** Theme preference (light/dark), grid density slider, and metadata-related toggles.
- **Admin components (`LibraryListPage.vue`, `LibraryDetailPage.vue`, `LibraryJobsPage.vue`, `JobsPage.vue`, `MaintenancePage.vue`):** Pragmatic form-and-table layout. Library registration form with name, import paths (multi-entry), exclusion patterns (glob). Scan/repair triggers with status polling. Job tables with type, status, progress, timestamps, and error messages.

## Do's and Don'ts

- Do lead with the virtual-scrolled grid — it is the dominant surface. Establish its weight before placing headers, sidebars, or secondary navigation.
- Do keep filesystem actions explicit. Library registration, scan triggers, and offline asset confirmation must show clear consequences with confirmation dialogs where files are involved.
- Don't hide filesystem consequences behind decorative UI or modal patterns that obscure what the action does.
- Don't use marketing-site ornament, decorative dashboards, or over-bright accent colors. The orange brand accent (--brand-accent: #ff6b35) is reserved for decorative hero text, section labels, and album card accents — never for primary CTAs.
- Do put validation messages, status indicators, and error text directly next to the data they explain. Toast notifications for background jobs; inline errors for forms.
- Do use the derivative-first lightbox pattern: 1440px WebP preview as the default PhotoSwipe source. Original images only on zoom, fullscreen, download, or animated images.
- Don't show probability, confidence percentage, generated explanations, detailed recorded-generation comparisons, or inferred lineage in Related Assets. Use honest evidence badges such as "Same recipe" and "Visually similar". No semantic search, AI similarity, or lineage detection language.
- Don't mix rounded and sharp corners in the same view. Use the established 4/8/12/16px scale consistently.
- Don't use pure black (#000000) anywhere. Lightbox overlay uses rgba(0,0,0,0.95); all dark surfaces use warm-tinted deep grays.
- Don't use neon glows, outer-glow shadows, or custom mouse cursors.
- Don't use 3-column equal-card feature rows. The gallery is a dynamic-density grid; admin pages use flat form-and-table layouts.
- Don't use floating labels on inputs. Label always above, error below, helper text in muted foreground.
- Don't use emojis, AI copywriting clichés ("Elevate", "Seamless", "Unleash", "Next-Gen"), or generic placeholder names in UI text.
- Do maintain WCAG AA contrast ratios (4.5:1 for normal text) across both themes. The focus ring must be a 3px external shadow — never an inset outline.
- Do use the responsive card family per device: AlbumCardDesktop/AlbumCardMobile/AlbumCardTablet. Same component, device-specific rendering.
- Do use semantic gallery tokens (`--gallery-*`) for surfaces, text, borders, radii, shadows, timing, and icon sizes. Prefer `--gallery-icon-toolbar` over hardcoded Lucide sizes.
- Do respect reduced-motion preferences. Animations use the `ease-gallery` cubic-bezier and only transform/opacity properties.
- Don't let hover-only effects apply on touch devices. Reset under `@media (hover: none)` and use `:active` for touch feedback.
- Don't use InterVariable outside the system stack for premium contexts — Inter is the primary font by design for this project (local tool, not marketing).
- Do lazy-load admin routes. The gallery route must be eager; metadata inspector, library management, and job pages can prefetch on idle or link hover.
