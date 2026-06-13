# Frontend UI/UX Audit & Adaptation Plan after DT/Immich Phase 1-2-3

Last reviewed: 2026-06-12

## 1. Executive Summary

### What the backend/pipeline already adapted from DT/Immich

The backend has completed a comprehensive adaptation of DT/Immich patterns across three implementation phases:

- **Phase 1 (Unified Parser + Background Indexer)**: Unified metadata parser core, background metadata indexing queue with coalesced jobs, batched SQLite writer (50 rows/transaction), and `/api/index/status` endpoint.
- **Phase 2A (Derivative-First Lightbox)**: `/api/preview` (1440px) as PhotoSwipe main `src`, shared `generate_derivative()` core, original `/api/image` on zoom/fullscreen/download/animated only.
- **Phase 2B (Fielded Search + DB-First Metadata)**: Full fielded search parser (`seed:`, `model:`, `sampler:`, `cfg:`, `negative:`, `prompt:`, 30+ supported fields), DB-first warm metadata reads for lightbox panel.
- **Phase 3 (Warm Listing + Watcher/Refresh + Facets)**: Warm indexed folder listing from `file_index` with `index_source: "warm_db"`, optional file watcher (`watchdog`), optional scheduled refresh, and `/api/facets` endpoint.

### What frontend UX is still missing

The backend has a rich set of capabilities that are either completely invisible or severely underutilized in the frontend:

| Missing UX | Backend Capability Exists? | Frontend Status |
|---|---|---|
| Index status visibility | Yes (`/api/index/status`, `indexer.py:599`) | No API wrapper, no UI component, no query key |
| Faceted search/advanced search | Yes (`/api/facets`, `facets.py:248`; fielded parser with 30+ fields) | No API wrapper for facets; search is single text input with scope toggle only |
| Watcher/refresh status | Yes (`get_watcher_status()`, `get_refresh_status()` exist) | No HTTP endpoints wired; no frontend exposure possible |
| TanStack Vue Table for metadata/admin | Installed (v8.21.3) | Not used in any runtime component |
| TanStack Vue Form for advanced search/settings | Installed (v1.33.0) | Not used in any runtime component |

### Why a frontend control/visibility layer is needed

DT/Immich-style background jobs (indexing, watcher, search caching) require user-visible status and progress. Without it:
- Users cannot tell if indexing is running, complete, or failed.
- The powerful fielded search parser exists but has no discoverable search UI.
- Facets data is computed on the backend but never presented to users.
- The TanStack Table/Form foundations are installed but unused, while ideal use cases exist.

### Where TanStack Table/Form fit

- **TanStack Vue Form**: Strong fit for AdvancedSearchDrawer (fielded search with validation, Apply/Cancel/Reset), future SettingsModal expansion (indexing/watcher settings), and future Batch Metadata Editor.
- **TanStack Vue Table**: Strong fit for metadata admin table, index error/job table, audit/diagnostics table, duplicate/broken image finder tables.
- **Neither should be used** for: main GalleryGrid (photo browsing), simple search input, toast, or lightbox metadata panel.

### Which shadcn-vue patterns should be adapted

- **Command palette pattern** for search/quick-command UX.
- **Dialog** for desktop settings/modal structure.
- **Drawer/Sheet** for mobile settings, mobile advanced search, and mobile index panel are future-only patterns, explicitly excluded from Phase 1. Phase 1 may only adapt desktop-safe Badge + Popover/Dialog patterns.
- **Popover** for index status details, filter mini-panels.
- **DropdownMenu** for search scope and toolbar actions.
- **Data Table** for metadata/audit/admin tables.
- **Form** layout (Label/Description/Error pattern) for advanced search and batch edit.
- **Badge** for indexing/error/facet states.
- **Tabs** for settings sections and admin panel sections.

### Current strategy: PC-first Phase 1

Phase 1 is desktop/PC-only. The previous attempt proved that wiring new status UI into mobile/tablet headers is too risky without a dedicated mobile/tablet design. Therefore, Phase 1 must only improve desktop visibility and desktop UI structure.

Mobile and tablet layouts are frozen during Phase 1.

---

### Mobile/Tablet Freeze for Phase 1

During Phase 1, these files and behaviors are out of scope:
- MobileHeader.vue
- TabletHeader.vue
- MobileLayout.vue
- TabletLayout.vue
- mobile bottom navigation
- mobile search
- mobile sort
- mobile theme toggle
- mobile/sidebar hamburger behavior
- tablet header actions
- tablet breadcrumb/header layout
- mobile/tablet lightbox behavior
- mobile/tablet sheet behavior

Phase 1 must not:
- add IndexStatusChip to mobile header
- add IndexStatusChip to tablet header
- reorder mobile/tablet buttons
- change mobile/tablet header CSS
- change mobile/tablet layout breakpoints
- change mobile/tablet event emit chains
- change mobile/tablet theme toggle behavior

Any mobile/tablet change requires:
1. a separate design spec
2. explicit approval
3. real iPhone Safari test
4. real iPad/tablet test
5. rollback plan

---

## 2. Current Backend Capabilities vs Frontend UX Coverage

| Capability | Backend Status | Frontend API Wrapper | Frontend UI | Gap | Priority |
|---|---|---|---|---|---|
| Background metadata indexing | Complete (`indexer.py`, 607 lines) | **Missing** — no `fetchIndexStatus()` | **Missing** — no status chip/panel | Backend capability exists, frontend UX missing | P1 (Phase 1) |
| Index status (`/api/index/status`) | Complete (`indexer.py:599`) | **Missing** | **Missing** — referenced only in debug `reloadMonitor.ts:163` | Full gap | P1 (Phase 1) |
| Facets (`/api/facets`) | Complete (`facets.py:248`, 8 facet types) | **Missing** — no `fetchFacets()` | **Missing** — no facet chips, filter UI, or suggestion dropdowns | Full gap | Phase 1: add/verify API wrappers, frontend types, query keys, and composables. Phase 2: expose visible facets UI, filter chips, and AdvancedSearchDrawer integration. |
| Fielded search parser | Complete (`fielded_search_parser.py`, 30+ field types) | Partial — `unifiedSearch()` supports `scope` but no fielded search API wrapper | **Missing** — no AdvancedSearchDrawer, no filter chips, no field autocomplete | Backend is ready, frontend has basic text search only | P1 (Phase 2) |
| Warm indexed folder listing | Complete (`scan.py` returns `index_source`) | Partial — `scanDirectory()` does not distinguish source | **Missing** — no visual indicator of warm vs direct scan source | Low priority (transparent optimization) | P3 |
| Watcher | Watcher module implemented (`watcher.py:191`); HTTP route missing | **Missing** — no HTTP route for watcher status | **Missing** — frontend UI blocked until route exists | Both sides need work; watcher is P3 | P3 |
| Scheduled refresh | Refresh module implemented (`refresh.py:150`); HTTP route missing | **Missing** — no HTTP route for refresh status | **Missing** — frontend UI blocked until route exists | Both sides need work; refresh is P3 | P3 |
| Metadata extraction | Complete (`metadata_extract.py`, 5+ tools) | Complete — `fetchMetadata()` exists (`api.ts:179`) | **Complete** — lightbox panels display metadata well | No gap | N/A |
| `/api/health` | Complete (`health.py:23`) | **Missing** — no `fetchHealth()` | **Missing** — not displayed in UI | Low priority; backend status is adequate | P3 |
| `/api/search-metadata` (legacy) | Complete (`search.py:17`) | Not used — unified search replaced it | Not needed | No gap | N/A |
| Duplicate/broken image handling | **Missing** — no duplicate detection endpoint | **Missing** | **Missing** | Backend prerequisite | Future |
| Audit/diagnostics endpoint | **Missing** — no unified `/api/diagnostics` | **Missing** | **Missing** | Backend prerequisite | Future |

### Key Gap: Watcher/Refresh Status Endpoints

`get_watcher_status()` (`watcher.py:191`) and `get_refresh_status()` (`refresh.py:150`) are implemented at the Python module level but not wired to any HTTP route in `app.py`. These need backend API routes before any frontend UI can be built. Treat as Phase 3 prerequisite.

---

## 3. API & Type Contract Checklist

Purpose: Make it clear what backend endpoints and frontend types/composables must exist before UI implementation. Frontend should not invent a new payload shape when an existing backend contract already exists.

| Endpoint | Frontend Type | API Wrapper | Query/Composable | Notes |
|---|---|---|---|---|
| `/api/index/status` | `IndexStatusResponse` | `fetchIndexStatus()` | `useIndexStatusQuery()` | Backend complete at `indexer.py:599` |
| `/api/facets` | `FacetsResponse` | `fetchFacets()` | `useFacetsQuery()` | Backend complete at `facets.py:248` |
| `/api/search` | Existing `unifiedSearch()` contract | `unifiedSearch()` | Existing query composable | Current contract: `q`, `scope`, `path`, `limit`. Fielded search is parsed server-side from the `q` string. Advanced Search should serialize form state into backend-compatible `q`. |
| `/api/scan` | `ScanResponse` (add/check `index_source?: "warm_db" \| "direct_scan" \| "mixed"` if backend returns it) | `scanDirectory()` | Existing scan composable | Backend returns `index_source`; frontend type should reflect it if available. |

Frontend should not invent a new payload shape when an existing backend contract already exists.

---

## 4. Current Frontend Component Audit

