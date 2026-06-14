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
| Index status visibility | Yes (`/api/index/status`, `indexer.py:599`) | Desktop API wrapper/query/UI complete after Tailwind Phase 2B refactor |
| Faceted search/advanced search | Yes (`/api/facets`, `facets.py:248`; fielded parser with 30+ fields) | Facets data layer complete; visible facets/search UI remains Phase 2 |
| Watcher/refresh status | Yes (`get_watcher_status()`, `get_refresh_status()` exist) | No HTTP endpoints wired; no frontend exposure possible |
| Metadata list / library inspector | Yes (`/api/search?scope=all&limit=200`, indexed metadata via `unifiedSearch()`) | Not built; Phase 3 should use a lightweight read-only table/list, not TanStack Table |
| TanStack Vue Form for advanced search/settings | Installed (v1.33.0) | Not used in any runtime component |

### Why a frontend control/visibility layer is needed

DT/Immich-style background jobs (indexing, watcher, search caching) require user-visible status and progress. Without it:
- Users cannot tell if indexing is running, complete, or failed.
- The powerful fielded search parser exists but has no discoverable search UI.
- Facets data is computed on the backend but never presented to users.
- The TanStack Form foundation is installed but unused, while Advanced Search is a strong fit. TanStack Table is not needed for the Phase 3 Metadata List MVP.

### Where TanStack Table/Form fit

- **TanStack Vue Form**: Strong fit for AdvancedSearchDrawer (fielded search with validation, Apply/Cancel/Reset). Future settings or editing workflows may use it only after backend and UX prerequisites exist.
- **TanStack Vue Table**: Not needed for the Phase 3 Metadata List MVP. Revisit only if a dedicated paginated metadata or diagnostics endpoint is added and heavier table features become necessary.
- **Neither should be used** for: main GalleryGrid (photo browsing), simple search input, toast, or lightbox metadata panel.

### Which shadcn-vue patterns should be adapted

- **Command palette pattern** for search/quick-command UX.
- **Dialog** for desktop settings/modal structure.
- **Drawer/Sheet** for mobile settings, mobile advanced search, and mobile index panel are future-only patterns, explicitly excluded from Phase 1. Phase 1 may only adapt desktop-safe Badge + Popover/Dialog patterns.
- **Popover** for index status details, filter mini-panels.
- **DropdownMenu** for search scope and toolbar actions.
- **Data Table** only for future backend-backed paginated metadata or diagnostics tables; Phase 3 MetadataList uses plain table/list styling.
- **Form** layout (Label/Description/Error pattern) for advanced search and future backend-backed editing workflows.
- **Badge** for indexing/error/facet states.
- **Tabs** for settings sections and future diagnostics sections.

### Current strategy: PC-first Phase 1

Phase 1 is desktop/PC-only. The previous attempt proved that wiring new status UI into mobile/tablet headers is too risky without a dedicated mobile/tablet design. Therefore, Phase 1 must only improve desktop visibility and desktop UI structure.

Mobile and tablet layouts are frozen during Phase 1.

---

### Cross-Plan Status Map

| FRONTEND plan scope | TAILWIND plan status |
|---|---|
| FRONTEND Phase 1A/1B | Superseded by TAILWIND Phase 2B (Index Status) |
| FRONTEND Phase 1C (SettingsModal, Dialog) | Superseded by TAILWIND Phase 1.5 + 2B |
| FRONTEND Phase 1D (SearchFilterChips, Badge) | Superseded by TAILWIND Phase 2B |
| FRONTEND Phase 2 (AdvancedSearchDrawer, facets UI) | Still valid; NOT superseded |

### Desktop Theme Note

Desktop theme selection now uses the `useGalleryTheme()` composable with a shadcn `DropdownMenu` for Light/Dark/System. This replaces the old two-state toggle while keeping `[data-theme="dark"]` as the dark-mode selector.

---

### Mobile/Tablet Freeze for Phase 1

During Phase 1, these files and behaviors are out of scope:
- frontend/src/components/MobileHeader.vue
- frontend/src/components/TabletHeader.vue
- frontend/src/layouts/MobileLayout.vue
- frontend/src/layouts/TabletLayout.vue
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
| Background metadata indexing | Complete (`indexer.py`, 607 lines) | Complete — `fetchIndexStatus(path)` | Complete — desktop `IndexStatusChip`/`IndexStatusPanel` | Desktop visibility complete after Tailwind Phase 2B refactor; mobile/tablet remains frozen | Complete for desktop Phase 1 |
| Index status (`/api/index/status`) | Complete (`indexer.py:599`) | Complete | Complete — desktop AppHeader chip + popover panel | Mobile/tablet intentionally excluded | Complete for desktop Phase 1 |
| Facets (`/api/facets`) | Complete (`facets.py:248`, 8 facet types) | Complete — `fetchFacets(path)` | **Missing** — no visible facet chips, filter UI, or suggestion dropdowns | Phase 1 data layer complete. Phase 2 exposes visible facets UI, filter chips, and AdvancedSearchDrawer integration. | Phase 2 UI |
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
| `/api/scan` | `ScanResponse` (include `index_source?: "warm_db" \| "direct_scan" \| "mixed"`) | `scanDirectory()` | Existing scan composable | Backend returns `index_source`; frontend type must reflect it. |

Frontend should not invent a new payload shape when an existing backend contract already exists.

---

## 4. Current Frontend Component Audit

