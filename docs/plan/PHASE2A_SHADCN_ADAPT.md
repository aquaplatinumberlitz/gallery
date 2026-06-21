# Phase 2A — Desktop UI Integration with shadcn-vue

**Status:** ✅ COMPLETED — 7ac7ec9

**Goal:** Migrate 6 desktop UI areas from hand-rolled HTML/CSS to shadcn-vue components.

Phase 1 and Phase 1.5 have already generated and validated the primitive shadcn-vue components. Phase 2A is the first desktop integration pass: replace selected raw buttons, hand-rolled dropdowns, and desktop navigation controls with those generated primitives while preserving existing behavior.

This phase is deliberately narrow. It must not become a broader layout, card, mobile, tablet, virtualization, or visual identity migration.

## Prerequisites

- Phase 1 + Phase 1.5 complete.
- shadcn-vue components available under `frontend/src/components/ui`.
- Required primitives present:
  - `frontend/src/components/ui/Button.vue`
  - `frontend/src/components/ui/Input.vue`
  - `frontend/src/components/ui/dropdown-menu/index.ts`
  - `DropdownMenu`, `DropdownMenuTrigger`, `DropdownMenuContent`, `DropdownMenuItem`, `DropdownMenuRadioGroup`, `DropdownMenuRadioItem`
- Neutral shadcn token bridge active through `_shadcn-token-bridge.css`.
- Desktop tests are passing before edits.

## Pixel-Level Defaults Policy

All migrated standard UI controls must use shadcn pixel-level defaults:

- Radius: `rounded-md` from the primitive, not `rounded-gallery-*`, `rounded-lg`, `rounded-[10px]`, or pills unless the primitive owns it.
- Shadow: shadcn primitive shadows only, such as `shadow-xs` on outline buttons and dropdown content defaults. Do not use `shadow-gallery-*` or warm orange shadows.
- Hover: neutral `hover:bg-accent hover:text-accent-foreground`.
- Focus: `focus-visible:ring-ring` through the primitive.
- Transition: `transition-colors` through the primitive.
- Colors: neutral bridged shadcn tokens only for standard UI. Do not apply gallery warm `--primary-color`, `--title-color`, `--folder-color`, or `color-mix()` to migrated controls.

Allowed exceptions:

- Brand hero visuals in `AppHeader.vue` remain warm/gallery-specific.
- Folder icons may keep semantic folder coloring where the icon itself is a content cue, but the standard button row hover/active/focus surface must be neutral shadcn styling.
- Existing mobile/tablet-only code remains unchanged.

## Migration order (by risk)

1. Open folder button — lowest risk, single button.
2. Nav buttons — simple icon button swap.
3. Sort dropdown — moderate risk, behavior preservation.
4. Density dropdown — moderate risk, radio group.
5. Search bar — higher risk, UX preservation.
6. Sidebar items — moderate risk, layout preservation.

After each item, run at least a focused browser smoke check and confirm there are no console errors.

## Import Policy

Use `@/components/ui/...` imports for all shadcn components touched in this phase. Normalize existing relative imports while editing the file.

Preferred imports:

```ts
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
```

Do not add new local wrapper components for this phase.

## 1. Open Folder Button

### File

- `frontend/src/components/GalleryGrid.vue`

### Current code location

In the desktop toolbar, immediately after `Breadcrumb`:

```vue
<button
  class="nav-btn open-folder"
  @click="openFolder"
  title="Open current folder in file explorer"
>
  <ArrowUpRight />
</button>
```

Current styles include warm, gallery-specific treatment:

- `.nav-btn.open-folder`
- `.nav-btn.open-folder:hover`
- `.nav-btn.open-folder:active`

These styles use `color-mix()`, `--primary-color`, warm borders, and warm shadows. They must be removed for the migrated desktop control.

### Target shadcn component

Use:

```vue
<Button
  variant="outline"
  size="sm"
  class="open-folder-btn"
  type="button"
  @click="openFolder"
  title="Open current folder in file explorer"
>
  <ArrowUpRight class="gallery-icon-sm" />
  <span>Open</span>
</Button>
```

If the toolbar becomes too tight at desktop width, keep the text because the requirement is an outline small button, not an icon-only button. Prefer reducing the label to `Open` over adding custom sizing.

### Import changes

Normalize `GalleryGrid.vue` shadcn imports:

