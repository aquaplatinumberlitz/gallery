# Immich Library Management UI/UX Adaptation Plan

> **Goal:** Adapt Immich's library management interface into our gallery app as a Desktop-only admin panel for managing library registrations, scanning, folders, and exclusion patterns.
>
> **Status:** Backend API already exists — `GET/POST /api/libraries`, `GET /api/libraries/{id}`, `POST /api/libraries/{id}/scan`, `POST /api/libraries/{id}/repair`, `DELETE /api/libraries/{id}`, `POST /api/index/rebuild`. No frontend exists yet.

---

## 1. Immich Library Management Overview

Immich implements library management as a **SvelteKit route group** under `/admin/library-management/` with:

| Route | File | Purpose |
|---|---|---|
| `/admin/library-management` | `(list)/+page.svelte` + `(list)/+layout.svelte` | **Library List** — table of all libraries with stats (photos, videos, size), owner, actions per row |
| `(list)/+layout.ts` | Data loader — fetches `getAllLibraries()`, `getLibraryStatistics()`, owner info | |
| `/admin/library-management/new` | `(list)/new/+page.svelte` | **New Library** — modal-style form (page, not actual modal) with owner picker |
| `/admin/library-management/[id]` | `[id]/+layout.svelte` | **Library Detail** — stat cards (photos/videos/usage), **Import Paths** card, **Exclusion Patterns** card |
| `[id]/+layout.ts` | Data loader — fetches `getLibrary({id})` + `getLibraryStatistics({id})` | |
| `/admin/library-management/[id]/edit` | `[id]/edit/+page.svelte` | **Edit Library** — rename-only modal-style form |

### Modal Components (opened via `action` items on cards):

| Modal | File | Purpose |
|---|---|---|
| `LibraryFolderAddModal` | `.../LibraryFolderAddModal.svelte` | Add an import path (single text input) |
| `LibraryFolderEditModal` | `.../LibraryFolderEditModal.svelte` | Edit an existing import path |
| `LibraryExclusionPatternAddModal` | `.../LibraryExclusionPatternAddModal.svelte` | Add a glob exclusion pattern |
| `LibraryExclusionPatternEditModal` | `.../LibraryExclusionPatternEditModal.svelte` | Edit an exclusion pattern |

### Key UI Patterns Used:

1. **AdminPageLayout** — breadcrumb + action buttons bar wrapper for all admin pages
2. **Container** — centered content wrapper with size variants (`large`, `small`)
3. **Table** — striped table with skeleton loaders while stats resolve
4. **ServerStatisticsCard** — icon+title+value card for stats (photos/videos/usage)
5. **AdminCard** — reusable card with icon, title, and optional header action button
6. **FormModal** — full-page modal pattern (rendered as an in-page route, not an overlay)
7. **ContextMenuButton** — 3-dot menu per row for row actions (Detail, Scan, Edit, Delete)
8. **CommandPaletteDefaultProvider** — keyboard shortcut integration
9. **EventManager** — event-based invalidation via `OnEvents` component (`LibraryCreate`, `LibraryUpdate`, `LibraryDelete`)

---

## 2. What to Learn (Patterns Worth Adopting)

### 2.1 Layout Architecture

**Immich Pattern (SvelteKit route groups):**
```
( list )/  ← route group (no URL segment)
  +layout.svelte  ← list page shell with table + slot for children
  +layout.ts      ← data fetching (libraries, owners, stats)
  new/+page.svelte ← create form
  new/+page.ts     ← loader
[id]/             ← detail route
  +layout.svelte  ← detail page with stat cards + folders + exclusion patterns
  +layout.ts      ← data fetching (library, stats)
  edit/+page.svelte ← edit form
  edit/+page.ts     ← loader
```

**Gallery Adaptation:** Use Vue Router nested route structure with named views if needed. A flat route structure with separate components works too:

```
/admin/libraries          → LibraryListPage.vue
/admin/libraries/new      → LibraryCreatePage.vue (modal dialog instead of page)
/admin/libraries/:id      → LibraryDetailPage.vue
/admin/libraries/:id/edit → LibraryEditModal.vue (dialog)
```

