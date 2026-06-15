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
| Faceted search/advanced search | Yes (`/api/facets`, `facets.py:248`; fielded parser with 30+ fields) | Phase 2 complete for desktop Advanced Search; Library Inspector reuses the same fielded syntax rather than creating a parallel filter UI |
| Watcher/refresh status | Yes (`get_watcher_status()`, `get_refresh_status()` exist) | No HTTP endpoints wired; no frontend exposure possible |
| Library Inspector | Partial — indexed metadata exists, but no inspector list/detail endpoints yet | Not built; Phase 3 adds `/metadata`, inspector list/detail APIs, TanStack Query, and TanStack Table |
| TanStack Vue Form for advanced search/settings | Installed (v1.33.0) | Used for Phase 2 Advanced Search; future settings/editing workflows remain separate |

### Why a frontend control/visibility layer is needed

DT/Immich-style background jobs (indexing, watcher, search caching) require user-visible status and progress. Without it:
- Users cannot tell if indexing is running, complete, or failed.
- The powerful fielded search parser is now exposed through Phase 2 Advanced Search and must also be reused by Phase 3 Library Inspector.
- Facets data is computed on the backend and belongs to the Phase 2 advanced-search UX, not the Phase 3 inspector MVP.
- TanStack Table is now appropriate for the Phase 3 Library Inspector MVP because the feature is a bounded metadata table with sortable columns and structured row rendering.

### Where TanStack Table/Form fit

- **TanStack Vue Form**: Strong fit for AdvancedSearchDrawer (fielded search with validation, Apply/Cancel/Reset). Future settings or editing workflows may use it only after backend and UX prerequisites exist.
- **TanStack Vue Table**: Use for the Phase 3 Library Inspector MVP: column definitions, sorting state, row model, bounded rows, and clean cell rendering. Do not use it for GalleryGrid.
- **Neither should be used** for: main GalleryGrid (photo browsing), simple search input, toast, or lightbox metadata panel.

### Which shadcn-vue patterns should be adapted

- **Command palette pattern** for search/quick-command UX.
- **Dialog** for desktop settings/modal structure.
- **Drawer/Sheet** for mobile settings, mobile advanced search, and mobile index panel are future-only patterns, explicitly excluded from Phase 1. Phase 1 may only adapt desktop-safe Badge + Popover/Dialog patterns.
- **Popover** for index status details, filter mini-panels.
- **DropdownMenu** for search scope and toolbar actions.
- **Data Table** for Phase 3 Library Inspector and future backend-backed metadata/diagnostics tables. Use neutral shadcn-style table chrome, not gallery warm/premium styling.
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
| Library Inspector listing/detail | **Missing endpoints** — indexed rows exist in `file_index` + `image_metadata`, but `/api/search?q=` intentionally returns empty | **Missing** — add `fetchLibraryInspector()` and `fetchLibraryInspectorMetadata()` | **Missing** — no `/metadata` route/view | Add read-only `/api/library/inspector` list and `/api/library/inspector/metadata` detail endpoints, sharing Phase 2 fielded parser/query semantics where possible | P3 |
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
| `/api/library/inspector` | `LibraryInspectorResponse`, `LibraryInspectorRow` | `fetchLibraryInspector()` | `useLibraryInspectorQuery()` | **New Phase 3 list endpoint.** Empty `q` returns latest indexed metadata rows; optional `q` supports free text plus shared Phase 2 fielded syntax (`prompt:`, `negative:`, `model:`, `sampler:`, `seed:`, `date:`, `folder:`, `lora:`, `resource:`, `resource_hash:`). This endpoint must not change `/api/search?q=` empty-query behavior. |
| `/api/library/inspector/metadata` | `LibraryInspectorMetadataResponse` | `fetchLibraryInspectorMetadata(path)` | `useLibraryInspectorMetadataQuery(path, enabled)` | **New Phase 3 detail endpoint.** Reads prompt/negative/LoRA/resource detail from indexed DB metadata by `path`; must not synchronously parse original image files during Popover open. |
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
| **Future: LibraryInspector** | Does not exist | — | TanStack Table + shadcn table/popover/dropdown patterns | **Add desktop-only `/metadata` route with read-only metadata inspection table** backed by `/api/library/inspector` and detail-on-demand metadata endpoint. See Phase 3. | Phase 3. |

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
| **LibraryInspector** | **YES** | Phase 3 is a bounded metadata inspection table. TanStack Table should own column definitions, sorting state, row model, bounded rows, and clean shadcn-compatible cell rendering. | Do not turn this into a full admin/data-management surface: no row selection, batch actions, column customization, or server-side pagination in MVP. Client-side sorting only sorts returned rows. | Phase 3 |
| **Future paginated metadata table** | **YES (conditional)** | If the backend later exposes cursor/pagination and server-side sorting, TanStack Table can extend the same table architecture. | Backend pagination/cursors and server-side sorting are not MVP. | Future (backend prerequisite) |
| **Future diagnostics/audit tables** | **YES (conditional)** | Row-level index errors, metadata parse errors, duplicate candidates, and broken-image scan results would be structured table data if the backend exposes them. | Current backend does not expose row-level diagnostics, per-job errors, duplicate data, or broken-image data. | Future (backend prerequisite) |
| **Facets Table** | **NO** | Facets are better rendered as chips/tokens with counts, not as a table. A table would waste space on what is essentially a filter UI. | Use Badge/Popover pattern for facets, not TanStack Table. | Never |
| **Main GalleryGrid** | **NO (hard rule)** | GalleryGrid is a visual photo browsing experience using TanStack Virtual and CSS Grid. It shows image thumbnails, not tabular data. | TanStack Table would replace thumbnails with text rows, destroy the visual browsing experience, and conflict with virtual scrolling architecture. | Never |