```ts
- import Button from "./ui/Button.vue";
+ import Button from "@/components/ui/Button.vue";
```

Keep `ArrowUpRight` from `lucide-vue-next`.

### Style changes

Delete these blocks entirely:

```scss
.nav-btn.open-folder { ... }
.nav-btn.open-folder:hover { ... }
.nav-btn.open-folder:active { ... }
```

Do not replace them with custom warm variants.

Optional local class only for responsive hooks:

```scss
.open-folder-btn {
  /* Empty hook only if needed by existing responsive rules. */
}
```

If existing mobile rules hide `.nav-btn.open-folder`, do not depend on that for this new desktop-only button. The button lives inside `v-if="deviceCategory === 'desktop'"`, so no mobile/tablet hiding rule is needed.

### Preserve

- `openFolder()` must continue to call `galleryStore.openInExplorer()`.
- Button title must remain `Open current folder in file explorer`.
- Toolbar order must remain: nav buttons, breadcrumb, open folder, sort, density, loading badge.
- No changes to breadcrumb behavior.

### Verification

- Click the button with a valid current path and confirm the existing open-in-explorer behavior still fires.
- Confirm neutral outline appearance in light and dark themes.
- Confirm no warm hover, warm shadow, or orange active state remains on the button.

## 2. Nav Buttons

### File

- `frontend/src/components/GalleryGrid.vue`

### Current code location

In the desktop toolbar `nav-group`:

```vue
<Button
  variant="ghost"
  size="nav"
  class="nav-btn border border-border"
  :disabled="!canBack"
  @click="goBack"
  title="Back"
>
  <ArrowLeft />
</Button>
```

and the matching forward button.

The file already uses a local shadcn `Button`, but this phase should align it to the required target.

### Target shadcn component

Use `variant="ghost"` and `size="icon"`:

```vue
<Button
  variant="ghost"
  size="icon"
  class="nav-btn"
  :disabled="!canBack"
  type="button"
  @click="goBack"
  title="Back"
>
  <ArrowLeft class="gallery-icon-toolbar" />
</Button>

<Button
  variant="ghost"
  size="icon"
  class="nav-btn"
  :disabled="!canForward"
  type="button"
  @click="goForward"
  title="Forward"
>
  <ArrowRight class="gallery-icon-toolbar" />
</Button>
```

Do not keep `border border-border` unless product explicitly asks for bordered icon buttons. `ghost` should visually read as the shadcn ghost default.

### Import changes

Same as section 1:

```ts
import Button from "@/components/ui/Button.vue";
```

### Style changes

Keep `.nav-group` only if it remains needed for toolbar spacing:

```scss
.nav-group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
```

Keep `.nav-btn` only as a responsive/layout hook if needed. It must not define:

- `background`
- `border`
- `border-radius`
- `box-shadow`
- `color`
- `transition`
- hover/active visual states

Remove the migrated controls from this legacy focus selector:

```scss
.nav-btn:focus-visible,
.sort-trigger:focus-visible,
.sort-option:focus-visible,
.density-trigger:focus-visible,
.density-option:focus-visible { ... }
```

After this phase, focus visuals for migrated controls should come from shadcn primitives.

### Preserve

- `:disabled="!canBack"` and `:disabled="!canForward"`.
- `goBack()` and `goForward()` calls.
- Existing titles `Back` and `Forward`.
- Lucide chevron direction.

### Verification

- Back and forward disabled states match store state.
- Hover uses neutral `accent`.
- Focus-visible ring is neutral `ring`.
- No border appears unless inherited from the primitive.

## 3. Sort Dropdown

### File

- `frontend/src/components/GalleryGrid.vue`

### Current code location

State and handlers near the top of the script:

```ts
const showSortMenu = ref(false);
const sortMenuRef = ref<HTMLElement | null>(null);
const toggleSortMenu = () => { ... };
const selectSort = (field: SortField) => { ... };
const closeSortMenu = (e: MouseEvent) => { ... };
const handleSortMenuKeydown = (e: KeyboardEvent) => { ... };
```

Template block:

```vue
<div class="sort-dropdown" :class="{ open: showSortMenu }">
  <button class="sort-trigger" @click.stop="toggleSortMenu" title="Sort by">
    ...
  </button>
  <Transition name="dropdown">
    <div v-if="showSortMenu" ref="sortMenuRef" class="sort-menu" @keydown="handleSortMenuKeydown">
      <button v-for="option in sortOptions" class="sort-option" ...>
        ...
      </button>
    </div>
  </Transition>
</div>
```