| Component | Current Role | Problems/Gaps | shadcn-vue Pattern to Learn | Recommendation | Phase 1 Constraint |
|---|---|---|---|---|---|
| **AppHeader + Search** (`AppHeader.vue`) | Desktop header with brand, theme toggle, search box + scope selector | Search is single text input; no fielded search, no facet chips, no advanced search trigger. Scope selector is a native `<select>`. | Command palette (search suggestions), Popover (scope/field selector), Badge (fielded search chips) | **Phase 1: allowed** — Add IndexStatusChip and desktop panel/popover. Must not affect mobile/tablet. Keep native `<select>` for scope in Phase 1. | Add IndexStatusChip only. No mobile/tablet impact. |
| **MobileHeader** (`MobileHeader.vue`) | Mobile top bar with expandable search, sort popover, theme toggle | Same search limitations as desktop. Search overlay has no fielded mode. | Command (mobile search palette), Sheet (advanced search drawer on mobile) | **Phase 1: frozen** — No changes. No IndexStatusChip. No status panel. No button reorder. | Frozen. No changes. |
| **TabletHeader** (`TabletHeader.vue`) | Tablet top bar | Scope selector, theme toggle, search. | — | **Phase 1: frozen** — No changes. No IndexStatusChip. No status panel. No layout changes. | Frozen. No changes. |
| **SettingsModal** (`SettingsModal.vue`) | Application settings: intro screen mode, theme selection, original-image toggle | Now uses shadcn Dialog component (migrated in Tailwind Phase 1.5/2B). No tabs yet; flat auto-save settings remain correct. | Dialog is complete for current scope; Tabs/Form remain future-only if settings grow. | **Superseded by Tailwind Phase 1.5/2B** — shadcn Dialog migration complete. Keep current auto-save behavior (watcher/localStorage). | No mobile behavior changes. |
| **RootPathSheet** (`RootPathSheet.vue`) | Bottom sheet for editing root folder path on mobile | No loading state during path load. Missing ARIA dialog roles. Paste button hides when textarea focused (discoverability). | Sheet (Header/Description/Footer pattern) | **Phase 1: NOT in Phase 1. Deferred to future Mobile/Tablet Spec.** | Not in Phase 1. Deferred to future Mobile/Tablet Spec. |
| **Lightbox + Metadata Panel** (`Lightbox.vue`, `LightboxDesktopPanel.vue`, `LightboxMobileSheet.vue`, `LightboxTabletPanel.vue`) | Device-adaptive image viewer with metadata display | Desktop panel lacks `role="complementary"`. Mobile sheet tabs lack `role="tablist"`/`role="tab"`/`aria-selected`. Metadata display itself is well-built with sections, copy buttons, LoRA highlighting. | Tabs (mobile metadata tabs ARIA roles), Sheet (mobile panel structure) | **Keep as-is with light accessibility fixes**. Metadata panels are mature and should not be rewritten. Add ARIA roles for tabs and complementary landmark. | Lightbox behavior frozen for mobile/tablet. |
| **Toast** (`ToastContainer.vue`, `ToastItem.vue`) | Fixed-position toast notifications with TransitionGroup | No `role="alert"` or `aria-live` for screen reader announcements. No toast queue overflow beyond capping at 3. | Toast/Sonner pattern (position, stacking, dismiss) | **Keep as-is**. Toast system is mature and styled per gallery theme. Add `role="alert"` to ToastItem. | Desktop-safe ARIA only. |
| **GalleryGrid** (`GalleryGrid.vue`) | Primary content display: virtualized photo grid, infinite scroll, search results, toolbar | Search results rendering is adequate. No filter chips for active fielded search. Sort/density triggers lack `aria-haspopup`/`aria-expanded` (except density). Error banner lacks `role="alert"`. No `aria-live` for search results. | Data Table toolbar pattern (for sort/density/filter controls), Badge/Alert (error states) | **Phase 1: frozen for behavior/layout/virtualization/image loading** — Do NOT use TanStack Table. `role="alert"` on error banner is desktop-safe only if it does not change mobile behavior. | Frozen for behavior/layout/virtualization/image loading. |
| **FolderTreeItem** (`FolderTreeItem.vue`) | Recursive folder tree with keyboard navigation | Missing proper TreeView ARIA roles (`role="tree"`, `role="treeitem"`, `aria-expanded`, `aria-selected`). | TreeView widget pattern from WAI-ARIA | **Refactor ARIA**: Add TreeView roles. Keep existing keyboard navigation. | Desktop-safe ARIA only. |
| **EmptyState** (`EmptyState.vue`) | Generic empty/error/loading state with 7 types | SVGs lack `role="img"`/`aria-label`. Loading type lacks `aria-busy`. | N/A (custom component) | **Keep as-is**. Light accessibility improvements only. | Desktop-safe ARIA only. |
| **Future: IndexStatusChip** | Does not exist | — | Badge + Popover pattern | **Phase 1: desktop-only** — Must not be imported by MobileHeader or TabletHeader. | Desktop-only. No mobile/tablet import. |
| **Future: IndexStatusPanel** | Does not exist | — | Popover/Sheet pattern for details | **Phase 1: desktop-only** — Must not open as mobile sheet in Phase 1. | Desktop-only. No mobile sheet. |
| **Future: AdvancedSearchDrawer** | Does not exist | — | Sheet (mobile) / Side Sheet (desktop), Form (TanStack), Command palette | **Add new component**. See Phase 2. | Phase 2. |
| **Future: SearchFilterChips** | Does not exist | — | Badge (removable chips) | **Add new component**. See Phase 2. | Phase 2. |
| **Future: MetadataList** | Does not exist | — | Plain table/list styling | **Add lightweight read-only component**. See Phase 3. | Phase 3. |

---

## 5. TanStack Vue Form Decision Matrix

| Candidate | Use Form? | Why | Why Not | Phase |
|---|---|---|---|---|
| **AdvancedSearchDrawer** | **YES** | Complex form with multiple field types (text, number, select, boolean), field validation (numeric ranges, valid dimensions), dirty state tracking, Apply/Cancel/Reset behavior. Backend already supports 30+ fielded search predicates. | — | Phase 2 |
| **SettingsModal** (current scope) | **NO** | Only 3 options (intro mode, theme, alwaysLoadOriginal). All auto-save via watcher to localStorage. No complex validation. Apply/Cancel/Reset would be incompatible UX with the auto-save watcher model. | Form overhead is not justified for current content. Footer should use Done/Close, not Apply/Cancel. Revisit only if settings expand into staged, validated configuration. | Not now |
| **RootPathSheet** | **NO** | Single text field with path validation. Simple v-model with inline validation message is sufficient. | TanStack Form would add overhead without clear value. No dirty/save complexity. | Never |
| **Simple Search Input** | **NO** | Single text field with debounce. No validation needed beyond non-empty check. Dirty/Action/Cancel would harm the instant-search UX. | TanStack Form's state management would interfere with debounced instant search and clear UX. | Never |

### Mandatory Conclusions

- **Simple search input should NOT use TanStack Form.** It is a single, debounced text field. Instant-search UX is incompatible with Form's dirty/Apply/Cancel model.
- **Advanced Search SHOULD use TanStack Form.** It is a complex form with validation, multiple field types, dirty state, and explicit Apply/Cancel/Reset. This is the canonical TanStack Form use case.
- **Current SettingsModal is too small for TanStack Form.** Keep the auto-save watcher model and use a Done/Close footer. If settings later grow into complex multi-section configuration (indexing/watcher/cache/debug), switch to staged draft state with Apply/Cancel/Reset and introduce TanStack Form at that point. Apply/Cancel/Reset require staged draft state — they should not be mixed with the current auto-save watcher model.
- **Future editing/configuration forms may be TanStack Form use cases**, including indexing/watcher settings, single-image metadata editing, or batch metadata editing. These are not Phase 3 MVP work and require backend endpoints plus a staged edit UX.

---

## 6. TanStack Vue Table Decision Matrix

