# shadcn-vue Sidebar Migration Plan

> **Archived:** Implemented in commit `267d5df`. See [Architecture](../ARCHITECTURE.md) for current state.

Date: 2026-06-14

Original status at authoring: plan only. The migration was later implemented and this
document is retained as historical design context.

Primary sources:

- Current codebase audit in `frontend/src/layouts/DesktopLayout.vue`, `frontend/src/layouts/TabletLayout.vue`, `frontend/src/layouts/MobileLayout.vue`, `frontend/src/App.vue`, `frontend/src/components/SidebarHeader.vue`, `frontend/src/components/FolderTreeItem.vue`, `frontend/src/stores/gallery.ts`, `frontend/src/injectionKeys.ts`, `frontend/src/composables/useGalleryTheme.ts`, `frontend/src/composables/useDevice.ts`, `frontend/src/styles/tokens.css`, `frontend/src/styles/_shadcn-token-bridge.css`, and `frontend/src/styles/tailwind.css`.
- shadcn-vue Sidebar docs: https://www.shadcn-vue.com/docs/components/sidebar
- shadcn-vue default sidebar registry inspected read-only: https://shadcn-vue.com/r/styles/default/sidebar.json
- shadcn-vue new-york-v4 sidebar registry inspected read-only for Tailwind v4/source-shape comparison: https://shadcn-vue.com/r/styles/new-york-v4/sidebar.json

## Executive Summary

Migrate the gallery sidebar to shadcn-vue Sidebar primitives, but do not force the folder tree and root path controls into `SidebarMenu` on the first pass. The current sidebar is not a simple nav menu: it contains a root path form, async recursive folder tree, custom close-on-select behavior, and separate desktop/tablet/mobile layout mechanics. The lowest-risk path is to let shadcn own the sidebar shell, state context, Sheet-backed overlay, and structural slots while keeping app-specific content in dedicated gallery components.

Recommended architecture:

- Generate `frontend/src/components/ui/sidebar` with `pnpm dlx shadcn-vue@latest add sidebar`, then review generated imports and supporting dependencies (`sheet`, `skeleton`, `tooltip`, `separator`, `button`, `input`) against this repo's existing `components/ui` conventions.
- Add missing Tailwind v4 theme mappings for `bg-sidebar`, `text-sidebar-foreground`, `border-sidebar-border`, and related sidebar colors. The bridge file already defines `--sidebar-*` values, but `tailwind.css` currently does not expose `--color-sidebar*` names.
- Extract duplicated sidebar body markup into `frontend/src/components/GallerySidebarContent.vue`.
- Use shadcn `SidebarHeader`, `SidebarContent`, `SidebarGroup`, `SidebarGroupLabel`, and `SidebarGroupContent` as structure around the existing root path header and `FolderTreeItem`.
- Keep `FolderTreeItem` custom in the first migration. It already owns recursive async loading, selected state, folder expansion, keyboard handling, and close-on-select behavior.
- Migrate desktop first with controlled `SidebarProvider`, `Sidebar collapsible="offcanvas"`, `SidebarInset`, and a custom edge toggle using `useSidebar`. Do not use `collapsible="icon"` unless the product intentionally wants a 3rem icon rail; today's collapsed desktop width is 0.
- Migrate mobile/tablet overlays second. shadcn's generated provider treats only `max-width: 768px` as mobile, while this app treats both mobile and tablet (`<1200px`) as overlay sidebars. The generated sidebar must be customized or wrapped so tablet keeps overlay behavior.
- Preserve the existing `closeSidebarKey` injection. It is used by `SidebarHeader.vue` after a successful load and by `FolderTreeItem.vue` after selecting a folder on mobile/tablet.

The migration should reduce duplicated layout code and align the shell with shadcn-vue without changing gallery navigation semantics.

## Current Implementation Audit

### Layouts

`DesktopLayout.vue` owns a persistent sidebar in CSS Grid:

- `.layout` uses `grid-template-columns: 280px 1fr`.
- `.layout.collapsed` uses `grid-template-columns: 0 1fr`.
- `.sidebar.closed` translates the sidebar offscreen.
- The edge toggle is a fixed shadcn `Button` at `left: 260px`, moving to `left: 0` when collapsed.
- Content remains in a `.content` section with app-specific padding and `GalleryGrid`.

`TabletLayout.vue` owns an overlay drawer:

- `.layout` is single-column.
- `.sidebar.tablet-overlay` is `position: fixed`, `width: 280px`, `height: 100dvh`, `z-index: 100`.
- Closed state uses `transform: translateX(-100%)`, `pointer-events: none`, and `:inert="!isSidebarOpen"`.
- Open state restores `transform: translateX(0)` and `pointer-events: auto`.
- Backdrop is a custom `Transition` with `z-index: 90`.

`MobileLayout.vue` owns an overlay drawer:

- `.sidebar.mobile` is `position: fixed`, `width: 240px`, `height: 100dvh`, `z-index: 100`.
- Below 480px, sidebar width becomes `width: 100%` with `max-width: 300px`.
- Backdrop is custom and includes `backdrop-filter: blur(2px)`.

### Shared Sidebar Content

All three layout files duplicate:

- `<SidebarHeader />`, which is the app's root path input/display component, not the shadcn sidebar primitive.
- "Folder Tree" title.
- Loading pill with `Loader`.
- Scrollable `.tree-container`.
- Empty state text.
- Recursive `<FolderTreeItem>` for each root node.