### Mandatory Conclusions

- **Main GalleryGrid MUST NOT use TanStack Table.** It is a visual photo browser, not a data table. TanStack Virtual is the correct technology for this component.
- **LibraryInspector SHOULD use TanStack Table for the MVP.** It is a real metadata table, but it remains bounded, read-only, and secondary to GalleryGrid.
- **TanStack Virtual is deferred for LibraryInspector.** Keep the table architecture virtual-ready, but do not enable virtualization until the inspector intentionally renders many rows or moves to infinite/paginated large-result browsing.

---

## 7. shadcn-vue Pattern Mapping

| shadcn-vue Pattern | Gallery Use Case | Adaptation Approach |
|---|---|---|
| **Command** | Search suggestions, quick command palette (e.g., "Go to folder...", "Search by model...") | Adapt the keyboard-navigable list + filter pattern. Standard UI chrome uses shadcn-vue Stone defaults. Bind to existing search store and folder navigation. |
| **Dialog** | Desktop SettingsModal, Index Status detail view | SettingsModal now uses the shadcn Dialog component (migrated in Tailwind Phase 1.5/2B). A search filter panel with form fields (Advanced Search on desktop) should use a Side Sheet, not a Dialog per MD3. |
| **Drawer / Sheet** | Mobile Settings (sheet), Advanced Search (mobile: bottom sheet; desktop: side sheet), Index Status (mobile), RootPathSheet | Existing `RootPathSheet` already has sheet-like behavior. Standardize the Header/Description/Footer pattern. Use existing VSBS for metadata sheet; do not replace it. New sheets (advanced search, index panel) should follow the same structure. **Future-only. All mobile/tablet Drawer/Sheet uses excluded from Phase 1.** |
| **Popover** | Index status details, long path reveal/copy, prompt/negative detail, LoRA/resource detail | Use Popover for interactive long metadata previews. Do not put copy buttons or long metadata in Tooltip. Prompt/LoRA popovers fetch detail on demand via TanStack Query and must be DB-first/index-first. |
| **DropdownMenu** | Search scope, sort options, density grid options, toolbar actions menu, LibraryInspector row actions | Use DropdownMenu for row actions: open image, copy path, copy seed, copy prompt/negative, copy LoRA list/resource hashes, copy full metadata. Avoid many repeated icon buttons in every row. |
| **Data Table** | Phase 3 LibraryInspector; future backend-backed metadata/diagnostics tables | LibraryInspector should use TanStack Table with shadcn-compatible table chrome: neutral borders, muted text, hover/focus states, Skeleton loading, empty/error states. Do not use gallery warm/premium card styling for the metadata table. |
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

### Phase 3 — Library Inspector (`/metadata`, Desktop-First MVP)

**Goal:** Add a read-only desktop `LibraryInspector` route for inspecting, searching, and sorting indexed AI photo metadata. This is a secondary metadata utility for power users, not an admin cockpit and not a replacement for GalleryGrid.

**Why:** `/api/search` is the visual GalleryGrid/Advanced Search endpoint and intentionally returns no results for empty `q`. Library Inspector needs different empty-query behavior and a metadata-oriented row shape. The new inspector APIs should share Phase 2 fielded-search semantics where possible while keeping their payloads optimized for metadata inspection.

**Product split:** `GalleryGrid` = visual photo browsing. `LibraryInspector` = metadata inspection. Phase 3 must not replace, modify, or table-ify GalleryGrid.

**Mobile/tablet constraint:** Mobile/tablet Library Inspector is deferred. The `/metadata` navigation entry is desktop-only unless a later mobile/tablet spec defines a clean supported pattern.

#### Backend/API Contract