### Target shadcn component

Use `DropdownMenu` with an outline small `Button` trigger:

```vue
<DropdownMenu>
  <DropdownMenuTrigger as-child>
    <Button variant="outline" size="sm" type="button" title="Sort by">
      <ArrowUpDown class="gallery-icon-sm" />
      <span>{{ currentSortLabel }}</span>
      <component
        :is="sortOrder === 'asc' ? ArrowUp : ArrowDown"
        class="gallery-icon-xs"
      />
      <ChevronDown class="gallery-icon-xs opacity-60" />
    </Button>
  </DropdownMenuTrigger>

  <DropdownMenuContent align="end" class="w-44">
    <DropdownMenuItem
      v-for="option in sortOptions"
      :key="option.field"
      class="gap-2"
      @select="selectSort(option.field)"
    >
      <component :is="_icons[option.icon]" class="gallery-icon-sm" />
      <span class="flex-1">{{ option.label }}</span>
      <component
        v-if="sortField === option.field"
        :is="sortOrder === 'asc' ? ArrowUp : ArrowDown"
        class="gallery-icon-xs"
      />
    </DropdownMenuItem>
  </DropdownMenuContent>
</DropdownMenu>
```

`DropdownMenuItem` should use `@select`, not `@click`, so keyboard activation and pointer selection share the same path.

### Import changes

Add:

```ts
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
```

Keep:

```ts
import Button from "@/components/ui/Button.vue";
```

### Script changes

Keep:

```ts
const sortOptions = ...
const currentSortLabel = ...
const selectSort = (field: SortField) => {
  if (sortField.value === field) {
    galleryStore.toggleSortOrder();
  } else {
    galleryStore.setSortField(field);
    galleryStore.setSortOrder(field === "date" ? "desc" : "asc");
  }
};
```

Remove because shadcn/reka owns open state, outside click, escape, roving focus, and keyboard navigation:

```ts
const showSortMenu = ref(false);
const sortMenuRef = ref<HTMLElement | null>(null);
const toggleSortMenu = () => { ... };
const closeSortMenu = (e: MouseEvent) => { ... };
const handleSortMenuKeydown = (e: KeyboardEvent) => { ... };
```

Remove sort references from lifecycle listeners:

```ts
document.addEventListener("click", closeSortMenu);
document.removeEventListener("click", closeSortMenu);
```

Only remove `onMounted` / `onBeforeUnmount` imports if density migration has also removed its document listeners.

### Style changes

Delete the entire legacy sort dropdown CSS:

```scss
.sort-dropdown { ... }
.sort-trigger { ... }
.sort-trigger:hover,
.density-trigger:hover { ... } // split first if density still uses it
.sort-dropdown.open .sort-trigger,
.density-dropdown.open .density-trigger { ... } // split first if density still uses it
.sort-label { ... }
.sort-chevron { ... }
.sort-dropdown.open .sort-chevron { ... }
.sort-menu { ... }
.sort-option { ... }
.sort-option:hover { ... }
.sort-option.active { ... }
.sort-direction { ... }
.dropdown-enter-active,
.dropdown-leave-active,
.dropdown-enter-from,
.dropdown-leave-to { ... } // after both dropdowns migrate
```

Do not recreate old dropdown animation with Vue `<Transition>`. The generated dropdown component owns its own animation and uses shadcn defaults.

### Preserve

- Clicking the currently selected sort item reverses direction.
- Selecting a different sort field sets default direction:
  - `date` defaults to `desc`
  - `name` defaults to `asc`
- Current selection indicator remains visible with the direction icon.
- Keyboard navigation works through shadcn/reka menu behavior.
- `sortItems()` behavior and gallery data ordering remain unchanged.

### Verification

- Open dropdown with mouse, Enter, and Space.
- Arrow through items with keyboard.
- Press Escape and confirm it closes.
- Select `Name`, click `Name` again, confirm direction toggles.
- Select `Date modified`, confirm default direction is descending.
- Confirm no custom warm active background or warm focus ring remains.

## 4. Density Dropdown

### File

- `frontend/src/components/GalleryGrid.vue`

### Current code location

State and handlers:

```ts
const showDensityMenu = ref(false);
const densityMenuRef = ref<HTMLElement | null>(null);
const densityOptions = computed(() => { ... });
const toggleDensityMenu = () => { ... };
const selectDensity = (level: number) => { ... };
const closeDensityMenu = (e: MouseEvent) => { ... };
const handleDensityMenuKeydown = (e: KeyboardEvent) => { ... };
```

Template block:

```vue
<div class="density-dropdown" :class="{ open: showDensityMenu }">
  <button class="density-trigger" ...>
    ...
  </button>
  <Transition name="dropdown">
    <div v-if="showDensityMenu" ref="densityMenuRef" class="density-menu" ...>
      <button v-for="option in densityOptions" class="density-option" ...>
        ...
      </button>
    </div>
  </Transition>
</div>
```

### Target shadcn component

Use `DropdownMenuRadioGroup` for exclusive selection:

```vue
<DropdownMenu>
  <DropdownMenuTrigger as-child>
    <Button variant="outline" size="sm" type="button" title="Thumbnail size">
      <LayoutGrid class="gallery-icon-sm" />
      <span>{{ columnCount }} cols</span>
      <ChevronDown class="gallery-icon-xs opacity-60" />
    </Button>
  </DropdownMenuTrigger>

  <DropdownMenuContent align="end" class="w-48">
    <DropdownMenuRadioGroup
      :model-value="String(sliderLevel)"
      @update:model-value="(value: string) => selectDensity(Number(value))"
    >
      <DropdownMenuRadioItem
        v-for="option in densityOptions"
        :key="option.level"
        :value="String(option.level)"
        class="gap-2"
      >
        <LayoutGrid class="gallery-icon-sm" />
        <span class="flex-1">{{ option.label }}</span>
        <span class="text-xs text-muted-foreground">{{ option.columns }} cols</span>
      </DropdownMenuRadioItem>
    </DropdownMenuRadioGroup>
  </DropdownMenuContent>
</DropdownMenu>
```

Do not add a manual `Check` icon if `DropdownMenuRadioItem` already renders a radio/check indicator. If the generated local component does not render an indicator, add a trailing `Check` only using neutral `text-foreground` or `text-muted-foreground`, not `--primary-color`.

### Import changes

Add:

```ts
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
```

If sort and density are migrated in the same commit, combine the dropdown imports once.

### Script changes

Keep:

```ts
const densityOptions = computed(() => { ... });
const selectDensity = (level: number) => {
  sliderLevel.value = level;
};
```

Remove menu-state concerns:

```ts
const showDensityMenu = ref(false);
const densityMenuRef = ref<HTMLElement | null>(null);
const toggleDensityMenu = () => { ... };
const closeDensityMenu = (e: MouseEvent) => { ... };
const handleDensityMenuKeydown = (e: KeyboardEvent) => { ... };
```

Remove density document listeners:

```ts
document.addEventListener("click", closeDensityMenu);
document.removeEventListener("click", closeDensityMenu);
```

After both sort and density are migrated, remove unused imports:

```ts
onMounted;
onBeforeUnmount;
ref; // only if no other refs remain in the file
Check; // if no longer used elsewhere
```

Do not remove `computed`, `inject`, or other refs used by virtualization or scroller code.

### Style changes

Delete the entire legacy density dropdown CSS:

```scss
.density-dropdown { ... }
.density-trigger { ... }
.density-label { ... }
.density-chevron { ... }
.density-dropdown.open .density-chevron { ... }
.density-menu { ... }
.density-option { ... }
.density-option:hover { ... }
.density-option.active { ... }
.density-cols { ... }
.density-option.active .density-cols { ... }
.density-check { ... }
```

After both dropdowns are migrated, delete shared dropdown transition styles:

```scss
.dropdown-enter-active,
.dropdown-leave-active,
.dropdown-enter-from,
.dropdown-leave-to { ... }
```

### Preserve

- `densityOptions` tablet dedupe logic exactly as-is:
  - Keep `deviceCategory.value !== 'tablet'` branch.
  - Keep `GRID_COLUMN_MAP.tablet`.
  - Keep `seen` Set dedupe by `columns`.
- Trigger label continues to show current count: `{{ columnCount }} cols`.
- Selecting an item continues to update `sliderLevel.value`.
- Gallery grid column calculation remains owned by `useColumnResize`.

### Verification