| Candidate | Use Table? | Why | Why Not | Phase |
|---|---|---|---|---|
| **MetadataList** | **NO** | Phase 3 needs a compact read-only utility view over up to 200 search results. Client-side sorting and text filtering can be handled with simple Vue state/computed values. | TanStack Table would add column visibility, row selection, pagination, and table state overhead that the MVP explicitly excludes. Revisit if/when a dedicated backend paginated listing endpoint is added. | Phase 3 |
| **Future paginated metadata table** | **YES (conditional)** | If the backend later exposes an all-indexed paginated listing endpoint with server-side sorting/filtering, TanStack Table may be appropriate. | No such endpoint exists today, and editable/batch metadata workflows are out of Phase 3 scope. | Future (backend prerequisite) |
| **Future diagnostics/audit tables** | **YES (conditional)** | Row-level index errors, metadata parse errors, duplicate candidates, and broken-image scan results would be structured table data if the backend exposes them. | Current backend does not expose row-level diagnostics, per-job errors, duplicate data, or broken-image data. | Future (backend prerequisite) |
| **Facets Table** | **NO** | Facets are better rendered as chips/tokens with counts, not as a table. A table would waste space on what is essentially a filter UI. | Use Badge/Popover pattern for facets, not TanStack Table. | Never |
| **Main GalleryGrid** | **NO (hard rule)** | GalleryGrid is a visual photo browsing experience using TanStack Virtual and CSS Grid. It shows image thumbnails, not tabular data. | TanStack Table would replace thumbnails with text rows, destroy the visual browsing experience, and conflict with virtual scrolling architecture. | Never |

### Mandatory Conclusions

- **Main GalleryGrid MUST NOT use TanStack Table.** It is a visual photo browser, not a data table. TanStack Virtual is the correct technology for this component.
- **MetadataList SHOULD NOT use TanStack Table for the MVP.** It is a lightweight read-only inspector with a bounded search result set, not a full data-management surface.
- **TanStack Table is future-only for metadata/diagnostics.** Use it only if backend pagination or row-level diagnostics make table state management necessary.

---

## 7. shadcn-vue Pattern Mapping

| shadcn-vue Pattern | Gallery Use Case | Adaptation Approach |
|---|---|---|
| **Command** | Search suggestions, quick command palette (e.g., "Go to folder...", "Search by model...") | Adapt the keyboard-navigable list + filter pattern. Standard UI chrome uses shadcn-vue Stone defaults. Bind to existing search store and folder navigation. |
| **Dialog** | Desktop SettingsModal, Index Status detail view | SettingsModal now uses the shadcn Dialog component (migrated in Tailwind Phase 1.5/2B). A search filter panel with form fields (Advanced Search on desktop) should use a Side Sheet, not a Dialog per MD3. |
| **Drawer / Sheet** | Mobile Settings (sheet), Advanced Search (mobile: bottom sheet; desktop: side sheet), Index Status (mobile), RootPathSheet | Existing `RootPathSheet` already has sheet-like behavior. Standardize the Header/Description/Footer pattern. Use existing VSBS for metadata sheet; do not replace it. New sheets (advanced search, index panel) should follow the same structure. **Future-only. All mobile/tablet Drawer/Sheet uses excluded from Phase 1.** |
| **Popover** | Index status details (click chip to see queue counts), search scope selector (future: Phase 2, if scope options expand beyond simple "This folder"/"All indexed"), field help tooltips | Keep native `<select>` for scope in Phase 1. Replace with Popover/DropdownMenu only in Phase 2 if scope options grow. Keep popovers compact and non-modal. |
| **DropdownMenu** | Search scope, sort options, density grid options, toolbar actions menu | Current custom dropdowns (sort, density) already function well. Adapt them to DropdownMenu pattern for consistency: keyboard navigation, `aria-haspopup`/`aria-expanded`, focus management. |
| **Data Table** | Future backend-backed metadata/diagnostics tables; not Phase 3 MetadataList MVP | MetadataList should use plain table/list styling, not TanStack Table with the shadcn Data Table pattern. Revisit if/when a dedicated backend paginated listing endpoint is added. |
| **Form** | AdvancedSearchDrawer, future batch editor, expanded SettingsModal | TanStack Form with shadcn-vue Stone form controls: field label, description, error message, Apply/Cancel/Reset buttons. Use Stone border/focus/input defaults for standard form chrome. |
| **Badge** | Index status (idle/active/queued/failed/disabled), facet chips, fielded search filter chips, error counts | Use shadcn-vue Stone Badge defaults for standard chips. Removable badge pattern for filter chips (x button to clear). State colors should be semantic and minimal, not brand warm colors. |
| **Alert** | Indexing errors, scan errors, metadata parse warnings | Existing error banner in GalleryGrid and toast system already cover this. Enhance with Alert pattern: icon + title + description + dismiss. Keep gallery toast styling. |
| **Tabs** | Settings sections (General / Indexing / Watcher), admin panel sections, mobile metadata tabs (ARIA already needed) | Existing mobile metadata tabs need `role="tablist"`/`role="tab"`/`aria-selected`. SettingsModal should add Tabs if indexing/watcher config is added. Use shadcn-vue Stone defaults for standard tab chrome. |
| **Toast / Sonner** | Existing toast system | Keep current toast implementation. It already handles positioning, stacking, dismiss, and types. Add `role="alert"` to ToastItem for accessibility. |

### Key Principle

**Do not blindly copy shadcn-vue code.** Standard UI components use shadcn-vue Stone defaults, not gallery warm colors. Gallery warm/premium identity is reserved for the brand hero and explicitly approved brand/artwork surfaces. The shadcn-vue patterns are valuable for structure, accessibility, keyboard behavior, and standard UI styling.

### shadcn-vue Selective Adoption Decision