### 2.2 Table with Skeleton Loading

Immich's library list table renders skeleton loaders inline (`#await data.statisticsPromise`) while stats are being fetched:

```svelte
<TableCell class={classes.column3}>
  <span class="skeleton-loader inline-block h-4 w-14"></span>
</TableCell>
```

**Gallery Adaptation:** Use TanStack Query's `isPending` state + `<Skeleton>` component (already exists at `@/components/ui/skeleton/`) to show shimmer placeholders while stats load.

### 2.3 Card-Based Detail Layout with Grid

Immich uses a responsive 2-column grid for the detail page:

```svelte
<div class="grid w-full grid-cols-1 gap-4 lg:grid-cols-2">
  <Heading tag="h1" size="large" class="col-span-full">{library.name}</Heading>
  <div class="col-span-full flex flex-col gap-4 lg:flex-row">
    <!-- stat cards -->
  </div>
  <AdminCard icon={mdiFolderOutline} title={$t('folders')} headerAction={AddFolder}>
    <!-- import paths list -->
  </AdminCard>
  <AdminCard icon={mdiFilterMinusOutline} title={$t('exclusion_pattern')} headerAction={AddExclusionPattern}>
    <!-- exclusion patterns list -->
  </AdminCard>
</div>
```

**Gallery Adaptation:** Use Tailwind's `grid-cols-1 lg:grid-cols-2` with `Card` components from shadcn-vue (via `@/components/ui/card/` if it exists, or the existing library-inspector table approach).

### 2.4 Inline Action Items Pattern

Immich uses `ActionItem` objects with icon + title + onAction + keyboard shortcuts:

```ts
const Edit: ActionItem = {
  icon: mdiPencilOutline,
  title: $t('edit'),
  onAction: () => goto(Route.editLibrary(library)),
  shortcuts: { key: 'r' },
};
```

**Gallery Adaptation:** Use a simpler Vue-friendly approach — emit events or call composable functions directly from button click handlers. Since we don't have a global command palette, we can skip the `ActionItem` abstraction and use inline handlers.

### 2.5 Modal-as-Page vs. Dialog Overlay

Immich renders modals as **actual routes** (`new/+page.svelte`, `edit/+page.svelte`) using `FormModal` which looks like a modal overlay but is a full page:

```svelte
<FormModal title={$t('create_library')} icon={mdiFolderSync}
  size="small" submitText={$t('create')} {onClose} {onSubmit}>
  <Field label={$t('owner')}>
    <Select bind:value={ownerId} options={...} />
    <HelperText color="warning">...</HelperText>
  </Field>
</FormModal>
```

**Gallery Adaptation:** **Do the opposite** — use actual `<Dialog>` components from shadcn-vue (Reka UI based) as overlays. This is simpler and avoids route nesting for transient forms. The `Dialog` components already exist at `@/components/ui/dialog/`.

### 2.6 Duplicate Detection Before API Call

Immich checks for duplicate folders/patterns **client-side** before calling the API:

```ts
if (library.importPaths.includes(folder)) {
  toastManager.danger($t('errors.library_folder_already_exists'));
  return false;
}
```

**Gallery Adaptation:** Adopt the same pattern — validate client-side for a fast feedback loop, then call the API.

### 2.7 Confirmation Dialogs for Destructive Actions

Deleting a library shows a two-stage confirmation if it has assets:

```ts
const confirmed = await modalManager.showDialog({ prompt: ... });
if (!confirmed) return;
if (library.assetCount > 0) {
  const isConfirmed = await modalManager.showDialog({ prompt: ... });
  if (!isConfirmed) return;
}
```

**Gallery Adaptation:** Use Vue's `<Dialog>` with a confirmation message + a `confirm` query param or internal state. The `useToast` composable already exists for success/error notifications.

---

## 3. What NOT to Follow

### 3.1 No Route Group Pattern (SvelteKit-specific)

Immich's `(list)/` route group is a SvelteKit convention for URL-less grouping. Vue Router doesn't have this concept. Instead, use flat route paths as described above.

### 3.2 No Svelte Runes / $state / $derived