| Component | Current Role | Problems/Gaps | shadcn-vue Pattern to Learn | Recommendation | Phase 1 Constraint |
|---|---|---|---|---|---|
| **AppHeader + Search** (`AppHeader.vue`) | Desktop header with brand, theme toggle, search box + scope selector | Search is single text input; no fielded search, no facet chips, no advanced search trigger. Scope selector is a native `<select>`. | Command palette (search suggestions), Popover (scope/field selector), Badge (fielded search chips) | **Phase 1: allowed** — Add IndexStatusChip and desktop panel/popover. Must not affect mobile/tablet. Keep native `<select>` for scope in Phase 1. | Add IndexStatusChip only. No mobile/tablet impact. |
| **MobileHeader** (`MobileHeader.vue`) | Mobile top bar with expandable search, sort popover, theme toggle | Same search limitations as desktop. Search overlay has no fielded mode. | Command (mobile search palette), Sheet (advanced search drawer on mobile) | **Phase 1: frozen** — No changes. No IndexStatusChip. No status panel. No button reorder. | Frozen. No changes. |
| **TabletHeader** (`TabletHeader.vue`) | Tablet top bar | Scope selector, theme toggle, search. | — | **Phase 1: frozen** — No changes. No IndexStatusChip. No status panel. No layout changes. | Frozen. No changes. |
| **SettingsModal** (`SettingsModal.vue`) | Application settings: intro screen mode, theme selection, original-image toggle | No Footer (auto-saves silently). No tabs (flat vertical scroll). No ARIA dialog roles (`role="dialog"`, `aria-modal` missing). Error state is console-only. | Dialog (Header/Body/Footer structure), Tabs (settings sections), Form layout (Label/Description pattern) | **Phase 1: desktop-safe ARIA/structure only** — No mobile behavior changes. Add Header/Body/Footer with Done/Close button. Add ARIA roles. Keep current auto-save behavior (watcher/localStorage). | Desktop-safe ARIA/structure only. No mobile behavior changes. |
| **RootPathSheet** (`RootPathSheet.vue`) | Bottom sheet for editing root folder path on mobile | No loading state during path load. Missing ARIA dialog roles. Paste button hides when textarea focused (discoverability). | Sheet (Header/Description/Footer pattern) | **Phase 1: avoid unless change is proven desktop-safe** — Add loading spinner. Add ARIA roles. Keep functional layout. | Avoid unless proven desktop-safe. |
| **Lightbox + Metadata Panel** (`Lightbox.vue`, `LightboxDesktopPanel.vue`, `LightboxMobileSheet.vue`, `LightboxTabletPanel.vue`) | Device-adaptive image viewer with metadata display | Desktop panel lacks `role="complementary"`. Mobile sheet tabs lack `role="tablist"`/`role="tab"`/`aria-selected`. Metadata display itself is well-built with sections, copy buttons, LoRA highlighting. | Tabs (mobile metadata tabs ARIA roles), Sheet (mobile panel structure) | **Keep as-is with light accessibility fixes**. Metadata panels are mature and should not be rewritten. Add ARIA roles for tabs and complementary landmark. | Lightbox behavior frozen for mobile/tablet. |
| **Toast** (`ToastContainer.vue`, `ToastItem.vue`) | Fixed-position toast notifications with TransitionGroup | No `role="alert"` or `aria-live` for screen reader announcements. No toast queue overflow beyond capping at 3. | Toast/Sonner pattern (position, stacking, dismiss) | **Keep as-is**. Toast system is mature and styled per gallery theme. Add `role="alert"` to ToastItem. | Desktop-safe ARIA only. |
| **GalleryGrid** (`GalleryGrid.vue`) | Primary content display: virtualized photo grid, infinite scroll, search results, toolbar | Search results rendering is adequate. No filter chips for active fielded search. Sort/density triggers lack `aria-haspopup`/`aria-expanded` (except density). Error banner lacks `role="alert"`. No `aria-live` for search results. | Data Table toolbar pattern (for sort/density/filter controls), Badge/Alert (error states) | **Phase 1: frozen for behavior/layout/virtualization/image loading** — Do NOT use TanStack Table. `role="alert"` on error banner is desktop-safe only if it does not change mobile behavior. | Frozen for behavior/layout/virtualization/image loading. |
| **FolderTreeItem** (`FolderTreeItem.vue`) | Recursive folder tree with keyboard navigation | Missing proper TreeView ARIA roles (`role="tree"`, `role="treeitem"`, `aria-expanded`, `aria-selected`). | TreeView widget pattern from WAI-ARIA | **Refactor ARIA**: Add TreeView roles. Keep existing keyboard navigation. | Desktop-safe ARIA only. |
| **EmptyState** (`EmptyState.vue`) | Generic empty/error/loading state with 7 types | SVGs lack `role="img"`/`aria-label`. Loading type lacks `aria-busy`. | N/A (custom component) | **Keep as-is**. Light accessibility improvements only. | Desktop-safe ARIA only. |
| **Future: IndexStatusChip** | Does not exist | — | Badge + Popover pattern | **Phase 1: desktop-only** — Must not be imported by MobileHeader or TabletHeader. | Desktop-only. No mobile/tablet import. |
| **Future: IndexStatusPanel** | Does not exist | — | Popover/Sheet pattern for details | **Phase 1: desktop-only** — Must not open as mobile sheet in Phase 1. | Desktop-only. No mobile sheet. |
| **Future: AdvancedSearchDrawer** | Does not exist | — | Sheet (mobile) / Side Sheet (desktop), Form (TanStack), Command palette | **Add new component**. See Phase 2. | Phase 2. |
| **Future: SearchFilterChips** | Does not exist | — | Badge (removable chips) | **Add new component**. See Phase 2. | Phase 2. |
| **Future: MetadataTable/MetadataAdminView** | Does not exist | — | Data Table (TanStack Table) | **Add new component**. See Phase 3. | Phase 3. |

---

## 5. TanStack Vue Form Decision Matrix

| Candidate | Use Form? | Why | Why Not | Phase |
|---|---|---|---|---|
| **AdvancedSearchDrawer** | **YES** | Complex form with multiple field types (text, number, select, boolean), field validation (numeric ranges, valid dimensions), dirty state tracking, Apply/Cancel/Reset behavior. Backend already supports 30+ fielded search predicates. | — | Phase 2 |
| **SettingsModal** (future: indexing/watcher config) | **YES (conditional)** | If indexing/watcher/refresh configuration (thresholds, intervals, enabled/disabled toggles) is added, switch to staged draft state with Apply/Cancel/Reset. TanStack Form can then provide validation, dirty state tracking, and explicit save behavior. **Apply/Cancel/Reset require staged draft state. They should not be mixed with the current auto-save watcher model.** | Current content (3 options) uses auto-save via watcher/localStorage. This is correct for simple toggles and should be preserved in Phase 1 with a Done/Close footer. | Phase 3 (only if config grows) |
| **Index/Watcher Settings** | **YES** | Numeric thresholds (worker count, batch size, debounce seconds), boolean toggles (enable/disable), path lists (watch roots). This is a configuration form with validation needs. | Backend watcher/refresh status routes don't exist yet. | Phase 3 |
| **Batch Metadata Editor** | **YES** | Strongest use case: editing metadata fields across multiple selected images. Validation, dirty per-field tracking, Apply/Cancel across batch. | Requires table row selection + backend batch-update endpoint (neither exists). | Phase 3+ |
| **Metadata Edit Form** (single image) | **YES** | If editable metadata fields are added, TanStack Form provides validation and dirty/save patterns. | Single-image metadata editing is a future feature. Current metadata is read-only. | Phase 3+ |
| **RootPathSheet** | **NO** | Single text field with path validation. Simple v-model with inline validation message is sufficient. | TanStack Form would add overhead without clear value. No dirty/save complexity. | Never |
| **Simple Search Input** | **NO** | Single text field with debounce. No validation needed beyond non-empty check. Dirty/Action/Cancel would harm the instant-search UX. | TanStack Form's state management would interfere with debounced instant search and clear UX. | Never |
| **SettingsModal** (current scope) | **NO** | Only 3 options (intro mode, theme, alwaysLoadOriginal). All auto-save via watcher to localStorage. No complex validation. Apply/Cancel/Reset would be incompatible UX with the auto-save watcher model. | Form overhead is not justified for current content. Footer should use Done/Close, not Apply/Cancel. Revisit if settings expand with indexing/watcher config in Phase 3. | Not now |

### Mandatory Conclusions

- **Simple search input should NOT use TanStack Form.** It is a single, debounced text field. Instant-search UX is incompatible with Form's dirty/Apply/Cancel model.
- **Advanced Search SHOULD use TanStack Form.** It is a complex form with validation, multiple field types, dirty state, and explicit Apply/Cancel/Reset. This is the canonical TanStack Form use case.
- **Current SettingsModal is too small for TanStack Form.** Keep the auto-save watcher model and use a Done/Close footer. If settings later grow into complex multi-section configuration (indexing/watcher/cache/debug), switch to staged draft state with Apply/Cancel/Reset and introduce TanStack Form at that point. Apply/Cancel/Reset require staged draft state — they should not be mixed with the current auto-save watcher model.
- **Batch Metadata Editor is a strong TanStack Form use case**, but it requires table row selection (TanStack Table) + backend batch-update endpoint. This is a Phase 3+ combined workflow.