This duplication is the first thing to remove. The migration should introduce a gallery-owned content component before changing state mechanics.

### App State and Behavior

`App.vue` owns a single `isSidebarOpen` ref:

- Initial value is `true`.
- `toggleSidebar()` flips the ref for all layouts.
- `closeSidebar()` closes only on mobile/tablet.
- `closeSidebarKey` is provided to descendants.
- Escape closes the sidebar only on mobile/tablet when it is open.

`SidebarHeader.vue`:

- Uses Pinia `useGalleryStore`.
- Loads/reset root path.
- Closes the sidebar after successful root path load through `closeSidebarKey`.
- Renders a compact mobile root path display and `RootPathSheet`; desktop/tablet render the full input.

`FolderTreeItem.vue`:

- Uses Pinia for expanded paths and selected path.
- Uses TanStack Query via `useFolderChildrenQuery` for lazy folder children.
- Closes the sidebar after folder selection only on mobile/tablet.
- Owns recursive tree rendering and partial keyboard behavior.

### Token and UI State

The project already has shadcn token values in `frontend/src/styles/_shadcn-token-bridge.css`, including:

- `--sidebar`
- `--sidebar-foreground`
- `--sidebar-primary`
- `--sidebar-primary-foreground`
- `--sidebar-accent`
- `--sidebar-accent-foreground`
- `--sidebar-border`
- `--sidebar-ring`

However, `frontend/src/styles/tailwind.css` currently maps standard shadcn colors into Tailwind v4 `@theme inline`, but does not map sidebar colors. Generated shadcn Sidebar components use classes such as `bg-sidebar`, `text-sidebar-foreground`, `border-sidebar-border`, and `ring-sidebar-ring`. Those mappings must be added before relying on the generated components.

## shadcn Sidebar API Overview

The shadcn-vue Sidebar docs describe the component as a composable, themeable, customizable sidebar foundation. The generated code is intended to be edited in the application, not treated as an external black box.

### Installation

Run from `frontend`:

```bash
pnpm dlx shadcn-vue@latest add sidebar
```

The sidebar registry declares dependencies on:

- `reka-ui`
- `@vueuse/core`

It also declares registry dependencies:

- `sheet`
- `input`
- `tooltip`
- `skeleton`
- `separator`
- `button`

This repo already has local `Button.vue`, `Input.vue`, `Separator.vue`, and tooltip components, but does not currently have `components/ui/sidebar`, `components/ui/sheet`, or shadcn `components/ui/skeleton`.

### Provider and Context

`SidebarProvider`:

- Provides sidebar context to descendant sidebar components.
- Accepts `defaultOpen` and controlled `open`.
- Emits `update:open`.
- Exposes CSS variables on its root wrapper:
  - `--sidebar-width`
  - `--sidebar-width-icon`
- Uses a cookie named `sidebar_state` in generated source.
- Adds a keyboard shortcut listener for `cmd+b` / `ctrl+b` in generated source.
- Wraps children in a `TooltipProvider` with zero delay in generated source.
- Provides context consumed by `useSidebar()`.

`useSidebar()` exposes:

- `state`: `"expanded"` or `"collapsed"`
- `open`
- `setOpen`
- `openMobile`
- `setOpenMobile`
- `isMobile`
- `toggleSidebar`

Important generated defaults:

- `SIDEBAR_WIDTH = "16rem"` (256px at default root font size)
- `SIDEBAR_WIDTH_MOBILE = "18rem"` (288px)
- `SIDEBAR_WIDTH_ICON = "3rem"`
- `SIDEBAR_KEYBOARD_SHORTCUT = "b"`
- `isMobile = useMediaQuery("(max-width: 768px)")`

### Sidebar Container

`Sidebar` props:

- `side`: `"left"` or `"right"`; current gallery needs `"left"`.
- `variant`: `"sidebar"`, `"floating"`, or `"inset"`; current gallery maps best to `"sidebar"`.
- `collapsible`: `"offcanvas"`, `"icon"`, or `"none"`.

Desktop generated behavior:

- Renders a peer/group wrapper with data attributes:
  - `data-state`
  - `data-collapsible`
  - `data-variant`
  - `data-side`
- Renders a transparent width spacer to reserve layout width.
- Renders the actual sidebar as a fixed element.
- `collapsible="offcanvas"` collapses reserved width to 0 and moves the fixed sidebar left by `calc(var(--sidebar-width) * -1)`.
- `collapsible="icon"` collapses to `--sidebar-width-icon`, not to 0.

Mobile generated behavior:

- If `isMobile` is true, `Sidebar` renders a shadcn `Sheet`.
- `SheetContent` receives `data-sidebar="sidebar"` and `data-mobile="true"`.
- Mobile width uses `SIDEBAR_WIDTH_MOBILE`.
- The Sheet close button is hidden by default in the generated sidebar source.
- Sheet handles overlay/focus-trap behavior through Reka/shadcn primitives.

### Layout Companion

`SidebarInset`:

- Renders the main content surface.
- Uses peer data selectors to coordinate with inset variants.
- For this app, it can replace the desktop/tablet/mobile `section.content` wrapper while preserving `id="main-content"` and `tabindex="-1"`.

### Structural Primitives

Use these for gallery sidebar structure:

- `SidebarHeader`: top region. It should wrap the app's existing root path header component.
- `SidebarContent`: scrollable flexible body.
- `SidebarFooter`: optional bottom region. No current footer.
- `SidebarGroup`: section container.
- `SidebarGroupLabel`: group title row. Use for "Folder Tree" if the loading pill can be placed cleanly, or use `as-child` / a custom div.
- `SidebarGroupAction`: optional group header action.
- `SidebarGroupContent`: content wrapper below the label.
- `SidebarSeparator`: optional separator between sections.
- `SidebarInput`: shadcn-styled input variant for sidebar contexts. Do not replace the current root path input in phase 1 unless needed.

### Menu Primitives

Use these only where the content is menu-like:

- `SidebarMenu`
- `SidebarMenuItem`
- `SidebarMenuButton`
- `SidebarMenuAction`
- `SidebarMenuBadge`
- `SidebarMenuSkeleton`
- `SidebarMenuSub`
- `SidebarMenuSubItem`
- `SidebarMenuSubButton`

The current `FolderTreeItem` is not a direct 1:1 fit for `SidebarMenu` because it is recursive, async, path-keyed, and already has folder-specific controls. Forcing it into these primitives in the first migration would increase risk without solving the layout duplication.

### Triggers and Rail

`SidebarTrigger`:

- A default small button using a panel icon.
- Calls `toggleSidebar()` from context.
- Good for header/menu bar toggles.
- Does not match the current desktop edge toggle shape or positioning.

`SidebarRail`:

- A thin rail intended mostly for toggling when the sidebar is collapsed.
- Uses resize-style cursors.
- Has `tabindex="-1"` in generated source.
- Does not match the current accessible fixed pill edge toggle.

Recommendation: create a gallery-specific `GallerySidebarEdgeTrigger.vue` for desktop and optionally use `SidebarTrigger` only in headers if the app decides to replace existing header toggle wiring.

## Current vs Target Comparison

| Area                   | Current                                                      | shadcn target                                              | Notes                                                                      |
| ---------------------- | ------------------------------------------------------------ | ---------------------------------------------------------- | -------------------------------------------------------------------------- |
| Sidebar shell          | Three custom `<aside>` implementations                       | `SidebarProvider` + `Sidebar`                              | Desktop first, overlay second.                                             |
| Desktop layout         | CSS Grid `280px 1fr` / `0 1fr`                               | shadcn width spacer + fixed sidebar + `SidebarInset`       | Use `collapsible="offcanvas"` to preserve 0px collapsed width.             |
| Tablet layout          | Custom fixed overlay, 280px, inert/pointer-events            | shadcn Sheet-backed sidebar with customized breakpoint     | Generated `max-width: 768px` is not enough; gallery needs `<1200px`.       |
| Mobile layout          | Custom fixed overlay, 240px, compact max 300px               | shadcn Sheet-backed sidebar with customized width variable | Preserve `240px` default and compact `min(300px, 100vw)` behavior.         |
| State owner            | `App.vue` single `isSidebarOpen`                             | Keep `App.vue` as source of truth; bind provider state     | Add controlled mobile state support or a bridge for `openMobile`.          |
| Close on folder select | `closeSidebarKey` injection                                  | Keep injection                                             | Required by `FolderTreeItem` and `SidebarHeader`.                          |
| Escape close           | App global handler for mobile/tablet                         | Sheet handles Escape; keep handler until verified          | Avoid removing current handler before overlay migration is validated.      |
| Backdrop               | Custom div, tablet transition, mobile blur                   | Sheet overlay                                              | Match z-index and blur intentionally if keeping visual parity.             |
| Desktop edge toggle    | Fixed 24x48 pill at sidebar edge                             | Custom component using `useSidebar`                        | `SidebarTrigger` and `SidebarRail` are not visual matches.                 |
| Root path header       | Custom `SidebarHeader.vue`                                   | Wrap with shadcn `SidebarHeader`                           | Alias names to avoid confusion with shadcn primitive.                      |
| Folder tree            | Custom recursive `FolderTreeItem`                            | Keep custom inside `SidebarGroupContent`                   | Do not force into `SidebarMenu` in phase 1.                                |
| Loading pill           | Custom span                                                  | Keep custom, optionally use `Badge` later                  | Low risk to keep as-is.                                                    |
| Empty state            | Custom paragraph                                             | Keep custom                                                | Could later use shadcn Empty if installed.                                 |
| Background             | Custom gradient over `--surface-color`                       | Scoped gallery surface class inside shadcn shell           | Do not globally remap neutral shadcn sidebar tokens unless design changes. |
| Width variables        | Hardcoded CSS widths                                         | `--sidebar-width` and mobile width constants               | Generated defaults are 256px desktop and 288px mobile; must customize.     |
| Breakpoints            | `useDevice`: mobile `<768`, tablet `<1200`, desktop `>=1200` | Generated provider: mobile `<=768`                         | Must align with gallery breakpoint model.                                  |
| Persistence            | Sidebar open state not meaningfully persisted                | Generated cookie persistence                               | Disable or ignore cookie when using controlled `open`; document behavior.  |
| Keyboard shortcut      | Escape only                                                  | Generated `cmd/ctrl+b` toggle                              | Treat as behavior change; add a prop or remove if not wanted.              |
| Tooltip timing         | App-level `TooltipProvider` delay 300ms                      | SidebarProvider nests zero-delay TooltipProvider           | Align or remove nested provider to avoid tooltip timing changes.           |

