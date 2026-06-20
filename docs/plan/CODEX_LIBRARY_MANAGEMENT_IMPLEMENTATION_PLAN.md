# Codex Library Management Implementation Plan

Status: plan only, no implementation in this step.

Goal: implement a desktop-only Library Import / Library Management frontend for registered libraries. Immich is used only as a UI pattern reference. Do not copy Immich source code, Svelte/SvelteKit architecture, or Immich API shapes.

## 1. Current Findings

### 1.1 Gallery backend contract to target

The implementation must target the gallery backend that exists in this repo, not Immich.

Current registered library endpoints:

| Method | Endpoint | Purpose | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/libraries` | List registered libraries | Returns DB rows from `libraries`. |
| `POST` | `/api/libraries` | Register one library root | Body: `{ root_path: string, name?: string }`. Validates path safety, existence, directory, overlap. |
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
- There are no `import_paths` or `exclusion_patterns` fields/endpoints in the current gallery backend. V1 should register one explicit library root per library.
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
- localStorage key `gallery-root-path`

The new UX must replace arbitrary root entry with an explicit active library selection. Internally, the existing scan/folder/search APIs can continue receiving the selected library's `root_path`.

### 1.3 Immich patterns to adapt, not copy

Patterns worth adapting:

- Separate admin route area for library management.
- List page with table, row status, row actions, loading/empty/error states.
- Detail page with status summary, progress, registered folders/actions, and destructive confirmation.
- Add/register dialog with validation and server error display.
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

## Entry Point Design

Chosen approach: Option B, with a strict split between library selection and library management.

The app has two separate entry points:

- Admin/management entry point: a desktop-only `Libraries` button in `AppHeader.vue`, placed next to the existing `Metadata` button.
- Gallery selection entry point: the existing sidebar header slot above the folder tree, currently implemented by `RootPathSidebarHeader.vue`.

The main gallery needs an in-context way to choose the registered library it is browsing. `GallerySidebarContent.vue` already mounts `RootPathSidebarHeader.vue` above the folder tree, so that slot should be reused for active library selection on desktop. This keeps the selected library, derived root path, and folder tree context together. Keep the component name initially if that reduces churn; a later rename to `LibrarySidebarHeader.vue` can happen only if the implementation diff stays manageable.

Library management is a separate workflow: register, scan, repair, inspect, and unregister libraries. Expose that workflow through the desktop header by adding `Libraries` beside `Metadata` in `AppHeader.vue`. The button routes to `/admin/libraries`, is active for `/admin/libraries` routes, and remains hidden from mobile and tablet.

`RootPathSheet.vue` stays untouched for this implementation. It is coupled to the legacy arbitrary-path flow with paste, clear, textarea, and load semantics, and mobile/tablet behavior is frozen. Treat it as a compatibility surface for the frozen mobile/tablet legacy path-entry behavior. Do not turn it into a library-management drawer or a registered-library selector during this work.

Selection persistence migrates from the legacy path key to the new active library id:

1. Add `gallery-active-library-id` as the new persisted selection key.
2. Fetch registered libraries during active-library hydration.
3. If `gallery-active-library-id` exists and matches a registered library, use it.
4. Else, if legacy `gallery-root-path` exactly matches or is inside a registered library root, select that library and persist its id.
5. Else, if exactly one registered library exists, select it.
6. Else, leave no active library selected and show the desktop empty state with a `Manage Libraries` link.

Keep `galleryStore.rootPath` as derived compatibility state for existing scan, folder, and search queries. After migration, arbitrary root-path entry is no longer the authoritative desktop model.

Gating logic:

- New admin pages and the header `Libraries` entry are desktop-only.
- The new active library selector is desktop-only.
- Mobile and tablet remain visually and behaviorally unchanged for this phase.
- `GallerySidebarContent.vue` is shared by desktop, tablet, and mobile layouts, so gate the new selector to true desktop/wide breakpoints or split the desktop sidebar header implementation from frozen tablet/mobile surfaces.

## 2. Product Scope

### 2.1 V1 scope

V1 will provide:

1. Desktop-only admin pages:
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
3. Register library dialog:
   - absolute folder path
   - optional display name
   - duplicate/overlap client warning where possible
   - server error handling
   - optional "Register and scan" workflow
4. Library detail page:
   - status badge
   - progress card
   - registered root path card
   - scan/rescan action
   - repair action
   - unregister action
   - last error display
5. Main gallery active library selector:
   - no arbitrary root path input in desktop sidebar
   - user selects one registered library
   - selected library root drives `galleryStore.rootPath/currentPath`
   - persisted active library id
   - fallback/migration from legacy `gallery-root-path`
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
- No mobile/tablet admin page.

## 3. UX Plan

### 3.1 Admin navigation

Add a desktop-only "Libraries" entry near the existing "Metadata" header button in `AppHeader.vue`.

Behavior:

- Visible only on desktop.
- Active when `route.path.startsWith("/admin/libraries")`.
- Prefetch route component on pointer enter/focus, matching the metadata prefetch style if useful.
- Keep main gallery viewer-first; do not make library management the default first screen.

### 3.2 Desktop route guard

Extend the existing route/device handling in `App.vue`:

- Admin routes should set `showIntro=false`.
- If `isMobile || isTablet` and route starts with `/admin/libraries`, redirect to `/`.
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
  - primary action: `Register Library`
- Table columns:
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
- CTA: `Register Library`

Error state:

- Inline error panel with retry.
- Keep existing shell stable; do not navigate away.

Loading state:

- Table skeleton rows using existing `Skeleton`.

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

### 3.5 Register library dialog

Component: `frontend/src/components/admin/dialogs/LibraryCreateDialog.vue`

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

- `Register`: `POST /api/libraries`
- `Register and Scan`: create, then `POST /api/libraries/{id}/scan`

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

Implement the gallery selection side of the [Entry Point Design](#entry-point-design): replace arbitrary root path entry in the desktop sidebar with a registered-library selector, while leaving mobile/tablet behavior unchanged.

Primary target: `RootPathSidebarHeader.vue`

Suggested approach:

- Keep file name initially to reduce churn, but change the UI semantics from "root path input" to "active library selector".
- Later rename to `LibrarySidebarHeader.vue` only if the diff stays manageable.
- Gate the new selector to true desktop/wide breakpoints because `GallerySidebarContent.vue` is shared by desktop, tablet, and mobile layouts.
- Leave `RootPathSheet.vue` untouched as the frozen mobile/tablet legacy compatibility surface.

UI states:

- Loading libraries: skeleton or compact loading row.
- No libraries:
  - desktop: show `No libraries registered` and a `Manage Libraries` link.
  - mobile/tablet: unchanged from current legacy behavior.
- Libraries available:
  - select/dropdown with library name and status
  - secondary root path display
  - `Manage` link on desktop
  - optional scan status indicator

Store behavior:

- Add `activeLibraryId` persisted to localStorage key `gallery-active-library-id`.
- Keep `rootPath` as the active library root path for compatibility with existing gallery queries.
- Add actions:
  - `hydrateActiveLibrary()`
  - `setActiveLibrary(library: RegisteredLibrary)`
  - `clearActiveLibrary()`
- On startup:
  1. Fetch registered libraries.
  2. If persisted `activeLibraryId` exists and still exists, select it.
  3. Else if legacy `gallery-root-path` matches or is inside a registered library, select that library.
  4. Else if exactly one library exists, select it.
  5. Else leave unselected and show empty state.
- On active library selection:
  - set `rootPath = library.root_path`
  - set `currentPath = library.root_path`
  - clear search
  - reset folder expansion/history
  - call existing scan flow for that root

Important: keep `selectFolder()` behavior unchanged for folders inside the active library.

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

There is no existing shadcn `Card` primitive. Use simple local `div` panels with `border`, `bg-card`, and `rounded-md`, or add a card primitive only if the diff remains small and consistent.

### 5.2 New admin shared components

Create as needed:

- `frontend/src/components/admin/LibraryStatusBadge.vue`
- `frontend/src/components/admin/LibraryProgressBar.vue`
- `frontend/src/components/admin/LibraryActionMenu.vue`
- `frontend/src/components/admin/LibrarySummaryPanel.vue`
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
  - mobile/tablet redirect for admin route
  - active library hydration
- `frontend/src/components/AppHeader.vue`
  - add desktop `Libraries` nav button
- `frontend/src/components/RootPathSidebarHeader.vue`
  - replace raw path input with active library selector
- `frontend/src/components/GallerySidebarContent.vue`
  - keep header usage stable, update desktop empty copy from "Enter a root path" to registered library language
- `frontend/src/stores/gallery.ts`
  - add active library id handling
  - migrate legacy root path behavior
  - keep existing gallery browsing behavior stable
- `frontend/src/components/GalleryGrid.vue`
  - update desktop no-path/not-loaded copy to registered library language where it is part of the registered-library flow
  - error action for `library_not_registered` should route to admin on desktop, not just clear error

## 6. Routing

Update `frontend/src/router/index.ts`:

```ts
const loadLibraryListPage = () => import("@/components/admin/LibraryListPage.vue");
const loadLibraryDetailPage = () => import("@/components/admin/LibraryDetailPage.vue");