- [ ] **Add read-only list endpoint `GET /api/library/inspector`**:
  - Purpose: bounded metadata listing for `LibraryInspector`; do not change `/api/search?q=` empty-query behavior.
  - Query params: `q` (optional), `scope=current|all` (default `all`), `path` (for `scope=current`), `limit` (1-200, default 200).
  - Empty or missing `q`: return latest indexed metadata rows ordered recent-first, preferably `mtime_desc`.
  - Non-empty `q`: support free text and shared Phase 2 fielded syntax where applicable, including `prompt:`, `negative:`, `model:`, `sampler:`, `seed:`, `date:`, `folder:`, `lora:`, `resource:`, and `resource_hash:`.
  - Reuse the existing backend fielded-search parser/query builder used by `/api/search`; do not implement a second independent parser.
  - Data source: indexed DB tables (`file_index` + `image_metadata`) joined by `path`; include rows when core file data exists even if optional metadata is missing.
  - Response wrapper: `{ root, scope, query, limit, total_indexed, returned, truncated, sort: "mtime_desc", rows }`.
  - `LibraryInspectorRow`: `path`, `name`, `folder`, `relative_path`, `mtime`, `width`, `height`, `model`, `tool`, `sampler`, `seed`, `prompt_preview`, `has_prompt`, `has_negative`, `has_lora`, `lora_count`, `lora_preview`, `metadata_detail_available`.
  - Keep list rows lightweight: no full prompt, negative prompt, raw metadata, or full LoRA/resource metadata. `prompt_preview` should be short and safe for table display (about 100-160 chars).
  - Apply the same path-safety/stale cleanup filtering used by `/api/search`.

- [ ] **Add DB-first detail endpoint `GET /api/library/inspector/metadata?path=<encoded_path>`**:
  - Called only when the user opens prompt/LoRA/path metadata UI or chooses copy metadata actions.
  - Response: `path`, `prompt`, `negative_prompt`, `raw_metadata` only if already indexed/cheap, `model`, `tool`, `sampler`, `seed`, `width`, `height`, `mtime`, `loras`, `resources`.
  - LoRA/resource entries include name, hash/resource_hash, and weight/strength when available.
  - Must read full prompt/negative/LoRA/resource detail from indexed DB metadata; must not synchronously parse original image files during Popover open.
  - If DB metadata is missing, return a clear unavailable / needs-index state.

#### Frontend Route, Data Layer, and Table

- [ ] **Add a real desktop `/metadata` route/view**:
  - The current frontend does not show an existing Vue Router setup. Phase 3 should add minimal Vue Router support to satisfy the `/metadata` + `RouterLink` decision.
  - Route `/` keeps the existing gallery experience.
  - Route `/metadata` renders `LibraryInspector` in the desktop layout.
  - Mobile/tablet route behavior can redirect to the gallery or show a deferred/unsupported state; do not add mobile/tablet navigation in MVP.

- [ ] **Add desktop AppHeader button**:
  - Label: `Metadata`.
  - Icon: `Table2`.
  - Pattern: `Button as-child` with `RouterLink to="/metadata"`.
  - Inactive variant: `ghost`.
  - Active variant: `secondary` plus `aria-current="page"`.
  - Desktop-only; do not import into `MobileHeader.vue` or `TabletHeader.vue`.

- [ ] **Add frontend data layer**:
  - Types: `LibraryInspectorRow`, `LibraryInspectorResponse`, `LibraryInspectorMetadataResponse`.
  - API helpers: `fetchLibraryInspector({ q, scope, path, limit })`, `fetchLibraryInspectorMetadata(path)`.
  - Query keys: `queryKeys.libraryInspector(...)`, `queryKeys.libraryInspectorMetadata(path)`.
  - Composables: `useLibraryInspectorQuery()` for the list and `useLibraryInspectorMetadataQuery(path, enabled)` for Popover/detail fetches.
  - Use TanStack Query for both list fetches and detail metadata fetches.

- [ ] **Use `@tanstack/vue-table` for `LibraryInspector`**:
  - Use TanStack Table for column definitions, sorting state, filtering/search state where appropriate, row model, bounded rows, and clean cell rendering.
  - Do not use TanStack Table in GalleryGrid.
  - Do not enable TanStack Virtual for MVP; keep the table architecture virtual-ready. Add `@tanstack/vue-virtual` only if a later version intentionally renders many rows or moves to infinite/paginated large-result browsing.

#### MVP Table UI

- **Default columns**:
  - thumbnail
  - filename/title
  - compact folder/path
  - model/tool
  - seed
  - dimensions
  - modified date
  - prompt preview
  - actions

- **Model cell decision**:
  - Primary line: model/checkpoint/tool, for example `SDXL`.
  - Secondary compact Badge/line: `LoRA` or `LoRA N` if LoRA/resource metadata exists.
  - Do not show `sampler` as the default visible secondary line under model.
  - `sampler` may remain in API/detail payload and may appear in detail/full metadata copy or as a future optional/hidden column.

- **Prompt/negative UX**:
  - Prompt and negative prompt are core AI metadata; prompt and negative search are required.
  - Prompt sorting is not required; do not add a sortable prompt header in MVP.
  - Use one compact `Prompt` column with one-line truncated `prompt_preview`.
  - Do not render full prompt/negative text as default columns.
  - Do not show `P` / `N` badges in the prompt cell.
  - Clicking the prompt preview opens a shadcn-vue `Popover` that fetches detail via TanStack Query.
  - Popover shows loading Skeleton, full prompt, negative prompt if available, `Copy prompt`, `Copy negative`, and `Copy full metadata`.
  - If no prompt metadata exists, show a compact muted state such as `No prompt metadata`.