## Target Architecture

### Component Structure

Create `frontend/src/components/GallerySidebarContent.vue`:

```txt
GallerySidebarContent
  ShadSidebarHeader
    App SidebarHeader.vue root path component
  ShadSidebarContent
    ShadSidebarGroup
      title row: Folder Tree + loading pill
      ShadSidebarGroupContent
        tree-container
          empty state
          FolderTreeItem...
```

Keep imports explicit to avoid the app component and shadcn primitive sharing the same local name:

```ts
import RootPathSidebarHeader from "@/components/SidebarHeader.vue";
import {
  SidebarHeader as ShadSidebarHeader,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
} from "@/components/ui/sidebar";
```

Optional cleanup: rename the app component from `SidebarHeader.vue` to `RootPathSidebarHeader.vue` in a later mechanical pass. This is not required for the migration but would reduce ambiguity.

### Desktop Layout Shape

Replace the custom desktop grid shell with shadcn's shell:

```txt
SidebarProvider(controlled open)
  Sidebar(side="left", variant="sidebar", collapsible="offcanvas")
    GallerySidebarContent
  GallerySidebarEdgeTrigger
  SidebarInset#main-content.content
    AppHeader
    content-body
      GalleryGrid
```

Implementation details:

- Use `collapsible="offcanvas"` to match current `0 1fr` collapsed behavior.
- Do not use `collapsible="icon"` in the initial migration.
- Do not use `SidebarRail` as the primary desktop trigger; it is not the same visual or accessibility model.
- Set desktop width through generated constants or CSS variable indirection so the final `--sidebar-width` is `280px`.
- Preserve `.content` padding, `.content-body`, and gallery layout behavior.
- Confirm the generated fixed sidebar plus width spacer does not conflict with `height: 100dvh`, `overflow: hidden`, or the app header.

### Overlay Layout Shape

For mobile and tablet, the target is shadcn's Sheet-backed branch:

```txt
SidebarProvider(controlled desktop open and controlled mobile/tablet open)
  Sidebar(side="left", variant="sidebar", collapsible="offcanvas")
    GallerySidebarContent
  SidebarInset#main-content.content
    MobileHeader or TabletHeader
    GalleryGrid
    optional MobileFloatingBottomBar
```

The generated provider is not sufficient as-is for this app because:

- It treats only `max-width: 768px` as mobile.
- It keeps `openMobile` internal and uncontrolled.
- Tablet (`768px` to `1199px`) would otherwise use desktop fixed/sidebar-spacer behavior, not the existing overlay drawer.

Customize the generated local sidebar source in `components/ui/sidebar`:

- Add a sidebar overlay breakpoint constant matching the app's layout switch, for example `SIDEBAR_OVERLAY_MEDIA = "(max-width: 1199px)"`.
- Use that media query in `SidebarProvider` instead of the generated `"(max-width: 768px)"`.
- Add controlled `openMobile` / `update:openMobile` support, or a narrowly scoped bridge component that syncs the provider's `openMobile` to `App.vue` state.
- Set `SIDEBAR_WIDTH_MOBILE` through a CSS variable indirection so mobile and compact widths can match current behavior.

Recommended width variables:

```css
:root {
  --gallery-sidebar-width: 280px;
  --gallery-sidebar-mobile-width: 240px;
}

@media (max-width: 480px) {
  :root {
    --gallery-sidebar-mobile-width: min(300px, 100vw);
  }
}
```

Generated constants can then use:

```ts
export const SIDEBAR_WIDTH = "var(--gallery-sidebar-width, 280px)";
export const SIDEBAR_WIDTH_MOBILE =
  "var(--gallery-sidebar-mobile-width, 240px)";
```

This preserves shadcn's `--sidebar-width` mechanism while keeping gallery dimensions.

### State Bridge

Keep `App.vue` as the source of truth:

- `isSidebarOpen` remains the single public state for all three layout variants.
- `toggleSidebar()` remains available for existing headers.
- `closeSidebar()` remains injected and still closes only on mobile/tablet.
- The layout components emit either:
  - `toggleSidebar`, as today, or
  - a new `update:sidebarOpen` event for provider-originated changes.

Recommended event model during migration:

- Keep existing `@toggle-sidebar` events for `AppHeader`, `TabletHeader`, and `MobileHeader`.
- Add `@update:sidebar-open` from layouts to `App.vue` only where `SidebarProvider` needs to update controlled state.
- In a later cleanup, replace toggle-only events with `v-model:sidebarOpen` if it simplifies the layout APIs.

The shadcn context's `toggleSidebar()` should update the same `isSidebarOpen` ref through controlled provider emits. This is required for the custom desktop edge trigger and Sheet backdrop/Escape close to stay in sync with `App.vue`.

## Migration Phases

### Phase 0: Preflight and Generated Component Audit

Goal: install the primitives and make them build in this repo without changing runtime layout.

Steps:

1. Run from `frontend`:

   ```bash
   pnpm dlx shadcn-vue@latest add sidebar
   ```

2. Review generated file paths. Expected new files:

   - `frontend/src/components/ui/sidebar/*`
   - `frontend/src/components/ui/sheet/*` if not already present
   - `frontend/src/components/ui/skeleton/*` or `Skeleton.vue` if not already present

