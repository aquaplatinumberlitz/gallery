# Imported Data Maintenance UX Refactor Plan

Status: Complete

Created: 2026-06-28

Last revised: 2026-06-28

## Summary

Refactor catalog maintenance to reduce user-facing actions to the correct risk
levels:

- `Update`: safe daily action in catalog and library admin.
- `[Rebuild]`: maintenance action for imported data; clears derived data first,
  then rebuilds from registered libraries.
- `[Clear]`: maintenance action for imported data; clears derived
  catalog/metadata/preview data but keeps library registrations.
- `[Reset All]`: destructive Settings Danger Zone action; deletes the full
  catalog database state including libraries/import paths.

This keeps the useful lifecycle/status protections already adapted from Immich,
but does not copy Immich's UI or distributed job architecture.

## Binding UX Decisions

- Gallery/catalog:
  - Show `Update current folder` when scoped.
  - Show `Update library` at library root.
  - Remove `Rebuild` from Catalog Status.
  - Do not use user-facing `Scan` / `Rescan`.
- `/admin/libraries`:
  - Header action: `Update all libraries`.
  - Row/detail action: `Update library`.
  - Keep existing scan endpoints behind those labels:
    - `POST /api/libraries/{id}/scan`
    - `POST /api/libraries/scan-all`
- `/admin/maintenance`:
  - Remove separate action buttons for catalog, metadata jobs, thumbnails, and
    previews.
  - Header shows exactly two imported-data actions:
    - `[Rebuild]`
    - `[Clear]`
  - `Catalogs`, `Metadata jobs`, and `Thumbnails & previews` remain
    diagnostics-only/read-only sections.
  - `[Clear]` has tooltip/help copy explaining it clears imported data while
    keeping libraries/import paths.
- Settings modal:
  - Add `Danger Zone`.
  - Show `[Reset All]` with destructive styling, explanatory copy, and
    type-confirm phrase `RESET CATALOG DATABASE`.

## API And Behavior

- Keep public update endpoints:
  - `POST /api/libraries/{id}/scan`
  - `POST /api/libraries/scan-all`
- Remove public UI usage and frontend service wrappers for old maintenance
  endpoints:
  - `POST /api/libraries/{id}/rebuild`
  - `POST /api/derivatives/rebuild`
  - `POST /api/derivatives/clear`
  - Backend primitives may stay: rebuild staging pipeline, `queue_rebuild`,
    derivative `clear_all()`, metadata lifecycle helpers.
- Add `POST /api/maintenance/imported-data/clear`.
  - Body requires `{ "confirm": true }`.
  - Returns `400` without confirm.
  - Returns `409` if catalog jobs, metadata jobs, derivative jobs, or another
    maintenance operation is active.
  - Preserves `libraries`, `library_import_paths`,
    `library_exclusion_patterns`, library settings, and source files.
  - Deletes derived data: assets, file/folder indexes, FTS/search rows,
    extracted image metadata/resources, metadata jobs, library job history,
    rebuild staging rows, derivative rows/jobs, and generated thumbnail/preview
    files.
  - Resets library runtime state so UI does not show stale scan/progress status.
- Add `POST /api/maintenance/imported-data/rebuild`.
  - Body requires `{ "confirm": true }`.
  - Runs the same clear operation first.
  - Queues parent aggregate job `rebuild_imported_data`.
  - Queues one child whole-library rebuild job per registered library.
  - Parent job transitions based on child results: `running -> succeeded` when
    all child jobs succeed or coalesce successfully; `running -> failed` when
    any child rebuild fails.
  - If no libraries exist, returns succeeded no-op.
  - Metadata extraction is requeued by the rebuild pipeline.
  - v1 does not eagerly regenerate every preview after rebuild; preview cache
    regenerates through existing lazy/warm behavior after assets exist again.
- Add Settings Danger Zone endpoint:
  - `POST /api/maintenance/catalog/reset`
  - Requires type-confirm phrase `RESET CATALOG DATABASE`.
  - Rejects active work with `409`.
  - Deletes all SQLite catalog/metadata app data including libraries/import
    paths/exclusions.
  - Clears generated preview files.
  - App returns to empty setup state.

## Lifecycle And Safety

- DB-backed job state remains the source of truth.
- New endpoints must not create a parallel status model.
- Use active-job preflight and a global maintenance lock.
- Publish/invalidate catalog, library, runtime, and maintenance queries after
  mutation.
- Rebuild must reuse existing staging + atomic activation flow.
- Derivative file deletion must reuse scheduler protection for files being
  served/generated.
- Metadata lifecycle counters remain diagnostics after clear/rebuild.
- `[Reset All]` in Settings is visible only to admin/maintenance-capable users,
  and backend permission/confirm checks remain authoritative.

## Implementation Phases

### Phase 0 - Create Plan Document

- Add this plan as
  `docs/plans/IMPORTED_DATA_MAINTENANCE_UX_REFACTOR_PLAN.md`.
- Update `docs/plans/README.md` Active plans list to include this file.
- Do not modify archived plans except if a later archival step is explicitly
  requested.