- Open density menu and confirm radio selection reflects current `sliderLevel`.
- Select each density option and confirm thumbnail column count changes.
- Confirm tablet options remain deduped by columns if testing tablet viewport, but do not edit `TabletGalleryToolbar.vue`.
- Confirm dropdown keyboard navigation works.
- Confirm no manual warm selected background remains.

## 5. Search Bar

### File

- `frontend/src/components/AppHeader.vue`

### Current code location

Desktop search shell inside `.header-actions`:

```vue
<div class="search-box">
  <Search class="gallery-icon-toolbar search-icon" />
  <Input ... variant="ghost" type="search" ... />
  <Button v-if="searchQuery" variant="ghost" size="icon-sm" class="clear-btn" ...>
    <X class="gallery-icon-xs" />
  </Button>
  <select class="scope-select" ...>
    ...
  </select>
</div>
```

The file already uses local `Input` and `Button` primitives, but still has a hand-rolled search shell with warm hover/focus styling.

### Target shadcn components

Use shadcn `Input` for the field and shadcn ghost icon buttons for icon/clear actions. Keep the existing container only as a layout shell.

Target desktop structure:

```vue
<div class="search-box">
  <Button
    variant="ghost"
    size="icon"
    class="search-icon-btn"
    type="button"
    title="Search"
    aria-label="Search"
  >
    <Search class="gallery-icon-toolbar" />
  </Button>

  <Input
    id="gallery-search"
    :modelValue="searchQuery"
    @update:model-value="(v: string) => emit('update:searchQuery', v)"
    type="search"
    placeholder="Photos, albums, prompts"
    autocomplete="off"
    class="search-input"
  />

  <Button
    v-if="searchQuery"
    variant="ghost"
    size="icon"
    class="clear-btn"
    type="button"
    title="Clear search"
    aria-label="Clear search"
    @click="clearSearch"
  >
    <X class="gallery-icon-xs" />
  </Button>

  <select
    class="scope-select"
    :value="searchScope"
    aria-label="Search scope"
    @change="onScopeChange"
  >
    <option value="current">This folder</option>
    <option value="all">All indexed</option>
  </select>
</div>
```

If the actual current branch still has desktop expand/collapse/backdrop/cancel behavior, preserve it. In that case:

- Keep the reactive state and backdrop/cancel template branches.
- Replace only the raw input with `Input`.
- Replace raw search and clear icon buttons with `Button variant="ghost" size="icon"`.
- Preserve the cancel text button behavior; it may remain a plain text button if it is not a standard icon control, but remove warm hover/focus styles from it.

### Import changes

Normalize:

```ts
- import Button from './ui/Button.vue'
- import Input from './ui/Input.vue'
+ import Button from "@/components/ui/Button.vue";
+ import Input from "@/components/ui/Input.vue";
```

### Style changes

Change `.search-box` from warm custom focus shell to neutral shadcn-compatible shell.

Replace:

```scss
.search-box {
  background: var(--surface-color);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 10px;
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
}

.search-box:hover {
  border-color: var(--primary-color);
  box-shadow: var(--gallery-shadow-md, ...);
}

.search-box:focus-within {
  border-color: var(--primary-color);
  box-shadow: var(--gallery-shadow-md, ...);
}
```

with:

```scss
.search-box {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 220px;
  height: 40px;
}
```

Let `Input` own border, radius, shadow, focus ring, and transition. Do not put a second visible border/focus ring on `.search-box`.

Use layout-only classes if needed:

```scss
.search-input {
  min-width: 0;
}

.search-icon-btn,
.clear-btn {
  flex-shrink: 0;
}
```

Remove warm search styles:

- `.search-box:hover` with `--primary-color`
- `.search-box:focus-within` with `--primary-color`
- mobile-only duplicated `.search-box:hover` / `:focus-within` warm rules if they affect desktop code paths
- custom `.search-box input` rules that override shadcn `Input`, except the iOS font-size rule listed below
- custom `.search-box .clear-btn` background/border/radius/hover rules

Keep and verify the iOS Safari zoom fix:

```scss
@media (max-width: 767px) {
  .search-box input {
    font-size: 16px;
  }
}
```

Do not edit `MobileHeader.vue` or `TabletHeader.vue`.

### Preserve