---

## 6. TanStack Vue Table Decision Matrix

| Candidate | Use Table? | Why | Why Not | Phase |
|---|---|---|---|---|
| **MetadataAdminTable** | **YES** | Sorted/filtered metadata view with columns: thumbnail, name, folder, model, sampler, seed, dimensions, modified, match_type, actions. TanStack Table provides sorting, column visibility, row selection, and pagination. This is exactly what TanStack Table is designed for. | — | Phase 3 |
| **Index Job/Error Table** | **YES** | List of indexing jobs with columns: path, status, attempts, error, timestamps. Sorting by status/date, filtering by status. Data from `/api/index/status` (needs expansion for row-level data). | Backend endpoint currently returns counts only, not per-job rows. Needs backend expansion first. | Phase 3 (backend prerequisite) |
| **Audit Dashboard Table** | **YES** | Unified diagnostics table covering index status, watcher status, refresh status, cache stats. | No unified backend diagnostics endpoint exists. Backend prerequisite. | Phase 3+ (backend prerequisite) |
| **Duplicate Finder Table** | **YES** | Side-by-side comparison of suspected duplicates with path, dimensions, checksum, match score, actions. | No backend duplicate detection exists. Backend prerequisite. | Future (backend prerequisite) |
| **Broken Image Table** | **YES** | List of files with missing thumbnails, parse errors, or inaccessible paths. Sortable by error type. | No backend broken-image scan endpoint exists. Backend prerequisite. | Future (backend prerequisite) |
| **Facets Table** | **NO** | Facets are better rendered as chips/tokens with counts, not as a table. A table would waste space on what is essentially a filter UI. | Use Badge/Popover pattern for facets, not TanStack Table. | Never |
| **Main GalleryGrid** | **NO (hard rule)** | GalleryGrid is a visual photo browsing experience using TanStack Virtual and CSS Grid. It shows image thumbnails, not tabular data. | TanStack Table would replace thumbnails with text rows, destroy the visual browsing experience, and conflict with virtual scrolling architecture. | Never |

### Mandatory Conclusions

- **Main GalleryGrid MUST NOT use TanStack Table.** It is a visual photo browser, not a data table. TanStack Virtual is the correct technology for this component.
- **Metadata/Admin/Audit views are strong TanStack Table use cases.** They display structured data with sortable/filterable columns, exactly what TanStack Table provides.
- **Table row selection + TanStack Form batch actions should be treated as a major Phase 3+ workflow.** Selecting rows in a TanStack Table and applying batch edits via a TanStack Form is the strongest combined use case for both libraries.

---

## 7. shadcn-vue Pattern Mapping

| shadcn-vue Pattern | Gallery Use Case | Adaptation Approach |
|---|---|---|
| **Command** | Search suggestions, quick command palette (e.g., "Go to folder...", "Search by model...") | Adapt the keyboard-navigable list + filter pattern. Use gallery's existing warm-latte theme tokens instead of shadcn defaults. Bind to existing search store and folder navigation. |
| **Dialog** | Desktop SettingsModal, Index Status detail view | Refactor SettingsModal to use Header/Body/Footer structure with proper ARIA roles (`role="dialog"`, `aria-modal`, `aria-labelledby`). A search filter panel with form fields (Advanced Search on desktop) should use a Side Sheet, not a Dialog per MD3. |
| **Drawer / Sheet** | Mobile Settings (sheet), Advanced Search (mobile: bottom sheet; desktop: side sheet), Index Status (mobile), RootPathSheet | Existing `RootPathSheet` already has sheet-like behavior. Standardize the Header/Description/Footer pattern. Use existing VSBS for metadata sheet; do not replace it. New sheets (advanced search, index panel) should follow the same structure. **Future-only. All mobile/tablet Drawer/Sheet uses excluded from Phase 1.** |
| **Popover** | Index status details (click chip to see queue counts), search scope selector (future: Phase 2, if scope options expand beyond simple "This folder"/"All indexed"), field help tooltips | Keep native `<select>` for scope in Phase 1. Replace with Popover/DropdownMenu only in Phase 2 if scope options grow. Keep popovers compact and non-modal. |
| **DropdownMenu** | Search scope, sort options, density grid options, toolbar actions menu | Current custom dropdowns (sort, density) already function well. Adapt them to DropdownMenu pattern for consistency: keyboard navigation, `aria-haspopup`/`aria-expanded`, focus management. |
| **Data Table** | MetadataAdminTable, IndexJobTable, AuditTable, DuplicateFinderTable | Use TanStack Table with gallery-themed styling. Columns: thumbnail, name, folder, model, sampler, seed, dimensions, modified, actions. Sorting, filtering, column visibility, row selection. Match the gallery warm-latte color palette, not shadcn defaults. |
| **Form** | AdvancedSearchDrawer, future batch editor, expanded SettingsModal | TanStack Form with gallery form layout: field label, description, error message, Apply/Cancel/Reset buttons. Use gallery form tokens for spacing, borders, and focus states. |
| **Badge** | Index status (idle/active/queued/failed/disabled), facet chips, fielded search filter chips, error counts | Adapt Badge variants with gallery semantic colors. Removeable badge pattern for filter chips (x button to clear). |
| **Alert** | Indexing errors, scan errors, metadata parse warnings | Existing error banner in GalleryGrid and toast system already cover this. Enhance with Alert pattern: icon + title + description + dismiss. Keep gallery toast styling. |
| **Tabs** | Settings sections (General / Indexing / Watcher), admin panel sections, mobile metadata tabs (ARIA already needed) | Existing mobile metadata tabs need `role="tablist"`/`role="tab"`/`aria-selected`. SettingsModal should add Tabs if indexing/watcher config is added. Use gallery token styling. |
| **Toast / Sonner** | Existing toast system | Keep current toast implementation. It already handles positioning, stacking, dismiss, and types. Add `role="alert"` to ToastItem for accessibility. |

### Key Principle

**Do not blindly copy shadcn-vue code.** The gallery has an established SCSS/warm-latte/premium design language with `--gallery-*` CSS custom properties. Adapt patterns to use these tokens rather than replacing the theme system. The shadcn-vue patterns are valuable for structure, accessibility, and keyboard behavior — the visual styling should remain gallery-native.

---

## 8. Implementation Phases

---

### Phase 1 — Desktop visibility & UI standardization foundation

**Goal:** Expose background indexing/search readiness to desktop users and standardize existing desktop UI structure without large rewrites.

**Why:** The previous attempt proved that wiring new status UI into mobile/tablet headers is too risky without a dedicated mobile/tablet design. Phase 1 is desktop-only. Mobile and tablet layouts are frozen.

**Allowed in Phase 1:**
- Desktop AppHeader index status visibility
- Desktop-only IndexStatusChip
- Desktop-only IndexStatusPanel / Popover
- Desktop AppHeader placement only
- Desktop SettingsModal ARIA cleanup if it does not affect mobile runtime
- Desktop RootPathSheet/dialog structure cleanup only if it does not affect mobile runtime
- API wrappers/types/query keys/composables required by desktop UI
- Data-layer only facets wrapper, with no visible mobile/tablet UI

**Not allowed in Phase 1:**
- No MobileHeader changes
- No TabletHeader changes
- No mobile/tablet status chip
- No mobile/tablet panel/sheet wiring
- No mobile/tablet ARIA refactor unless proven desktop-only
- No GalleryGrid behavior/layout/virtualization/image loading changes
- No search/sort/theme/sidebar mobile changes

**shadcn-vue adaptation in Phase 1 means:**
- Badge-like desktop status chip
- Popover/Dialog-like desktop detail panel
- Header/Body/Footer structure
- ARIA/focus behavior where safe

**It does not mean:**
- shadcn rewrite
- Tailwind adoption
- mobile/tablet sheet adoption
- replacing existing mobile/tablet components

#### Preflight Checklist before Phase 1

This is a preflight checklist, not a fourth implementation phase.

- [ ] Verify `/api/index/status` response shape against frontend type.
- [ ] Verify `/api/facets` response shape against frontend type.
- [ ] Verify frontend types for index status and facets are defined or document gaps.
- [ ] Verify `ScanResponse.index_source` if backend returns it.
- [ ] Confirm Advanced Search will serialize to `q` and call existing `unifiedSearch()`.
- [ ] Confirm no `beforeunload`/`unload` lifecycle regression is introduced.
- [ ] Confirm Phase 1 does not change GalleryGrid behavior, layout, virtualization, image loading, or browsing semantics. Only small accessibility annotations or non-behavioral wiring are allowed if needed.

---

#### Phase 1A — Desktop data layer

- [ ] IndexStatusResponse, FacetsResponse, IndexStatusState types
- [ ] `queryKeys.indexStatus(path)`, `queryKeys.facets(path)`
- [ ] `fetchIndexStatus(path)`, `fetchFacets(path)` in `api.ts`
- [ ] `useIndexStatusQuery(path, enabled)` composable
- [ ] `useFacetsQuery(path, enabled)` composable

Rules:
- no mobile/tablet consumption
- no visible mobile/tablet UI
- no global behavior changes

---

#### Phase 1B — Desktop index status UI

- [ ] Desktop AppHeader-only IndexStatusChip
- [ ] Desktop-only IndexStatusPanel
- [ ] Use Badge + Popover/Dialog pattern inspired by shadcn-vue
- [ ] Adaptive polling: fast only when active/queued work exists; failed-only/no moving work slow-polls; unavailable/error visible but not noisy
- [ ] No MobileHeader/TabletHeader imports