{
  path: "/admin/libraries",
  name: "admin-libraries",
  component: loadLibraryListPage,
  meta: { desktopOnly: true },
},
{
  path: "/admin/libraries/:id",
  name: "admin-library-detail",
  component: loadLibraryDetailPage,
  props: (route) => ({ id: Number(route.params.id) }),
  meta: { desktopOnly: true },
},
```

Keep wildcard redirect last.

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
  invalidate scan/search/facets for root path if known
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
  rootPath = library.root_path
  currentPath = library.root_path
  reset history to root
  clear search
  persist active id
  fetch scan for root
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

- `library_not_registered` should guide desktop users to `/admin/libraries`
- mobile/tablet should keep existing legacy behavior for this phase and must not add admin entry points

## 9. Testing Plan

### 9.1 Unit tests

Add or update tests for:

- `GalleryAPIError` maps `bad_request` and registered library errors.
- `libraryStatus` utility maps states and progress percent correctly.
- `gallery` store active library selection:
  - selects persisted id
  - falls back from legacy `gallery-root-path`
  - clears active library when deleted
  - keeps folder navigation unchanged

### 9.2 Component tests

Use focused component tests where low-friction:

- `LibraryStatusBadge` renders expected labels.
- `LibraryCreateDialog` validates empty/non-absolute paths and preserves input on API error.
- `LibraryDeleteConfirmDialog` sends confirm event and states source files are not deleted.

### 9.3 E2E tests

Add: `frontend/tests/e2e/library-management.spec.ts`

Mock `/api/**` with Playwright, similar to existing inspector tests.

Scenarios:

1. Desktop route renders list:
   - loading skeleton
   - populated table
   - empty state
   - API error state with retry
2. Register library:
   - open dialog
   - validation blocks empty path
   - successful create calls `/api/libraries`
   - `Register and Scan` calls scan endpoint after create
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
   - arbitrary path input is not present on desktop
6. Desktop-only:
   - mobile/tablet viewport redirects `/admin/libraries` to `/`

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

## 10. Implementation Phases

### Phase 0 - Contract lock and small design cleanup

Deliverable: no UI behavior yet, just implementation-ready contract.

Steps:

1. Confirm backend endpoint shapes from code/tests.
2. Decide v1 excludes rename/import paths/exclusion patterns.
3. Add final type names and query key names.
4. Identify all root-path copy that must change to registered-library copy.

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

Deliverable: `/admin/libraries` works on desktop with list, empty, loading, error, and row actions.

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
2. Add desktop-only redirect in `App.vue`.
3. Add `Libraries` header nav.
4. Build list table and states.
5. Build create dialog.
6. Wire create, scan, repair row actions.

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
- `frontend/src/components/RootPathSidebarHeader.vue`
- `frontend/src/components/GallerySidebarContent.vue`
- `frontend/src/components/GalleryGrid.vue`
- `frontend/src/App.vue`

Steps:

1. Add `activeLibraryId` state and persistence.
2. Add `hydrateActiveLibrary()` startup action.
3. Convert root path header to library selector.
4. Update no-library empty copy.
5. Update `library_not_registered` action to route users to admin on desktop.
6. Ensure folder navigation inside selected library still works.
7. Ensure search scope/current path behavior is unchanged after selection.

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
6. Verify route redirects on mobile/tablet.

## 11. Acceptance Criteria

The implementation is complete when:

1. Desktop users can open `/admin/libraries`.
2. Desktop users can register a library folder.
3. Desktop users can scan/rescan a registered library.
4. Desktop users can repair a registered library catalog.
5. Desktop users can see library state, progress, and last errors.
6. Desktop users can unregister a library with clear source-file-safe confirmation.
7. The main gallery no longer asks for arbitrary root path entry on desktop.
8. The main gallery loads the selected registered library root.
9. Existing viewer-first gallery browsing remains visually and behaviorally stable.
10. Mobile/tablet users cannot access the admin pages.
11. Tests and typecheck pass for the touched frontend surface.

## 12. Future Extensions

Only add these after backend support exists:

- Rename library.
- Multiple import paths per library.
- Exclusion pattern management.
- Aggregate library stats endpoint.
- Derivative warm/rebuild controls in the library detail page.
- Bulk scan all libraries.
- Server-sent events or websocket progress instead of polling.
