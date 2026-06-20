# Codex Library Management Implementation Plan

Status: plan only, no implementation in this step.

Goal: implement a responsive Library Import / Library Management frontend for registered libraries across desktop, tablet, and mobile. Immich is used only as a UI pattern reference. Do not copy Immich source code, Svelte/SvelteKit architecture, or Immich API shapes.

## 1. Current Findings

### 1.1 Gallery backend contract to target

The implementation must target the gallery backend that exists in this repo, not Immich.

Current registered library endpoints:

| Method | Endpoint | Purpose | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/libraries` | List registered libraries | Returns DB rows from `libraries`. |
| `POST` | `/api/libraries` | Add one library root | Body: `{ root_path: string, name?: string }`. Validates path safety, existence, directory, overlap. |
| `GET` | `/api/libraries/{library_id}` | Get one library | `library_id` is numeric. |
| `GET` | `/api/libraries/{library_id}/progress` | Get scan/import progress | Returns indexed/estimated counts and lifecycle state. |
| `POST` | `/api/libraries/{library_id}/scan` | Trigger background discovery/import | Returns `202` with `{ library_id, state: "discovering" }`. |
| `POST` | `/api/libraries/{library_id}/repair` | Reconcile catalog with filesystem | Returns `{ library_id, added, removed, modified }`. |
| `DELETE` | `/api/libraries/{library_id}?confirm=true` | Unregister library | Deletes catalog rows only. Source files are not deleted. |

Known response shape from backend code:

```ts
type LibraryState = "discovering" | "indexing" | "ready" | "error" | "offline";

interface RegisteredLibrary {
  id: number;
  root_path: string;
  name: string;
  state: LibraryState | string;
  watch_enabled: 0 | 1;
  warm_enabled: 0 | 1;
  created_at: number;
  updated_at: number;
  last_scan_at: number | null;
  last_error: string | null;
}