**Tasks:**

- [ ] **Add `fetchIndexStatus()` to `api.ts`** — wraps `GET /api/index/status?path=...`. Response includes: `enabled`, `worker_count`, `active_jobs`, `runtime_queue_depth`, counts by state, `last_error`, `updated_at`.
- [ ] **Add `useIndexStatusQuery()` composable** — TanStack Query wrapper with `queryKeys.indexStatus(path)`. Adaptive polling per Section 10 policy: fast 2-3s only when active/queued work exists; failed-only with no work slow-polls at 60s; unavailable/error slow-polls at 60s. Browser tab hidden: pause or slow down. Window focus: local debounced refetch. No beforeunload/unload listeners. Enabled only when a folder is loaded.
- [ ] **Add query key `indexStatus(path)` in `query/keys.ts`**.
- [ ] **Add `IndexStatusChip.vue`** — small badge in AppHeader (desktop only) near search area. Shows one of four states:
  - `failed` — `failed > 0 || staged_path_failed > 0 || last_error` (red badge with error icon)
  - `active` — workers are running (amber/yellow badge with pulse animation)
  - `queued` — jobs are pending (blue badge)
  - `idle` — no errors, no active jobs, no queued jobs; up-to-date (compact muted chip or muted icon/text)
  - `disabled` — no folder loaded or status unavailable (hidden)
  - **State mapping**:
    ```
    failed = failed > 0 || staged_path_failed > 0 || last_error
    active = running > 0 || active_jobs > 0 || active_scan_requests > 0
    queued = queued > 0 || runtime_queue_depth > 0 || staged_path_queue_depth > 0
    idle = !failed && !active && !queued
    ```
  - **UI behavior**: Click chip opens IndexStatusPanel (popover on desktop). **Do NOT auto-hide when idle.** Idle/up-to-date state collapses into a muted status (compact chip or muted icon) — not disappear completely. Indexing status should be quiet but discoverable. Active/error states should be obvious. Disabled/no-folder state is hidden. Never blocks interaction. Never creates toast spam.
  - **Phase 1 constraint**: Must not be imported by MobileHeader or TabletHeader.
- [ ] **Add `IndexStatusPanel.vue`** — detailed index status shown on chip click. Shows:
  - Summary line: "Indexing — X queued, Y active, Z done" (using queued/running/done/failed counts that the backend actually returns; there is no total file count from `/api/index/status`)
  - Per-state counts: queued, running, done, failed, stale, skipped
  - Last error text (if any)
  - Worker count and queue depth
  - **Progress indicator**: `LinearProgressIndicator` (determinate when running/done counts allow percentage computation, indeterminate otherwise) or compact `CircularProgressIndicator` to satisfy MD3 requirement for visible progress on background operations. Show in IndexStatusPanel; may also appear as a subtle indicator on IndexStatusChip when in active state.
  - **Desktop**: Popover anchored to chip
  - **Not allowed in Phase 1**: Mobile bottom sheet following RootPathSheet-style structure
  - **No blocking overlay, no toast per job**
- [ ] **Add `fetchFacets()` to `api.ts`** — wraps `GET /api/facets?path=...`. Response includes `tool`, `model`, `sampler`, `scheduler`, `orientation`, `seed_availability`, `metadata_availability`, `lora`, `folders`. Backend endpoint confirmed at `facets.py:248`.
- [ ] **Add `useFacetsQuery()` composable** — TanStack Query wrapper with `queryKeys.facets(path)`. Long staleTime (5min) since facets change slowly. Phase 1 prepares the facets data layer only. Visible facets UI belongs to Phase 2.

---

#### Phase 1C — Desktop-safe UI standardization

- [ ] Desktop-safe dialog/header/body/footer cleanup
- [ ] Desktop-safe ARIA only
- [ ] No mobile/tablet runtime changes

**Tasks:**

- [ ] **Refactor SettingsModal structure** — add formal Header/Body/Footer sections:
  - **Header**: Title "Settings" + Close button
  - **Body**: Scrollable content area (current settings)
  - **Footer**: "Done" or "Close" button. **Do NOT use Apply/Cancel.** Settings auto-save immediately via existing watcher/localStorage behavior; there is no staged draft state to apply or cancel.
  - Add `role="dialog"`, `aria-modal="true"`, `aria-labelledby` referencing title element.
  - Do NOT add tabs yet; keep flat layout until more settings are added.
  - Do NOT migrate to TanStack Form in Phase 1; the current auto-save watcher model is correct and TanStack Form's dirty/Apply/Cancel/Reset lifecycle would conflict.
  - Phase 1 constraint: Desktop-safe ARIA/structure only. No mobile behavior changes.
- [ ] **RootPathSheet refactor** — Deferred to future Mobile/Tablet Spec. NOT in Phase 1.
  - **Header**: "Edit Root Path" title + FolderOpen icon
  - **Description**: Brief explanation text
  - **Body**: Textarea + error message
  - **Footer**: Action buttons (Clear, Cancel, Load)
  - Add loading spinner during `setRootPath` resolution
  - Add `role="dialog"`, `aria-modal` for iOS VoiceOver
  - Phase 1 constraint: Avoid unless change is proven desktop-safe.
- [ ] **Keep native search scope `<select>` as-is in Phase 1** — the current native select with simple options ("This folder", "All indexed") is simple, accessible, low-risk, and sufficient for Phase 1. **Do not replace the native search scope selector just for visual consistency. Replace it only when the interaction model grows beyond simple scope selection** (e.g., Advanced Search with search presets, fielded search shortcuts, facets, metadata/admin entry — Phase 2+). If scope options expand in Phase 2, consider DropdownMenu or Popover at that point.
- [ ] **Add accessibility fixes** (desktop-safe only, non-breaking):
  - ToastItem: add `role="alert"` for screen reader announcements
  - GalleryGrid error banner: add `role="alert"` (desktop-safe only)
  - FolderTreeItem: add `role="tree"`, `role="treeitem"`, `aria-expanded`
  - LightboxMobileSheet tabs: Deferred to future Mobile/Tablet Spec. NOT in Phase 1.
  - SettingsModal: add ARIA dialog roles (covered above)
  - AppHeader: add `role="banner"` landmark
- [ ] **Add tests**:
  - IndexStatusChip renders failed/active/queued/idle/disabled states
  - IndexStatusPanel shows correct counts from mock API response
  - IndexStatusPanel opens/closes on chip click
  - facets data-layer loading/error states (fetch, query key, composable); visible facets UI belongs to Phase 2
  - SettingsModal ARIA roles present
  - RootPathSheet ARIA roles present
  - No toast spam from index status (assert toast queue does not grow from index updates)
  - Existing search and GalleryGrid tests unchanged

#### Files Affected (Phase 1)

| File | Change | Phase 1 Constraint |
|---|---|---|
| `frontend/src/services/api.ts` | Add `fetchIndexStatus()`, `fetchFacets()` | Data-layer only |
| `frontend/src/query/keys.ts` | Add `indexStatus(path)`, `facets(path)` keys | Data-layer only |
| `frontend/src/composables/useIndexStatusQuery.ts` | New composable | Data-layer only |
| `frontend/src/composables/useFacetsQuery.ts` | New composable | Data-layer only, no visible UI in Phase 1 |
| `frontend/src/components/indexing/IndexStatusChip.vue` | New component | Desktop-only |
| `frontend/src/components/indexing/IndexStatusPanel.vue` | New component | Desktop-only |
| `frontend/src/components/SettingsModal.vue` | Structure refactor + ARIA | Desktop-safe only |
| `frontend/src/components/RootPathSheet.vue` | Deferred to future Mobile/Tablet Spec | Not in Phase 1 |
| `frontend/src/components/AppHeader.vue` | Add IndexStatusChip | Desktop-only. Must not affect mobile/tablet. |
| `frontend/src/components/ToastItem.vue` | Add `role="alert"` | Desktop-safe only |
| `frontend/src/components/GalleryGrid.vue` | Add `role="alert"` to error banner | Frozen for behavior/layout/virtualization |
| `frontend/src/components/FolderTreeItem.vue` | Add TreeView ARIA roles | Desktop-safe only |
| `frontend/src/components/LightboxMobileSheet.vue` | Deferred to future Mobile/Tablet Spec | Not in Phase 1 |
| `frontend/src/types/index.ts` | Add `IndexStatus`, `FacetsResponse`, `FacetEntry` types | Data-layer only |

**Not touched in Phase 1:**
- `MobileHeader.vue` — frozen
- `TabletHeader.vue` — frozen
- `MobileLayout.vue` — frozen
- `TabletLayout.vue` — frozen

#### Phase 1 Risk Assessment

- **Low risk for desktop.** This phase is purely additive for new desktop components; Phase 1 should not change GalleryGrid behavior, layout, virtualization, image loading, or browsing semantics.
- **Mobile/tablet risk is reduced** because those surfaces are frozen.
- IndexStatusChip is unobtrusive, uses muted idle state (never auto-hides), and never blocks interaction.
- SettingsModal desktop-safe refactor is structural only; behavior is preserved. RootPathSheet is deferred to a future Mobile/Tablet Spec and is not part of Phase 1.

#### Phase 1 Acceptance Criteria