- `searchQuery` remains controlled through `update:searchQuery`.
- `clearSearch()` continues to emit an empty string.
- `searchScope` select continues to emit `scope-change`.
- Existing desktop search expand/collapse behavior, if present in the active branch.
- Clear button only appears when `searchQuery` is non-empty.
- Backdrop behavior, if present in the active branch.
- Cancel text button behavior, if present in the active branch.
- iOS font-size must remain 16px for mobile search input rules to avoid auto zoom.

### Verification

- Type in desktop header search and confirm gallery filtering/search still updates.
- Clear button clears the query and disappears.
- Scope select still switches between `current` and `all`.
- If expand/collapse exists, test expand, type, clear, cancel, and backdrop click.
- Inspect focus state: neutral shadcn ring, no warm shadow.
- In mobile-sized viewport, confirm no mobile/tablet header files were touched and iOS font-size rule remains.

## 6. Sidebar Items

### Files

- `frontend/src/components/SidebarHeader.vue`
- `frontend/src/components/FolderTreeItem.vue`
- `frontend/src/layouts/DesktopLayout.vue`

### Scope

This item migrates desktop sidebar navigation item controls to shadcn `Button`. It does not redesign the sidebar, root path editor, mobile root path sheet, or tablet overlay behavior.

### Current code locations

`FolderTreeItem.vue` uses a clickable row plus a raw toggle button:

```vue
<div
  ref="itemRef"
  class="tree-row ..."
  :class="{ active: isActive }"
  @click="onSelect"
  @keydown="handleKeydown"
>
  <button class="toggle-btn" ...>
    <component :is="arrowIcon" class="gallery-icon-xs" />
  </button>
  ...
</div>
```

`DesktopLayout.vue` uses a raw sidebar edge toggle:

```vue
<button class="sidebar-edge-toggle" ...>
  <ChevronLeft v-if="isSidebarOpen" class="gallery-icon-sm" />
  <ChevronRight v-else class="gallery-icon-sm" />
</button>
```

`SidebarHeader.vue` already uses local shadcn `Input` and `Button` for the desktop root path reset, but imports are relative.

### Target shadcn components

#### Folder row

Use a shadcn ghost small button for the row:

```vue
<Button
  ref="itemRef"
  variant="ghost"
  size="sm"
  type="button"
  class="tree-row w-full justify-start gap-1.5 px-1.5 py-[3px] text-[13px]"
  :class="{ 'bg-accent text-accent-foreground': isActive }"
  @click="onSelect"
  @keydown="handleKeydown"
>
  ...
</Button>
```

Important: `Button.vue` currently exposes a native `<button>`, so check whether Vue component refs still resolve correctly for `itemRef`. If `itemRef` is not used elsewhere, remove it. If it is needed later, prefer a native wrapper ref outside the button.

#### Folder expand/collapse control

Avoid nesting a `<button>` inside a shadcn `<Button>` row. HTML must not contain nested interactive buttons.

Preferred structure:

```vue
<div class="tree-row-shell flex items-center gap-1.5">
  <Button
    variant="ghost"
    size="icon"
    class="toggle-btn size-7 shrink-0"
    type="button"
    :disabled="!node.has_children"
    @click.stop="onToggle"
    :aria-label="isOpen ? 'Collapse folder' : 'Expand folder'"
  >
    <component :is="arrowIcon" class="gallery-icon-xs" />
  </Button>

  <Button
    variant="ghost"
    size="sm"
    type="button"
    class="tree-row min-w-0 flex-1 justify-start gap-1.5 px-1.5 py-[3px] text-[13px]"
    :class="{ 'bg-accent text-accent-foreground': isActive }"
    @click="onSelect"
    @keydown="handleKeydown"
  >
    <component :is="folderIcon" class="folder-icon gallery-icon-md" />
    <span class="name flex-1 min-w-0 truncate text-left">{{ node.name }}</span>
    <Loader v-if="isLoading" class="gallery-icon-sm lucide-spin spinner" />
  </Button>
</div>
```

This preserves independent expand/collapse and select actions while using shadcn buttons for both controls.

#### Sidebar edge toggle

Use shadcn `Button` for the edge toggle only if it can preserve fixed positioning without fighting the primitive:

```vue
<Button
  variant="ghost"
  size="icon"
  class="sidebar-edge-toggle"
  type="button"
  @click="emit('toggleSidebar')"
  :title="isSidebarOpen ? 'Hide Sidebar' : 'Show Sidebar'"
>
  <ChevronLeft v-if="isSidebarOpen" class="gallery-icon-sm" />
  <ChevronRight v-else class="gallery-icon-sm" />
</Button>
```