- **LoRA/resource UX**:
  - `lora:`, `resource:`, and `resource_hash:` queries must work if supported by the shared Phase 2 parser.
  - List rows include `has_lora`, `lora_count`, and `lora_preview`; do not return full LoRA/resource/raw metadata in every row.
  - Clicking `LoRA` / `LoRA N` opens a shadcn-vue `Popover` backed by the DB-first detail endpoint.
  - Popover actions: `Copy LoRA list`, `Copy resource hashes`, `Copy full metadata`.

- **Path UX**:
  - Do not render full absolute paths as a wide default column.
  - Prefer filename as primary text and relative parent folder as muted/truncated secondary text, with an optional compact folder column if needed.
  - Full path appears in an interactive shadcn-vue `Popover`, with `Copy full path`.
  - Do not rely only on Tooltip for path because path actions are interactive.

- **Long-text truncation rule**:
  - Long-text cell wrapper: `min-w-0 max-w-full overflow-hidden`.
  - Trigger/button: `block w-full min-w-0 max-w-full overflow-hidden text-left`.
  - Inner text: `block w-full min-w-0 max-w-full truncate`.
  - Do not put `truncate` only on the inner span if the parent button/cell can still expand.

- **shadcn-vue UI standard**:
  - Use shadcn-compatible Table/Input/Button/DropdownMenu/Badge/Skeleton/Tooltip/Popover patterns.
  - Table chrome should be neutral/shadcn-style: standard spacing, radius, border, muted text, hover, focus-visible, loading, empty, and error states.
  - Use `Popover` for interactive long path, prompt, and LoRA metadata.
  - Use `DropdownMenu` for row actions such as open image, copy path, copy seed, copy prompt, copy negative, copy LoRA list, copy resource hashes, and copy full metadata.
  - Use `Tooltip` only for short non-interactive hints.
  - Do not use `HoverCard` for click-to-copy metadata interactions.
  - Avoid bespoke CSS except for layout/truncation/future virtualization. Do not introduce decorative gallery card styling into the metadata table.

#### Sorting, Search, and Interaction Rules

- MVP has one `q` input only. It supports free text and Phase 2 fielded syntax through the shared parser.
- Do not add separate facet chips/filter UI in MVP. Do not rebuild a parallel filter system inside Library Inspector.
- Sorting should focus on useful columns: modified date, filename, model, seed, and dimensions. Sampler may be future/optional. Prompt sorting is not required.
- If sorting is client-side, document and implement it as sorting only the returned row set. For example, sorting after `/api/library/inspector?limit=100` or `limit=200` sorts only those returned rows, not the whole library.
- Full-library sorting requires future server-side sorting plus pagination/cursor support.
- Row click selects/focuses the row. Thumbnail click or explicit Open action opens the existing image/lightbox flow if supported cleanly.
- Copy path/seed/prompt/negative/LoRA/resource hashes/full metadata must be explicit through row `DropdownMenu` or the prompt/path/LoRA Popover.
- Do not add complex up/down table keyboard navigation in MVP; rely on native keyboard accessibility for inputs, buttons, popover triggers, dropdown items, and sortable headers.

#### Strict Non-Goals

- Do not replace or modify GalleryGrid.
- Do not turn the main photo browsing experience into a table.
- Do not add duplicate finder, broken image scanner, audit dashboard, watcher controls, refresh controls, batch delete, batch move, batch metadata editing, destructive actions, or admin cockpit features.
- Do not add server-side pagination/cursors, full-library sorting, column customization, row selection, bulk actions, or TanStack Virtual in MVP.

#### Files Affected (Phase 3)

| File | Change |
|---|---|
| `backend/metadata_store.py` | Add DB-backed inspector list/detail query helpers that reuse shared fielded-search SQL/parser building blocks where possible |
| `backend/search.py` | Add `GET /api/library/inspector` and `GET /api/library/inspector/metadata` |
| `frontend/src/router/index.ts` | New minimal Vue Router setup for `/` and `/metadata` |
| `frontend/src/main.ts` / `frontend/src/App.vue` | Install/render router while preserving existing app shell behavior |
| `frontend/src/components/LibraryInspector.vue` | New desktop read-only metadata inspector table |
| `frontend/src/composables/useLibraryInspectorQuery.ts` | TanStack Query wrapper for `/api/library/inspector` |
| `frontend/src/composables/useLibraryInspectorMetadataQuery.ts` | TanStack Query wrapper for detail metadata endpoint |
| `frontend/src/services/api.ts` | Add `fetchLibraryInspector()` and `fetchLibraryInspectorMetadata()` |
| `frontend/src/query/keys.ts` | Add `libraryInspector` and `libraryInspectorMetadata` keys |
| `frontend/src/types/index.ts` | Add `LibraryInspectorRow`, `LibraryInspectorResponse`, and `LibraryInspectorMetadataResponse` |
| `frontend/src/components/AppHeader.vue` | Add desktop-only `Metadata` RouterLink button using `Table2` |