**Desktop:**
- AppHeader layout remains stable
- IndexStatusChip appears only on desktop
- IndexStatusPanel opens/closes correctly
- failed/active/queued/idle/unavailable states are visible
- No noisy polling
- SettingsModal behavior unchanged except safe ARIA/structure

**Mobile (freeze verification):**
- MobileHeader unchanged from pre-Phase-1 baseline
- Hamburger visible and working
- Search visible and working
- Sort visible and working
- Theme toggle visible and working
- No IndexStatusChip in MobileHeader
- No new mobile header CSS

**Tablet (freeze verification):**
- TabletHeader unchanged from pre-Phase-1 baseline
- No IndexStatusChip in TabletHeader
- No tablet header layout changes

**Gallery:**
- GalleryGrid behavior unchanged
- Virtualization unchanged
- Image loading unchanged
- Lightbox behavior unchanged

---

### Phase 2 — Desktop advanced search first

**Goal:** Expose fielded search and facets as usable frontend UX, desktop-first.

**Why:** The backend fielded search parser supports 30+ field types and `/api/facets` provides 8 facet categories, but the frontend has zero discoverability for these capabilities. TanStack Form is justified because advanced search is a complex form with validation, dirty state, and Apply/Cancel/Reset behavior.

**Mobile/tablet constraint:** Mobile/tablet advanced search is deferred to a separate spec.

#### Tasks

- [ ] **Add `serializeAdvancedSearchToQuery()` utility** — serializes `AdvancedSearchDrawer` TanStack Form state into a backend-compatible `q` string using fielded search token syntax (e.g. `model:"PonyXL" sampler:"Euler a" seed:123 prompt:"blue archive"`). The resulting `q` string is passed to the existing `unifiedSearch(q, opts)` path. No new API wrapper is needed; no `fields[]` or `residual_text` structured payload is introduced. **Do not introduce a structured `fields[]` frontend-to-backend API unless the backend first adds and documents that contract.**
- [ ] **Add `AdvancedSearchDrawer.vue` using `@tanstack/vue-form`** — structured search form with:
  - **Text fields**: `prompt:`/`positive:`, `negative:`, `model:`, `sampler:`, `scheduler:`, `lora:`, `vae:`, `path:`/`folder:`, `name:`
  - **Numeric fields with operators**: `seed:` (=), `steps:` (=/>/>=/</<=), `cfg:` (same operators), `width:`, `height:`, `clip_skip:`, `hires_upscale:`, `hires_steps:`, `denoising_strength:`
  - **Select/autocomplete fields**: `source:`/`tool:`, `model:` (suggestions from facets), `sampler:` (suggestions from facets), `orientation:` (landscape/portrait/square), `seed_availability:` (has_seed/no_seed), `metadata_availability:` (has_metadata/no_metadata)
  - **Size field**: `size:` with width×height input
  - **Aspect ratio field**: `ratio:` with common preset buttons (1:1, 4:3, 16:9, 3:2, 2:3, 9:16)
  - **Date field**: `date:` with date range picker or text input
  - **Generic fallback fields**: `param:`, `advanced:`, `raw:` (text inputs for advanced users)
  - **Form actions**: Apply (executes search), Cancel (closes drawer, restores previous search), Reset (clears all fields)

- [ ] **Use TanStack Form features**:
  - **Validation**: numeric fields must be valid numbers, dimensions must be positive, ratio format must be valid
  - **Dirty state**: Apply button enabled only when form is dirty
  - **Apply/Cancel/Reset**: Cancel restores previous search state; Reset clears all fields
  - **Initial values**: populate from current search state (if user previously searched with fielded query)

- [ ] **Build query strings compatible with existing backend parser**:
  - `serializeAdvancedSearchToQuery()` converts form state into a properly formatted `q` string using the same token syntax the backend fielded-search parser already understands (e.g. `txt model:"PonyXL" sampler:"Euler a" seed:123 prompt:"blue archive"`)
  - The serializer must produce query strings that match the format tested in `fielded_search_parser.py`
  - The output `q` string is passed directly to the existing `unifiedSearch(q, opts)` — no new API payload or endpoint is required
  - Keep the plain-text search path completely unchanged; plain-text queries continue to use `unifiedSearch(q, opts)` without any serialization step

- [ ] **Add `SearchFilterChips.vue`** — shows active fielded search filters as removable badges below the search bar:
  - Each chip shows "field: value" (e.g., "model: realistic", "seed: 12345")
  - X button removes individual filter
  - "Clear All" button when multiple filters are active
  - Styled as gallery Badge variant with warm-latte tokens
  - Displays when fielded search is active (in both plain search and advanced search modes)
  - Phase 2 constraint: Desktop-first. Mobile/tablet filter chips deferred.

- [ ] **Desktop responsive behavior**:
  - **Desktop**: AdvancedSearchDrawer opens as a right-side drawer/slide-over panel (similar to sidebar pattern). Animation: slide in from right.

- [ ] **Add command/palette pattern** (light, optional):
  - Cmd+K (desktop) or tap search icon (mobile) opens a quick search palette
  - Palette shows: recent searches, common field shortcuts, "Advanced search..." entry point
  - Adapts shadcn-vue Command pattern using gallery tokens

- [ ] **Reuse existing `queryKeys.search(q, scope, path)`** — Advanced Search produces a normal backend-compatible `q` string and must reuse the existing `unifiedSearch()` path and `queryKeys.search(q, scope, path)`. Do not create a separate fielded-search cache path unless the backend/API contract changes.

- [ ] **Add tests**:
  - AdvancedSearchDrawer renders all field groups
  - TanStack Form validation: invalid numbers show error
  - Dirty state: Apply enabled only when dirty
  - Apply/Cancel/Reset behavior correct
  - Field serialization matches backend parser format
  - SearchFilterChips render active filters
  - Chip removal updates search and clears filter
  - "Clear All" removes all fielded filters
  - Plain text search regression (no fielded search) still works
  - Desktop drawer opens/closes correctly

#### Files Affected (Phase 2)

| File | Change |
|---|---|
| `frontend/src/utils/serializeAdvancedSearchToQuery.ts` | New utility (serialize form → q string) |
| `frontend/src/components/search/AdvancedSearchDrawer.vue` | New component (TanStack Form) |
| `frontend/src/components/search/SearchFilterChips.vue` | New component |
| `frontend/src/components/search/SearchCommandPalette.vue` | New component (optional, light) |
| `frontend/src/components/AppHeader.vue` | Add Advanced Search trigger button, SearchFilterChips (desktop) |
| `frontend/src/components/GalleryGrid.vue` | Integrate SearchFilterChips near the search/results context. Must not alter GalleryGrid virtualization or photo browsing behavior. |
| `frontend/src/types/index.ts` | Add `FieldedSearchParams`, `FieldFilter` types |

**Not touched in Phase 2:**
- `MobileHeader.vue` — advanced search entry point deferred to separate spec
- `TabletHeader.vue` — advanced search entry point deferred to separate spec

#### Risk Assessment (Phase 2)

- **Medium risk.** TanStack Form integration is new territory. The form serialization must match the backend parser format exactly.
- Mitigation: build query serialization tests first, validate against known-good backend query examples. Keep plain search path fully isolated.
- Plain text search must not regress. The AdvancedSearchDrawer is an opt-in extension; default search behavior is unchanged.

#### Acceptance Criteria (Phase 2)

1. AdvancedSearchDrawer opens with structured form fields
2. TanStack Form validation catches invalid numeric/format entries
3. Apply executes fielded search against backend; Cancel restores previous state; Reset clears all
4. SearchFilterChips appear when fielded search is active
5. Removing a chip updates the active search and removes the filter
6. Plain text search (no fielded search) behavior is unchanged
7. Desktop drawer slides from right
8. All existing search and gallery tests pass
9. New tests pass (form validation, Apply/Cancel/Reset, chip removal, serialization)

---

### Phase 3 — Desktop metadata/admin cockpit

**Goal:** Use TanStack Table in the right places: admin, metadata, audit, and diagnostics — not photo browsing.

**Why:** DT/Immich both emphasize visibility into jobs/status/metadata/indexing at scale. TanStack Table is appropriate for management/audit workflows with sortable/filterable columns. Table row selection + TanStack Form batch editing is the strongest combined use case for both libraries.

**Mobile/tablet constraint:** Mobile/tablet admin view deferred to separate spec.

#### Tasks

- [ ] **Add `MetadataAdminView.vue`** — a new view/section accessible from the header or settings. Contains a table of all indexed metadata rows with filtering and sorting.
  - **Routing approach**: Since there is no vue-router, use a view-switching pattern (like the current IntroScreen vs Gallery condition). Add a "Metadata" navigation entry.
  - **Or**: Render as a slide-over panel or tabbed view within the existing layout.

