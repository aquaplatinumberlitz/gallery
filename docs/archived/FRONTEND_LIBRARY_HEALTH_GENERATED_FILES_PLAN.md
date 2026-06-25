# Frontend Plan: Library Health And Generated Files UI

Status: Archived completed plan

Archived: 2026-06-25

Current source of truth: [Architecture](../ARCHITECTURE.md), [Configuration](../CONFIGURATION.md), and the frontend/backend source files.

## Summary

Add frontend support for the remaining library lifecycle surfaces that are already present or emerging in the backend, while keeping user-facing labels simple.

Approved UI mapping:

- `Admin > Libraries > detail`
  - `Generated images`
  - `Live status`
  - `Problems`
- `Admin > Maintenance`
  - `File issues`
  - `Check files`
  - `Repair results`

Do not expose backend terms such as `derivatives`, `runtime`, `diagnostics`, or `integrity` in primary UI labels.

`derivative_ready` is the one lifecycle field that should not become a visible admin card. It should be used silently in grid and lightbox behavior for loading, placeholders, preload, warm, and fallback.

## Current Repo Context

- Main gallery already focuses on browsing and viewing assets.
- `/metadata` is for asset and file metadata inspection, not global queue or repair state.
- `Admin > Libraries` already owns library registration, scan/rebuild actions, catalog status, import paths, exclusion patterns, and job history.
- The index/catalog panel already provides a simple summary of scan/index status. Keep it concise.
- Backend derivative endpoints exist at `/api/derivatives/status`, `/api/derivatives/warm`, `/api/derivatives/rebuild`, and `/api/derivatives/clear`.
- Frontend types already know `FileNode.derivative_ready`, `RegisteredLibrary.watch_enabled`, `RegisteredLibrary.warm_enabled`, and `metadata_lifecycle`, but the UI does not fully use them.

## UI/UX Implementation Rules

Use the frontend stack and visual language already present in the codebase.

Required libraries and primitives:

- Use Vue single-file components and the existing Composition API style.
- Use TanStack Query through the repo's existing query/composable pattern for server state, mutations, invalidation, loading, and error states.
- Use existing shadcn-vue/Reka-based UI primitives from `frontend/src/components/ui/`:
  - `Button`
  - `Badge`
  - `Skeleton`
  - `Table`
  - `Dialog`
  - `Tooltip`
  - `Popover`
  - `Separator`
- Use `lucide-vue-next` icons for actions and status indicators.
- Use existing Tailwind v4/shadcn token classes and current admin page patterns. Do not introduce another component library, charting library, icon set, or global design system.

Visual rules:

- Match `LibraryDetailPage.vue` and `LibraryListPage.vue`: quiet admin cards, compact rows, small status badges, clear action buttons.
- Keep cards to the existing `rounded-md border bg-background p-5` pattern unless the surrounding page has a more specific local pattern.
- Use `Button variant="outline"` for normal maintenance actions, `variant="secondary"` for lower-emphasis alternates, and `variant="destructive"` only for clear/delete actions.
- Use `Skeleton` for loading card bodies, not custom spinners unless the existing section already uses one.
- Use `Dialog` for confirmation flows; confirmation text must say source image files are not deleted where relevant.
- Use tables only for report/detail lists. Use compact definition-list rows for summary cards.
- Keep labels short and user-facing. Do not expose raw backend field names in primary UI.

Suggested icons:

- `Generated images`: `Images`, `Image`, or `RefreshCw`.
- `Live status`: `Activity`, `RefreshCw`, or `Radio`.
- `Problems`: `AlertTriangle`.
- `File issues`: `AlertTriangle` or `FileWarning`.
- `Check files`: `ScanLine`.
- `Repair results`: `Wrench` or `CheckCircle`.

## Implementation Changes

### 1. Admin Libraries Detail: `Generated images`

Add a `Generated images` card to `frontend/src/components/admin/LibraryDetailPage.vue`.

Purpose:

- Show thumbnail/preview generated-file coverage without exposing the word `derivatives`.
- Let admins warm, rebuild, and clear generated preview files for a library.

Show:

- `Ready`: generated files ready count.
- `Expected`: expected generated files count.
- `Progress`: ready divided by expected.
- `Cache usage`: quota used bytes.
- `Cache limit`: quota bytes.
- `Cache used`: quota utilization percentage.

Actions:

- `Generate missing`
  - Calls `POST /api/derivatives/warm?library_id=...`.
  - Queues missing generated thumbnail and preview files for the selected library.
