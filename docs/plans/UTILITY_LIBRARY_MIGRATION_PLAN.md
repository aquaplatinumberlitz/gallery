# Utility / Library Migration Plan

**Status:** Draft
**Scope:** gallery repo frontend-first cleanup, with backend keep/decision notes
**Goal:** replace fragile self-written plumbing with already-installed libraries or standard platform APIs where it clearly reduces bug surface, improves maintainability, or prevents performance regressions.

---

## 1. Background

The repo has already benefited from replacing custom infrastructure with mature libraries or proven workflow patterns:

- Legacy custom lightbox was replaced by PhotoSwipe 5, improving smoothness and reducing UI jank.
- Image loading / metadata / scan workflow was improved by adapting proven Immich-style architecture ideas while keeping Gallery's SQLite/local-first constraints.
- Recent scan worker stale-state bug was fixed with repo-appropriate startup recovery instead of over-engineering heartbeat/Redis/BullMQ.

This plan continues the same principle:
- Replace custom infrastructure/plumbing when a mature dependency or standard API already solves it better.
- Do not replace domain-specific Gallery workflow just because a library exists.

---

## 2. Current Consensus

Three audit sources were compared:
- GPT review
- Hermes review
- OpenCode frontend audit

### Strong agreement

These areas are good migration candidates:

| Area | Replacement | Reason |
|------|-------------|--------|
| Search debounce | VueUse `refDebounced` / `useDebounceFn` | duplicated `setTimeout` / `clearTimeout` lifecycle |
| Clipboard | VueUse `useClipboard` | browser clipboard edge cases handled by library |
| Device breakpoints | VueUse `useWindowSize` / `useBreakpoints` / `useMediaQuery` | removes singleton resize listener |
| Focus trap | Reka `FocusScope` / existing Reka primitives | accessibility primitive should not be custom |
| Column resize plumbing | VueUse `useResizeObserver` / `useStorage` | replace observer/storage plumbing only |
| Natural sort frontend | `Intl.Collator({ numeric: true })` | standard Web API, no dependency |
| Axios API error mapping | Axios response interceptor | removes repeated try/catch mapping |

### Strong keep decisions

These areas should not be migrated without a concrete bug, benchmark, or feature need:

| Area | Keep | Reason |
|------|------|--------|
| PhotoSwipe glue / original-load policy | Keep custom Gallery glue | domain-specific integration |
| VSBS mobile sheet contract | Keep current non-modal contract | fragile mobile/focus behavior |
| `useScrollVisibility` full rewrite | Keep, maybe partial VueUse plumbing later | contains iOS/rubber-band/workaround logic |
| Pull-to-refresh | Keep | domain UX, nested scroll risk |
| Toast store | Keep | feature-complete, no need to add dependency |
| SQLite FTS5 search | Keep | correct for local-first app |
| Diskcache/Pillow thumbnail cache | Keep | already uses mature libraries |
| Scan worker SQLite startup recovery | Keep | correct for current architecture |
| Backend metadata parser | Keep for now | ExifTool would add external binary/process complexity |
| Admin Library table/form | Keep current shadcn/v-model | no sorting/filtering/bulk/complex form requirement yet |

---

## 3. Rules

### 3.1 Prefer existing dependencies
Use libraries already installed:
- `@vueuse/core`
- `reka-ui`
- `axios`
- PhotoSwipe / Embla / Fuse where already used
- TanStack libraries only where their feature set is justified
- **Do not add new dependencies** unless there is a strong measurable benefit.

### 3.2 Migrate plumbing, not domain workflow

**Allowed:**
- event listener lifecycle
- clipboard behavior
- debounce timers
- resize/intersection observer lifecycle
- focus trapping
- localStorage sync
- API error normalization

**Avoid:**
- rewriting metadata workflow
- rewriting thumbnail pipeline
- changing search backend
- changing PhotoSwipe original-load policy
- replacing scan worker model
- replacing UI behavior without test coverage

### 3.3 One migration per commit
Each migration should be independently reviewable.

**Bad:** `refactor: migrate all utilities to vueuse`

**Good:** `refactor: debounce search queries with refDebounced`