Immich uses Svelte 5's runes (`$state()`, `$derived()`, `$props()`) which don't exist in Vue. Use Vue 3's `ref()`, `computed()`, `defineProps()` instead.

### 3.3 No Global Modal Manager

Immich's `modalManager.show(Component, props)` is a singleton service. In Vue, use a composable or pass dialog open state via props/events. Shadcn-vue's `<Dialog>` handles this with `v-model:open`.

### 3.4 No Event Manager for Cache Invalidation

Immich uses `eventManager.emit()` + `OnEvents` component + `invalidate()` for cache invalidation. Gallery uses TanStack Query — simply call `queryClient.invalidateQueries({ queryKey: [...] })` after mutations.

### 3.5 Skip the Command Palette Integration

Immich's `CommandPaletteDefaultProvider` is a heavy abstraction for keyboard shortcuts. Gallery doesn't have a command palette. Skip it.

### 3.6 No Separate Edit Page

Immich creates an entire route for editing (`[id]/edit/+page.svelte`). For the gallery, use a `<Dialog>` triggered from the detail page instead — simpler UX, no route change.

### 3.7 Skip Owner Assignment (Gallery is Single-User)

Immich's library creation requires an owner picker (`<Select>` with users). Our gallery is single-user. Skip the owner field entirely — libraries are implicitly owned by the single gallery user.

### 3.8 No Skeleton-Loader CSS in Components

Immich defines skeleton-loader CSS locally in each component. We already have `<Skeleton>` from shadcn-vue (`@/components/ui/skeleton/`). Use that instead.

### 3.9 No Stale-While-Revalidate for Stats

Immich loads stats via a separate promise and renders skeletons. Since our TanStack Query setup already handles caching and stale time, we can load stats as part of the normal query flow.

---

## 4. Gallery Adaptation Plan

### 4.1 New Components to Create

#### Pages (Vue Router views):

| Component | Path | Purpose |
|---|---|---|
| `LibraryListPage.vue` | `@/components/admin/LibraryListPage.vue` | Library list with table |
| `LibraryDetailPage.vue` | `@/components/admin/LibraryDetailPage.vue` | Library detail with stats + folders + exclusion patterns |

#### Shared Components:

| Component | Path | Purpose |
|---|---|---|
| `LibraryStatCard.vue` | `@/components/admin/LibraryStatCard.vue` | Single stat card (icon + label + value) |
| `LibraryImportPathsCard.vue` | `@/components/admin/LibraryImportPathsCard.vue` | Card showing import paths list with edit/delete |
| `LibraryExclusionPatternsCard.vue` | `@/components/admin/LibraryExclusionPatternsCard.vue` | Card showing exclusion patterns with edit/delete |

#### Dialogs / Modals:

| Component | Path | Purpose |
|---|---|---|
| `LibraryCreateDialog.vue` | `@/components/admin/dialogs/LibraryCreateDialog.vue` | Create library dialog (path input + optional name) |
| `LibraryEditDialog.vue` | `@/components/admin/dialogs/LibraryEditDialog.vue` | Edit library name dialog |
| `LibraryFolderAddDialog.vue` | `@/components/admin/dialogs/LibraryFolderAddDialog.vue` | Add import path dialog |
| `LibraryFolderEditDialog.vue` | `@/components/admin/dialogs/LibraryFolderEditDialog.vue` | Edit import path dialog |
| `LibraryExclusionPatternAddDialog.vue` | `@/components/admin/dialogs/LibraryExclusionPatternAddDialog.vue` | Add exclusion pattern dialog |
| `LibraryExclusionPatternEditDialog.vue` | `@/components/admin/dialogs/LibraryExclusionPatternEditDialog.vue` | Edit exclusion pattern dialog |
| `LibraryDeleteConfirmDialog.vue` | `@/components/admin/dialogs/LibraryDeleteConfirmDialog.vue` | Confirm delete (with asset warning) |

#### Composables:

| Composable | Path | Purpose |
|---|---|---|
| `useLibrariesQuery.ts` | `@/composables/admin/useLibrariesQuery.ts` | TanStack Query for library list |
| `useLibraryQuery.ts` | `@/composables/admin/useLibraryQuery.ts` | TanStack Query for single library |
| `useLibraryStatsQuery.ts` | `@/composables/admin/useLibraryStatsQuery.ts` | TanStack Query for library stats |
| `useLibraryMutations.ts` | `@/composables/admin/useLibraryMutations.ts` | All library mutations (create, update, delete, scan, repair) |
| `useLibraryFolderMutations.ts` | `@/composables/admin/useLibraryFolderMutations.ts` | Import path mutations |
| `useLibraryExclusionMutations.ts` | `@/composables/admin/useLibraryExclusionMutations.ts` | Exclusion pattern mutations |

### 4.2 API Service Functions to Add

Add to `@/services/api.ts`:

```ts
export interface LibraryDto {
  id: string;
  name: string;
  root_path: string;
  import_paths: string[];
  exclusion_patterns: string[];
  asset_count: number;
  created_at: string;
  updated_at: string;
}

export interface LibraryStats {
  photos: number;
  videos: number;
  total: number;
  usage: number; // bytes
  scanned_files: number;
  scan_progress: number | null; // 0-100 or null if idle
  status: 'idle' | 'scanning' | 'completed' | 'error';
}

// API functions:
export const fetchLibraries = async (): Promise<LibraryDto[]>;
export const fetchLibrary = async (id: string): Promise<LibraryDto>;
export const fetchLibraryStats = async (id: string): Promise<LibraryStats>;
export const createLibrary = async (dto: { root_path: string; name?: string }): Promise<LibraryDto>;
export const updateLibrary = async (id: string, dto: { name?: string; import_paths?: string[]; exclusion_patterns?: string[] }): Promise<LibraryDto>;
export const deleteLibrary = async (id: string): Promise<void>;
export const scanLibrary = async (id: string): Promise<void>;
export const repairLibrary = async (id: string): Promise<void>;
export const rebuildAllIndexes = async (): Promise<void>;
```

### 4.3 TanStack Query Keys

Add to `@/query/keys.ts`:

```ts
// Library management query keys
libraries: () => ['libraries'] as const,
library: (id: string) => ['libraries', id] as const,
libraryStats: (id: string) => ['libraries', id, 'stats'] as const,
```

### 4.4 Route Design

Add to `@/router/index.ts`:

```ts
const LibraryListPage = () => import('@/components/admin/LibraryListPage.vue');
const LibraryDetailPage = () => import('@/components/admin/LibraryDetailPage.vue');

routes: [
  // ... existing routes
  {
    path: '/admin/libraries',
    name: 'libraries',
    component: LibraryListPage,
  },
  {
    path: '/admin/libraries/:id',
    name: 'library-detail',
    component: LibraryDetailPage,
    props: true,
  },
]
```

The `/metadata` route already exists and redirects mobile/tablet users. Add the same redirect guard for `/admin/libraries/*` routes.

### 4.5 Data Flow

#### Reading:

```
LibraryListPage.vue
  └─ useLibrariesQuery() → queryClient → fetchLibraries()
       └─ For each library: useLibraryStatsQuery(id) → fetchLibraryStats(id)
            └─ Uses computed enabled to avoid fetching before parent resolves

LibraryDetailPage.vue
  └─ useLibraryQuery(id) → queryClient → fetchLibrary(id)
  └─ useLibraryStatsQuery(id) → queryClient → fetchLibraryStats(id)
```

#### Mutations:

```
Create Dialog → createLibrary(dto) → queryClient.invalidateQueries(['libraries'])
Edit Dialog → updateLibrary(id, dto) → queryClient.invalidateQueries(['libraries', id])
Delete Dialog → deleteLibrary(id) → queryClient.invalidateQueries(['libraries'])
Scan Button → scanLibrary(id) → queryClient.invalidateQueries(['libraries', id, 'stats'])
  (also starts polling stats until status !== 'scanning')
Folder Add/Edit → updateLibrary with import_paths → invalidate(['libraries', id])
Pattern Add/Edit → updateLibrary with exclusion_patterns → invalidate(['libraries', id])
Rebuild All → rebuildAllIndexes() → invalidate(['libraries'])
```

---

## 5. Phase Breakdown

### Phase 1: API Service + Query Infrastructure (Effort: 2-3 hours)