- `Refresh stale`
  - Requires confirmation.
  - Calls `POST /api/derivatives/rebuild?confirm=true`.
  - Queues generated files whose source changed.
- `Clear generated files`
  - Requires confirmation.
  - Calls `POST /api/derivatives/clear?confirm=true`.
  - Deletes generated-file catalog/cache state, not source images.

Frontend API work:

- Add types in `frontend/src/types/index.ts`:
  - `GeneratedImagesStatus`
  - `GeneratedImagesWarmResponse`
  - `GeneratedImagesRebuildResponse`
  - `GeneratedImagesClearResponse`
- Add wrappers in `frontend/src/services/api.ts`:
  - `fetchGeneratedImagesStatus(libraryId: number)`
  - `generateMissingImages(libraryId: number)`
  - `refreshStaleGeneratedImages()`
  - `clearGeneratedImages()`
- Add query key helpers in `frontend/src/query/keys.ts`:
  - `generatedImages(libraryId)`
- Add composables under `frontend/src/composables/admin/`:
  - `useGeneratedImagesStatusQuery`
  - `useGeneratedImagesMutations`

Invalidation:

- After any generated-image mutation, invalidate:
  - generated images status
  - library status
  - library jobs
  - global jobs
  - browse/root queries when clearing generated files

UX rules:

- Keep this card on the admin detail page, not main gallery.
- Use existing `Button`, `Skeleton`, and card styling patterns from `LibraryDetailPage.vue`.
- Show clear loading, success toast, and error toast states.
- Explain destructive actions in confirmations: source image files are not deleted.

### 2. Main Gallery And Lightbox: Use `derivative_ready` Silently

Use `FileNode.derivative_ready` as an internal hint only.

Do not add visible labels such as `thumbnail ready`, `preview ready`, `derivative ready`, or `generated image status` in the grid or lightbox.

Grid behavior:

- If thumbnail readiness is false or missing, continue showing the existing loading placeholder/skeleton while the image URL loads.
- Do not block rendering entirely. The existing URL flow can still trigger generation.
- Avoid extra eager preloads for assets where preview readiness is explicitly false.

Lightbox behavior:

- Keep the current preview-first flow.
- Keep original fallback when preview load fails.
- Use readiness to decide whether neighbor preload should start immediately:
  - if `derivative_ready.preview === true`, preload thumbnail and preview as today.
  - if `derivative_ready.preview === false`, avoid aggressive neighbor preview preload and let active navigation trigger generation.
  - if readiness is missing or null, keep current behavior for backward compatibility.
- Do not show a technical error for readiness false. Only show existing image load failure states.

Likely files:

- `frontend/src/utils/lightbox.ts`
- `frontend/src/stores/lightbox.ts`
- `frontend/src/composables/usePhotoSwipe.ts`
- `frontend/src/components/PhotoCard.vue`
- `frontend/src/components/VideoCard.vue`

Tests:

- `derivative_ready` does not render as visible text.
- neighbor preload is skipped or delayed when preview readiness is explicitly false.
- current slide still loads through existing thumbnail/preview/original fallback.
- null or missing readiness preserves current behavior.

### 3. Admin Libraries Detail: `Live status`

Add a `Live status` card to `frontend/src/components/admin/LibraryDetailPage.vue`.

Purpose:

- Show background watcher and scheduled refresh state in plain language.
- Make it clear whether the app is watching folders and refreshing the catalog automatically.

Show:

- `Watching for changes`
  - `On`, `Off`, or `Needs attention`.
- `Scheduled refresh`
  - `On` or `Off`.
- `Watched folders`
  - count when available.
- `Refresh interval`
  - when available.
- `Latest issue`
  - watcher issue text if present.

Data source:

- Prefer existing catalog status `global_runtime`:
  - `watcher_enabled`
  - `watcher_healthy`
  - `watcher_issue`
  - `scheduled_reconciliation_enabled`
- If backend exposes watcher/refresh detailed status in future, extend this card without changing labels.

UX rules:

- Do not claim per-library watcher state unless backend exposes it directly.
- Do not add per-library watcher toggles yet. `watch_enabled` and `warm_enabled` exist in types/schema, but current update payload does not expose them in `LibraryForm.vue`.
- If a field is unavailable, show a neutral `Not available` value rather than guessing.

Tests:

- healthy watcher renders `Watching for changes: On`.
- unhealthy watcher renders `Needs attention` and issue text.
- scheduled refresh enabled/disabled renders correctly.
- missing runtime data renders neutral copy.