#### Risk Assessment (Phase 3)

- **Medium risk.** Phase 3 adds one route, two read-only APIs, and a real table surface, but stays bounded and read-only.
- Main UX risk: users may assume client-side sorting is full-library sorting. Mitigation: document capped results and only claim sorting over returned rows.
- Main backend risk: accidentally duplicating fielded parser logic. Mitigation: reuse Phase 2 parser/query builder semantics wherever possible and cover shared field examples in tests.
- Main performance risk: Popovers triggering expensive file parsing. Mitigation: DB-first/index-first detail endpoint only; missing metadata returns unavailable / needs-index state.
- GalleryGrid remains unchanged and continues to be the primary visual browsing surface.

#### Acceptance Criteria (Phase 3)

1. `/metadata` renders a real desktop `LibraryInspector` view, not a placeholder.
2. Desktop AppHeader shows a `Metadata` button using `Button as-child`, `RouterLink to="/metadata"`, `Table2`, inactive `ghost`, active `secondary`, and `aria-current="page"`.
3. `GET /api/library/inspector?scope=all&limit=200` returns latest indexed metadata rows when `q` is empty; `/api/search?q=` remains empty by design.
4. Inspector list search reuses shared fielded semantics for prompt, negative, model, sampler, seed, date, folder, lora, resource, and resource_hash where applicable.
5. List response is lightweight and includes `prompt_preview`, `has_prompt`, `has_negative`, `has_lora`, `lora_count`, `lora_preview`, and `metadata_detail_available`.
6. `GET /api/library/inspector/metadata?path=...` returns prompt/negative/LoRA/resource detail from indexed DB metadata and does not synchronously parse original image files.
7. LibraryInspector uses TanStack Query for list/detail fetches and TanStack Table for column definitions, sorting state, and row model.
8. TanStack Virtual is not enabled in MVP.
9. Default model cell shows model/tool primary text and LoRA summary when available; sampler is not a default visible secondary line.
10. Prompt preview and path text truncate at wrapper, trigger, and inner text levels and cannot stretch the table or bleed into adjacent columns.
11. Prompt and LoRA Popovers fetch detail on demand and expose safe copy actions.
12. Client-side sorting works over returned rows for modified date and filename; prompt sort is not required.
13. GalleryGrid remains untouched and is not replaced by a table.
14. No admin/destructive/batch/audit/watcher/refresh features are introduced.
15. New tests pass and typecheck/build pass.

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
| `LibraryInspector` | Desktop-only `Metadata` button in `AppHeader.vue`, implemented as `Button as-child` + `RouterLink to="/metadata"` + `Table2`; active state uses `variant="secondary"` and `aria-current="page"` |
| `FacetsPanel` | Inside Advanced Search only for MVP; Library Inspector facet UI is deferred |
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

- [x] Advanced Search uses TanStack Form only for the complex form.
- [x] Form state serializes to backend-compatible `q`.
- [x] Existing `unifiedSearch()` path is used.
- [x] Plain text search still works.
- [x] Filter chips can remove individual filters.
- [x] Reset/Cancel/Apply behavior is clear.
- [x] Query serializer tests pass.

### Phase 3 Done when:

- [ ] `/metadata` renders a real desktop `LibraryInspector` route/view.
- [ ] Desktop AppHeader has a `Metadata` RouterLink button with correct active/inactive state.
- [ ] `GET /api/library/inspector` exists and returns latest indexed metadata rows for empty `q`.
- [ ] `GET /api/library/inspector/metadata?path=...` returns DB-first prompt/negative/LoRA/resource detail.
- [ ] LibraryInspector renders columns from `LibraryInspectorResponse.rows` using TanStack Table.
- [ ] GalleryGrid is not replaced by a table.
- [ ] Search supports free text plus shared fielded syntax for prompt, negative, model, sampler, seed, date, folder, lora, resource, and resource_hash where applicable.
- [ ] Returned-row sorting works for modified date and filename; prompt sorting is not required.
- [ ] Prompt/path/LoRA long text truncates safely and does not stretch the table.
- [ ] Prompt and LoRA Popovers fetch detail on demand.
- [ ] Copy path, seed, prompt, negative, LoRA list, resource hashes, and full metadata work.
- [ ] No admin cockpit features are introduced.
- [ ] Backend prerequisites are clearly documented for deferred admin features.
- [ ] LibraryInspector tests pass.

---

## 14. Backend Prerequisites Backlog

Purpose: Separate the Phase 3 Library Inspector MVP from future features that require backend data first. Do not ask the frontend to build diagnostics, duplicate, broken-image, watcher/refresh, pagination, full-library server-side sorting, virtualized large-result browsing, or editing workflows before the backend exposes the required row-level data and write endpoints.

Phase 3 adds bounded read-only `/api/library/inspector` and DB-first `/api/library/inspector/metadata` endpoints. The backend still does NOT expose row-level diagnostics, per-job errors, duplicate/broken-image data, pagination cursors, or inspector server-side sorting beyond default `mtime_desc`.