Keep the fixed position, dimensions, and collapsed left offset in `.sidebar-edge-toggle`; remove warm hover color/shadow.

### Import changes

`FolderTreeItem.vue`:

```ts
import Button from "@/components/ui/Button.vue";
```

`DesktopLayout.vue`:

```ts
import Button from "@/components/ui/Button.vue";
```

`SidebarHeader.vue`:

```ts
- import Input from "./ui/Input.vue";
- import Button from "./ui/Button.vue";
+ import Input from "@/components/ui/Input.vue";
+ import Button from "@/components/ui/Button.vue";
```

### Style changes

#### `FolderTreeItem.vue`

Remove warm row hover/active styling:

```scss
.tree-row:hover {
  background: var(--gallery-surface-hover, ...);
}

.tree-row.active {
  background: color-mix(in srgb, var(--primary-color) 16%, transparent);
  color: var(--primary-color);
}

.tree-row.active::before { ... }
```

Replace with neutral class bindings in the template:

```vue
:class="{ 'bg-accent text-accent-foreground': isActive }"
```

Remove warm toggle styles:

```scss
.toggle-btn {
  border: 1px solid var(--gallery-border-subtle, ...);
  border-radius: 8px;
  transition:
    border-color 120ms ease,
    background-color 120ms ease;
}

.toggle-btn:not(:disabled):hover {
  border-color: var(--primary-color);
  background: var(--gallery-surface-hover, ...);
}
```

Do not recreate the active left rail with `--primary-color` in Phase 2A. If product still needs an active marker later, implement it with neutral border/accent tokens after approval.

Keep only layout and icon-size rules:

```scss
.tree-item {
}
.children {
}
.empty-children {
}
.folder-icon {
  color: var(--folder-color);
}
```

`--folder-color` is acceptable for the folder glyph itself, not for standard button surfaces.

Remove custom focus styles:

```scss
.tree-row:focus { ... }
.tree-row:focus:not(:focus-visible) { ... }
.tree-row:focus-visible { ... }
```

The shadcn `Button` focus-visible ring should own focus.

#### `DesktopLayout.vue`

Keep layout-only edge toggle rules:

```scss
.sidebar-edge-toggle {
  position: fixed;
  left: 260px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 101;
  width: 24px;
  height: 48px;
}

.sidebar-edge-toggle:not(.sidebar-open) {
  left: 0;
}
```

Remove warm standard UI styling from `.sidebar-edge-toggle`:

- `background: var(--surface-color)`
- `color: var(--muted-text)`
- `box-shadow: var(--gallery-shadow-sm, ...)`
- hover `color: var(--primary-color)`
- hover `box-shadow: var(--gallery-shadow-md, ...)`

If a visible edge handle is still required, add neutral Tailwind utilities in the template instead of CSS color formulas:

```vue
class="sidebar-edge-toggle border border-border bg-background shadow-xs"
```

Prefer relying on the `Button` primitive and keeping only fixed positioning unless the handle loses necessary visibility.

#### `SidebarHeader.vue`

For Phase 2A, only normalize imports unless the root path field is explicitly included in the sidebar item migration. Do not edit mobile root path display.

If touching the desktop root path field, remove warm shell hover/focus:

```scss
.field-container:hover {
  border-color: var(--primary-color, #ff6b35);
  box-shadow: var(--gallery-shadow-md, ...);
}

.field-container:focus-within {
  border-color: var(--primary-color, #ff6b35);
  box-shadow: var(--gallery-shadow-md, ...);
}
```

and let `Input` / `Button` own their focus and hover states. Keep `field-container` as a layout shell only.

### Preserve

- Folder select behavior calls `galleryStore.selectFolder(props.node)`.
- Mobile/tablet close behavior remains:

```ts
if (isMobile.value || isTablet.value) {
  closeSidebar();
}
```

- Folder expand/collapse behavior calls `galleryStore.toggleFolderExpanded(props.node.path)`.
- Keyboard behavior:
  - Enter/Space select folder.
  - ArrowRight expands when children exist.
  - ArrowLeft collapses when open.
- Lazy child loading through `useFolderChildrenQuery`.
- Empty and error child states.
- Collapsible sidebar state in `DesktopLayout.vue`.
- Edge-toggle position and behavior.
- Tablet rule hiding the edge toggle.