- [ ] **Add `MetadataTable.vue` using `@tanstack/vue-table`** — TanStack Table with:
  - **Columns** (configurable visibility):
    - Thumbnail (small 80px inline preview)
    - Name (filename)
    - Folder (parent path, truncated with tooltip)
    - Model (with text search filter)
    - Sampler (with text search filter)
    - Seed (numeric, sortable)
    - Dimensions (width × height, sortable by area)
    - Modified (date, sortable)
    - Match Type (from search results, e.g., "prompt", "filename", "field filter")
    - Actions (open lightbox, copy path, reveal in folder)
  - **Features**:
    - Sorting (click column headers, multi-sort via shift+click)
    - Filtering (per-column text/number filters, global search across all columns)
    - Column visibility (show/hide toggle, persist to localStorage)
    - Row selection (checkbox column for batch operations)
    - Pagination (page size selector: 25/50/100)
    - Responsive: collapse less-important columns on mobile/tablet
   - **Data source (Phase 3A — read-only, no new endpoint required)**:
     - Read-only `MetadataAdminTable` can start from existing `unifiedSearch()` / indexed metadata fields.
     - No editable metadata endpoint is required for the initial read-only table.
     - Read-only admin browsing is not blocked by future editable metadata endpoints.
   - **Data source (Phase 3B / Future — needs new or extended backend endpoints)**:
     - A dedicated metadata table endpoint may be added later for all-indexed pagination at scale, server-side sorting/filtering, editable user metadata, and batch metadata workflows.
     - `/api/photos/user-metadata` is required for editing user metadata.
     - `/api/photos/batch-metadata` is required for batch metadata editing.

- [ ] **Row actions (per-row)**:
  - Open in lightbox (click thumbnail or "View" action)
  - Copy path to clipboard
  - "Reveal in folder" — navigate to the parent folder in the gallery view
  - Jump to folder if supported

- [ ] **Bulk actions foundation** (UI only, backend prerequisite):
  - Toolbar showing selected count: "X selected"
  - Batch action buttons: "Export Metadata", "Re-index Selected", "Clear Metadata Cache"
  - Row selection via checkbox column
  - "Select All" / "Deselect All" in header checkbox

- [ ] **Future: `BatchMetadataEditor.vue` using TanStack Form** (Phase 3+ or future):
  - Opens when batch action "Edit Metadata" is clicked
  - Fields match the extracted metadata schema (model, sampler, seed, etc.)
  - Apply writes changes to all selected rows
  - Requires backend batch-update endpoint (prerequisite)

- [ ] **Future tables** (backend prerequisites):
  - **IndexErrorTable**: per-job error listing. Requires backend to return per-job rows (current `/api/index/status` returns counts only).
  - **MetadataErrorTable**: parse failures with file path and error details.
  - **DuplicateFinderTable**: suspected duplicates side-by-side.
  - **BrokenImageAuditTable**: files with missing thumbnails or inaccessible paths.

- [ ] **Backend prerequisites to document** (not to implement in this phase):
  - Per-job row listing endpoint for index errors (extends `/api/index/status`)
  - Watcher/refresh status HTTP routes (wire `get_watcher_status()` and `get_refresh_status()` to API)
  - Unified `/api/diagnostics` endpoint for audit dashboard
  - Batch metadata update endpoint
  - Duplicate detection endpoint
  - Broken image scan endpoint

- [ ] **Add tests**:
  - MetadataTable renders columns with correct data
  - Sorting by column works (ascending/descending)
  - Column filtering works (text and numeric)
  - Column visibility toggle shows/hides columns
  - Row selection toggles individual and all rows
  - Row actions (open lightbox, copy path) function
  - Pagination shows correct page size and navigates pages
  - Responsive: columns collapse on mobile/tablet
  - GalleryGrid unchanged (regression)

#### Files Affected (Phase 3)

| File | Change |
|---|---|
| `frontend/src/components/admin/MetadataTable.vue` | New component (TanStack Table) |
| `frontend/src/views/MetadataAdminView.vue` | New view |
| `frontend/src/composables/useMetadataTableData.ts` | New composable (TanStack Query wrapper) |
| `frontend/src/services/api.ts` | Add `fetchMetadataTableData()` or extend search API |
| `frontend/src/query/keys.ts` | Add `metadataTable` key |
| `frontend/src/types/index.ts` | Add `MetadataTableRow`, `TableColumn`, `TableSort`, `TableFilter` types |
| `frontend/src/App.vue` | Add MetadataAdminView switching logic |
| `frontend/src/components/AppHeader.vue` | Add "Metadata" nav entry |

#### Risk Assessment (Phase 3)

- **Medium risk.** TanStack Table integration is the largest new dependency usage. Column configuration complexity, performance with large datasets, and responsive behavior need testing.
- Mitigation: start with a focused MetadataAdminTable for indexed metadata. Add more tables (error, audit, duplicate) incrementally in future phases.
- Backend prerequisites for many planned tables mean this phase is primarily the MetadataTable + admin view, with documentation of prerequisites for future tables.

#### Acceptance Criteria (Phase 3)

1. MetadataTable renders columns with correct data from backend
2. Sorting works on seed, dimensions, date columns
3. Text filtering works on model, sampler, name columns
4. Column visibility toggle hides/shows columns; persists to localStorage
5. Row selection works (checkbox column, select all/deselect all)
6. Row actions: open lightbox from thumbnail click, copy path
7. Pagination: page size selector and page navigation
8. GalleryGrid unchanged (regression test passes)
9. New tests pass

---

## 9. Index Status State Machine

Purpose: Define deterministic UI state mapping for `IndexStatusChip` and `IndexStatusPanel`.

Use this priority order:

```ts
failed = failed > 0 || staged_path_failed > 0 || Boolean(last_error)
active = running > 0 || active_jobs > 0 || active_scan_requests > 0
queued = queued > 0 || runtime_queue_depth > 0 || staged_path_queue_depth > 0
idle = !failed && !active && !queued
```

State priority:
1. **failed** — error affordance, visible chip, opens panel
2. **active** — "Indexing…" state, visible chip
3. **queued** — visible chip, queue count if available
4. **idle/up-to-date** — muted compact chip/icon, not fully hidden when folder/library context exists
5. **disabled** (no folder/no library context) — hidden
6. **unavailable** (API error/backend unreachable) — visible muted/error chip, distinct from disabled

UI behavior:
- **failed**: visible chip, error affordance, opens panel
- **active**: visible chip, "Indexing…" state
- **queued**: visible chip, queue count if available
- **idle/up-to-date**: muted compact chip/icon, not fully hidden when folder/library context exists
- **disabled/no folder/no status**: hidden or disabled state

Indexing status should be quiet but discoverable. Active/error states should be obvious; idle/up-to-date should collapse into a muted status, not disappear completely.

---

## 10. Index Status Polling Policy

Purpose: Avoid both noisy UI and wasteful polling.

Recommended policy:
- **active/queued** (work moving): refetch every 2-3 seconds
- **failed-only** (no active/queued work): slow-poll every 60 seconds or manual refresh only
- **unavailable/error** with no data: slow-poll every 60 seconds, do not fast-poll forever
- **idle/up-to-date**: refetch every 60 seconds or disable polling
- **browser tab hidden**: pause polling or slow it down significantly
- **window focus**: refetch once via local, debounced mechanism scoped to index status only. Do not change global TanStack Query focus behavior (keep `refetchOnWindowFocus: false`). Must not introduce `beforeunload`/`unload` listeners.
- **manual refresh/open panel**: refetch immediately
- **avoid toast spam**: status should live in chip/panel

Polling policy should be implemented with TanStack Query options, not ad-hoc timers inside UI components, unless there is a strong reason.

---

## 11. Responsive Acceptance Criteria

Purpose: Make mobile/tablet behavior explicit without forcing one rigid layout.

### Mobile
- Advanced Search should open as bottom sheet or fullscreen sheet.
- No body scroll bleed.
- No Safari viewport jump.
- Sticky footer actions when the form is long.
- Touch targets should be large enough for comfortable touch use.
- Backdrop, Escape-equivalent, close, and cancel behaviors must be predictable.

### Tablet
- Advanced Search may be side drawer, large sheet, or centered dialog depending on fit.
- Panels must not awkwardly cover the primary grid.
- Tablet should not be accidentally forced into cramped phone layout.

### Desktop
- Dialog/popover/drawer can be used depending on content size.
- Keyboard navigation and focus return should work.
- Index status panel should not obscure primary controls.

Responsive behavior should follow the app's existing gallery-first layout and avoid mobile Safari regressions.

### MD3 Surface Elevation & Motion Tokens

Reference levels for new surfaces (use existing gallery `--gallery-*` drop-shadow tokens, not raw MD3 values):
- **Side Sheet / Bottom Sheet**: Level 1 (subtle shadow, aligned with existing sheet behavior)
- **Dialog** (SettingsModal, confirmations): Level 3 (more prominent)
- **Popover** (index status details, field help): Level 4 (close to trigger element)
- **DropdownMenu**: Level 2 (intermediate between sheet and dialog)

Motion tokens for consistent animation language:
- **Sheet entry/exit**: `250ms ease-out` (slide from right for desktop side sheet, slide up for mobile bottom sheet)
- **Chip/Popover transitions**: `150ms ease` (badge state changes, popover show/hide)
- **Pulse animation** (active index state): Keep existing CSS pulse keyframes
- **Keep existing gallery transition tokens** as defaults where they already cover the behavior

---

## 12. Navigation and Entry Points

Purpose: Every planned component should have a clear way for users to open it.

| Component | Opens From |
|---|---|
| `IndexStatusPanel` | `IndexStatusChip` (click) — desktop only in Phase 1 |
| `AdvancedSearchDrawer` | Search filter button or command/search affordance |
| `SearchFilterChips` | Appears near the search bar/results context after filters are applied |
| `MetadataAdminView` | Settings/Admin entry or future command palette |
| `FacetsPanel` | Inside Advanced Search or Metadata/Admin view |
| Future audit dashboards | Metadata/Admin/Diagnostics, not from the main gallery grid |