| Possible Future Endpoint | Deferred Feature | Why It Is Not Phase 3 MVP |
|---|---|---|
| Dedicated paginated metadata listing endpoint | Server-side metadata browsing at library scale | MVP uses bounded `/api/library/inspector` results with no pagination controls |
| Inspector server-side sort params | Server-side sort over full indexed library | MVP supports client-side single-sort over returned rows only |
| Inspector cursor/infinite browsing | Large-result browsing | MVP renders 100-200 bounded rows and defers TanStack Virtual |
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
| Library Inspector result set is too small for large libraries | Phase 3 | MVP fetches up to 200 rows through `/api/library/inspector`. Add pagination and server-side sorting later if users need larger library-wide inspection. |
| Users mistake returned-row sorting for full-library sorting | Phase 3 | Label/result copy and docs must state client-side sorting applies only to returned rows. Full-library sort requires future server-side sort plus pagination/cursors. |
| Library Inspector duplicates fielded search parser logic | Phase 3 | Reuse Phase 2 parser/query builder where possible. Add tests for shared prompt/negative/model/sampler/seed/date/folder/LoRA/resource semantics. |
| Prompt/LoRA Popovers trigger expensive file parsing | Phase 3 | Detail endpoint must be DB-first/index-first. If indexed metadata is missing, return unavailable / needs-index instead of parsing originals in the UI path. |
| Long prompt/path/LoRA text stretches the table | Phase 3 | Enforce truncation at cell wrapper, trigger/button, and inner text span. Add visual checks for no bleed into adjacent columns. |
| Over-engineering settings with TanStack Form too early | Phase 1/Future | Keep current v-model approach for SettingsModal in Phase 1. Only introduce TanStack Form when staged settings and backend configuration endpoints exist. |
| Breaking plain text search when adding Advanced Search | Phase 2 | Keep plain search input completely separate. AdvancedSearchDrawer is opt-in. Plain search regression tests guard this. |
| Accessibility regression from new components | All Phases | Add ARIA roles in Phase 1 accessibility fixes. New components follow the established patterns. Test with `role` assertions. |
| bfcache/lifecycle regressions on iOS Safari | All Phases | Keep global TanStack Query `refetchOnWindowFocus: false`. Index status may use a local, debounced refetch-on-focus/pageshow/visibilitychange if needed, but must not re-enable noisy global refetches. No `beforeunload`/`unload` listeners. Test mobile sheet behavior. |

**Lesson from failed Phase 1 attempt:** Mobile/tablet headers are high-risk surfaces. Even small status chips can break real iPhone Safari layout and touch behavior. Playwright/Chromium viewport tests are not enough to prove iPhone Safari safety.

Therefore, Phase 1 is desktop-only. Real-device Safari testing is mandatory before any future mobile/tablet implementation.

### Non-Goals (Explicitly Excluded)

- **Do not rewrite the whole UI into shadcn-vue.** Adapt patterns for structure, accessibility, and keyboard behavior. Standard UI uses shadcn-vue Stone defaults; gallery warm/premium styling is reserved for brand and explicitly approved artwork surfaces.
- **Do not replace GalleryGrid with a table.** GalleryGrid uses TanStack Virtual for visual photo browsing. Library Inspector is a secondary utility view, not the primary browsing UI.
- **Phase 3 is NOT an admin cockpit.** No duplicate finder, no broken image scanner, no audit dashboard, no watcher/refresh controls, no destructive actions, and no batch operations.
- **Do not use TanStack Virtual in the MVP.** TanStack Table is required for LibraryInspector, but virtualization is deferred until there is a large-result/infinite browsing requirement.
- **Do not add facet chips or a parallel filter system inside LibraryInspector.** The MVP has one `q` input using shared fielded syntax; Advanced/facet UI belongs to Phase 2.
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
| `/metadata` route renders | Phase 3 | Route renders real `LibraryInspector`, not a placeholder |
| Desktop Metadata button | Phase 3 | Button appears on desktop, uses `RouterLink to="/metadata"`, `Table2`, inactive `ghost`, active `secondary`, and `aria-current="page"` |
| Library Inspector endpoint empty query | Phase 3 | `GET /api/library/inspector?scope=all&limit=200` returns latest indexed metadata rows; `/api/search?q=` still returns empty |
| Library Inspector shared parser semantics | Phase 3 | `q` supports prompt, negative, model, sampler, seed, date, folder, lora, resource, and resource_hash using shared Phase 2 semantics where applicable |
| Library Inspector list response is lightweight | Phase 3 | List rows do not include full prompt/negative/raw/LoRA metadata and do include `prompt_preview`, `has_prompt`, `has_negative`, `has_lora`, `lora_count`, `lora_preview`, and `metadata_detail_available` |
| Library Inspector detail endpoint DB-first | Phase 3 | Detail fetch returns prompt/negative/LoRA/resource data from indexed DB metadata and does not synchronously parse original image files |
| LibraryInspector renders columns and data | Phase 3 | Thumbnail, filename, compact folder/path, model/tool with LoRA summary, seed, dimensions, modified date, prompt preview, and actions render from mocked `fetchLibraryInspector()` results |
| LibraryInspector sorting by returned rows | Phase 3 | Modified date and filename sorting reorder only the returned row set; prompt sort is not required |
| LibraryInspector query input | Phase 3 | One `q` input calls the inspector endpoint and narrows returned rows without separate facet UI |
| Prompt and path truncation | Phase 3 | Prompt preview and path text stay one-line/truncated and do not stretch table or bleed into adjacent columns |
| Prompt Popover detail-on-demand | Phase 3 | Clicking prompt preview opens Popover, shows loading Skeleton, fetches detail, and exposes Copy prompt / Copy negative / Copy full metadata |
| LoRA Popover detail-on-demand | Phase 3 | Clicking `LoRA` / `LoRA N` opens Popover, fetches detail, and exposes Copy LoRA list / Copy resource hashes / Copy full metadata |
| LibraryInspector row actions | Phase 3 | Safe row DropdownMenu actions work: open image, copy path, copy seed, copy prompt/negative, copy full metadata |
| LibraryInspector excludes admin controls | Phase 3 | No row selection, select-all checkbox, batch toolbar, column visibility toggle, facets, density control, audit dashboard, watcher/refresh controls, or destructive actions |
| GalleryGrid unchanged | Phase 3 | Existing GalleryGrid tests pass without modification |