### Verification

- Select a folder; active state changes and content loads.
- Expand/collapse nested folders with pointer and keyboard.
- Confirm no nested button accessibility warning appears in the DOM.
- Confirm sidebar closes on mobile/tablet selection, but do not edit mobile/tablet files.
- Toggle sidebar open/closed with edge button on desktop.
- Confirm edge toggle still hides on tablet breakpoint.
- Confirm standard sidebar item surfaces use neutral shadcn hover/focus/active styling.

## Do Not Touch

Frozen files and areas for Phase 2A:

- `frontend/src/components/MobileHeader.vue`
- `frontend/src/components/TabletHeader.vue`
- `frontend/src/components/TabletGalleryToolbar.vue`
- `frontend/src/components/MobileFloatingBottomBar.vue`
- `frontend/src/components/AlbumCard.vue`
- `frontend/src/components/PhotoCard.vue`
- `frontend/src/components/AlbumScroller.vue`
- `frontend/src/components/AlbumCardMobile.vue`
- `frontend/src/components/AlbumCardTablet.vue`
- `frontend/src/components/Lightbox.vue`
- `frontend/src/components/LightboxMobileSheet.vue`
- `frontend/src/components/LightboxTabletPanel.vue`
- `frontend/src/components/PhotoSwipeViewer.vue`
- `frontend/src/components/MobilePhotoSwipe.vue`
- `frontend/src/components/TabletPhotoSwipe.vue`
- GalleryGrid virtualization and scroller code.
- Image loading, infinite scan query, pull-to-refresh, and lightbox opening.
- AlbumCard, PhotoCard, and AlbumScroller templates or styles.
- Global brand hero animation/keyframe styles.
- shadcn primitive implementation files unless a compile error proves a local primitive API mismatch.

Frozen patterns for migrated standard UI:

- Do not add `shadow-gallery-*`.
- Do not add `rounded-gallery-*`.
- Do not add warm `--primary-color` hover/focus/active styling.
- Do not add warm `--title-color` or `--neon-color` to standard UI.
- Do not add `color-mix()` to migrated shadcn controls.
- Do not add bespoke click-outside handlers for shadcn dropdowns.
- Do not reintroduce Vue `<Transition>` around shadcn dropdown content.

## Testing

Run the full verification suite after all six migrations:

```bash
npx vue-tsc --noEmit
npm run build
npx playwright test
```

Expected Playwright result:

```text
101/101 passing
```

Additional manual checks:

- Open the app in light and dark themes.
- Check browser console after each migration area; there should be no warnings or errors.
- Confirm desktop toolbar controls still fit at common desktop widths.
- Confirm sort and density dropdowns work with pointer and keyboard.
- Confirm desktop search still updates, clears, and changes scope.
- Confirm sidebar folder navigation, expand/collapse, active state, and edge toggle still work.
- Confirm mobile/tablet routes and dedicated toolbar/header components were not modified.

## Implementation Checklist

- [ ] Normalize shadcn imports in touched files to `@/components/ui/...`.
- [ ] Replace GalleryGrid open-folder raw button with `Button variant="outline" size="sm"`.
- [ ] Replace GalleryGrid desktop back/forward controls with `Button variant="ghost" size="icon"`.
- [ ] Replace GalleryGrid sort dropdown with `DropdownMenu`.
- [ ] Remove sort dropdown document click handlers, refs, Vue transition, and warm CSS.
- [ ] Replace GalleryGrid density dropdown with `DropdownMenuRadioGroup`.
- [ ] Remove density dropdown document click handlers, refs, Vue transition, and warm CSS.
- [ ] Replace/normalize AppHeader desktop search field and icon controls with `Input` and `Button`.
- [ ] Preserve search clear/scope/expand/cancel/backdrop behavior where present.
- [ ] Replace desktop sidebar folder row/toggle controls with non-nested shadcn `Button` controls.
- [ ] Normalize `SidebarHeader.vue` imports and avoid mobile root path edits.
- [ ] Replace DesktopLayout edge toggle with shadcn `Button` if layout can be preserved.
- [ ] Remove migrated warm UI CSS and custom focus styles.
- [ ] Run `npx vue-tsc --noEmit`.
- [ ] Run `npm run build`.
- [ ] Run `npx playwright test`.
- [ ] Manually check browser console after each migration area.