### 4. Admin Libraries Detail: `Problems`

Add a `Problems` card to `frontend/src/components/admin/LibraryDetailPage.vue`.

Purpose:

- Make metadata lifecycle counters useful without turning the normal catalog panel into a backend dashboard.

Show summary rows:

- `Waiting`: queued metadata jobs.
- `Processing`: running metadata jobs.
- `Failed`: failed metadata jobs.
- `Needs refresh`: stale metadata jobs plus assets done but metadata missing or stale.
- `Can be repaired`: repairable metadata assets.
- `Worker`: active or inactive.

Advanced section:

- Add a collapsible `Advanced details` section.
- Render the full `metadata_lifecycle` counters using friendly labels.
- Keep raw field names out of the primary UI.

Data source:

- `StatusResponseEnvelope.metadata_lifecycle`.
- Handle `metadata_lifecycle: null` by showing `No problem details available`.

Do not change:

- Keep `IndexStatusPanel.vue` focused on scan/index summary.
- Do not move all counters into the gallery sidebar.

Tests:

- summary rows render from a valid lifecycle object.
- null lifecycle renders a neutral empty state.
- worker status uses `metadata_worker_alive`.
- failed and repairable counts use attention styling.

### 5. Admin Maintenance: File Health Screens

Add or extend an admin maintenance route with three user-facing sections:

- `File issues`
- `Check files`
- `Repair results`

Purpose:

- Provide a place for cross-table and storage health checks, similar to Immich Maintenance, without exposing the term `integrity`.

Initial frontend behavior:

- If backend only exposes counters/status:
  - render status-only cards.
  - show `No report history available` for missing persisted report APIs.
- If backend exposes report endpoints later:
  - connect report list, pagination, export, and delete actions.

`File issues` section:

- Show issue categories and counts.
- Use labels:
  - `Missing source files`
  - `Generated image missing`
  - `Metadata mismatch`
  - `Orphaned work item`
  - `Generated image job mismatch`
- Show latest run timestamp when available.
- Show latest issue text when available.

`Check files` section:

- Add `Run checks` action.
- Add optional per-check actions only when backend supports them.
- Disable buttons and show pending state while checks run.

`Repair results` section:

- Show what was repaired, requeued, marked failed, skipped, or unchanged.
- Do not imply source files were deleted unless backend returns that explicitly.
- Keep repair copy factual and auditable.

Route guidance:

- Preferred route: `Admin > Maintenance`.
- If no maintenance route exists yet, add a lightweight route under `frontend/src/router/index.ts` and link it from admin navigation.
- Do not put this under `/metadata`.

Backend dependency rule:

- Do not fake file issue reports from unrelated catalog counters.
- If backend does not provide report items, implement the UI shell with clear empty/unavailable states and wire the available counters only.

Tests:

- maintenance route renders all three sections.
- unavailable backend report data renders `No report history available`.
- check action handles loading, success, and error states.
- repair result counters render with friendly labels.

## Acceptance Criteria

- No primary UI uses the words `derivatives`, `runtime`, `diagnostics`, or `integrity`.
- Main gallery remains focused on browsing and viewing.
- `/metadata` remains metadata inspection only.
- `Admin > Libraries > detail` shows `Generated images`, `Live status`, and `Problems`.
- `Admin > Maintenance` shows `File issues`, `Check files`, and `Repair results`.
- `derivative_ready` changes behavior only, not visible labels.
- All new API wrappers and composables have focused tests.
- All new UI handles loading, empty, error, and unavailable backend states.

## Suggested Implementation Order

1. Add generated-image API types, wrappers, query keys, composables, and tests.
2. Add `Generated images` card to `LibraryDetailPage.vue`.
3. Add `Live status` card using existing `global_runtime`.
4. Add `Problems` card using `metadata_lifecycle`.
5. Use `derivative_ready` silently in grid/lightbox preload behavior.
6. Add the Maintenance route/shell and status-only `File issues`, `Check files`, `Repair results`.
7. Expand Maintenance to report tables only after backend report APIs exist.

## Notes From Immich

- Immich keeps generated thumbnail/preview work in Admin Queues and per-asset refresh actions, not in the main gallery.
- Immich viewer hides readiness behind thumbhash, spinner, broken image, and progressive loading behavior.
- Immich Maintenance makes file health auditable with check/report/delete/export flows.
- Immich uses global library watching/scanning settings and per-library scan/import-path controls, not per-library watcher toggles in the primary library form.