Do not add navigation clutter just to expose every future tool. Prefer progressive disclosure.

---

## 13. Definition of Done

### Phase 1 Done when:

- [ ] `fetchIndexStatus()` is typed and tested.
- [ ] `useIndexStatusQuery()` exists and uses sane polling.
- [ ] `IndexStatusChip` shows failed/active/queued/idle correctly (desktop only).
- [ ] `IndexStatusPanel` shows useful status details (desktop only).
- [ ] `fetchFacets()` and/or `useFacetsQuery()` are typed or explicitly deferred (data-layer only).
- [ ] `SettingsModal`/`RootPathSheet` standardization does not change behavior unexpectedly.
- [ ] No indexing toast spam.
- [ ] MobileHeader unchanged from pre-Phase-1 baseline.
- [ ] TabletHeader unchanged from pre-Phase-1 baseline.
- [ ] No IndexStatusChip in MobileHeader or TabletHeader.
- [ ] Desktop smoke tests pass.
- [ ] Mobile freeze verification passes (hamburger, search, sort, theme toggle).
- [ ] Tablet freeze verification passes.
- [ ] Typecheck passes.
- [ ] GalleryGrid behavior is unchanged.

### Phase 2 Done when:

- [ ] Advanced Search uses TanStack Form only for the complex form.
- [ ] Form state serializes to backend-compatible `q`.
- [ ] Existing `unifiedSearch()` path is used.
- [ ] Plain text search still works.
- [ ] Filter chips can remove individual filters.
- [ ] Reset/Cancel/Apply behavior is clear.
- [ ] Query serializer tests pass.

### Phase 3 Done when:

- [ ] Metadata table uses TanStack Vue Table.
- [ ] GalleryGrid is not replaced by a table.
- [ ] Sorting/filtering/column visibility/row selection work.
- [ ] Row actions are useful and safe.
- [ ] Bulk action foundation is present but does not perform destructive actions without confirmation.
- [ ] Backend prerequisites are clearly documented for audit/duplicate/broken-image tables.
- [ ] Table tests pass.

---

## 14. Backend Prerequisites Backlog

Purpose: Separate frontend work that can be done now from future admin/audit work that requires backend data first. Do not ask frontend to build a real audit table before backend exposes row-level audit data.

| Possible Future Endpoint | Frontend Feature | Table/Form Usage | Not Phase 1 Unless Already Supported |
|---|---|---|---|
| `/api/diagnostics` | Audit dashboard | TanStack Table | No backend endpoint exists |
| `/api/audit/duplicates` | Duplicate finder table | TanStack Table | No backend duplicate detection |
| `/api/audit/broken-images` | Broken image table | TanStack Table | No backend broken-image scan |
| `/api/index/errors` | Per-job error table | TanStack Table | Current endpoint returns counts only |
| `/api/watcher/status` | Watcher status component | Simple display (chip/panel) | No HTTP route wired (`watcher.py:191`) |
| `/api/refresh/status` | Refresh status component | Simple display (chip/panel) | No HTTP route wired (`refresh.py:150`) |
| `/api/photos/user-metadata` | Metadata admin table | TanStack Table | A read-only MetadataAdminTable can start from existing `unifiedSearch()`/metadata index fields. Editable user metadata requires this endpoint. |
| `/api/photos/batch-metadata` | Batch metadata editor | TanStack Form | Batch metadata editing requires this backend batch-update endpoint. |

---

## 15. Risks & Non-Goals

### Risks

| Risk | Phase | Mitigation |
|---|---|---|
| IndexStatusChip becomes noisy or distracting | Phase 1 | Use muted idle state (compact muted chip/icon), not auto-hide. Pulse-only when active. Never block interaction, no toasts. Test `no-toast-spam` assertion. |
| TanStack Form serialization doesn't match backend parser | Phase 2 | Build serializer tests first. Validate against known-good query examples from `fielded_search_parser.py` tests. |
| TanStack Table performance with large datasets | Phase 3 | Server-side pagination via TanStack Query. Start with 25/50/100 page sizes. Lazy-load thumbnails only when visible. |
| Column visibility/responsive complexity on mobile | Phase 3 | Collapse non-essential columns on small screens. Keep name, model, actions visible. Provide horizontal scroll as fallback. |
| Over-engineering settings with TanStack Form too early | Phase 1/3 | Keep current v-model approach for SettingsModal in Phase 1. Only introduce TanStack Form when indexing/watcher config is added in Phase 3. |
| Breaking plain text search when adding Advanced Search | Phase 2 | Keep plain search input completely separate. AdvancedSearchDrawer is opt-in. Plain search regression tests guard this. |
| Accessibility regression from new components | All Phases | Add ARIA roles in Phase 1 accessibility fixes. New components follow the established patterns. Test with `role` assertions. |
| bfcache/lifecycle regressions on iOS Safari | All Phases | Keep global TanStack Query `refetchOnWindowFocus: false`. Index status may use a local, debounced refetch-on-focus/pageshow/visibilitychange if needed, but must not re-enable noisy global refetches. No `beforeunload`/`unload` listeners. Test mobile sheet behavior. |

**Lesson from failed Phase 1 attempt:** Mobile/tablet headers are high-risk surfaces. Even small status chips can break real iPhone Safari layout and touch behavior. Playwright/Chromium viewport tests are not enough to prove iPhone Safari safety.

Therefore, Phase 1 is desktop-only. Real-device Safari testing is mandatory before any future mobile/tablet implementation.

### Non-Goals (Explicitly Excluded)

- **Do not rewrite the whole UI into shadcn-vue.** Adapt patterns for structure, accessibility, and keyboard behavior. Keep gallery-native SCSS/warm-latte/premium theme.
- **Do not replace GalleryGrid with a table.** GalleryGrid uses TanStack Virtual for visual photo browsing. TanStack Table is for data admin only.
- **Do not add new dependencies unless clearly justified.** TanStack Table and Form are already installed. No additional Vue ecosystem packages needed.
- **Do not create indexing toast spam.** IndexStatusChip is a passive indicator. No toasts per job. Errors shown only in panel on click.
- **Do not regress mobile sheets or introduce bounce/jank.** Keep VSBS for metadata sheet; new sheets follow established patterns.
- **Do not break iOS Safari lifecycle/bfcache behavior.** No `beforeunload`/`unload` listeners. Query refetch behavior unchanged.
- **Do not move backend indexing work back into the scan hot path.** This is a frontend plan. Backend hot-path contracts are preserved.
- **Do not touch MobileHeader or TabletHeader in Phase 1.** These files are frozen.

---

## 16. Testing Plan

### Required Regression Tests (Phase 1)

**Desktop tests:**
- Desktop index chip visible
- Panel opens/closes
- Unavailable state visible on API failure
- Failed-only does not fast-poll
- Active/queued fast-polls

**Mobile freeze tests (pre- and post-Phase 1, must pass identically):**
- Hamburger visible
- Hamburger click works
- Search button visible
- Sort button visible
- Theme button visible
- Theme click changes `document.documentElement.dataset.theme`
- No IndexStatusChip in MobileHeader

**Tablet freeze tests:**
- Tablet header renders baseline actions
- No IndexStatusChip in TabletHeader

### Unit/Component Tests

| Test | Phase | Assertion |
|---|---|---|
| IndexStatusChip renders each state (failed/active/queued/idle/disabled) | Phase 1 | Correct badge text, color, and icon per state |
| IndexStatusChip shows muted idle state when up-to-date (does not fully auto-hide) | Phase 1 | Chip visible with muted styling when idle and a folder context exists; hidden only when no folder/status available |
| IndexStatusChip click opens IndexStatusPanel | Phase 1 | Panel visibility toggled |
| IndexStatusPanel shows correct counts from API response | Phase 1 | Counts match mock `fetchIndexStatus()` response |
| No toast spam from index status updates | Phase 1 | Toast store queue length unchanged during index status polling |
| Facets data-layer loading and error states | Phase 1 | `fetchFacets()` resolves with correct shape; query key and composable handle loading/error |
| SettingsModal has ARIA dialog roles | Phase 1 | `role="dialog"`, `aria-modal="true"`, `aria-labelledby` present |
| AdvancedSearchDrawer form renders all field groups | Phase 2 | Text, numeric, select, and size/ratio field groups visible |
| TanStack Form validation: invalid number shows error | Phase 2 | Error message displayed for non-numeric seed input |
| Apply/Cancel/Reset behavior | Phase 2 | Apply triggers search; Cancel restores previous; Reset clears all fields |
| Field serialization matches backend parser format | Phase 2 | Serialized output matches expected `fielded_search_parser.py` format |
| SearchFilterChips render active filters | Phase 2 | Chips visible when fielded search is active; content matches filter values |
| SearchFilterChip removal updates search | Phase 2 | Removing chip removes filter from active query |
| Plain text search regression | Phase 2 | Existing search behavior unchanged when no fielded filters active |
| MetadataTable renders columns and data | Phase 3 | Column headers and data rows match mock response |
| Table sorting by column | Phase 3 | Click header toggles sort direction; data reorders correctly |
| Table filtering (text column) | Phase 3 | Filter input narrows visible rows |
| Column visibility toggle | Phase 3 | Hidden columns removed from DOM; visibility persists in localStorage |
| Row selection (individual, select all, deselect all) | Phase 3 | Checkbox state toggles; selected count toolbar appears |
| Pagination | Phase 3 | Page size selector changes rows per page; page navigation works |
| GalleryGrid unchanged | Phase 3 | Existing GalleryGrid tests pass without modification |