3. Resolve import path conventions.

   This repo has top-level `Button.vue`, `Input.vue`, and `Separator.vue`, plus lowercase directories for some compound components. The sidebar registry may generate imports that assume lowercase directories such as `@/components/ui/button` or registry paths. Normalize those imports deliberately rather than allowing duplicate or broken UI components.

4. Verify icon package imports.

   The default registry uses `lucide-vue-next`; the v4 registry uses `@lucide/vue`. This repo has both installed, but existing app code uses `lucide-vue-next`. Prefer consistency unless the generated component requires the other package.

5. Add Tailwind v4 sidebar color mappings in `frontend/src/styles/tailwind.css`:

   ```css
   --color-sidebar: var(--sidebar);
   --color-sidebar-foreground: var(--sidebar-foreground);
   --color-sidebar-primary: var(--sidebar-primary);
   --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
   --color-sidebar-accent: var(--sidebar-accent);
   --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
   --color-sidebar-border: var(--sidebar-border);
   --color-sidebar-ring: var(--sidebar-ring);
   ```

6. Run:

   ```bash
   pnpm build
   ```

Exit criteria:

- Generated sidebar primitives compile.
- No duplicate generated `Button` / `Input` import path conflict remains.
- `bg-sidebar` and related classes are backed by Tailwind v4 theme variables.
- No layout files have been migrated yet.

### Phase 1: Extract Shared Gallery Sidebar Content

Goal: remove duplicated sidebar content while preserving the current three custom shells.

Create:

- `frontend/src/components/GallerySidebarContent.vue`

Move into it:

- App root path header component.
- Folder Tree title row.
- Loading pill.
- Tree container.
- Empty state.
- `FolderTreeItem` loop.
- Shared scrollbar and tree container CSS.

Use shadcn structural primitives inside the new content component:

- `SidebarHeader` as an outer shell around the app's root path header.
- `SidebarContent` for scrollable body.
- `SidebarGroup` for Folder Tree section.
- `SidebarGroupContent` for the recursive tree.

Keep custom CSS that is app-specific:

- `.gallery-sidebar-surface`
- `.sidebar-title` or equivalent title row class
- `.loading-pill`
- `.tree-container`
- scrollbar styling
- `.empty-state`

Modify:

- `DesktopLayout.vue`
- `TabletLayout.vue`
- `MobileLayout.vue`

Replace their duplicated sidebar body with:

```vue
<GallerySidebarContent
  :tree="tree"
  :is-loading="isLoading"
  :current-path="currentPath"
/>
```

Do not change:

- Layout shells.
- Widths.
- Overlay/backdrop behavior.
- `App.vue` state.
- `closeSidebarKey`.

Exit criteria:

- All three layouts look and behave the same as before.
- One source owns the root path + Folder Tree content.
- `pnpm build` passes.

### Phase 2: Migrate Desktop Shell

Goal: replace only the desktop sidebar shell with shadcn Sidebar while keeping tablet/mobile custom overlays intact.

Modify `DesktopLayout.vue`:

- Import:
  - `SidebarProvider`
  - `Sidebar`
  - `SidebarInset`
  - `useSidebar` indirectly through the custom edge trigger component.
- Replace `.layout` grid wrapper with `SidebarProvider`.
- Render `<Sidebar side="left" variant="sidebar" collapsible="offcanvas">`.
- Render `<GallerySidebarContent />` inside `<Sidebar>`.
- Render `<SidebarInset id="main-content" tabindex="-1" class="content">` around the existing header and content body.

Create:

- `frontend/src/components/GallerySidebarEdgeTrigger.vue`

The trigger should:

- Use `useSidebar()`.
- Render the current 24x48 fixed pill shape.
- Use `ChevronLeft` when expanded and `ChevronRight` when collapsed.
- Keep the current tooltip labels: "Hide Sidebar" / "Show Sidebar".
- Position itself using `--sidebar-width`, not a hardcoded `260px`.

Suggested positioning:

```css
.gallery-sidebar-edge-trigger {
  left: calc(var(--sidebar-width) - 20px);
}

.gallery-sidebar-edge-trigger[data-state="collapsed"] {
  left: 0;
}
```

Generated source customization:

- Change `SIDEBAR_WIDTH` to `var(--gallery-sidebar-width, 280px)`.
- Keep `SIDEBAR_WIDTH_ICON` at `3rem`, but do not use icon collapse in this phase.
- Consider disabling generated cookie writes and `cmd/ctrl+b` until product approves those behavior changes.
- Align the nested `TooltipProvider` delay with the app provider or remove the nested provider if tooltips behave differently.

Remove from `DesktopLayout.vue` once replaced:

- `.layout` grid column rules.
- `.layout.collapsed`.
- `.sidebar.closed`.
- Duplicated sidebar body CSS if already moved in Phase 1.
- Old `.sidebar-edge-toggle` implementation if replaced by `GallerySidebarEdgeTrigger`.

Exit criteria:

- Desktop open width is exactly 280px.
- Desktop collapsed content starts at the left edge, matching the old `0 1fr` behavior.
- Edge trigger visually tracks the sidebar edge during transition.
- Header toggle and edge trigger update the same `isSidebarOpen` state.
- Tablet and mobile are untouched and still pass behavior checks.

### Phase 3: Customize shadcn Overlay State for Tablet and Mobile

Goal: make shadcn Sidebar's Sheet branch match current mobile and tablet overlay behavior.