### Integration/E2E Tests

| Test | Phase | Description |
|---|---|---|
| Desktop AdvancedSearchDrawer opens/closes | Phase 2 | Slide-over panel behavior on desktop breakpoint |
| Full search flow: plain → advanced → filter chip removal → plain | Phase 2 | End-to-end search state transitions |
| LibraryInspector → lightbox round-trip | Phase 3 | Click thumbnail or Open action opens lightbox using current visible rows; close returns to `/metadata` |

### Performance Tests

| Test | Phase | Assertion |
|---|---|---|
| Album-open perf unchanged | All | Scan p95, first thumbnail, thumbnail p95 within existing budgets |
| Lightbox perf unchanged | All | Visible time, preview loaded time within existing budgets |
| LibraryInspector render time with 200 rows | Phase 3 | Initial render under 500ms |

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
| LibraryInspector sortable headers accessible via keyboard | Phase 3 | Enter/Space on sortable header triggers sort |
| LibraryInspector Popover/Dropdown accessibility | Phase 3 | Prompt/path/LoRA Popover triggers and row DropdownMenu items are keyboard reachable with visible focus |

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
| `frontend/src/router/index.ts` | Phase 3 | Minimal Vue Router setup for `/` and `/metadata` |
| `frontend/src/components/LibraryInspector.vue` | Phase 3 | Desktop read-only Library Inspector using TanStack Table |
| `frontend/src/composables/useLibraryInspectorQuery.ts` | Phase 3 | TanStack Query wrapper for `/api/library/inspector` |
| `frontend/src/composables/useLibraryInspectorMetadataQuery.ts` | Phase 3 | TanStack Query wrapper for `/api/library/inspector/metadata` |

### Modified Files