1. Add `LibraryDto` and `LibraryStats` types to `@/types/index.ts`
2. Add `fetchLibraries`, `fetchLibrary`, `fetchLibraryStats`, `createLibrary`, `updateLibrary`, `deleteLibrary`, `scanLibrary`, `repairLibrary`, `rebuildAllIndexes` to `@/services/api.ts`
3. Add `libraries`, `library(id)`, `libraryStats(id)` to `@/query/keys.ts`
4. Create `useLibrariesQuery`, `useLibraryQuery`, `useLibraryStatsQuery` composables
5. Create `useLibraryMutations` composable

**Deliverable:** Working data layer, testable via Vue DevTools or console.

### Phase 2: Library List Page (Effort: 3-4 hours)

1. Create `LibraryListPage.vue` with:
   - Page header with "Libraries" title + "New Library" + "Scan All" buttons
   - `<Table>` with columns: Name, Root Path, Photos, Videos, Size, Status, Actions
   - Get started state (empty placeholder) with "Add your first library" CTA
   - Skeleton loading states for stats
   - Inline status badge for scan state (idle/scanning/completed/error)
   - Per-row dropdown menu (Detail, Scan, Edit, Delete)
2. Register `/admin/libraries` route in Vue Router
3. Add route guard for mobile/tablet redirect (matching existing `/metadata` pattern)

**Deliverable:** Fully functional library list page with loading, empty, and error states.

### Phase 3: Library Detail Page (Effort: 4-5 hours)

1. Create `LibraryDetailPage.vue` with:
   - Back navigation + breadcrumb
   - Library name header + action buttons (Scan, Repair, Edit, Delete)
   - Stats row: 3 stat cards (Photos, Videos, Disk Usage) with icon + value
   - Import Paths card: list of paths with edit/delete per row, "Add Folder" button
   - Exclusion Patterns card: list of patterns with edit/delete per row, "Add Pattern" button
   - Scan progress bar (polling) when status is "scanning"
2. Create `LibraryStatCard.vue` (reusable)
3. Create `LibraryImportPathsCard.vue`
4. Create `LibraryExclusionPatternsCard.vue`
5. Register `/admin/libraries/:id` route

**Deliverable:** Fully functional library detail page with polled scan progress.

### Phase 4: Dialogs & Modals (Effort: 3-4 hours)

1. Create `LibraryCreateDialog.vue` using shadcn-vue `<Dialog>`:
   - Root path input (required, validated as absolute path)
   - Name input (optional, defaults to folder basename)
   - Create button + Cancel button
   - Error handling for path overlap / invalid path
2. Create `LibraryEditDialog.vue`:
   - Name input pre-filled
3. Create `LibraryFolderAddDialog.vue`:
   - Path input with duplicate validation
4. Create `LibraryFolderEditDialog.vue`:
   - Path input, pre-filled with old value
5. Create `LibraryExclusionPatternAddDialog.vue`:
   - Pattern input (glob syntax), pre-populated with `**/.stfolder/**` as hint
6. Create `LibraryExclusionPatternEditDialog.vue`:
   - Pattern input, pre-filled
7. Create `LibraryDeleteConfirmDialog.vue`:
   - Warning text with asset count
   - Two-stage confirmation if asset_count > 0

**Deliverable:** All dialog workflows functional with proper error handling.

### Phase 5: Polish & Edge Cases (Effort: 2-3 hours)

1. Add loading states to all buttons (disabled + spinner during mutation)
2. Add toast notifications for all CRUD operations using existing `useToast`
3. Handle error states: API errors shown inline or in toast
4. Add dark mode verification on all new components
5. Keyboard shortcuts: Escape to close dialogs, Enter to submit
6. Form validation: path must be absolute (`/`-starting), no empty strings, no duplicates
7. Test scan progress polling: auto-stop polling when status changes from "scanning" to "completed" or "error"

**Deliverable:** Production-ready library management UI.

Total estimated effort: **14-19 hours**

---

## 6. Component Tree