### 3.4 Preserve behavior first
Before changing implementation, identify the current contract and either add tests or verify existing tests cover it.

---

## 4. Final Ordered Plan

### Phase 0 — Baseline
Before changes:

```bash
git status --short
git diff --stat
./test.sh fast

cd frontend
corepack pnpm run lint
corepack pnpm run test:unit
corepack pnpm run build

python scripts/check_docs_staleness.py
python scripts/check_test_docs.py
python scripts/audit_test_matrix.py
```

---

### Phase 1 — Low-risk wins

#### 1. Raw clipboard callsite cleanup
**Target:** `LibraryDetailPage.vue`
**Goal:** Remove direct raw clipboard call if present. Use existing `useClipboard` wrapper.
**Reason:** Smallest change. Very low risk. Reduces duplicate clipboard logic.
**Acceptance criteria:**
- Copy action still works
- Success/error toast still appears
- No UI behavior change
**Suggested commit:** `refactor: route raw clipboard copy through shared helper`

#### 2. Debounced search queries
**Targets:**
- `frontend/src/composables/useUnifiedSearchQuery.ts`
- `frontend/src/composables/useInfiniteLibraryInspectorQuery.ts`

Replace manual `setTimeout`/`clearTimeout`/`onBeforeUnmount` cleanup with `refDebounced` or `useDebounceFn`.

**Behavior to preserve:**
- Existing delay values (250ms / 300ms)
- Empty query clears or disables search as before
- TanStack Query `enabled` logic remains correct
- No duplicate requests
- Infinite query cursor behavior remains correct

**Suggested commit:** `refactor: debounce search query refs with VueUse`

#### 3. `useClipboard.ts` → VueUse core
**Target:** `frontend/src/composables/useClipboard.ts`
Use `import { useClipboard as useVueUseClipboard } from "@vueuse/core"`.
Keep Gallery-specific wrapper: toast success/error, `copied` status by id, labels.

**Suggested commit:** `refactor: use VueUse clipboard helper`

---

### Phase 2 — Standard API / central cleanup

#### 4. Frontend natural sort → `Intl.Collator`
**Target:** `frontend/src/composables/useNaturalSort.ts`
Replace regex-based numeric splitting with `Intl.Collator({ numeric: true, sensitivity: "base" })`.
Keep exported API stable if possible.

**Test cases:** `1.png < 2.png < 10.png`, mixed case, CJK, empty/null-safe.

**Suggested commit:** `refactor: use Intl.Collator for frontend natural sort`

#### 5. Axios response interceptor
**Target:** `frontend/src/services/api.ts`

Add `api.interceptors.response.use(...)` to centralize `AxiosError → GalleryAPIError` mapping.
Simplify API functions where safe (no additional transforms).

**Tests:** 404/409/500 → `GalleryAPIError`. Non-Axios errors propagate. Special endpoint transforms intact.

**Suggested commit:** `refactor: centralize API error mapping in axios interceptor`

---

### Phase 3 — Responsive/layout plumbing

#### 6. `useDevice.ts` → VueUse breakpoints
**Target:** `frontend/src/composables/useDevice.ts`
Replace custom singleton resize listener with `useWindowSize` / `useBreakpoints` / `useMediaQuery`.

Preserve current public API and breakpoint boundaries:
- compact: <480, mobile: 480-767, tablet: 768-1199, desktop: 1200-1439, wide: >=1440

**Tests:** boundary widths 479, 480, 767, 768, 1199, 1200, 1439, 1440.

**Suggested commit:** `refactor: implement device breakpoints with VueUse`

#### 7. Simple manual listeners → `useEventListener`
**Targets:** Files with `addEventListener`/`removeEventListener` patterns.
Good candidates: `keydown`, `resize`, `visibility`, `focus` listeners.
Avoid: pull-to-refresh, scroll visibility, PhotoSwipe touch/keyboard glue.

**Suggested commit:** `refactor: use VueUse event listeners for simple handlers`

---

### Phase 4 — Observer/storage plumbing