### Integration/E2E Tests

| Test | Phase | Description |
|---|---|---|
| Desktop AdvancedSearchDrawer opens/closes | Phase 2 | Slide-over panel behavior on desktop breakpoint |
| Full search flow: plain → advanced → filter chip removal → plain | Phase 2 | End-to-end search state transitions |
| MetadataTable → lightbox round-trip | Phase 3 | Click thumbnail opens lightbox; close returns to table |

### Performance Tests

| Test | Phase | Assertion |
|---|---|---|
| Album-open perf unchanged | All | Scan p95, first thumbnail, thumbnail p95 within existing budgets |
| Lightbox perf unchanged | All | Visible time, preview loaded time within existing budgets |
| MetadataTable render time with 100 rows | Phase 3 | Initial render under 500ms |

### Accessibility Tests

| Test | Phase | Assertion |
|---|---|---|
| SettingsModal dialog roles present | Phase 1 | `role="dialog"`, `aria-modal`, `aria-labelledby` |
| ToastItem `role="alert"` present | Phase 1 | Screen reader announces new toasts |
| LightboxMobileSheet tab roles | Phase 1 | `role="tablist"`, `role="tab"`, `aria-selected` |
| FolderTreeItem TreeView roles | Phase 1 | `role="tree"`, `role="treeitem"`, `aria-expanded` |
| Form field labels linked to inputs | Phase 2 | Each input has `aria-labelledby` or `<label>` association |
| Table column headers sortable via keyboard | Phase 3 | Enter/Space on column header triggers sort |

---

## 17. Recommended File/Component Map

### New Files

| File | Phase | Description |
|---|---|---|
| `frontend/src/composables/useIndexStatusQuery.ts` | Phase 1A | TanStack Query wrapper for `/api/index/status` |
| `frontend/src/composables/useFacetsQuery.ts` | Phase 1A | TanStack Query wrapper for `/api/facets` |
| `frontend/src/components/indexing/IndexStatusChip.vue` | Phase 1B | Compact status badge (failed/active/queued/idle/disabled) — desktop-only |
| `frontend/src/components/indexing/IndexStatusPanel.vue` | Phase 1B | Detailed popover with job counts — desktop-only |
| `frontend/src/utils/serializeAdvancedSearchToQuery.ts` | Phase 2 | Serializer: TanStack Form state → q string |
| `frontend/src/components/search/AdvancedSearchDrawer.vue` | Phase 2 | TanStack Form search builder |
| `frontend/src/components/search/SearchFilterChips.vue` | Phase 2 | Removable active filter chips |
| `frontend/src/components/search/SearchCommandPalette.vue` | Phase 2 | Quick command/search palette (optional) |
| `frontend/src/components/admin/MetadataTable.vue` | Phase 3 | TanStack Table metadata browser |
| `frontend/src/views/MetadataAdminView.vue` | Phase 3 | Admin view container |
| `frontend/src/composables/useMetadataTableData.ts` | Phase 3 | TanStack Query wrapper for table data |

### Modified Files

| File | Phase | Description | Constraint |
|---|---|---|---|
| `frontend/src/services/api.ts` | Phase 1A | Add `fetchIndexStatus()`, `fetchFacets()` | Data-layer only |
| `frontend/src/services/api.ts` | Phase 3 | Add `fetchMetadataTableData()` | Data-layer only |
| `frontend/src/query/keys.ts` | Phase 1A | Add `indexStatus`, `facets` keys | Data-layer only |
| `frontend/src/query/keys.ts` | Phase 3 | Add `metadataTable` key | Data-layer only |
| `frontend/src/types/index.ts` | Phase 1A | Add index status, facets types | Data-layer only |
| `frontend/src/types/index.ts` | Phase 2 | Add fielded search types | Data-layer only |
| `frontend/src/types/index.ts` | Phase 3 | Add table row, column, sort, filter types | Data-layer only |
| `frontend/src/components/AppHeader.vue` | Phase 1B | IndexStatusChip (desktop-only) | Must not affect mobile/tablet |
| `frontend/src/components/AppHeader.vue` | Phase 2 | AdvancedSearch trigger, SearchFilterChips (desktop) | Desktop-only |
| `frontend/src/components/AppHeader.vue` | Phase 3 | Metadata admin nav entry | Desktop-only |
| `frontend/src/components/GalleryGrid.vue` | Phase 1C | `role="alert"` on error banner (desktop-safe only) | Frozen for behavior/layout/virtualization |
| `frontend/src/components/GalleryGrid.vue` | Phase 2 | SearchFilterChips integration | Frozen for behavior/layout/virtualization |
| `frontend/src/components/SettingsModal.vue` | Phase 1C | Header/Body/Footer structure, ARIA roles | Desktop-safe only. No mobile behavior changes. |
| `frontend/src/components/SettingsModal.vue` | Phase 3 | Tabs + TanStack Form (if indexing config added) | Phase 3 only if config grows |
| `frontend/src/components/RootPathSheet.vue` | Phase 1C | Structure refactor, loading state, ARIA | Avoid unless proven desktop-safe |
| `frontend/src/components/ToastItem.vue` | Phase 1C | `role="alert"` | Desktop-safe only |
| `frontend/src/components/FolderTreeItem.vue` | Phase 1C | TreeView ARIA roles | Desktop-safe only |
| `frontend/src/components/LightboxMobileSheet.vue` | Phase 1C | Tab ARIA roles | Avoid unless proven desktop-safe |
| `frontend/src/App.vue` | Phase 3 | MetadataAdminView switching | Desktop-only |

### Files Frozen in Phase 1

| File | Status |
|---|---|
| `frontend/src/components/MobileHeader.vue` | Frozen — no changes |
| `frontend/src/components/TabletHeader.vue` | Frozen — no changes |
| `frontend/src/layouts/MobileLayout.vue` | Frozen — no changes |
| `frontend/src/layouts/TabletLayout.vue` | Frozen — no changes |

### Test Files Expected

| File | Phase |
|---|---|
| `frontend/tests/index-status-chip.spec.ts` | Phase 1 |
| `frontend/tests/index-status-panel.spec.ts` | Phase 1 |
| `frontend/tests/facets-loading.spec.ts` | Phase 1 |
| `frontend/tests/settings-modal-aria.spec.ts` | Phase 1 |
| `frontend/tests/mobile-header-freeze.spec.ts` | Phase 1 |
| `frontend/tests/tablet-header-freeze.spec.ts` | Phase 1 |
| `frontend/tests/advanced-search-drawer.spec.ts` | Phase 2 |
| `frontend/tests/search-filter-chips.spec.ts` | Phase 2 |
| `frontend/tests/search-plain-regression.spec.ts` | Phase 2 |
| `frontend/tests/metadata-table.spec.ts` | Phase 3 |
| `frontend/tests/gallery-grid-unchanged.spec.ts` | Phase 3 |

---

## 18. Final Recommendation

### Implementation Order

1. **Phase 1 first (desktop-only)** — Expose the backend indexing/facets capabilities that already exist. Standardize desktop UI structure before adding complexity. This phase has the lowest risk (purely additive components; Phase 1 should not change GalleryGrid behavior, layout, virtualization, image loading, or browsing semantics) and immediately makes the app feel more "aware" of its background processing. Users gain visibility into what the backend is doing. Mobile and tablet are frozen.

2. **Phase 2 second (desktop-first)** — Unlock the powerful fielded search that the backend already supports. TanStack Form is the correct tool for this and justifies the existing installation. The AdvancedSearchDrawer + SearchFilterChips provide a discoverable interface for 30+ search fields that currently require manual query construction. Mobile/tablet advanced search deferred to separate spec.

3. **Phase 3 last (desktop-first)** — TanStack Table for admin/metadata management. This is the largest new dependency usage and should come last to ensure the TanStack Form patterns from Phase 2 are well-understood. Many planned tables require backend prerequisites (per-job rows, diagnostics endpoint) that should be documented but not blocked on. Mobile/tablet admin view deferred.

### Risk/Reward Balance

- **Phase 1**: Lowest risk (desktop-only, mobile/tablet frozen), immediate UX value. Visibility into background indexing is the single biggest missing piece.
- **Phase 2**: Medium risk (new TanStack Form usage, desktop-first), high reward. Fielded search turns an invisible backend capability into a primary user feature.
- **Phase 3**: Medium risk (new TanStack Table usage, desktop-first), moderate reward. Admin/metadata views benefit power users but are not essential for the core gallery browsing experience.

### What Makes This Different

This is not a generic UI modernization plan. Every recommendation is grounded in specific backend capabilities, specific frontend gaps, and specific code locations discovered through audit. The three phases correspond directly to the three DT/Immich adaptation phases already completed on the backend:

- Backend Phase 1 (indexer, batch writer, index status) → Frontend Phase 1 (index visibility, UI standardization) — desktop-only
- Backend Phase 2B (fielded search, DB-first metadata) → Frontend Phase 2 (advanced search, faceted discovery) — desktop-first
- Backend Phase 3 (warm listing, watcher, facets) → Frontend Phase 3 (admin cockpit, audit tables) — desktop-first