Modify generated local sidebar source in `frontend/src/components/ui/sidebar`.

Provider changes:

- Replace generated `useMediaQuery("(max-width: 768px)")` with a gallery overlay query matching layout selection:

  ```ts
  export const SIDEBAR_OVERLAY_MEDIA = "(max-width: 1199px)";
  ```

- Add controlled mobile state support:

  ```ts
  openMobile?: boolean
  defaultOpenMobile?: boolean
  "update:openMobile": [open: boolean]
  ```

- Use `useVModel` for `openMobile`, similar to generated desktop `open`.

Sidebar changes:

- Use `SIDEBAR_WIDTH_MOBILE = "var(--gallery-sidebar-mobile-width, 240px)"`.
- Ensure the Sheet content keeps `data-sidebar="sidebar"` and `data-mobile="true"`.
- Adjust `SheetContent` classes if needed to match current z-index, backdrop, and no-padding behavior.

Style changes:

- Add width variables in `tokens.css` or a sidebar-specific global stylesheet.
- Preserve compact mobile width:

  ```css
  @media (max-width: 480px) {
    :root {
      --gallery-sidebar-mobile-width: min(300px, 100vw);
    }
  }
  ```

Accessibility:

- shadcn Sheet should replace the custom `inert` + `pointer-events` accessibility mechanism for tablet/mobile.
- Keep `App.vue` Escape handler during initial migration. Remove it only after verifying Sheet Escape behavior, focus restore, and no double-close issues.
- Keep `closeSidebarKey`; it should set `isSidebarOpen = false`, which then controls `openMobile`.

Exit criteria:

- Tablet width is 280px if preserving exact tablet behavior, or explicitly documented if using the mobile variable. The preferred match is tablet 280px and mobile 240px/compact 300px; this may require separate tablet/mobile CSS variables or a media query range.
- Mobile width is 240px above compact and `min(300px, 100vw)` below compact.
- Backdrop click closes the sidebar and updates `App.vue`.
- Escape closes on tablet/mobile and updates `App.vue`.
- Selecting a folder closes tablet/mobile only.
- Root path successful load closes tablet/mobile only.
- Focus cannot reach the hidden overlay content.

### Phase 4: Migrate Tablet and Mobile Layout Shells

Goal: remove the custom overlay `<aside>` and backdrop implementations from `TabletLayout.vue` and `MobileLayout.vue`.

Modify `TabletLayout.vue`:

- Replace custom `<aside class="sidebar tablet-overlay">` with shadcn `<Sidebar>`.
- Replace custom backdrop with Sheet overlay behavior.
- Wrap content with `SidebarInset` or an equivalent content wrapper inside `SidebarProvider`.
- Preserve `TabletHeader`, search props/emits, theme toggle, and `GalleryGrid` options.
- Remove `.sidebar.tablet-overlay`, `.sidebar-backdrop`, and backdrop transition CSS after verification.

Modify `MobileLayout.vue`:

- Replace custom `<aside class="sidebar mobile">` with shadcn `<Sidebar>`.
- Replace custom backdrop with Sheet overlay behavior.
- Preserve `MobileHeader`, `MobileFloatingBottomBar`, bar visibility classes, safe-area padding, and `GalleryGrid` mobile props.
- Remove `.sidebar`, `.sidebar.mobile.open`, `.sidebar.closed`, `.sidebar-backdrop`, and compact sidebar width CSS after width variables are verified.

State wiring:

- Both layouts should bind provider mobile/tablet open state to `isSidebarOpen`.
- Keep existing header `@toggle-sidebar` emits unless a later cleanup introduces direct shadcn triggers.

Exit criteria:

- No custom overlay aside/backdrop CSS remains in tablet/mobile layouts.
- The shadcn Sheet overlay meets or exceeds the current inert/focus behavior.
- App headers, bottom bar, and lightbox are not covered incorrectly by sidebar z-index changes.

### Phase 5: Cleanup and Consolidation

Goal: remove dead styles and standardize naming after the behavior is stable.

Candidates:

- Rename app `SidebarHeader.vue` to `RootPathSidebarHeader.vue`.
- Rename CSS classes from generic `.sidebar-*` to `.gallery-sidebar-*` to avoid colliding mentally with shadcn's generated data attributes.
- Remove unused `toggleSidebar` layout emits if all toggles use provider context.
- Remove App-level Escape handler only if shadcn Sheet Escape behavior is fully verified across tablet/mobile.
- Document any accepted new behaviors, such as `cmd/ctrl+b`, if kept.

Verification:

- `pnpm build`
- Desktop viewport at 1200px and 1440px:
  - open/collapse via edge trigger
  - open/collapse via header toggle
  - search/header layout unchanged
  - tree scroll unchanged
- Tablet viewport around 768px, 900px, 1199px:
  - overlay, backdrop, Escape, focus behavior
  - width and animation
  - folder select closes
- Mobile viewport around 390px and 479px:
  - compact width cap
  - backdrop blur decision
  - bottom bar and header z-index
  - RootPathSheet still opens above/within expected overlay context
- Dark and light themes:
  - sidebar surface
  - border/readability
  - folder active state
- Regression checks:
  - `rg "sidebar-body|tablet-overlay|sidebar-backdrop|sidebar-edge-toggle" frontend/src`
  - ensure remaining matches are intentional.

## File Plan