#### 8. `useColumnResize.ts` partial migration
Replace `ResizeObserver` → `useResizeObserver`, `localStorage` → `useStorage`/`useLocalStorage`.
Do not rewrite domain logic (PHOTO_GRID_LEVELS, GRID_COLUMN_MAP, rowHeight calculation).

**Suggested commit:** `refactor: use VueUse resize and storage helpers for column sizing`

#### 9. Other simple `ResizeObserver` callsites
Candidates: `ExpandableText`, `AlbumScrollerNative`. Only if simple.

**Suggested commit:** `refactor: use VueUse resize observer in simple layout components`

#### 10. Simple localStorage callsites
Candidates: `App.vue`, `IntroScreen.vue`, `AlbumScroller.vue`. Use `useStorage`.

**Suggested commit:** `refactor: use VueUse storage helper for simple preferences`

---

### Phase 5 — Accessibility-sensitive migration

#### 11. `useFocusTrap.ts` → Reka FocusScope / Reka primitives
**Important:** Do NOT use `@vueuse/core` for focus trap. The repo already uses Reka UI — prefer `Reka FocusScope` or existing Reka `Dialog`/`Sheet`.

**Before migrating:** `rg "useFocusTrap" frontend/src` to find actual consumers.

**Tests:** Tab loops inside modal, Shift+Tab backwards, initial focus correct, return focus on close, Escape works, mobile sheet (VSBS) unaffected.

**Suggested commit:** `refactor: replace custom focus trap with Reka focus primitives`

---

### Phase 6 — Small DRY cleanup

#### 12. `formatBytes` duplicate
Extract from `LibraryListPage.vue` + `LibraryDetailPage.vue` to `frontend/src/utils/format.ts`.
Displayed byte values unchanged.

**Suggested commit:** `refactor: share byte formatting helper`

---

### Deferred / Conditional

| Item | Status |
|------|--------|
| `useScrollVisibility.ts` | Keep. Optional partial VueUse plumbing only. |
| `usePullToRefresh.ts` | Keep. Domain UX. |
| GalleryGrid IntersectionObserver | Defer. Only if simple + test-covered. |
| Toast store | Keep. Feature-complete. |
| Admin Library Table/Form | Defer until sort/filter/bulk feature required. |
| Backend pipeline | Keep current architecture. |

---

## 5. Test Strategy

Run after each small commit:
```bash
cd frontend
corepack pnpm run lint
corepack pnpm run test:unit
corepack pnpm run build
```

Repo-level check when touching shared behavior:
```bash
./test.sh fast
python scripts/check_docs_staleness.py
python scripts/check_test_docs.py
python scripts/audit_test_matrix.py
```

---

## 6. Docs Update Rules

Do not create new docs unless there is no existing suitable place.
Likely docs to update:
- `docs/THIRD_PARTY_LIBRARIES.md`
- `docs/ARCHITECTURE.md`
- `docs/testing/TEST_CATALOG.md`
- `docs/testing/README.md`

---

## 7. Review Checklist Per Commit

- [ ] Is this one logical migration only?
- [ ] Did it add a new dependency? If yes, is it justified?
- [ ] Did public behavior remain the same?
- [ ] Are fragile domain workflows untouched?
- [ ] Are tests updated?
- [ ] Are docs updated only if needed?

---

## 8. Non-goals

This plan does **not** aim to:
- rewrite GalleryGrid
- rewrite PhotoSwipe integration
- replace backend job queue
- replace SQLite FTS5
- replace metadata extraction pipeline
- migrate all forms/tables to TanStack
- add new dependencies casually
- rewrite all custom composables

---

## 9. Final Recommended Execution Order

1. Raw clipboard callsite cleanup
2. Debounced search refs
3. `useClipboard.ts` → VueUse
4. Natural sort → `Intl.Collator`
5. Axios interceptor
6. `useDevice.ts` → VueUse breakpoints
7. Simple manual listeners → `useEventListener`
8. `useColumnResize.ts` partial VueUse migration
9. Simple `ResizeObserver` callsites
10. Simple localStorage callsites
11. `useFocusTrap.ts` → Reka FocusScope
12. `formatBytes` dedup

**Deferred:** scroll visibility, pull-to-refresh, GalleryGrid observer, toast, admin table/form, backend pipeline.