```
App.vue
└── DesktopLayout.vue (when !isMobile && !isTablet)
    └── RouterView
        ├── LibraryListPage.vue                    ← /admin/libraries
        │   ├── Button ("New Library")
        │   ├── Button ("Scan All")
        │   ├── Table
        │   │   ├── TableHeader
        │   │   │   └── TableRow
        │   │   │       ├── TableHead "Name"
        │   │   │       ├── TableHead "Root Path"
        │   │   │       ├── TableHead "Photos"
        │   │   │       ├── TableHead "Videos"
        │   │   │       ├── TableHead "Size"
        │   │   │       ├── TableHead "Status"
        │   │   │       └── TableHead ""
        │   │   └── TableBody
        │   │       └── TableRow (per library)
        │   │           ├── TableCell → router-link (library name)
        │   │           ├── TableCell → root_path (monospace)
        │   │           ├── TableCell → Skeleton or stats.photos
        │   │           ├── TableCell → Skeleton or stats.videos
        │   │           ├── TableCell → Skeleton or formatted size
        │   │           ├── TableCell → Badge (status)
        │   │           └── TableCell → DropdownMenu (actions)
        │   └── EmptyState (when libraries.length === 0)
        │
        └── LibraryDetailPage.vue                  ← /admin/libraries/:id
            ├── Breadcrumb (Libraries > Library Name)
            ├── div (action buttons)
            │   ├── Button "Scan"
            │   ├── Button "Repair"
            │   ├── Button "Edit"
            │   └── Button "Delete" (variant="destructive")
            ├── div (stat cards, flex row)
            │   ├── LibraryStatCard (Photos)
            │   ├── LibraryStatCard (Videos)
            │   └── LibraryStatCard (Usage)
            ├── Progress (scan progress bar, conditional)
            ├── LibraryImportPathsCard
            │   ├── CardHeader (icon + title + Add button)
            │   └── CardBody
            │       └── table
            │           └── tr (per import path)
            │               ├── td → Code (path)
            │               └── td → Button (edit) + Button (delete)
            └── LibraryExclusionPatternsCard
                ├── CardHeader (icon + title + Add button)
                └── CardBody
                    └── table
                        └── tr (per pattern)
                            ├── td → Code (pattern)
                            └── td → Button (edit) + Button (delete)

Dialogs (opened on demand, not nested in router):
├── LibraryCreateDialog
│   └── Dialog
│       ├── DialogHeader + DialogTitle "Create Library"
│       ├── Input (root path, required)
│       ├── Input (name, optional)
│       └── Button "Create" + Button "Cancel"
├── LibraryEditDialog
│   └── Dialog
│       ├── DialogHeader + DialogTitle "Edit Library"
│       ├── Input (name, pre-filled)
│       └── Button "Save" + Button "Cancel"
├── LibraryFolderAddDialog
│   └── Dialog
│       ├── DialogHeader + DialogTitle "Add Import Path"
│       ├── Input (path)
│       └── Button "Add" + Button "Cancel"
├── LibraryFolderEditDialog
│   └── Dialog
│       ├── DialogHeader + DialogTitle "Edit Import Path"
│       ├── Input (path, pre-filled)
│       └── Button "Save" + Button "Cancel"
├── LibraryExclusionPatternAddDialog
│   └── Dialog
│       ├── DialogHeader + DialogTitle "Add Exclusion Pattern"
│       ├── Input (pattern)
│       └── Button "Add" + Button "Cancel"
├── LibraryExclusionPatternEditDialog
│   └── Dialog
│       ├── DialogHeader + DialogTitle "Edit Exclusion Pattern"
│       ├── Input (pattern, pre-filled)
│       └── Button "Save" + Button "Cancel"
└── LibraryDeleteConfirmDialog
    └── Dialog
        ├── DialogHeader + DialogTitle "Delete Library"
        ├── DialogDescription (warning + asset count)
        └── Button "Delete" (destructive) + Button "Cancel"
```

---

## 7. Route Design

| Path | Name | Component | Purpose |
|---|---|---|---|
| `/admin/libraries` | `libraries` | `LibraryListPage.vue` | View all registered libraries |
| `/admin/libraries/:id` | `library-detail` | `LibraryDetailPage.vue` | View/edit a single library |