shadcn-vue is now approved for selective adoption of desktop primitive UI components where it improves accessibility or maintainability. Use this plan for frontend use cases, and use [Tailwind plan §6](TAILWIND_MIGRATION_ANIMATION_PRESERVATION_PLAN.md#6-shadcn-vue-selective-adoption-strategy) for the full component grouping and token-bridge/testing rules.

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
- [ ] Verify `ScanResponse.index_source` is present in frontend types and scan data handling.
- [ ] Confirm Advanced Search will serialize to `q` and call existing `unifiedSearch()`.
- [ ] Confirm no `beforeunload`/`unload` lifecycle regression is introduced.
- [ ] Confirm Phase 1 does not change GalleryGrid behavior, layout, virtualization, image loading, or browsing semantics. Only small accessibility annotations or non-behavioral wiring are allowed if needed.

---

#### Phase 1A — Desktop data layer

- [x] IndexStatusResponse, FacetsResponse, IndexStatusState types
- [x] `queryKeys.indexStatus(path)`, `queryKeys.facets(path)`
- [x] `fetchIndexStatus(path)`, `fetchFacets(path)` in `api.ts`
- [x] `useIndexStatusQuery(path, enabled)` composable
- [x] `useFacetsQuery(path, enabled)` composable

Completed via Tailwind Phase 2B Index Status refactor: status/facets data layer is path-scoped and desktop-only consumers remain isolated from mobile/tablet headers.

Rules:
- no mobile/tablet consumption
- no visible mobile/tablet UI
- no global behavior changes

---

#### Phase 1B — Desktop index status UI

- [x] Desktop AppHeader-only IndexStatusChip
- [x] Desktop-only IndexStatusPanel
- [x] Use Badge + Popover/Dialog pattern inspired by shadcn-vue
- [x] Adaptive polling: fast only when active/queued work exists; failed-only/no moving work slow-polls; unavailable/error visible but not noisy
- [x] No MobileHeader/TabletHeader imports

Completed via Tailwind Phase 2B Index Status refactor: `fetchIndexStatus(path)` and `queryKeys.indexStatus(path)` are path-scoped, polling is adaptive, and the desktop AppHeader chip opens a shadcn Popover panel.

**Tasks:**

- [x] **Add `fetchIndexStatus()` to `api.ts`** — wraps `GET /api/index/status?path=...`. Response includes: `enabled`, `worker_count`, `active_jobs`, `runtime_queue_depth`, counts by state, `last_error`, `updated_at`.
- [x] **Add `useIndexStatusQuery()` composable** — TanStack Query wrapper with `queryKeys.indexStatus(path)`. Adaptive polling per Section 10 policy: fast 2-3s only when active/queued work exists; failed-only with no work slow-polls at 60s; unavailable/error slow-polls at 60s. Browser tab hidden: pause or slow down. Window focus: local debounced refetch. No beforeunload/unload listeners. Enabled only when a folder is loaded.
- [x] **Add query key `indexStatus(path)` in `query/keys.ts`**.
- [x] **Add `IndexStatusChip.vue`** — small badge in AppHeader (desktop only) near search area. Shows one of six states:
  - `failed` — `failed > 0 || staged_path_failed > 0 || last_error` (red badge with error icon)
  - `active` — workers are running (amber/yellow badge with pulse animation)
  - `queued` — jobs are pending (blue badge)
  - `idle` — no errors, no active jobs, no queued jobs; up-to-date (compact muted chip or muted icon/text)
  - `unavailable` — API error, backend unreachable (visible orange/gray chip)
  - `disabled` — no folder loaded or no library context (hidden)
  - **State mapping**:
    ```
    failed = failed > 0 || staged_path_failed > 0 || last_error
    active = running > 0 || active_jobs > 0 || active_scan_requests > 0
    queued = queued > 0 || runtime_queue_depth > 0 || staged_path_queue_depth > 0
    idle = !failed && !active && !queued
    ```
  - **UI behavior**: Click chip opens IndexStatusPanel (popover on desktop). **Do NOT auto-hide when idle.** Idle/up-to-date state collapses into a muted status (compact chip or muted icon) — not disappear completely. Indexing status should be quiet but discoverable. Active/error states should be obvious. Disabled/no-folder state is hidden. Never blocks interaction. Never creates toast spam.
  - **Phase 1 constraint**: Must not be imported by MobileHeader or TabletHeader.
- [x] **Add `IndexStatusPanel.vue`** — detailed index status shown on chip click. Shows:
  - Summary line: "Indexing — X queued, Y active, Z done" (using queued/running/done/failed counts that the backend actually returns; there is no total file count from `/api/index/status`)
  - Per-state counts: queued, running, done, failed, stale, skipped
  - Last error text (if any)
  - Worker count and queue depth
  - **Progress indicator**: `LinearProgressIndicator` (determinate when running/done counts allow percentage computation, indeterminate otherwise) or compact `CircularProgressIndicator` to satisfy MD3 requirement for visible progress on background operations. Show in IndexStatusPanel; may also appear as a subtle indicator on IndexStatusChip when in active state.
  - **Desktop**: Popover anchored to chip
  - **Not allowed in Phase 1**: Mobile bottom sheet following RootPathSheet-style structure
  - **No blocking overlay, no toast per job**
- [x] **Add `fetchFacets()` to `api.ts`** — wraps `GET /api/facets?path=...`. Response includes `tool`, `model`, `sampler`, `scheduler`, `orientation`, `seed_availability`, `metadata_availability`, `lora`, `folders`. Backend endpoint confirmed at `facets.py:248`.
- [x] **Add `useFacetsQuery()` composable** — TanStack Query wrapper with `queryKeys.facets(path)`. Long staleTime (5min) since facets change slowly. Phase 1 prepares the facets data layer only. Visible facets UI belongs to Phase 2.

---

#### Phase 1C — Desktop-safe UI standardization

- [ ] Desktop-safe dialog/header/body/footer cleanup
- [ ] Desktop-safe ARIA only
- [ ] No mobile/tablet runtime changes

**Tasks:**

- [x] **SettingsModal shadcn Dialog migration** — now uses the shadcn Dialog component, migrated in Tailwind Phase 1.5/2B:
  - **Header**: Title "Settings" + Close button
  - **Body**: Scrollable content area (current settings)
  - **Footer**: "Close" button (desktop-safe, no API call — just closes the modal). **Do NOT use Apply/Cancel.** Settings auto-save immediately via existing watcher/localStorage behavior; there is no staged draft state to apply or cancel.
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
- [x] **Add accessibility fixes** (desktop-safe only, non-breaking):
  - [x] ToastItem: add `role="alert"` for screen reader announcements (completed)
  - [x] GalleryGrid error banner: add `role="alert"` (desktop-safe only) (completed)
  - [x] FolderTreeItem: add `role="tree"`, `role="treeitem"`, `aria-expanded` (desktop sidebar only, verified not to affect mobile sidebar) (completed)
  - [ ] LightboxMobileSheet tabs: Deferred to future Mobile/Tablet Spec. NOT in Phase 1.
  - SettingsModal: add ARIA dialog roles (covered above)
  - [x] AppHeader: add `role="banner"` landmark (completed)
- [x] Accessibility fixes completed: ToastItem (role=alert), GalleryGrid (role=alert), FolderTreeItem (treeview roles), AppHeader (role=banner)
- [ ] **Add tests**:
  - [ ] IndexStatusChip renders failed/active/queued/idle/disabled states (not done; chip was removed from AppHeader, replaced by popover button)
  - [x] IndexStatusPanel shows correct counts from mock API response
  - [x] IndexStatusPanel opens/closes on chip click
  - [ ] facets data-layer loading/error states (fetch, query key, composable); visible facets UI belongs to Phase 2 (not written)
  - [x] SettingsModal ARIA roles present
  - [ ] RootPathSheet ARIA roles present (deferred)
  - [ ] No toast spam from index status (assert toast queue does not grow from index updates) (not written)
  - [x] Existing search and GalleryGrid tests unchanged

#### Files Affected (Phase 1)

| File | Change | Phase 1 Constraint |
|---|---|---|
| `frontend/src/services/api.ts` | Add `fetchIndexStatus()`, `fetchFacets()` | Data-layer only |
| `frontend/src/query/keys.ts` | Add `indexStatus(path)`, `facets(path)` keys | Data-layer only |
| `frontend/src/composables/useIndexStatusQuery.ts` | New composable | Data-layer only |
| `frontend/src/composables/useFacetsQuery.ts` | New composable | Data-layer only, no visible UI in Phase 1 |
| `frontend/src/components/IndexStatusChip.vue` | New component | Desktop-only |
| `frontend/src/components/IndexStatusPanel.vue` | New component | Desktop-only |
| `frontend/src/components/SettingsModal.vue` | shadcn Dialog migration complete | Desktop-safe only |
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

- [x] **Add `serializeAdvancedSearchToQuery()` utility** — serializes `AdvancedSearchDrawer` TanStack Form state into a backend-compatible `q` string using fielded search token syntax (e.g. `model:"PonyXL" sampler:"Euler a" seed:123 prompt:"blue archive"`). The resulting `q` string is passed to the existing `unifiedSearch(q, opts)` path. No new API wrapper is needed; no `fields[]` or `residual_text` structured payload is introduced. **Do not introduce a structured `fields[]` frontend-to-backend API unless the backend first adds and documents that contract.**
- [x] **Add `AdvancedSearchDrawer.vue` using `@tanstack/vue-form`** — structured search form with:
  - **Text fields**: `prompt:`/`positive:`, `negative:`, `model:`, `sampler:`, `scheduler:`, `lora:`, `vae:`, `path:`/`folder:`, `name:`
  - **Numeric fields with operators**: `seed:` (=), `steps:` (=/>/>=/</<=), `cfg:` (same operators), `width:`, `height:`, `clip_skip:`, `hires_upscale:`, `hires_steps:`, `denoising_strength:`
  - **Select/autocomplete fields**: `source:`/`tool:`, `model:` (suggestions from facets), `sampler:` (suggestions from facets), `orientation:` (landscape/portrait/square), `seed_availability:` (has_seed/no_seed), `metadata_availability:` (has_metadata/no_metadata)
  - **Size field**: `size:` with width×height input
  - **Aspect ratio field**: `ratio:` with common preset buttons (1:1, 4:3, 16:9, 3:2, 2:3, 9:16)
  - **Date field**: `date:` with date range picker or text input
  - **Generic fallback fields**: `param:`, `advanced:`, `raw:` (text inputs for advanced users)
  - **Form actions**: Apply (executes search), Cancel (closes drawer, restores previous search), Reset (clears all fields)

- [x] **Use TanStack Form features**:
  - **Validation**: numeric fields must be valid numbers, dimensions must be positive, ratio format must be valid
  - **Dirty state**: Apply button enabled only when form is dirty
  - **Apply/Cancel/Reset**: Cancel restores previous search state; Reset clears all fields
  - **Initial values**: populate from current search state (if user previously searched with fielded query)

- [x] **Build query strings compatible with existing backend parser**:
  - `serializeAdvancedSearchToQuery()` converts form state into a properly formatted `q` string using the same token syntax the backend fielded-search parser already understands (e.g. `txt model:"PonyXL" sampler:"Euler a" seed:123 prompt:"blue archive"`)
  - The serializer must produce query strings that match the format tested in `fielded_search_parser.py`
  - The output `q` string is passed directly to the existing `unifiedSearch(q, opts)` — no new API payload or endpoint is required
  - Keep the plain-text search path completely unchanged; plain-text queries continue to use `unifiedSearch(q, opts)` without any serialization step

- [x] **Add `SearchFilterChips.vue`** — shows active fielded search filters as removable badges below the search bar:
  - Each chip shows "field: value" (e.g., "model: realistic", "seed: 12345")
  - X button removes individual filter
  - "Clear All" button when multiple filters are active
  - Styled as shadcn-vue Badge with Stone defaults for standard chip chrome
  - Displays when fielded search is active (in both plain search and advanced search modes)
  - Phase 2 constraint: Desktop-first. Mobile/tablet filter chips deferred.

- [x] **Desktop responsive behavior**:
  - **Desktop**: AdvancedSearchDrawer opens as a right-side drawer/slide-over panel (similar to sidebar pattern). Animation: slide in from right.

- [ ] **Add command/palette pattern** (light, optional):
  - Cmd+K (desktop) or tap search icon (mobile) opens a quick search palette
  - Palette shows: recent searches, common field shortcuts, "Advanced search..." entry point
  - Adapts shadcn-vue Command pattern using Stone defaults for standard command chrome

- [x] **Reuse existing `queryKeys.search(q, scope, path)`** — Advanced Search produces a normal backend-compatible `q` string and must reuse the existing `unifiedSearch()` path and `queryKeys.search(q, scope, path)`. Do not create a separate fielded-search cache path unless the backend/API contract changes.

- [x] **Add tests**:
  - [x] AdvancedSearchDrawer renders all field groups
  - [x] TanStack Form validation: invalid numbers show error (App disabled when invalid)
  - [x] Dirty state: Apply enabled only when dirty
  - [x] Apply/Cancel/Reset behavior correct
  - [x] Field serialization matches backend parser format
  - [x] SearchFilterChips render active filters
  - [x] Chip removal updates search and clears filter
  - [x] "Clear All" removes all fielded filters
  - [x] Plain text search regression (no fielded search) still works
  - [x] Desktop drawer opens/closes correctly
- [x] **Implementation complete** — Phase 2 implemented, audited, and fixed. All 8 Playwright tests pass. See commits: d695e45 (initial), 83d3035 (audit fixes), fcf9ea1 (validation), 80633e9 (tests).

#### Files Affected (Phase 2)

| File | Change | Status |
|---|---|---|
| `frontend/src/utils/serializeAdvancedSearchToQuery.ts` | New utility (serialize form → q string) | ✅ Created |
| `frontend/src/components/search/AdvancedSearchDrawer.vue` | New component (TanStack Form) | ✅ Created + fixed |
| `frontend/src/components/SearchFilterChips.vue` | Updated to use FieldFilter[] | ✅ Updated |
| `frontend/src/composables/useFieldedSearch.ts` | New composable | ✅ Created |
| `frontend/src/components/AppHeader.vue` | Add Advanced Search trigger + filter chips | ✅ Updated |
| `frontend/src/types/index.ts` | Add FieldFilter, FieldedSearchParams | ✅ Added |
| `frontend/tests/advanced-search-drawer.spec.ts` | 8 integration tests | ✅ 8/8 pass |

**Not touched in Phase 2:**
- `MobileHeader.vue` — advanced search entry point deferred to separate spec
- `TabletHeader.vue` — advanced search entry point deferred to separate spec

#### Risk Assessment (Phase 2)

- **Medium risk.** TanStack Form integration is new territory. The form serialization must match the backend parser format exactly.
- Mitigation: build query serialization tests first, validate against known-good backend query examples. Keep plain search path fully isolated.
- Plain text search must not regress. The AdvancedSearchDrawer is an opt-in extension; default search behavior is unchanged.

#### Acceptance Criteria (Phase 2)

- [x] AdvancedSearchDrawer renders all field groups
- [x] TanStack Form validation: invalid numbers show error (App disabled when invalid)
- [x] Dirty state: Apply enabled only when dirty
- [x] Apply/Cancel/Reset behavior correct
- [x] Field serialization matches backend parser format
- [x] SearchFilterChips render active filters
- [x] Chip removal updates search and clears filter
- [x] "Clear All" removes all fielded filters
- [x] Plain text search regression (no fielded search) still works
- [x] Desktop drawer opens/closes correctly

---

### Phase 3 — Desktop Metadata List / Library Inspector (Desktop-First)

**Goal:** Add a lightweight read-only metadata list view for inspecting indexed photos and AI metadata. This is a secondary utility for power users, not an admin cockpit and not a replacement for GalleryGrid.

**Why:** The backend indexes rich metadata, but the frontend has no compact way to scan, search, and compare metadata across photos. A desktop-first Metadata List fills that gap while keeping the visual GalleryGrid as the primary browsing UI.

**Mobile/tablet constraint:** Mobile/tablet metadata list experience is deferred to a separate spec.

#### Tasks

- [ ] **Add `MetadataList.vue`** — a lightweight read-only table/list component. Use a native table or basic component structure, not TanStack Table.
  - **Columns**:
    - Thumbnail
    - Name
    - Folder
    - Model
    - Sampler
    - Seed
    - Dimensions
    - Modified date
  - **Features**:
    - Client-side sorting by supported columns
    - Text search filter across visible metadata fields
    - Row limit display/control for the bounded search result set
    - Open-in-lightbox from thumbnail or row action
    - Copy path
    - Copy metadata
  - **Explicitly excluded from MVP**:
    - Row selection
    - Bulk actions
    - Column visibility toggle
    - Server-side pagination
    - Editable metadata

- [ ] **Add `useMetadataListQuery.ts`** — a small TanStack Query composable that reuses the existing search API:
  - `unifiedSearch(q = '', scope = 'all', limit = 200)`
  - No new backend endpoint required for the MVP.
  - Normalize only the fields needed by `MetadataList.vue`.

- [ ] **Add a desktop entry point**:
  - Add a small "Metadata" button in `AppHeader.vue`.
  - Use the existing no-router view-switching pattern if a full-page utility view is needed.
  - Keep GalleryGrid as the default and primary photo browsing UI.

- [ ] **Keep desktop-only scope explicit**:
  - Do not add metadata navigation to `MobileHeader.vue` or `TabletHeader.vue` in this phase.
  - Do not design mobile/tablet table collapse behavior in this phase.

- [ ] **Out of scope for Phase 3 MVP**:
  - Admin cockpit
  - Duplicate finder
  - Broken image scanner
  - Diagnostics dashboard
  - Watcher/refresh control panel
  - Batch delete
  - Batch move
  - Batch metadata editing
  - Row selection
  - Index error table
  - Metadata error table

- [ ] **Future/backend prerequisites to document**:
  - Current backend does not expose row-level diagnostics, per-job errors, duplicate data, or broken-image data.
  - Those features remain future backend prerequisites and should not be represented as Phase 3 MVP tasks.

- [ ] **Add tests**:
  - MetadataList renders columns with correct data
  - Sorting by column works (ascending/descending)
  - Text filtering narrows visible rows
  - Row limit is respected
  - Thumbnail opens lightbox
  - Copy path and copy metadata actions function
  - Row selection and bulk action controls are absent
  - GalleryGrid unchanged (regression)

#### Files Affected (Phase 3)

| File | Change |
|---|---|
| `frontend/src/components/MetadataList.vue` | New lightweight read-only metadata list |
| `frontend/src/composables/useMetadataListQuery.ts` | New composable that reuses `unifiedSearch()` |
| `frontend/src/query/keys.ts` | Add `metadataList` key, or reuse existing search keys if that is cleaner |
| `frontend/src/components/AppHeader.vue` | Add small "Metadata" nav entry |

**Removed from Phase 3 MVP scope:** `MetadataTable.vue`, `MetadataAdminView.vue`, `useMetadataTableData.ts`, and `api.ts` additions for metadata table data.

#### Risk Assessment (Phase 3)

- **Low risk.** The MVP reuses the existing search API, adds no new dependency, and remains read-only.
- Main risk is dataset size: `MetadataList` fetches up to 200 results through search. Larger libraries may need a future backend paginated listing endpoint.
- GalleryGrid remains unchanged and continues to be the primary browsing surface.

#### Acceptance Criteria (Phase 3)

1. MetadataList renders thumbnail, name, folder, model, sampler, seed, dimensions, and modified date from `unifiedSearch(q = '', scope = 'all', limit = 200)`.
2. Sorting works for supported columns.
3. Text filtering narrows visible results.
4. Row limit behavior is clear and bounded.
5. Thumbnail click opens the lightbox.
6. Copy path and copy metadata actions work.
7. GalleryGrid remains the primary browsing UI and is not replaced by a table.
8. No admin cockpit features are introduced.
9. Backend prerequisites are clearly documented for deferred diagnostics, duplicate finder, broken-image scanner, watcher/refresh panel, and batch editing features.
10. New tests pass.

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

Indexing status should be quiet but discoverable. Active/error states should be obvious; idle/up-to-date should reduce to a muted status, not disappear completely.

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
- **Sheet entry/exit**: `250ms ease-out` (slide from right for desktop side sheet; mobile sheet deferred to future spec)
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
| `MetadataList` | Small "Metadata" button in `AppHeader.vue` — desktop only |
| `FacetsPanel` | Inside Advanced Search or MetadataList if useful |
| Future diagnostics dashboards | Future diagnostics area, not from the main gallery grid |

Do not add navigation clutter just to expose every future tool. Prefer progressive disclosure.

---

## 13. Definition of Done

### Phase 1 Done when:

- [x] `fetchIndexStatus()` is typed and tested.
- [x] `useIndexStatusQuery()` exists and uses sane polling.
- [x] `IndexStatusChip` shows failed/active/queued/idle correctly (desktop only).
- [x] `IndexStatusPanel` shows useful status details (desktop only).
- [x] `fetchFacets()` and/or `useFacetsQuery()` are typed or explicitly deferred (data-layer only).
- [x] `SettingsModal` desktop-safe refactor does not change behavior unexpectedly (RootPathSheet deferred to future Mobile/Tablet Spec)
- [x] No indexing toast spam.
- [x] MobileHeader unchanged from pre-Phase-1 baseline.
- [x] TabletHeader unchanged from pre-Phase-1 baseline.
- [x] No IndexStatusChip in MobileHeader or TabletHeader.
- [x] Desktop smoke tests pass.
- [x] Mobile freeze verification passes (hamburger, search, sort, theme toggle).
- [x] Tablet freeze verification passes.
- [x] Typecheck passes.
- [x] GalleryGrid behavior is unchanged.

### Phase 2 Done when:

- [ ] Advanced Search uses TanStack Form only for the complex form.
- [ ] Form state serializes to backend-compatible `q`.
- [ ] Existing `unifiedSearch()` path is used.
- [ ] Plain text search still works.
- [ ] Filter chips can remove individual filters.
- [ ] Reset/Cancel/Apply behavior is clear.
- [ ] Query serializer tests pass.

### Phase 3 Done when:

- [ ] MetadataList renders columns from the existing search API.
- [ ] GalleryGrid is not replaced by a table.
- [ ] Sorting works.
- [ ] Text filtering narrows results.
- [ ] Thumbnail click opens lightbox.
- [ ] No admin cockpit features are introduced.
- [ ] Backend prerequisites are clearly documented for deferred admin features.
- [ ] MetadataList tests pass.

---

## 14. Backend Prerequisites Backlog

Purpose: Separate the Phase 3 MetadataList MVP from future features that require backend data first. Do not ask the frontend to build diagnostics, duplicate, broken-image, watcher/refresh, or editing workflows before the backend exposes the required row-level data and write endpoints.

Current backend does NOT expose row-level diagnostics, per-job errors, or duplicate/broken-image data. These remain future backend prerequisites.

| Possible Future Endpoint | Deferred Feature | Why It Is Not Phase 3 MVP |
|---|---|---|
| Dedicated paginated metadata listing endpoint | Server-side metadata browsing at library scale | MVP uses `unifiedSearch(q = '', scope = 'all', limit = 200)` and client-side sorting/filtering |
| `/api/index/errors` | Index error table | Current `/api/index/status` returns counts and summary state, not per-job rows |
| `/api/metadata/errors` | Metadata parse error table | No endpoint exposes row-level metadata parse failures |
| `/api/diagnostics` | Diagnostics dashboard | No unified diagnostics endpoint exists |
| `/api/audit/duplicates` | Duplicate finder | No backend duplicate detection exists |
| `/api/audit/broken-images` | Broken image scanner | No backend broken-image scan exists |
| `/api/watcher/status` | Watcher status panel | No HTTP route wired for watcher status (`watcher.py:191`) |
| `/api/refresh/status` | Refresh status panel | No HTTP route wired for refresh status (`refresh.py:150`) |
| `/api/photos/user-metadata` | Editable metadata | Phase 3 is read-only |
| `/api/photos/batch-metadata` | Batch metadata editing | Phase 3 has no row selection or batch operations |

---

## 15. Risks & Non-Goals

### Risks

| Risk | Phase | Mitigation |
|---|---|---|
| IndexStatusChip becomes noisy or distracting | Phase 1 | Use muted idle state (compact muted chip/icon), not auto-hide. Pulse-only when active. Never block interaction, no toasts. Test `no-toast-spam` assertion. |
| TanStack Form serialization doesn't match backend parser | Phase 2 | Build serializer tests first. Validate against known-good query examples from `fielded_search_parser.py` tests. |
| MetadataList result set is too small for large libraries | Phase 3 | MVP fetches up to 200 results via search. Add a dedicated paginated backend listing endpoint later if users need larger library-wide inspection. |
| Over-engineering settings with TanStack Form too early | Phase 1/Future | Keep current v-model approach for SettingsModal in Phase 1. Only introduce TanStack Form when staged settings and backend configuration endpoints exist. |
| Breaking plain text search when adding Advanced Search | Phase 2 | Keep plain search input completely separate. AdvancedSearchDrawer is opt-in. Plain search regression tests guard this. |
| Accessibility regression from new components | All Phases | Add ARIA roles in Phase 1 accessibility fixes. New components follow the established patterns. Test with `role` assertions. |
| bfcache/lifecycle regressions on iOS Safari | All Phases | Keep global TanStack Query `refetchOnWindowFocus: false`. Index status may use a local, debounced refetch-on-focus/pageshow/visibilitychange if needed, but must not re-enable noisy global refetches. No `beforeunload`/`unload` listeners. Test mobile sheet behavior. |

**Lesson from failed Phase 1 attempt:** Mobile/tablet headers are high-risk surfaces. Even small status chips can break real iPhone Safari layout and touch behavior. Playwright/Chromium viewport tests are not enough to prove iPhone Safari safety.

Therefore, Phase 1 is desktop-only. Real-device Safari testing is mandatory before any future mobile/tablet implementation.

### Non-Goals (Explicitly Excluded)

- **Do not rewrite the whole UI into shadcn-vue.** Adapt patterns for structure, accessibility, and keyboard behavior. Standard UI uses shadcn-vue Stone defaults; gallery warm/premium styling is reserved for brand and explicitly approved artwork surfaces.
- **Do not replace GalleryGrid with a table.** GalleryGrid uses TanStack Virtual for visual photo browsing. MetadataList is a secondary utility view, not the primary browsing UI.
- **Phase 3 is NOT an admin cockpit.** No duplicate finder, no broken image scanner, no watcher/refresh panel, no batch operations.
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
| IndexStatusChip renders each state (failed/active/queued/idle/unavailable/disabled) | Phase 1 | Correct badge text, color, and icon per state. disabled = hidden allowed; unavailable = visible required. |
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
| MetadataList renders columns and data | Phase 3 | Thumbnail, name, folder, model, sampler, seed, dimensions, and modified date render from mocked `unifiedSearch()` results |
| MetadataList sorting by column | Phase 3 | Click sortable headers to toggle direction; visible data reorders correctly |
| MetadataList text filtering | Phase 3 | Search input narrows visible rows across supported metadata fields |
| MetadataList row limit | Phase 3 | Result count is bounded by the configured limit and communicates the cap clearly |
| MetadataList row actions | Phase 3 | Thumbnail opens lightbox; copy path and copy metadata actions call clipboard APIs |
| MetadataList excludes bulk controls | Phase 3 | No row selection, select-all checkbox, batch toolbar, or column visibility toggle is rendered |
| GalleryGrid unchanged | Phase 3 | Existing GalleryGrid tests pass without modification |

### Integration/E2E Tests

| Test | Phase | Description |
|---|---|---|
| Desktop AdvancedSearchDrawer opens/closes | Phase 2 | Slide-over panel behavior on desktop breakpoint |
| Full search flow: plain → advanced → filter chip removal → plain | Phase 2 | End-to-end search state transitions |
| MetadataList → lightbox round-trip | Phase 3 | Click thumbnail opens lightbox; close returns to MetadataList |

### Performance Tests

| Test | Phase | Assertion |
|---|---|---|
| Album-open perf unchanged | All | Scan p95, first thumbnail, thumbnail p95 within existing budgets |
| Lightbox perf unchanged | All | Visible time, preview loaded time within existing budgets |
| MetadataList render time with 200 rows | Phase 3 | Initial render under 500ms |

### Accessibility Tests

| Test | Phase | Assertion |
|---|---|---|
| SettingsModal dialog roles present | Phase 1 | `role="dialog"`, `aria-modal`, `aria-labelledby` |
| ToastItem `role="alert"` present | Phase 1 | Screen reader announces new toasts |
| LightboxMobileSheet tab roles | Future | `role="tablist"`, `role="tab"`, `aria-selected` — deferred to future Mobile/Tablet Spec |
| AppHeader `role="banner"` landmark | Phase 1C | `role="banner"` present on desktop header |
| GalleryGrid error banner `role="alert"` | Phase 1C | `role="alert"` present on error banner |
| Native search scope `<select>` preserved | Phase 1C | Scope select unchanged from pre-Phase-1 baseline |
| Polling frequency not excessive | Phase 1B | Fast-poll only when active/queued work exists; failed-only slow-polls |
| FolderTreeItem TreeView roles | Phase 1 | `role="tree"`, `role="treeitem"`, `aria-expanded` |
| Form field labels linked to inputs | Phase 2 | Each input has `aria-labelledby` or `<label>` association |
| MetadataList sortable headers accessible via keyboard | Phase 3 | Enter/Space on sortable header triggers sort |

---

## 17. Recommended File/Component Map

### New Files

| File | Phase | Description |
|---|---|---|
| `frontend/src/composables/useIndexStatusQuery.ts` | Phase 1A | TanStack Query wrapper for `/api/index/status` |
| `frontend/src/composables/useFacetsQuery.ts` | Phase 1A | TanStack Query wrapper for `/api/facets` |
| `frontend/src/components/IndexStatusChip.vue` | Phase 1B | Compact status badge (failed/active/queued/idle/disabled) — desktop-only |
| `frontend/src/components/IndexStatusPanel.vue` | Phase 1B | Detailed popover with job counts — desktop-only |
| `frontend/src/utils/serializeAdvancedSearchToQuery.ts` | Phase 2 | Serializer: TanStack Form state → q string |
| `frontend/src/components/search/AdvancedSearchDrawer.vue` | Phase 2 | TanStack Form search builder |
| `frontend/src/components/SearchFilterChips.vue` | Phase 2 | Removable active filter chips |
| `frontend/src/components/search/SearchCommandPalette.vue` | Phase 2 | Quick command/search palette (optional) |
| `frontend/src/components/MetadataList.vue` | Phase 3 | Lightweight read-only metadata list / library inspector |
| `frontend/src/composables/useMetadataListQuery.ts` | Phase 3 | TanStack Query wrapper that reuses `unifiedSearch()` |

### Modified Files

| File | Phase | Description | Constraint |
|---|---|---|---|
| `frontend/src/services/api.ts` | Phase 1A | Add `fetchIndexStatus()`, `fetchFacets()` | Data-layer only |
| `frontend/src/query/keys.ts` | Phase 1A | Add `indexStatus`, `facets` keys | Data-layer only |
| `frontend/src/query/keys.ts` | Phase 3 | Add `metadataList` key, or reuse existing search keys if cleaner | Data-layer only |
| `frontend/src/types/index.ts` | Phase 1A | Add index status, facets types | Data-layer only |
| `frontend/src/types/index.ts` | Phase 2 | Add fielded search types | Data-layer only |
| `frontend/src/types/index.ts` | Phase 3 | Add `MetadataListRow` type if normalization needs a shared type | Data-layer only |
| `frontend/src/components/AppHeader.vue` | Phase 1B | IndexStatusChip (desktop-only) | Must not affect mobile/tablet |
| `frontend/src/components/AppHeader.vue` | Phase 2 | AdvancedSearch trigger, SearchFilterChips (desktop) | Desktop-only |
| `frontend/src/components/AppHeader.vue` | Phase 3 | Small Metadata nav entry | Desktop-only |
| `frontend/src/components/GalleryGrid.vue` | Phase 1C | `role="alert"` on error banner (desktop-safe only) | Frozen for behavior/layout/virtualization |
| `frontend/src/components/GalleryGrid.vue` | Phase 2 | SearchFilterChips integration | Frozen for behavior/layout/virtualization |
| `frontend/src/components/SettingsModal.vue` | Phase 1C | Header/Body/Footer structure, ARIA roles | Desktop-safe only. No mobile behavior changes. |
| `frontend/src/components/SettingsModal.vue` | Future | Tabs + TanStack Form only if staged backend configuration is added | Not Phase 3 MVP |
| `frontend/src/components/RootPathSheet.vue` | Future Mobile/Tablet Spec | Structure refactor, loading state, ARIA | Deferred to future Mobile/Tablet Spec |
| `frontend/src/components/ToastItem.vue` | Phase 1C | `role="alert"` | Desktop-safe only |
| `frontend/src/components/FolderTreeItem.vue` | Phase 1C | TreeView ARIA roles | Desktop-safe only |
| `frontend/src/components/LightboxMobileSheet.vue` | Future Mobile/Tablet Spec | Tab ARIA roles | Deferred to future Mobile/Tablet Spec |
| `frontend/src/App.vue` | Phase 3 | MetadataList view switching while keeping GalleryGrid as the default | Desktop-only |

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
| `frontend/tests/metadata-list.spec.ts` | Phase 3 |
| `frontend/tests/gallery-grid-unchanged.spec.ts` | Phase 3 |

---

## 18. Final Recommendation

### Implementation Order

1. **Phase 1 first (desktop-only)** — Expose the backend indexing/facets capabilities that already exist. Standardize desktop UI structure before adding complexity. This phase has the lowest risk (purely additive components; Phase 1 should not change GalleryGrid behavior, layout, virtualization, image loading, or browsing semantics) and immediately makes the app feel more "aware" of its background processing. Users gain visibility into what the backend is doing. Mobile and tablet are frozen.

2. **Phase 2 second (desktop-first)** — Unlock the powerful fielded search that the backend already supports. TanStack Form is the correct tool for this and justifies the existing installation. The AdvancedSearchDrawer + SearchFilterChips provide a discoverable interface for 30+ search fields that currently require manual query construction. Mobile/tablet advanced search deferred to separate spec.

3. **Phase 3 last (desktop-first)** — Lightweight Metadata List / Library Inspector. A read-only utility view that reuses the existing search API. The smallest dependency surface — no TanStack Table required for the MVP. Explicitly excludes admin cockpit, duplicate finder, broken image scanner, watcher/refresh panels, and batch operations. Mobile/tablet deferred.

### Risk/Reward Balance

- **Phase 1**: Lowest risk (desktop-only, mobile/tablet frozen), immediate UX value. Visibility into background indexing is the single biggest missing piece.
- **Phase 2**: Medium risk (new TanStack Form usage, desktop-first), high reward. Fielded search turns an invisible backend capability into a primary user feature.
- **Phase 3**: Low risk (reuses existing search API, no new dependencies, read-only), moderate reward. Metadata List gives power users a compact way to inspect indexed metadata while keeping GalleryGrid as the primary browsing experience.

### What Makes This Different

This is not a generic UI modernization plan. Every recommendation is grounded in specific backend capabilities, specific frontend gaps, and specific code locations discovered through audit. The three phases correspond directly to the three DT/Immich adaptation phases already completed on the backend:

- Backend Phase 1 (indexer, batch writer, index status) → Frontend Phase 1 (index visibility, UI standardization) — desktop-only
- Backend Phase 2B (fielded search, DB-first metadata) → Frontend Phase 2 (advanced search, faceted discovery) — desktop-first
- Backend Phase 3 (warm listing, watcher, facets) → Frontend Phase 3 (Metadata List / Lightweight Library Inspector) — desktop-first