| File | Phase | Description | Constraint |
|---|---|---|---|
| `frontend/src/services/api.ts` | Phase 1A | Add `fetchIndexStatus()`, `fetchFacets()` | Data-layer only |
| `frontend/src/query/keys.ts` | Phase 1A | Add `indexStatus`, `facets` keys | Data-layer only |
| `backend/metadata_store.py` | Phase 3 | Add DB-backed inspector list/detail helpers over `file_index` + `image_metadata`, reusing shared fielded-search parser/query builder where possible | Read-only |
| `backend/search.py` | Phase 3 | Add `GET /api/library/inspector` and `GET /api/library/inspector/metadata` | Read-only |
| `frontend/package.json` | Phase 3 | Add `vue-router` if not already installed when implementing the required `/metadata` route | Routing dependency only |
| `frontend/src/main.ts` | Phase 3 | Install Vue Router alongside Pinia and Vue Query | App shell only |
| `frontend/src/App.vue` | Phase 3 | Render router-compatible shell while preserving existing gallery behavior | Must not change mobile/tablet runtime |
| `frontend/src/services/api.ts` | Phase 3 | Add `fetchLibraryInspector()` and `fetchLibraryInspectorMetadata()` | Data-layer only |
| `frontend/src/query/keys.ts` | Phase 3 | Add `libraryInspector` and `libraryInspectorMetadata` keys | Data-layer only |
| `frontend/src/types/index.ts` | Phase 1A | Add index status, facets types | Data-layer only |
| `frontend/src/types/index.ts` | Phase 2 | Add fielded search types | Data-layer only |
| `frontend/src/types/index.ts` | Phase 3 | Add `LibraryInspectorRow`, `LibraryInspectorResponse`, and `LibraryInspectorMetadataResponse` types | Data-layer only |
| `frontend/src/components/AppHeader.vue` | Phase 1B | IndexStatusChip (desktop-only) | Must not affect mobile/tablet |
| `frontend/src/components/AppHeader.vue` | Phase 2 | AdvancedSearch trigger, SearchFilterChips (desktop) | Desktop-only |
| `frontend/src/components/AppHeader.vue` | Phase 3 | Desktop-only `Metadata` RouterLink button using `Button as-child`, `Table2`, active/inactive variants | Desktop-only |
| `frontend/src/components/GalleryGrid.vue` | Phase 1C | `role="alert"` on error banner (desktop-safe only) | Frozen for behavior/layout/virtualization |
| `frontend/src/components/GalleryGrid.vue` | Phase 2 | SearchFilterChips integration | Frozen for behavior/layout/virtualization |
| `frontend/src/components/SettingsModal.vue` | Phase 1C | Header/Body/Footer structure, ARIA roles | Desktop-safe only. No mobile behavior changes. |
| `frontend/src/components/SettingsModal.vue` | Future | Tabs + TanStack Form only if staged backend configuration is added | Not Phase 3 MVP |
| `frontend/src/components/RootPathSheet.vue` | Future Mobile/Tablet Spec | Structure refactor, loading state, ARIA | Deferred to future Mobile/Tablet Spec |
| `frontend/src/components/ToastItem.vue` | Phase 1C | `role="alert"` | Desktop-safe only |
| `frontend/src/components/FolderTreeItem.vue` | Phase 1C | TreeView ARIA roles | Desktop-safe only |
| `frontend/src/components/LightboxMobileSheet.vue` | Future Mobile/Tablet Spec | Tab ARIA roles | Deferred to future Mobile/Tablet Spec |
| `frontend/src/layouts/DesktopLayout.vue` | Phase 3 | Hosts existing gallery route content; GalleryGrid remains default visual browsing surface | Desktop-only |

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
| `frontend/tests/metadata-route.spec.ts` | Phase 3 |
| `frontend/tests/library-inspector.spec.ts` | Phase 3 |
| `frontend/tests/library-inspector-metadata.spec.ts` | Phase 3 |
| `backend/tests/test_library_inspector.py` | Phase 3 |
| `frontend/tests/gallery-grid-unchanged.spec.ts` | Phase 3 |

---

## 18. Final Recommendation

### Implementation Order

1. **Phase 1 first (desktop-only)** — Expose the backend indexing/facets capabilities that already exist. Standardize desktop UI structure before adding complexity. This phase has the lowest risk (purely additive components; Phase 1 should not change GalleryGrid behavior, layout, virtualization, image loading, or browsing semantics) and immediately makes the app feel more "aware" of its background processing. Users gain visibility into what the backend is doing. Mobile and tablet are frozen.

2. **Phase 2 second (desktop-first)** — Unlock the powerful fielded search that the backend already supports. TanStack Form is the correct tool for this and justifies the existing installation. The AdvancedSearchDrawer + SearchFilterChips provide a discoverable interface for 30+ search fields that currently require manual query construction. Mobile/tablet advanced search deferred to separate spec.

3. **Phase 3 last (desktop-first)** — Library Inspector. A read-only `/metadata` route backed by `/api/library/inspector` and `/api/library/inspector/metadata`. It uses TanStack Query and TanStack Table for a bounded metadata table, reuses shared Phase 2 fielded-search semantics, supports prompt/negative/LoRA inspection, and explicitly excludes admin cockpit, duplicate finder, broken image scanner, watcher/refresh controls, facets, destructive actions, batch operations, server-side pagination, and TanStack Virtual in the MVP. Mobile/tablet deferred.

### Risk/Reward Balance

- **Phase 1**: Lowest risk (desktop-only, mobile/tablet frozen), immediate UX value. Visibility into background indexing is the single biggest missing piece.
- **Phase 2**: Medium risk (new TanStack Form usage, desktop-first), high reward. Fielded search turns an invisible backend capability into a primary user feature.
- **Phase 3**: Medium risk (new route, two read-only endpoints, TanStack Table surface, DB-first detail fetch), moderate-to-high reward. Library Inspector gives power users a compact way to inspect prompt, negative, model/tool, LoRA/resource, seed, dimensions, and file metadata while keeping GalleryGrid as the primary browsing experience.

### What Makes This Different

This is not a generic UI modernization plan. Every recommendation is grounded in specific backend capabilities, specific frontend gaps, and specific code locations discovered through audit. The three phases correspond directly to the three DT/Immich adaptation phases already completed on the backend:

- Backend Phase 1 (indexer, batch writer, index status) → Frontend Phase 1 (index visibility, UI standardization) — desktop-only
- Backend Phase 2B (fielded search, DB-first metadata) → Frontend Phase 2 (advanced search, faceted discovery) — desktop-first
- Backend Phase 3 (warm listing, watcher, facets) + Phase 2 fielded parser/DB metadata → Frontend Phase 3 (`/metadata` Library Inspector, shared search semantics, DB-first prompt/LoRA detail) — desktop-first