**Route guard:** Both routes redirect to `/` when `isMobile || isTablet` (matching the existing `/metadata` guard in `App.vue`).

**No sub-routes for dialogs** — dialogs are overlay components managed by local state, not by the router.

---

## 8. Data Flow

### TanStack Query Keys

```ts
// In @/query/keys.ts — additions:
export const queryKeys = {
  // ... existing keys

  // Library management
  libraries: () => ['libraries'] as const,
  library: (id: string) => ['libraries', id] as const,
  libraryStats: (id: string) => ['libraries', id, 'stats'] as const,
};
```

### Mutation Patterns

```ts
// useLibraryMutations.ts — example structure
export function useLibraryMutations() {
  const queryClient = useQueryClient();

  const createLibrary = useMutation({
    mutationFn: (dto: { root_path: string; name?: string }) => api.createLibrary(dto),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.libraries() });
      toast.success('Library created');
    },
    onError: (error: GalleryAPIError) => {
      toast.error(error.userMessage);
    },
  });

  const updateLibrary = useMutation({
    mutationFn: ({ id, ...dto }: { id: string } & Partial<UpdateLibraryDto>) =>
      api.updateLibrary(id, dto),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.library(variables.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.libraries() });
      toast.success('Library updated');
    },
    onError: (error: GalleryAPIError) => {
      toast.error(error.userMessage);
    },
  });

  const deleteLibrary = useMutation({
    mutationFn: (id: string) => api.deleteLibrary(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.libraries() });
      toast.success('Library deleted');
    },
  });

  const scanLibrary = useMutation({
    mutationFn: (id: string) => api.scanLibrary(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.libraryStats(id) });
      toast.info('Library scan started');
    },
  });

  return { createLibrary, updateLibrary, deleteLibrary, scanLibrary };
}
```

### Scan Progress Polling Pattern

Immich has no real-time scan progress in the web UI — it's a fire-and-forget API call. For gallery, we want to show progress:

```ts
// In useLibraryStatsQuery.ts — for a single library:
export function useLibraryStatsQuery(id: string) {
  return useQuery({
    queryKey: queryKeys.libraryStats(id),
    queryFn: () => api.fetchLibraryStats(id),
    // Poll every 3s while scanning, stop when complete/error
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'scanning' || status === 'idle' || !status) return 3000;
      return false; // completed or error — stop polling
    },
    staleTime: 0, // Always refetch while polling
    enabled: !!id,
  });
}
```

### State Transitions

```
User clicks "Scan" → scanLibrary(id) mutation
  → API returns 202 Accepted
  → Invalidate libraryStats query → refetchInterval = 3000ms
  → Stats show progress: "Scanning 45%"
  → When stats.status === "completed" → refetchInterval stops
  → Invalidate libraries list → library asset counts update
```

### Error Handling Flow

```
API Error → GalleryAPIError
  → toast.error(error.userMessage)
  → Dialog stays open (user can fix and retry)
  → Fields remain filled (no data loss on error)
```

---

## Key Implementation Notes

1. **Use Existing shadcn-vue Components:** The table, dialog, button, input, select, skeleton, badge, dropdown-menu, and popover components are already set up at `@/components/ui/`. Use `Table`, `TableBody`, `TableCell`, `TableHead`, `TableHeader`, `TableRow` from `@/components/ui/table/` — exactly as `LibraryInspector.vue` already does.

2. **Path Normalization:** Use existing `normalizeQueryPath()` from `@/query/keys.ts` for all path inputs to ensure consistent formatting.

3. **Toast Notification Pattern:** Gallery already has `useToast()` composable. Follow the pattern from existing components — call `toast.success()`, `toast.error()`, `toast.info()`.

4. **Dark Mode:** All shadcn-vue components auto-adapt to `[data-theme="dark"]`. No extra work needed for new components if using shadcn-vue classes.

5. **Mobile/Tablet Guard:** Already present in `App.vue` for `/metadata` route — extend the same `watch` to redirect `/admin/libraries/*` paths when mobile/tablet.

6. **Pending Async States:** Use Vue Query's `isPending`, `isError`, `error` properties — rendered inline with `<Skeleton>` and conditional error messages.