### Create

- `frontend/src/components/GallerySidebarContent.vue`
- `frontend/src/components/GallerySidebarEdgeTrigger.vue`
- `frontend/src/components/ui/sidebar/*` from shadcn CLI
- `frontend/src/components/ui/sheet/*` if installed by sidebar CLI
- `frontend/src/components/ui/skeleton/*` or `Skeleton.vue` if installed by sidebar CLI

### Modify

- `frontend/src/styles/tailwind.css`
  - Add `--color-sidebar*` Tailwind v4 mappings.
- `frontend/src/styles/tokens.css` or a new sidebar-specific CSS file
  - Add `--gallery-sidebar-width` and mobile width variables.
- `frontend/src/components/ui/sidebar/utils.ts`
  - Customize width constants.
  - Customize overlay breakpoint.
  - Decide cookie and keyboard shortcut behavior.
- `frontend/src/components/ui/sidebar/SidebarProvider.vue`
  - Add controlled `openMobile` support if using shadcn overlay branch for tablet/mobile.
  - Align or remove nested tooltip provider behavior if needed.
- `frontend/src/components/ui/sidebar/Sidebar.vue`
  - Use mobile width variable.
  - Adjust Sheet content classes only if required for z-index/backdrop parity.
- `frontend/src/layouts/DesktopLayout.vue`
  - Migrate shell to shadcn Sidebar first.
- `frontend/src/layouts/TabletLayout.vue`
  - Migrate overlay shell after provider breakpoint/state customization.
- `frontend/src/layouts/MobileLayout.vue`
  - Migrate overlay shell after provider breakpoint/state customization.
- `frontend/src/App.vue`
  - Add `update:sidebar-open` handling if layouts expose controlled provider updates.
  - Keep `closeSidebarKey`.
  - Keep Escape handler until Sheet behavior is verified.
- `frontend/src/components/SidebarHeader.vue`
  - No required behavior change.
  - Optional later rename to `RootPathSidebarHeader.vue`.
- `frontend/src/components/FolderTreeItem.vue`
  - No required behavior change.

### Avoid in Initial Migration

- Do not convert `FolderTreeItem` into `SidebarMenu` recursively.
- Do not switch desktop to `collapsible="icon"` unless the desired collapsed behavior changes.
- Do not globally remap shadcn neutral sidebar tokens to the gallery gradient.
- Do not remove `closeSidebarKey`.
- Do not remove tablet/mobile Escape handling before Sheet behavior is tested.

## Key Challenges and Decisions

### Width Mismatch

Generated shadcn defaults:

- Desktop `16rem`, roughly 256px.
- Mobile `18rem`, roughly 288px.

Current gallery:

- Desktop 280px.
- Tablet overlay 280px.
- Mobile 240px, compact `min(300px, 100vw)`.

Mitigation:

- Use CSS variable indirection in generated constants.
- Add gallery width variables.
- Verify actual computed width in Playwright or browser devtools at desktop/tablet/mobile/compact breakpoints.

### Breakpoint Mismatch

Generated shadcn treats only `max-width: 768px` as mobile. The gallery has:

- Compact `<480px`
- Mobile `<768px`
- Tablet `<1200px`
- Desktop `>=1200px`

Current tablet requires overlay behavior. If the generated provider is not changed, tablet will render the desktop sidebar branch.

Mitigation:

- Use a gallery-specific overlay media query in generated `SidebarProvider`.
- Keep the app's `useDevice` layout selection as the product source of truth.
- Test at 768px exactly because the app uses `<768` for mobile while generated query uses `max-width`.

### Controlled State Split

shadcn has `open` for desktop and `openMobile` for Sheet. The gallery has one `isSidebarOpen`.

Mitigation:

- Keep `App.vue` as source of truth.
- Add controlled `openMobile` support to generated `SidebarProvider`.
- Ensure Sheet backdrop/Escape emits update the same `isSidebarOpen`.
- Keep `closeSidebarKey` as the cross-component close API.

### Custom Gradient Background

Current sidebars use:

```css
background:
  linear-gradient(180deg, rgba(0, 0, 0, 0.02), rgba(0, 0, 0, 0.04)),
  var(--surface-color);
```

shadcn uses `bg-sidebar`, backed by neutral sidebar tokens.

Mitigation:

- Preserve the gradient with a gallery-owned full-height content wrapper inside `<Sidebar>`.
- Do not change global `--sidebar` tokens unless the design intentionally wants all sidebar primitives to inherit the gallery surface.

### Edge Toggle Positioning

Current desktop trigger is a visible fixed pill at the sidebar edge. shadcn `SidebarTrigger` is a small content button, and `SidebarRail` is a thin rail with resize cursors.

Mitigation:

- Implement `GallerySidebarEdgeTrigger.vue`.
- Use `useSidebar()` for state and toggling.
- Compute left position from `--sidebar-width`.
- Keep current tooltip and icons.

### Folder Tree Is Not a Simple Menu

The folder tree is recursive, async, and path-keyed. It has custom expand/select controls and TanStack Query integration.

Mitigation:

- Keep `FolderTreeItem` as-is in phase 1.
- Wrap it in `SidebarGroupContent`.
- Consider a later accessibility-focused tree refactor separately, potentially with ARIA tree semantics. Do not combine that with the shell migration.

### Root Path Header Is App-Specific