### Phase 1 - Backend Maintenance Primitives

- Add a maintenance service/helper that performs imported-data active-work
  preflight.
- Add a global in-process maintenance lock so clear/rebuild/reset cannot
  overlap.
- Implement imported-data clear as a single coordinated operation:
  - delete derived SQLite rows in safe dependency order,
  - preserve library registration/config rows,
  - clear generated preview files using existing derivative scheduler
    protection,
  - reset library runtime fields.
- Add backend tests for preserved rows, deleted rows, active-work `409`, and
  missing-confirm `400`.

### Phase 2 - Backend Rebuild And Reset APIs

- Add `POST /api/maintenance/imported-data/clear`.
- Add `POST /api/maintenance/imported-data/rebuild`.
- Implement parent aggregate `rebuild_imported_data` job orchestration and child
  rebuild queueing.
- Add `POST /api/maintenance/catalog/reset` for Settings Danger Zone.
- Remove or de-public old maintenance route exposure only after new endpoints
  and tests pass.
- Add backend tests for rebuild parent/child behavior, no-library no-op, reset
  phrase validation, reset active-work rejection, and `/api/libraries` empty
  after reset.

### Phase 3 - Frontend API And Query Layer

- Add frontend service wrappers and types for:
  - imported-data clear,
  - imported-data rebuild,
  - catalog reset.
- Remove UI usage and tests for old derivative/rebuild endpoint wrappers.
- Add query invalidation for catalog, libraries, runtime, maintenance
  diagnostics, and jobs after clear/rebuild/reset.
- Keep scan endpoint wrappers but user-facing labels become Update vocabulary.

### Phase 4 - Maintenance UI Refactor

- Replace maintenance action buttons with exactly `[Rebuild]` and `[Clear]` in
  the maintenance header.
- Keep `Catalogs`, `Metadata jobs`, and `Thumbnails & previews` as
  diagnostics-only sections.
- Add tooltip/help copy for `[Clear]`.
- Ensure no preview-only, metadata-only, or catalog-only maintenance action
  buttons remain in UI.
- Keep compact operational UI; do not introduce a landing/marketing-style page.

### Phase 5 - Catalog And Libraries Label Cleanup

- Catalog:
  - replace scan action label with `Update current folder` or `Update library`,
  - remove rebuild action from Catalog Status.
- Admin libraries:
  - replace `Scan all` with `Update all libraries`,
  - replace row/detail `Scan` / `Scan / Rescan` with `Update library`.
- Keep endpoint behavior unchanged for update actions.

### Phase 6 - Settings Danger Zone

- Add Settings modal Danger Zone for `[Reset All]`.
- Show destructive styling and explanatory copy.
- Require typing `RESET CATALOG DATABASE`.
- Hide the action from non-admin/non-maintenance-capable users.
- Backend permission checks remain mandatory regardless of UI visibility.

### Phase 7 - Verification

- Frontend tests:
  - Catalog shows Update vocabulary and no Catalog Status rebuild action.
  - Admin libraries show Update vocabulary and no user-facing Scan/Rescan.
  - Maintenance shows only `[Rebuild]` and `[Clear]` action buttons.
  - Diagnostics sections remain read-only.
  - Settings shows `[Reset All]` in Danger Zone for authorized users.
- Backend tests:
  - Clear preserves libraries/import paths/exclusions and clears derived
    rows/files.
  - Rebuild clears first, then queues child rebuild jobs under parent aggregate
    job.
  - Imported-data endpoints return `400` without confirm and `409` with active
    work.
  - Reset requires phrase, rejects active work, deletes library registrations,
    and leaves `/api/libraries` empty.
- E2E:
  - Update buttons still call scan endpoints.
  - Clear leaves registered libraries intact but catalog empty.
  - Rebuild repopulates assets/metadata from existing import paths.
  - Reset requires type-confirm and returns UI to empty libraries state.
- Run the repo's relevant verification commands before commit:
  - backend tests for maintenance/libraries/derivatives/catalog lifecycle,
  - frontend unit tests for changed components/composables,
  - frontend typecheck/build if frontend API/types changed.

### Phase 8 - Commit And Push Handoff

- Before committing, run `git status --short --branch`.
- Stage only files changed for this implementation.
- Commit with a focused message, recommended:
  - `feat: simplify imported data maintenance`
- The current branch is `main` and was observed ahead of `origin/main` by 8
  commits before this plan was written.
- Before pushing, confirm those existing ahead commits are intended to be pushed
  with this work; do not rebase, reset, or revert unrelated user changes.
- Push to the configured remote/branch:
  - `git push origin main`

## Assumptions

- No backward compatibility is required for old maintenance public endpoints
  once the UI is migrated.
- Source files are never deleted by any maintenance action.
- “Imported data” means data derived from registered import paths, not the
  registrations themselves.
- `[Clear]`, `[Rebuild]`, and `[Reset All]` are the user-facing button labels by
  product decision.
- Confirm contract stays for imported-data clear/rebuild even if the button
  label is short.