interface LibraryProgress {
  indexed_assets: number;
  estimated_assets: number;
  discovery_complete: boolean;
  library_state: LibraryState | string;
}
```

Important contract corrections versus the older adaptation plan:

- There is no `/api/libraries/{id}/stats`; use `/api/libraries/{id}/progress`.
- There is no frontend-supported `PUT/PATCH /api/libraries/{id}` yet, so v1 must not promise rename/edit unless a backend endpoint is added first.
- There are no `import_paths` or `exclusion_patterns` fields/endpoints in the current gallery backend. V1 should add one explicit library root per library.
- Gallery is image-first. Do not add Immich-style video stats.
- Delete requires `confirm=true`; the UI confirmation must map to that query param.

### 1.2 Main gallery contract to preserve

Current viewer APIs already support explicit registered libraries:

- `/api/scan` with no `path` falls back to the first registered library root.
- `/api/folders` with no `path` falls back to the first registered library root.
- `/api/search` for `scope=current` with no `path` falls back to the first registered library root.
- `GALLERY_DB_REQUIRED=true` rejects unregistered arbitrary paths.

The frontend currently still stores and loads a raw root path through:

- `frontend/src/stores/gallery.ts`
- `frontend/src/components/RootPathSidebarHeader.vue`
- `frontend/src/components/RootPathSheet.vue`
- localStorage key `gallery-root-path`

The new UX must replace arbitrary root entry with an explicit active library selection on desktop, tablet, and mobile. Internally, the existing scan/folder/search APIs can continue receiving absolute filesystem paths, but those paths should come from the active registered library model rather than a second persisted root-path model.

Recommended state model:

- `activeLibraryId`: the only persisted gallery selection on every breakpoint, stored under `gallery-active-library-id`.
- `activeLibraryRootPath`: derived from the `GET /api/libraries` result by matching `activeLibraryId`; not independently persisted and not writable as primary state.
- `currentBrowsePath`: the absolute folder path currently being browsed inside the active library. It starts as `activeLibraryRootPath` and changes through folder navigation, breadcrumb navigation, search album selection, history, and back/forward.
- legacy `gallery-root-path`: read once during hydration as a migration hint, then removed from localStorage after migration succeeds or after it is determined unusable. New code must never write this key.

This avoids an unclean dual-state model. `activeLibraryId` owns selection identity; the library query owns the root path value; `currentBrowsePath` owns the viewer's path-scoped browsing context. No long-term frontend state should persist both `gallery-active-library-id` and `gallery-root-path` as competing sources of truth.

Do not keep `galleryStore.rootPath` as primary writable state in the registered-library flow. Rename or replace it in the store with explicit library/browse names. A short-lived compatibility getter named `rootPath` is acceptable only inside the migration implementation if it is read-only, derived from `activeLibraryRootPath`, and scheduled for removal in the same feature branch; it must not write to localStorage or accept arbitrary paths.

### 1.3 Immich patterns to adapt, not copy

Patterns worth adapting:

- Separate admin route area for library management.
- List page with table, row status, row actions, loading/empty/error states.
- Detail page with status summary, progress, registered folders/actions, and destructive confirmation.
- Add Library dialog with validation and server error display.
- Action menu per row: detail, scan, repair, delete.
- Status badges for ready/scanning/error/offline states.
- Confirmation dialogs for destructive actions.

Patterns to skip:

- Svelte/SvelteKit route groups and page-modal pattern.
- Owner assignment and multi-user library ownership.
- Video/mobile-backup features.
- Command palette/global modal manager.
- Immich API DTOs.
- Import paths/exclusion pattern UI until gallery backend supports them.

### 1.4 Frontend library and style reuse policy

Prefer existing, maintained frontend libraries over custom implementation for generic UI and data behavior. Custom code should mostly be app-specific glue: backend contract mapping, state ownership, library selection rules, copy, layout composition, and small presentation utilities.

Use the current gallery design system and shadcn-vue-style primitives as the visual baseline:

- Do not copy Immich CSS, exact spacing, color choices, component internals, or page structure.
- Adapt Immich only at the workflow/pattern level: admin list, detail page, action menu, status badge, add dialog, and destructive confirmation.
- Use existing `frontend/src/components/ui/*` primitives before creating new local primitives.
- If a needed generic primitive exists in shadcn-vue/Reka UI and is not already present locally, add/adapt the shadcn-vue primitive in the local `components/ui` style instead of hand-rolling accessibility, keyboard behavior, focus management, or overlay behavior.
- Keep styling aligned with the existing shadcn token bridge, `bg-card`, `border`, `rounded-md`, muted/destructive/default tokens, and existing gallery spacing conventions.
- Use `lucide-vue-next`/existing icons for actions; icon-only actions need accessible labels/tooltips.

Use the installed TanStack and viewer libraries where they fit:

- TanStack Query: server state, progress polling, mutations, cache invalidation, and route/page data loading.
- TanStack Table: admin tables when column definitions, sorting, row models, or action/state composition would otherwise be hand-written.
- TanStack Form: Add Library and confirmation/form-style interactions when validation/submission state would otherwise become bespoke component state.
- TanStack Virtual: large or potentially large scrollable lists/tables; do not hand-roll virtualization.
- TanStack DB: only for local reactive collection use cases with complete scoped datasets and stable row keys. Do not move one-off library detail/progress calls into DB.
- PhotoSwipe: keep image/lightbox behavior on PhotoSwipe; do not introduce a custom lightbox implementation for this feature.
- Existing bottom-sheet/dialog/select/dropdown implementations should be reused for responsive dialogs and compact library selection.

Do not add a dependency just because it exists. Add or scaffold one only when it replaces meaningful generic behavior, improves accessibility/state correctness, or matches an existing local pattern. For this feature, the repo already has the expected stack (`shadcn-vue`, `reka-ui`, PhotoSwipe, and TanStack Query/Table/Form/Virtual/DB), so the default should be reuse before new code.

### 1.5 Current frontend dependency audit

Current `rootPath` dependencies that need rename/adaptation:

| File | Current dependency | Required adaptation |
| --- | --- | --- |
| `frontend/src/stores/gallery.ts` | `STORAGE_KEY = "gallery-root-path"`, `getStoredRoot()`, writable `rootPath`, `setRootPath()`, `resetRootPath()` | Replace with `ACTIVE_LIBRARY_STORAGE_KEY`, `activeLibraryId`, derived `activeLibraryRootPath`, `currentBrowsePath`, `hydrateActiveLibrary()`, `setActiveLibrary()`, and `clearActiveLibrary()`. Keep legacy root-path read/remove helper only for migration. |
| `frontend/src/App.vue` | startup auto-load calls `galleryStore.setRootPath(galleryStore.rootPath)` | Replace with active-library hydration on every breakpoint before the first gallery scan/search flow. Remove old root-path startup writes. |
| `frontend/src/components/RootPathSidebarHeader.vue` | input initializes from `galleryStore.rootPath`, calls `setRootPath()`/`resetRootPath()` | Rename/replace with `LibrarySidebarHeader.vue`, a registered-library selector that calls `setActiveLibrary()`. Do not keep arbitrary root-path input semantics. |
| `frontend/src/components/RootPathSheet.vue` | mobile sheet calls `galleryStore.setRootPath()` | Rename/replace with `LibrarySelectorSheet.vue` or `LibrarySheet.vue`, using registered library selection and Add/Manage Library CTAs. Remove the arbitrary root-path textarea as primary UX. |
| `frontend/src/components/GalleryGrid.vue` | uses `galleryStore.currentPath` for scan/search browsing, but also checks `galleryStore.rootPath` in `pathReady`, `hasNoPath`, and `hasNotLoaded` | Continue passing the active browse path to `/api/scan` and `/api/search`; rename store access to `currentBrowsePath`. Replace `rootPath` gating with `activeLibraryId`/`activeLibraryRootPath` readiness. Update empty/error copy for all breakpoints. |
| `frontend/src/components/GallerySidebarContent.vue` | mounts `RootPathSidebarHeader.vue`; empty copy says to enter a root path | Mount `LibrarySidebarHeader.vue` where the sidebar is present. Update empty copy to registered-library language. Mobile/tablet entry points should use the library selector sheet instead of legacy root-path copy. |
| `frontend/src/components/search/AdvancedSearchDrawer.vue` | `facetsQueryPath = galleryStore.rootPath || ""` | Use `activeLibraryRootPath` for library-wide facets, or `currentBrowsePath` if facets should scope to the current folder. Recommended v1: `activeLibraryRootPath`, because the drawer currently behaves like library-level filter assistance. |
| `frontend/src/stores/__tests__/gallery.test.ts` | tests persisted root path, `setRootPath()`, `resetRootPath()` | Replace/add tests for active library hydration, one-shot legacy migration/removal, active library deletion, and browse path history. Remove writable root-path primary-state expectations. |
| `frontend/tests/e2e/*.spec.ts` | many tests seed `localStorage.gallery-root-path` | Add new library-management coverage using `/api/libraries` and `gallery-active-library-id`. Tests that rely on `gallery-root-path` should cover migration only; viewer tests across all breakpoints should use registered libraries. |

Current path-based render/query code that should stay library-id agnostic:

| File | Why it can remain path-based |
| --- | --- |
| `frontend/src/composables/useInfiniteScanQuery.ts` | Accepts a path ref and calls `/api/scan?path=...`; pass `currentBrowsePath`. |
| `frontend/src/composables/useUnifiedSearchQuery.ts` | Accepts a path ref for `scope=current`; pass `currentBrowsePath` through existing `GalleryGrid` flow. |
| `frontend/src/composables/useFolderChildrenQuery.ts` and `FolderTreeItem.vue` | Expands folders by absolute folder path. |
| `frontend/src/query/scan.ts` and `frontend/src/query/keys.ts` | Query cache keys are path-scoped and should remain so for viewer APIs. |
| `frontend/src/services/api.ts` path-based viewer functions | `scanDirectory`, `listFolderChildren`, `unifiedSearch`, `fetchFacets`, `fetchIndexStatus`, `fetchMetadata`, image/thumbnail/preview URL builders all operate on absolute paths. Add library admin API functions separately. |
| `frontend/src/components/PhotoCard.vue`, `frontend/src/stores/lightbox.ts`, `frontend/src/composables/usePhotoSwipe.ts`, `frontend/src/utils/lightbox.ts`, `frontend/src/components/Lightbox.vue` | Image display, metadata, previews, originals, and lightbox navigation use `FileNode.path`/`image.path`; no library id is needed if backend URLs still accept `path`. |
| `frontend/src/components/LibraryInspector.vue` | Uses current path for `scope=current`; rename store access to `currentBrowsePath` only if the store field changes. |

Answer to the render-layer compatibility question: yes, `GalleryGrid`, lightbox, and search can remain path-based if `/api/scan?path=...`, `/api/search?scope=current&path=...`, `/api/folders?path=...`, image URLs, thumbnail URLs, preview URLs, and metadata calls continue to accept absolute paths from `currentBrowsePath`/`image.path`. They should not receive or know about library IDs in v1.

## Entry Point Design

Chosen approach: Option B, with a strict split between library selection and library management.

The app has two separate entry points:

- Admin/management entry point: a responsive `Libraries` entry in `AppHeader.vue`, placed near the existing `Metadata` affordance on desktop and exposed through the compact header/navigation pattern on tablet/mobile.
- Gallery selection entry point: the existing sidebar header slot above the folder tree, currently implemented by `RootPathSidebarHeader.vue`, renamed/replaced by `LibrarySidebarHeader.vue`; compact layouts use a library selector sheet, currently rooted in `RootPathSheet.vue`, renamed/replaced by `LibrarySelectorSheet.vue` or `LibrarySheet.vue`.

The main gallery needs an in-context way to choose the registered library it is browsing. `GallerySidebarContent.vue` already mounts `RootPathSidebarHeader.vue` above the folder tree, so that slot should become active library selection by renaming/replacing it with `LibrarySidebarHeader.vue`. This keeps the selected library, derived root path, and folder tree context together. Compact layouts should offer the same registered-library model through `LibrarySelectorSheet.vue` or `LibrarySheet.vue`, not a separate arbitrary root-path flow.

Library management is a separate workflow: add libraries, scan, repair, inspect, and unregister libraries. Expose that workflow through the header/navigation system by adding `Libraries` near `Metadata` in `AppHeader.vue`. The entry routes to `/admin/libraries`, is active for `/admin/libraries` routes, and remains available on desktop, tablet, and mobile.

`RootPathSheet.vue` should not remain as a legacy arbitrary-path surface. Rename/replace it with `LibrarySelectorSheet.vue` or `LibrarySheet.vue`, remove the root-path textarea as primary UX, and use it for registered library selection plus Add/Manage Library actions on compact breakpoints.

Selection persistence migrates from the legacy path key to the new active library id:

1. Add `gallery-active-library-id` as the new persisted selection key.
2. Fetch registered libraries during active-library hydration.
3. If `gallery-active-library-id` exists and matches a registered library, use it, initialize `currentBrowsePath` to that library root, remove any leftover `gallery-root-path`, and stop.
4. Else, read legacy `gallery-root-path` once.
5. If the legacy path exactly matches or is inside a registered library root, select the most specific matching library, persist its id, initialize `currentBrowsePath` to the legacy path only if that path is inside the selected library, remove `gallery-root-path`, and stop.
6. If there is no legacy match, remove `gallery-root-path` so future starts do not retry stale migration.
7. If exactly one registered library exists, select it and initialize `currentBrowsePath` to its root.
8. Else, leave no active library selected and show a no-library state with `Add Library` and/or `Manage Libraries` actions.

Do not keep a second persisted root path. Existing scan, folder, and search queries should receive `currentBrowsePath` as their `path` parameter. If a temporary `rootPath` getter exists during implementation, it must be derived from `activeLibraryRootPath`, read-only from the perspective of the registered-library flow, and not persisted.

Gating logic:

- Admin pages and the header/navigation `Libraries` entry are available on desktop, tablet, and mobile.
- The active library selector is available on every breakpoint.
- Desktop/tablet sidebar surfaces should use `LibrarySidebarHeader.vue` where the sidebar is visible.
- Mobile and any compact tablet surfaces should use `LibrarySelectorSheet.vue` or `LibrarySheet.vue`.
- No breakpoint should keep arbitrary root-path entry as the primary gallery UX.

## 2. Product Scope

### 2.1 V1 scope

V1 will provide:

1. Responsive admin pages:
   - `/admin/libraries`
   - `/admin/libraries/:id`
2. Registered library list:
   - name
   - root path
   - status
   - progress counts
   - last scan / last update
   - last error when present
   - row actions
3. Add Library dialog/sheet:
   - absolute folder path
   - optional display name
   - duplicate/overlap client warning where possible
   - server error handling
   - optional "Add and scan" workflow
4. Library detail page:
   - status badge
   - progress card
   - registered root path card
   - scan/rescan action
   - repair action
   - unregister action
   - last error display
5. Main gallery active library selector:
   - no arbitrary root path input as primary UX on desktop, tablet, or mobile
   - user selects one registered library on every breakpoint
   - desktop/tablet sidebar selector through `LibrarySidebarHeader.vue`
   - compact selector through `LibrarySelectorSheet.vue` or `LibrarySheet.vue`
   - selected library root derives `activeLibraryRootPath`
   - selected library root initializes `currentBrowsePath`
   - persisted active library id
   - one-shot fallback/migration from legacy `gallery-root-path`
6. Loading, empty, error, and pending mutation states.

### 2.2 Explicit non-goals for V1

- No Immich code copying.
- No Svelte/SvelteKit concepts.
- No owner picker.
- No video stats.
- No import path list under a library.
- No exclusion pattern management.
- No rename/edit library UI unless a backend update endpoint is added before implementation.
- No backend schema migration as part of this frontend task.
- No command palette.
- No mobile/tablet arbitrary root-path legacy UX.

## 3. UX Plan

### 3.1 Admin navigation

Add a responsive "Libraries" entry near the existing "Metadata" header button in `AppHeader.vue`.

Behavior:

- Visible or reachable on desktop, tablet, and mobile through the existing header/navigation pattern.
- Desktop can use a text button beside `Metadata`; compact breakpoints can use the existing icon/menu/sheet navigation affordance if space is constrained.
- Active when `route.path.startsWith("/admin/libraries")`.
- Prefetch route component on pointer enter/focus, matching the metadata prefetch style if useful.
- Keep main gallery viewer-first; do not make library management the default first screen.

### 3.2 Responsive route handling

Extend the existing route/device handling in `App.vue`:

- Admin routes should set `showIntro=false`.
- Render the responsive management surface on tablet and mobile without redirecting away from `/admin/libraries`.
- Keep `/metadata` behavior intact.

Suggested helper:

```ts
const isAdminLibraryRoute = computed(() => route.path.startsWith("/admin/libraries"));
```

### 3.3 Library list page

Path: `/admin/libraries`

Primary layout:

- Header:
  - title: `Libraries`
  - summary: number of registered libraries
  - primary action: `Add Library`
- Desktop content:
  - table with the columns listed below
- Tablet/mobile content:
  - card list with the same data and actions
  - compact cards should prioritize name, root path, status, asset count, last scan, and actions
  - avoid horizontal scrolling for primary fields
- Desktop table columns:
  - Library
  - Root path
  - Status
  - Assets
  - Last scan
  - Updated
  - Actions

Row behavior:

- Library name links to detail page.
- Root path is monospace and truncated with full path in `title`.
- Status uses `LibraryStatusBadge`.
- Assets cell uses progress query:
  - loading: skeleton
  - success: `indexed_assets / estimated_assets`
  - unknown zero estimate: `0 indexed`
- Last error appears as a small destructive/outline indicator when present.
- Actions dropdown:
  - View details
  - Use in gallery
  - Scan / Rescan
  - Repair
  - Unregister

Empty state:

- Title: `No libraries registered`
- Description: explain that libraries must be registered before browsing.
- CTA: `Add Library`

Error state:

- Inline error panel with retry.
- Keep existing shell stable; do not navigate away.

Loading state:

- Desktop: table skeleton rows using existing `Skeleton`.
- Tablet/mobile: card skeleton rows using existing `Skeleton`.

### 3.4 Library detail page

Path: `/admin/libraries/:id`

Primary layout:

- Back link to `/admin/libraries`
- Breadcrumb: `Libraries / {name}`
- Header:
  - library name
  - status badge
  - actions: `Use in Gallery`, `Scan`, `Repair`, `Unregister`

Cards/sections:

1. Status and Progress
   - state label
   - `indexed_assets`
   - `estimated_assets`
   - progress bar when estimate is greater than zero
   - indeterminate state for discovering/indexing with zero estimate
2. Registered Folder
   - root path
   - copy path action if using existing clipboard composable is low-risk
   - open folder action only if existing `openFolder` path remains appropriate
3. Catalog Lifecycle
   - created, updated, last scan timestamps
   - watch/warm enabled display if useful
4. Last Error
   - render only when `last_error` exists or state is `error/offline`

Actions:

- `Use in Gallery`: set active library, navigate `/`.
- `Scan`: call scan mutation, invalidate list/detail/progress, start polling.
- `Repair`: call repair mutation, show counts in toast, invalidate relevant queries.
- `Unregister`: open confirmation dialog.

### 3.5 Add library dialog/sheet

Component: `frontend/src/components/admin/dialogs/LibraryCreateDialog.vue`

Presentation:

- Desktop: dialog.
- Tablet/mobile: bottom sheet or full-height sheet if that matches existing compact modal patterns.
- Same validation, API calls, and success behavior on all breakpoints.

Fields:

- `root_path` required
- `name` optional

Client validation:

- trim whitespace and surrounding quotes
- path must be absolute:
  - Unix: starts with `/`
  - Windows-style support can accept `^[A-Za-z]:[\\/]` if desired, but backend runs path resolution anyway
- exact duplicate root path warning based on loaded libraries
- overlap warning based on normalized path prefix checks

Submit modes:

- `Add Library`: `POST /api/libraries`
- `Add and Scan`: create, then `POST /api/libraries/{id}/scan`

Success behavior:

- invalidate `libraries`
- close dialog
- toast success
- set newly created library as active library
- either navigate to detail page or keep list page and highlight row

Recommended v1 behavior: navigate to `/admin/libraries/{id}` after creation, because scan/progress/error is more visible there.

Failure behavior:

- keep dialog open
- preserve fields
- show server error inline and toast via `GalleryAPIError`

### 3.6 Unregister confirmation

Component: `frontend/src/components/admin/dialogs/LibraryDeleteConfirmDialog.vue`

Copy requirements:

- Say "Unregister" instead of "Delete" where possible.
- Explicitly state source files are not deleted.
- Explicitly state catalog rows, metadata records, and derivatives for that library may be removed by backend behavior.
- If progress has `estimated_assets > 0`, include the count.

Submit:

- `DELETE /api/libraries/{id}?confirm=true`

After success:

- invalidate `libraries`
- remove detail cache for deleted library
- if active library was deleted, select next available library if any; otherwise clear active library state
- navigate back to `/admin/libraries`

### 3.7 Active library selector in main viewer

Implement the gallery selection side of the [Entry Point Design](#entry-point-design): replace arbitrary root path entry with a registered-library selector on desktop, tablet, and mobile.

Primary targets:

- Rename/replace `RootPathSidebarHeader.vue` with `LibrarySidebarHeader.vue`.
- Rename/replace `RootPathSheet.vue` with `LibrarySelectorSheet.vue` or `LibrarySheet.vue`.

Suggested approach:

- Change UI semantics from "root path input" to "active library selector" everywhere.
- Use `LibrarySidebarHeader.vue` for sidebar layouts.
- Use `LibrarySelectorSheet.vue` or `LibrarySheet.vue` for compact layouts.
- Remove textarea/paste/clear/load semantics tied to arbitrary root paths.

UI states:

- Loading libraries: skeleton or compact loading row.
- No libraries:
  - show `No libraries registered`.
  - show `Add Library` and/or `Manage Libraries` actions on every breakpoint.
- Libraries available:
  - select/dropdown with library name and status
  - secondary root path display
  - `Manage` link
  - optional scan status indicator

Store behavior:

- Add `activeLibraryId` persisted to localStorage key `gallery-active-library-id`.
- Add `activeLibraryRootPath` as a derived getter/value from the libraries query/list.
- Replace the primary writable browsing path name with `currentBrowsePath`.
- Do not persist `activeLibraryRootPath` or `currentBrowsePath` as independent source-of-truth values.
- Do not keep writable `rootPath` in the registered-library model.
- Add actions:
  - `hydrateActiveLibrary()`
  - `setActiveLibrary(library: RegisteredLibrary)`
  - `clearActiveLibrary()`
  - `selectBrowsePath(path: string)` or rename existing `selectFolder()` to use the clearer browse-path language if churn is manageable
- On startup:
  1. Fetch registered libraries.
  2. If persisted `activeLibraryId` exists and still exists, select it, initialize `currentBrowsePath` to that library root, remove any leftover `gallery-root-path`, and stop.
  3. Else read legacy `gallery-root-path` once.
  4. If the legacy path exactly matches or is inside a registered library, select the most specific matching library, persist the selected library id to `gallery-active-library-id`, initialize `currentBrowsePath` to the legacy folder only when it is inside the selected library, remove `gallery-root-path`, and stop.
  5. If no legacy match exists, remove `gallery-root-path` so future starts do not retry stale migration forever.
  6. If exactly one library exists after no persisted or legacy match, select it and initialize `currentBrowsePath` to its root.
  7. Else leave unselected and show empty state.
- On active library selection:
  - set `activeLibraryId = library.id`
  - let `activeLibraryRootPath` derive from `activeLibraryId` and the libraries query/list
  - set `currentBrowsePath = library.root_path`
  - clear search
  - reset folder expansion/history
  - call existing scan flow for that root

Important: keep folder browsing behavior unchanged for folders inside the active library. Folder-tree selection, breadcrumb navigation, search album selection, back/forward, index status, and library inspector `scope=current` should use `currentBrowsePath`.

## 4. Frontend Architecture

### 4.1 Types

Update: `frontend/src/types/index.ts`

Add:

```ts
export type LibraryState = "discovering" | "indexing" | "ready" | "error" | "offline" | string;

export interface RegisteredLibrary {
  id: number;
  root_path: string;
  name: string;
  state: LibraryState;
  watch_enabled: 0 | 1;
  warm_enabled: 0 | 1;
  created_at: number;
  updated_at: number;
  last_scan_at: number | null;
  last_error: string | null;
}

export interface LibraryProgress {
  indexed_assets: number;
  estimated_assets: number;
  discovery_complete: boolean;
  library_state: LibraryState;
}

export interface LibraryCreateRequest {
  root_path: string;
  name?: string;
}

export interface LibraryScanResponse {
  library_id: number;
  state: LibraryState;
}

export interface LibraryRepairResponse {
  library_id: number;
  added: number;
  removed: number;
  modified: number;
}
```

### 4.2 API service

Update: `frontend/src/services/api.ts`

Add:

```ts
export const fetchLibraries = async (): Promise<RegisteredLibrary[]>;
export const fetchLibrary = async (id: number): Promise<RegisteredLibrary>;
export const fetchLibraryProgress = async (id: number): Promise<LibraryProgress>;
export const createLibrary = async (payload: LibraryCreateRequest): Promise<RegisteredLibrary>;
export const scanLibrary = async (id: number): Promise<LibraryScanResponse>;
export const repairLibrary = async (id: number): Promise<LibraryRepairResponse>;
export const deleteLibrary = async (id: number): Promise<void>;
```

Implementation notes:

- Wrap all calls in the existing `GalleryAPIError.fromAxiosError` pattern.
- `deleteLibrary` must pass `{ params: { confirm: true } }`.
- Add `bad_request` to `ErrorType` handling if needed because backend uses `ErrorType.BAD_REQUEST`.
- Keep existing library error map.

### 4.3 Query keys

Update: `frontend/src/query/keys.ts`

Add:

```ts
librariesRoot: () => ["libraries"] as const,
libraries: () => ["libraries", "list"] as const,
library: (id: number) => ["libraries", "detail", id] as const,
libraryProgress: (id: number) => ["libraries", "progress", id] as const,
```

Use root key for broad invalidation:

```ts
queryClient.invalidateQueries({ queryKey: queryKeys.librariesRoot() });
```

### 4.4 Composables

Create:

- `frontend/src/composables/admin/useLibrariesQuery.ts`
- `frontend/src/composables/admin/useLibraryQuery.ts`
- `frontend/src/composables/admin/useLibraryProgressQuery.ts`
- `frontend/src/composables/admin/useLibraryMutations.ts`

`useLibraryProgressQuery` polling:

- enabled only with a valid id
- poll every 2-3 seconds while:
  - `library_state` is `discovering` or `indexing`
  - or `discovery_complete === false`
- stop polling for `ready`, `error`, `offline`
- refetch on window focus unless document hidden

`useLibraryMutations` responsibilities:

- create
- scan
- repair
- unregister
- consistent toast messages
- query invalidation
- active library cleanup after unregister

### 4.5 Library status utilities

Create: `frontend/src/utils/libraryStatus.ts`

Functions:

- `getLibraryStatusPresentation(library, progress)`
- `isLibraryBusy(state)`
- `getLibraryProgressPercent(progress)`
- `formatLibraryTimestamp(value)`
- `formatAssetCount(value)`

Presentation mapping:

| Backend state | Label | Badge variant | Meaning |
| --- | --- | --- | --- |
| `ready` | Ready | default/outline green-toned class if local class is needed | Imported and usable. |
| `discovering` | Discovering | loading/secondary | Scan has started. |
| `indexing` | Indexing | loading/secondary | Metadata/import work in progress. |
| `offline` | Offline | destructive | Root path unavailable. |
| `error` | Error | destructive | Last scan failed. |
| unknown | Unknown | outline | Forward-compatible fallback. |

Keep status styles aligned with existing `IndexStatusBadge` rather than inventing a new color system.

### 4.6 Gallery store naming and ownership

Update: `frontend/src/stores/gallery.ts`

Proposed store state:

```ts
activeLibraryId: number | null;
currentBrowsePath: string; // current folder path inside the active library
sidebarTree: FolderTreeNode[];
expandedFolderPaths: Record<string, boolean>;
history: string[];
historyIndex: number;
hasEverLoaded: boolean;
```

Proposed derived value/getter:

```ts
activeLibraryRootPath: string; // derived from activeLibraryId + libraries query/list, not writable or persisted
```

Proposed action names:

```ts
hydrateActiveLibrary(libraries: RegisteredLibrary[]): Promise<void> | void;
setActiveLibrary(library: RegisteredLibrary): Promise<boolean>;
clearActiveLibrary(): void;
selectBrowsePath(pathOrNode: FileNode | string): void;
resetBrowseState(): void;
```

Migration helper names:

```ts
const ACTIVE_LIBRARY_STORAGE_KEY = "gallery-active-library-id";
const LEGACY_ROOT_PATH_STORAGE_KEY = "gallery-root-path";
readLegacyRootPathForMigration();
clearLegacyRootPath();
findLibraryForPath(libraries, legacyPath);
```

Rules:

- Persist only `activeLibraryId`.
- Derive `activeLibraryRootPath` from loaded registered libraries.
- Keep `currentBrowsePath` in memory only. It is a navigation state, not a durable library selection.
- `currentBrowsePath` may temporarily initialize from a legacy migrated subfolder path if it is inside the selected registered library.
- Read `gallery-root-path` once for migration, then remove it after match/no-match is known. Do not write `gallery-root-path` from new code.
- Replace `galleryStore.currentPath` references with `galleryStore.currentBrowsePath` where the implementation touches the file. If churn becomes too broad, a temporary read-only alias named `currentPath` is acceptable, but new code should use `currentBrowsePath`.
- Avoid a writable `rootPath` alias. If an alias is needed to keep a diff small, it must be read-only, derived from `activeLibraryRootPath`, and removed before considering this feature complete.

## 5. Components And Files

### 5.1 New admin pages

Create:

- `frontend/src/components/admin/LibraryListPage.vue`
- `frontend/src/components/admin/LibraryDetailPage.vue`

These pages should use existing primitives:

- `Button`
- `ButtonLink`
- `Badge`
- `Input`
- `Skeleton`
- `Dialog`
- `DropdownMenu`
- `Table`
- `Tooltip`
- `Separator`

Library/component reuse rules:

- Use existing shadcn-vue local wrappers from `frontend/src/components/ui/*` first.
- If a needed shadcn-vue/Reka primitive is missing locally, add the local wrapper in the same style as the existing UI components instead of hand-rolling generic behavior.
- Use TanStack Query composables for all library admin server state and mutations.
- Use TanStack Table for the desktop admin table if the table needs reusable column definitions, row action state, sorting, or structured row models. A plain shadcn `Table` wrapper is acceptable only for static markup with no table state.
- Use TanStack Form for the Add Library dialog/sheet if validation, submit modes, touched/dirty state, pending state, and server errors would otherwise become bespoke form state.
- Use the existing bottom-sheet/dialog primitives for responsive Add Library and compact selector surfaces.
- Do not build a new lightbox; keep viewer/lightbox behavior on the existing PhotoSwipe integration.

There is no existing shadcn `Card` primitive. Use simple local `div` panels with `border`, `bg-card`, and `rounded-md`, or add a shadcn-vue-style card primitive only if the diff remains small and consistent.

### 5.2 New admin shared components

Create as needed:

- `frontend/src/components/admin/LibraryStatusBadge.vue`
- `frontend/src/components/admin/LibraryProgressBar.vue`
- `frontend/src/components/admin/LibraryActionMenu.vue`
- `frontend/src/components/admin/LibrarySummaryPanel.vue`
- `frontend/src/components/admin/LibraryCardList.vue` if the responsive list page benefits from separating compact cards from the desktop table
- `frontend/src/components/admin/dialogs/LibraryCreateDialog.vue`
- `frontend/src/components/admin/dialogs/LibraryDeleteConfirmDialog.vue`

Keep components small. Prefer plain props/events over global modal managers.

### 5.3 Existing components to update

Update:

- `frontend/src/router/index.ts`
  - lazy-load admin pages
  - export optional prefetch helper
- `frontend/src/App.vue`
  - intro suppression for admin route
  - render responsive admin route on mobile/tablet
  - active library hydration
- `frontend/src/components/AppHeader.vue`
  - add responsive `Libraries` nav entry
- `frontend/src/components/LibrarySidebarHeader.vue`
  - rename/replace `RootPathSidebarHeader.vue`
  - render registered-library selector for sidebar layouts
- `frontend/src/components/LibrarySelectorSheet.vue` or `frontend/src/components/LibrarySheet.vue`
  - rename/replace `RootPathSheet.vue`
  - render registered-library selector and Add/Manage Library actions for compact layouts
- `frontend/src/components/GallerySidebarContent.vue`
  - mount `LibrarySidebarHeader.vue`
  - update empty copy from "Enter a root path" to registered library language
- `frontend/src/stores/gallery.ts`
  - add active library id handling as the only persisted selection
  - add `activeLibraryRootPath` as a derived getter/value from the libraries query/list
  - rename/adapt `currentPath` to `currentBrowsePath`
  - migrate legacy `gallery-root-path` once, then remove it from localStorage
  - never write `gallery-root-path`
  - avoid writable/persisted `rootPath`
  - keep existing folder browsing behavior stable
- `frontend/src/components/GalleryGrid.vue`
  - update no-path/not-loaded copy to registered library language
  - use `currentBrowsePath` for scan/search context
  - replace `rootPath` readiness checks with active-library readiness
  - error action for `library_not_registered` should route to library management or show Add/Manage Library CTA, not just clear error
- `frontend/src/components/search/AdvancedSearchDrawer.vue`
  - replace `galleryStore.rootPath` with `activeLibraryRootPath` for facet queries unless product scope changes facets to current-folder scope

## 6. Routing

Update `frontend/src/router/index.ts`:

```ts
const loadLibraryListPage = () => import("@/components/admin/LibraryListPage.vue");
const loadLibraryDetailPage = () => import("@/components/admin/LibraryDetailPage.vue");

{
  path: "/admin/libraries",
  name: "admin-libraries",
  component: loadLibraryListPage,
},
{
  path: "/admin/libraries/:id",
  name: "admin-library-detail",
  component: loadLibraryDetailPage,
  props: (route) => ({ id: Number(route.params.id) }),
},
```

Keep wildcard redirect last.

Tablet and mobile users get the same `/admin/libraries` route with responsive layout; the page itself owns responsive layout.

Optional helper:

```ts
let librariesRoutePrefetch: Promise<unknown> | null = null;
export function prefetchLibrariesRoute() {
  librariesRoutePrefetch ??= loadLibraryListPage();
  return librariesRoutePrefetch;
}
```

## 7. Data Flow

### 7.1 List page

```text
LibraryListPage
  useLibrariesQuery()
    GET /api/libraries
  per visible row:
    useLibraryProgressQuery(id)
      GET /api/libraries/{id}/progress
```

For small lists, per-row progress queries are acceptable. If many libraries become likely later, add a backend aggregate progress endpoint instead of over-optimizing now.

### 7.2 Detail page

```text
LibraryDetailPage
  useLibraryQuery(id)
    GET /api/libraries/{id}
  useLibraryProgressQuery(id)
    GET /api/libraries/{id}/progress
```

If detail returns 404:

- show not-found state
- offer link back to `/admin/libraries`

### 7.3 Mutations

Create:

```text
LibraryCreateDialog
  createLibrary(payload)
  invalidate librariesRoot
  set active library
  optionally scan
  navigate detail
```

Scan:

```text
scanLibrary(id)
  invalidate libraryProgress(id)
  invalidate library(id)
  invalidate librariesRoot
  show "Scan started"
```

Repair:

```text
repairLibrary(id)
  invalidate libraryProgress(id)
  invalidate library(id)
  invalidate librariesRoot
  invalidate scan/search/facets for the library root path if known from the library record
  show added/removed/modified counts
```

Unregister:

```text
deleteLibrary(id)
  DELETE with confirm=true
  invalidate librariesRoot
  remove detail/progress cache
  if active id matches, clear or select next library
```

Active library selection:

```text
setActiveLibrary(library)
  activeLibraryId = library.id
  persist gallery-active-library-id
  activeLibraryRootPath is derived from activeLibraryId + libraries query/list
  currentBrowsePath = library.root_path
  reset history to root
  clear search
  fetch scan for root
```

Legacy migration:

```text
hydrateActiveLibrary(libraries)
  persistedId = read gallery-active-library-id
  if persistedId matches libraries:
    set activeLibraryId
    currentBrowsePath = matched.root_path
    remove gallery-root-path if present
    return

  legacyPath = read gallery-root-path once
  if legacyPath matches or is inside one or more libraries:
    library = most specific matching library root
    set activeLibraryId
    persist gallery-active-library-id
    currentBrowsePath = legacyPath if inside library.root_path else library.root_path
    remove gallery-root-path
    return

  remove gallery-root-path if present
  if libraries.length === 1:
    setActiveLibrary(libraries[0])
  else:
    clearActiveLibrary()
```

Viewer APIs after selection:

```text
GalleryGrid
  useInfiniteScanQuery(currentBrowsePath)
  useUnifiedSearchQuery(searchQuery, searchScope, currentBrowsePath)

FolderTreeItem
  useFolderChildrenQuery(node.path)

PhotoCard / Lightbox / metadata
  use image.path returned by scan/search
```

## 8. Error Handling

Use existing `GalleryAPIError` for API failures.

Expected backend errors to surface clearly:

- `library_overlap`: show "This folder overlaps with an existing library."
- `library_offline`: show "Library root is offline or unavailable."
- `not_found`: path does not exist.
- `not_directory`: path is not a folder.
- `permission`: path outside `PATH_SAFETY_ROOT` or not accessible.
- `confirmation_required`: should not happen from UI delete if `confirm=true` is sent; if it happens, show confirmation error.
- `bad_request`: add mapping if missing.

Dialog errors:

- inline message below form
- toast message
- fields preserved

Page errors:

- list/detail should render retry action
- no full-app crash

Main gallery errors:

- `library_not_registered` should guide users to `/admin/libraries` or surface an Add/Manage Library CTA on every breakpoint.
- Do not fall back to arbitrary root-path entry on mobile/tablet.

## 9. Testing Plan

### 9.1 Unit tests

Add or update tests for:

- `GalleryAPIError` maps `bad_request` and registered library errors.
- `libraryStatus` utility maps states and progress percent correctly.
- `gallery` store active library selection:
  - selects persisted id
  - falls back from legacy `gallery-root-path`
  - removes `gallery-root-path` after migration success
  - removes unusable legacy `gallery-root-path` after no library match
  - initializes `currentBrowsePath` from a migrated subfolder only when it is inside the selected library
  - does not persist `activeLibraryRootPath` or `currentBrowsePath`
  - clears active library when deleted
  - keeps folder navigation unchanged
  - does not expose a writable `rootPath` in the registered-library flow

### 9.2 Component tests

Use focused component tests where low-friction:

- `LibraryStatusBadge` renders expected labels.
- `LibraryCreateDialog` validates empty/non-absolute paths and preserves input on API error.
- `LibraryDeleteConfirmDialog` sends confirm event and states source files are not deleted.
- `LibrarySidebarHeader` renders registered libraries and does not render arbitrary root-path input.
- `LibrarySelectorSheet` or `LibrarySheet` renders registered libraries on compact layouts, can select a library, and does not render the legacy root-path textarea.

### 9.3 E2E tests

Add: `frontend/tests/e2e/library-management.spec.ts`

Mock `/api/**` with Playwright, similar to existing inspector tests.

Scenarios:

1. Responsive route renders list:
   - loading skeleton
   - populated desktop table
   - populated tablet/mobile card list
   - empty state
   - API error state with retry
   - tablet/mobile viewport stays on `/admin/libraries` and renders the responsive surface
2. Add Library flow:
   - open dialog on desktop
   - open sheet or compact modal on tablet/mobile
   - validation blocks empty path
   - successful create calls `/api/libraries`
   - `Add and Scan` calls scan endpoint after create
3. Detail page:
   - loads library and progress
   - scan button calls scan endpoint
   - progress updates from discovering to ready
   - last error renders for `error/offline`
4. Unregister:
   - confirmation dialog appears
   - request includes `confirm=true`
   - source files not deleted copy is visible
5. Active library:
   - selecting a library in sidebar drives `/api/scan?path={root_path}`
   - selecting a library in mobile/tablet sheet drives `/api/scan?path={root_path}`
   - arbitrary path input or textarea is not present on desktop, tablet, or mobile
   - persisted `gallery-active-library-id` survives reload
   - legacy `gallery-root-path` migrates to `gallery-active-library-id` and is removed
   - legacy subfolder path inside a registered library initializes `currentBrowsePath`
   - no duplicate persisted source of truth remains after hydration
6. Admin availability:
   - mobile/tablet viewport stays on `/admin/libraries` and renders the responsive surface
   - Add Library, Use in Gallery, Scan, Repair, and Unregister flows are available on compact layouts

### 9.4 Verification commands

Run from `frontend/`:

```bash
pnpm lint
pnpm typecheck
pnpm test:unit
pnpm exec playwright test tests/e2e/library-management.spec.ts --project=chromium
```

If the implementation touches broader viewer behavior, also run:

```bash
pnpm exec playwright test tests/e2e/gallery-no-reload.spec.ts --project=chromium
pnpm exec playwright test tests/e2e/library-inspector.spec.ts --project=chromium
```

### 9.5 Risks and regressions

State model risks:

- Accidentally keeping both `gallery-active-library-id` and `gallery-root-path` as durable selection sources would reintroduce ambiguous startup behavior. The migration must remove the legacy key.
- A writable `rootPath` alias would let new code bypass active library selection. Avoid it, or keep any temporary alias read-only and derived.
- Hydration can race the initial scan if `App.vue` still calls the old `setRootPath()` startup path. Startup should wait for active-library hydration before triggering the first scan on any breakpoint.
- If `activeLibraryId` points to a deleted or unavailable library, the store must clear or choose a deterministic fallback rather than leaving stale `currentBrowsePath`.

Viewer regressions:

- `GalleryGrid` empty/loading states currently check both `currentPath` and `rootPath`; those checks must move to active-library readiness or the gallery may show the wrong empty state.
- Search and scan cache keys remain path-based. Changing them to library-id-based in v1 would risk unnecessary cache churn and lightbox/search regressions.
- `AdvancedSearchDrawer` currently uses `rootPath` for facets; choosing `activeLibraryRootPath` preserves library-level facet suggestions, while choosing `currentBrowsePath` would narrow behavior.
- Legacy subfolder migration must choose the most specific matching library when registered roots overlap, although backend registration should generally prevent overlap.

Compatibility risks:

- Replacing `RootPathSheet.vue` means compact layouts need the same active-library hydration and empty states as desktop. Do not leave a hidden textarea/root-path branch behind.
- Existing Playwright fixtures that seed `gallery-root-path` will fail after migration unless they mock `/api/libraries` and assert one-shot migration/removal.
- Removing `gallery-root-path` too early, before libraries are fetched, could lose a valid migration hint. Read it during hydration, then remove it after match/no-match is known.
- Responsive admin layout can regress table/card parity. Keep row actions, Add Library, scan/repair, and unregister available on both desktop and compact cards.

## 10. Implementation Phases

### Phase 0 - Contract lock and small design cleanup

Deliverable: no UI behavior yet, just implementation-ready contract.

Steps:

1. Confirm backend endpoint shapes from code/tests.
2. Decide v1 excludes rename/import paths/exclusion patterns.
3. Add final type names and query key names.
4. Lock the clean state model:
   - persisted `activeLibraryId`
   - derived `activeLibraryRootPath`
   - in-memory `currentBrowsePath`
   - no persisted/writable `rootPath`
5. Lock the library reuse/style policy:
   - shadcn-vue/Reka primitives for accessible generic UI
   - TanStack Query/Table/Form/Virtual where they replace generic data/table/form/virtual behavior
   - PhotoSwipe for lightbox behavior
   - custom code only for gallery-specific composition and backend contract glue
6. Identify all root-path copy that must change to registered-library copy.
7. Identify all `rootPath` and `currentPath` store call sites that need rename/adaptation.

Risk: implementing old Immich-like import path/exclusion UI would create dead controls because backend has no API for it.

### Phase 1 - API, query, status foundation

Deliverable: data layer can list, create, scan, repair, delete, and poll progress.

Files:

- `frontend/src/types/index.ts`
- `frontend/src/services/api.ts`
- `frontend/src/query/keys.ts`
- `frontend/src/composables/admin/useLibrariesQuery.ts`
- `frontend/src/composables/admin/useLibraryQuery.ts`
- `frontend/src/composables/admin/useLibraryProgressQuery.ts`
- `frontend/src/composables/admin/useLibraryMutations.ts`
- `frontend/src/utils/libraryStatus.ts`

Steps:

1. Add types.
2. Add API functions using existing error wrapper.
3. Add query keys.
4. Add query composables.
5. Add mutation composable and invalidation rules.
6. Add status presentation utility and unit tests.

### Phase 2 - Admin routes and list page

Deliverable: `/admin/libraries` works responsively with list, empty, loading, error, and row actions.

Files:

- `frontend/src/router/index.ts`
- `frontend/src/App.vue`
- `frontend/src/components/AppHeader.vue`
- `frontend/src/components/admin/LibraryListPage.vue`
- `frontend/src/components/admin/LibraryStatusBadge.vue`
- `frontend/src/components/admin/LibraryActionMenu.vue`
- `frontend/src/components/admin/dialogs/LibraryCreateDialog.vue`

Steps:

1. Add lazy routes.
2. Suppress intro on admin routes without redirecting compact breakpoints.
3. Add responsive `Libraries` header/nav entry.
4. Build desktop table and states.
5. Build tablet/mobile card list and states.
6. Build Add Library dialog/sheet.
7. Wire create, scan, repair row actions on table and cards.

### Phase 3 - Detail page and unregister flow

Deliverable: `/admin/libraries/:id` works with progress, lifecycle actions, and unregister confirmation.

Files:

- `frontend/src/components/admin/LibraryDetailPage.vue`
- `frontend/src/components/admin/LibraryProgressBar.vue`
- `frontend/src/components/admin/LibrarySummaryPanel.vue`
- `frontend/src/components/admin/dialogs/LibraryDeleteConfirmDialog.vue`

Steps:

1. Build detail data loading.
2. Build status/progress panels.
3. Build registered folder panel.
4. Wire scan and repair actions.
5. Build unregister confirmation.
6. Handle 404/not-found.

### Phase 4 - Active library selection in main gallery

Deliverable: main viewer uses selected registered library instead of arbitrary root path.

Files:

- `frontend/src/stores/gallery.ts`
- `frontend/src/components/LibrarySidebarHeader.vue`
- `frontend/src/components/LibrarySelectorSheet.vue` or `frontend/src/components/LibrarySheet.vue`
- `frontend/src/components/GallerySidebarContent.vue`
- `frontend/src/components/GalleryGrid.vue`
- `frontend/src/App.vue`
- `frontend/src/components/search/AdvancedSearchDrawer.vue`

Steps:

1. Add `activeLibraryId` state and persistence under `gallery-active-library-id`.
2. Add `activeLibraryRootPath` as a derived getter/value from the libraries query/list.
3. Rename/adapt writable browse state from `currentPath` to `currentBrowsePath`.
4. Add `hydrateActiveLibrary()` startup action with one-shot `gallery-root-path` migration and removal.
5. Convert `RootPathSidebarHeader.vue` into `LibrarySidebarHeader.vue`.
6. Convert `RootPathSheet.vue` into `LibrarySelectorSheet.vue` or `LibrarySheet.vue`.
7. Update no-library empty copy and Add/Manage Library CTAs on all breakpoints.
8. Update `library_not_registered` action to route users to admin or show Add/Manage Library CTA.
9. Replace `GalleryGrid` `rootPath` gating with active-library readiness.
10. Replace advanced-search facets path with `activeLibraryRootPath`.
11. Ensure folder navigation inside selected library still works.
12. Ensure search scope/current browse path behavior is unchanged after selection.

### Phase 5 - Tests and polish

Deliverable: verified implementation with targeted tests.

Steps:

1. Add unit tests for API/error/status/store.
2. Add Playwright `library-management.spec.ts`.
3. Run lint/typecheck/unit/e2e commands.
4. Fix accessibility issues:
   - dialogs labelled
   - icon-only actions have labels/tooltips
   - table actions keyboard accessible
5. Verify dark mode with existing tokens.
6. Verify `/admin/libraries` renders on mobile/tablet and the Add Library flow is available.

## 11. Acceptance Criteria

The implementation is complete when:

1. Users can open `/admin/libraries` on desktop, tablet, and mobile.
2. Desktop renders the library list as a table; tablet/mobile render a card list.
3. Users can add a library folder on every breakpoint through the Add Library dialog/sheet.
4. Users can scan/rescan a registered library on desktop, tablet, and mobile.
5. Users can repair a registered library catalog on desktop, tablet, and mobile.
6. Users can see library state, progress, and last errors on desktop, tablet, and mobile.
7. Users can unregister a library with clear source-file-safe confirmation on desktop, tablet, and mobile.
8. The main gallery no longer shows arbitrary root path input or textarea as primary UX on desktop, tablet, or mobile.
9. All breakpoints can select a registered library.
10. The no-library gallery state shows Add Library and/or Manage Libraries CTA.
11. The main gallery loads the selected registered library root and browses folders via `currentBrowsePath`.
12. Grid, lightbox, and search remain path-based and library-id unaware.
13. Existing viewer-first gallery browsing remains visually and behaviorally stable.
14. Selection persists only `gallery-active-library-id`; `gallery-root-path` is read once for migration, removed afterward, and never written again.
15. Registered-library code does not keep writable/persisted `rootPath` as a competing source of truth.
16. Generic UI/data behavior uses existing shadcn-vue/Reka, PhotoSwipe, and TanStack libraries where available instead of bespoke implementations.
17. Tests and typecheck pass for the touched frontend surface.

## 12. Future Extensions

Only add these after backend support exists:

- Rename library.
- Multiple import paths per library.
- Exclusion pattern management.
- Aggregate library stats endpoint.
- Derivative warm/rebuild controls in the library detail page.
- Bulk scan all libraries.
- Server-sent events or websocket progress instead of polling.