The app's `SidebarHeader.vue` is a root path input/display component. shadcn's `SidebarHeader` is a layout primitive.

Mitigation:

- Alias imports in the extracted content component.
- Optionally rename the app component after migration.

### Tablet Accessibility

Current tablet uses `inert` and `pointer-events: none` when closed. shadcn Sheet should provide stronger modal/focus behavior, but only if tablet uses the Sheet branch.

Mitigation:

- Do not remove custom tablet overlay until provider breakpoint customization is complete.
- Validate closed sidebar focusability with keyboard navigation.
- Validate Escape, backdrop click, and focus restore.

### Generated Behavior Changes

shadcn generated source adds:

- `cmd/ctrl+b` toggle shortcut.
- Cookie persistence.
- Nested zero-delay TooltipProvider.

Mitigation:

- Treat these as product decisions, not incidental changes.
- Prefer disabling shortcut/cookie persistence during parity migration.
- Align tooltip timing with the app's existing `TooltipProvider`.

## Risks and Mitigations

| Risk                                                                                       | Impact                                  | Mitigation                                                                          |
| ------------------------------------------------------------------------------------------ | --------------------------------------- | ----------------------------------------------------------------------------------- |
| Generated imports do not match existing UI file conventions                                | Build failure or duplicate components   | Audit generated files immediately; normalize imports to local conventions.          |
| `bg-sidebar` classes have no Tailwind v4 color mapping                                     | Sidebar renders without expected colors | Add `--color-sidebar*` mappings in `tailwind.css` before layout migration.          |
| Tablet accidentally gets desktop sidebar behavior                                          | Major UX regression                     | Customize provider overlay breakpoint to `<1200px`; test 768, 900, and 1199 widths. |
| `openMobile` is not controlled by `App.vue`                                                | Backdrop/Escape/folder select desync    | Add controlled mobile state support or bridge provider state explicitly.            |
| Desktop fixed sidebar changes content sizing                                               | Header/grid layout shifts               | Use `SidebarInset`, keep content classes, verify 280px and collapsed 0px states.    |
| Edge trigger no longer tracks sidebar                                                      | Obvious visual regression               | Base trigger position on `--sidebar-width` and shadcn state.                        |
| Sheet overlay z-index conflicts with mobile header, bottom bar, lightbox, or RootPathSheet | Controls hidden or unusable             | Audit z-index stack; test overlay plus RootPathSheet and lightbox.                  |
| Focus behavior regresses after removing `inert`                                            | Accessibility regression                | Keep custom tablet until Sheet branch is proven; keyboard-test closed/open states.  |
| shadcn cookie persistence changes initial open state                                       | Unexpected startup behavior             | Keep `App.vue` controlled state; remove or ignore cookie writes.                    |
| `cmd/ctrl+b` conflicts with browser/app expectations                                       | Unexpected keyboard behavior            | Disable by default or add explicit opt-in prop.                                     |
| Nested TooltipProvider changes tooltip delay                                               | Subtle UX inconsistency                 | Remove nested provider or align delay with app provider.                            |
| Compact mobile width differs from current                                                  | Usability/visual regression             | Use CSS variable/media query; verify computed width at 390px and 479px.             |
| Gradient background is lost                                                                | Visual regression                       | Preserve scoped gallery surface wrapper.                                            |
| Folder tree active/hover states clash with sidebar tokens                                  | Readability regression                  | Keep current `FolderTreeItem` button classes; test light/dark.                      |
| Generated Sheet dependency introduces new overlay styles                                   | Broader modal style interactions        | Inspect generated `sheet` files and compare with existing `dialog` implementation.  |

## Open Questions

- Should desktop collapse remain true offcanvas width `0`, or is an icon rail acceptable? Recommendation: keep offcanvas for parity.
- Should tablet use the same 280px width as today while mobile uses 240px, or should all overlay sidebars use one shadcn mobile width? Recommendation: preserve 280px tablet and 240px mobile.
- Should the gallery keep the custom gradient sidebar surface, or adopt neutral shadcn sidebar colors? Recommendation: preserve current gradient in this migration.
- Should `cmd/ctrl+b` become a supported keyboard shortcut? Recommendation: disable or document explicitly; do not add silently.
- Should sidebar open/collapsed state be persisted? Recommendation: not in the parity migration; current `App.vue` starts open.
- Should `SidebarHeader.vue` be renamed to avoid confusion with shadcn `SidebarHeader`? Recommendation: yes, but as a cleanup after behavior is stable.
- Should the folder tree eventually become ARIA `tree`/`treeitem` instead of button-based recursive rows? Recommendation: separate accessibility refactor, not part of this shell migration.
- Should the App-level Escape handler be removed after Sheet migration? Recommendation: remove only after confirming Sheet Escape behavior across tablet/mobile.

## Rollback Plan

Each phase should be independently reversible:

- Phase 0 only adds generated primitives and token mappings.
- Phase 1 only extracts shared content and can be reverted by restoring duplicated markup.
- Phase 2 affects desktop only; tablet/mobile remain as fallbacks.
- Phase 3 customizes local generated sidebar source but does not remove existing overlays yet.
- Phase 4 removes tablet/mobile custom overlays only after the shadcn Sheet branch is proven.

If overlay behavior regresses late in the migration, keep the desktop shadcn sidebar and retain the current tablet/mobile custom overlay shells while still using `GallerySidebarContent` for deduplicated content.
