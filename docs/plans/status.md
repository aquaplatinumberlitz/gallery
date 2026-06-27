# Frontend Test Quality Refactor — Status

## Phase 0 — Baseline ✅

Commands run and recorded:

| Check | Result |
|---|---|
| `git status --short` | 3 untracked `.extra.test.ts` files |
| `pnpm lint:tests` | 1 error: unused `vi` in `Breadcrumb.extra.test.ts` |
| `pnpm test:unit` | 77 files, 952 tests — all passed |
| `audit_test_matrix.py --fail-on-gaps` | Exit 1 (failed) — 3 uncataloged extra files detected, matching Phase 1 plan expectation |

## Phase 1 — Normalize The Three Extra Component Tests ✅

### `Breadcrumb.extra.test.ts`
- Merged unique behavior into `Breadcrumb.test.ts`:
  - Ellipsis menu open/close via button click (aria-label selector)
  - Hidden segment navigation from ellipsis menu
  - Expand/collapse full path via "Show full path" / "Collapse path" buttons
  - Empty segments path (`///`) gracefully
  - Does not collapse when path has exactly maxVisible segments
- Replaced `wrapper.vm.isExpanded = true` with real DOM interaction flow
- Replaced `wrapper.vm.closeMenu()` — removed as implementation-only (jsdom click-outside unreliable)
- Replaced CSS class selectors (`.ellipsis-btn`, `.collapse-btn`) with aria-label selectors where available
- Deleted `Breadcrumb.extra.test.ts`

### `AppHeader.extra.test.ts`
- Merged unique behavior into `AppHeader.test.ts`:
  - Route-specific visibility (metadata/admin routes)
  - Mobile link hiding
  - Dark theme Moon icon display
  - Advanced Search drawer open/close/apply via interactive stub
  - Filter remove/clear via interactive SearchFilterChips stub
  - Theme switching via dropdown menu items
  - Maintenance route link
- Replaced all `wrapper.vm` accesses (`isAdvancedSearchOpen`, `handleAdvancedSearchClose`, `handleAdvancedSearchApply`, `handleRemoveFilter`, `handleClearAll`) with DOM interactions
- Made `AdvancedSearchDrawer` stub interactive (emits `close`/`apply`)
- Made `SearchFilterChips` stub interactive (emits `remove`/`clear-all`)
- Added `vi.mock("lucide-vue-next")` for data-testid-based icon assertions
- Deleted `AppHeader.extra.test.ts`

### `LibraryDetailPage.extra.test.ts`
- Merged unique behavior into `LibraryDetailPage.test.ts`:
  - Library not found (null + error states)
  - Loading skeleton
  - Contract error message
  - Latest issue display
  - Copy import path action
  - Scan mutation call
  - Generated images rendering
  - Runtime watcher states (healthy/unhealthy/disabled)
  - Lifecycle problems display
  - Jobs with data
  - Exclusion patterns
  - Advanced details toggle via button click
- Replaced `wrapper.vm.advancedOpen = true` with clicking "Show advanced details" button
- Made mock data mutable per-test via module-level variables
- Deleted `LibraryDetailPage.extra.test.ts`

### Acceptance Verification

| Check | Result |
|---|---|
| `rg -n "wrapper\\.vm" frontend/src -g '*.test.ts'` | No private state/method usage in touched files (only `$nextTick` calls remain) |
| `pnpm lint:tests` | ✅ Pass (0 errors) |
| `pnpm test:unit` | ✅ 74 files, 938 tests — all passed (939 before removing redundant highlight test in round 2) |
| `audit_test_matrix.py --fail-on-gaps` | ✅ Pass (exit 0) |
| No uncataloged `.extra.test.ts` files | ✅ Files deleted |
