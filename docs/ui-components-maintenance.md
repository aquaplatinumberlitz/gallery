# UI Components Maintenance

## EmptyState — State Model

The gallery displays 5 distinct states based on path + `hasEverLoaded`:

| State | Condition | Message |
|-------|-----------|---------|
| **No path selected** | `!rootPath` | Welcome screen with instructions |
| **Not loaded yet** | `rootPath && !hasEverLoaded` | "Gallery not loaded" — click Load to start |
| **Loading** | `isLoading` | Skeleton loader |
| **Loaded, truly empty** | `loaded && !folders.length && !images.length` | "This folder is empty" |
| **Folders only** | `loaded && folders.length && !images.length` | Shows albums only |
| **Has images** | `loaded && images.length` | Gallery grid with optional album carousel |

**Key guard:** `hasEverLoaded` flag in `gallery.ts` store — prevents false "empty" state before first scan completes. It is `false` initially, set to `true` only after a successful API scan. `resetRootPath()` resets it to `false`.

**Auto-load:** On mount, if a persisted root path exists (`localStorage`), `App.vue` auto-loads it via `setRootPath(rootPath)`. The `onMounted` guard ensures this only happens once.

## Sidebar / Drawer Behavior

### Desktop Sidebar
- Persistent 280px, always visible
- Collapsible via edge toggle button (narrow strip on sidebar edge)
- In DOM at all times (`v-if` not used)
- CSS class toggle for collapsed state

### Tablet Drawer
- Always in DOM (no `v-if`) — CSS `transform: translateX(-100%)` to hide
- Closed state: `inert`, `aria-hidden="true"`, `pointer-events: none`
- Open/close via `isSidebarOpen` ref + CSS class `.open`
- Animation: `transition: transform 0.22s cubic-bezier(...)`
- `backdrop-filter: blur(...)` was removed because it caused close delay on iPad
- Hamburger in `TabletHeader` toggles drawer — does NOT trigger path reload
- Successful path submit from `SidebarHeader` calls `closeSidebar()` via injection key
- Invalid path keeps drawer open
- Backdrop wrapped in `<Transition>` for fade animation

### Mobile Sidebar
- Overlay drawer, slides from left
- Wrapped in `<Transition>` with `v-if` (destroy on close)
- Backdrop close on tap

## Icon Token System

### CSS Variable Tokens (`tokens.css`)

```css
--gallery-icon-xs:  14px;
--gallery-icon-sm:  18px;
--gallery-icon-md:  22px;
--gallery-icon-lg:  28px;
--gallery-icon-xl:  32px;
--gallery-icon-xxl: 40px;

--gallery-icon-toolbar: var(--gallery-icon-sm);  /* toolbar buttons */
--gallery-icon-nav:     var(--gallery-icon-md);    /* navigation arrows */
--gallery-icon-action:  var(--gallery-icon-lg);    /* action buttons */
```

### Usage Rules

1. **Prefer semantic tokens** (`--gallery-icon-toolbar`) over raw size tokens (`--gallery-icon-sm`) for consistency
2. **Lucide SVGs in scoped components** — CSS may not penetrate Lucide's inline SVG. Use `:deep()` on the parent class + `flex-shrink: 0` to prevent flexbox squeeze
3. **Avoid hardcoded `:size` on Lucide components** unless component-specific (e.g., debug overlay needs 40px). Use `:size` with CSS token variable binding or omit for default
4. **Always set `flex-shrink: 0`** on icons inside flex/grid layouts — otherwise the SVG can be compressed irregularly

## AlbumScroller Arrows

- 46×46px circular buttons, absolutely positioned
- Edge fade gradient for visual hint
- Safari fallback: `rgba()` before `color-mix()`, guarded by `@supports`
- Disabled arrows: `opacity: 0` (not removed from DOM to avoid layout shift)

## Mobile Sort Menu

Unified with PC/tablet compact sort model:
- 2 options only: **Name** (default asc) and **Date modified** (default desc)
- Click same option → toggle direction (↕ icon)
- Switch option → default direction for new field
- Type/Clock icons + ArrowUp/ArrowDown on active row
- No 4-row menu (removed Newest/Oldest/Name A-Z/Z-A duplication)
