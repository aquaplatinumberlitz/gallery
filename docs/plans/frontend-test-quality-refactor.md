# Frontend Test Quality Refactor Plan

Status: Proposed

Last reviewed: 2026-06-27

## Summary

Refactor frontend tests to match
[`docs/testing/FRONTEND_TESTING_PRINCIPLES.md`](../testing/FRONTEND_TESTING_PRINCIPLES.md).

The goal is not to increase test count. The goal is to keep useful regression
coverage while making tests behavior-first, deterministic, and less coupled to
component internals.

Current audit findings:

- Three untracked component test files are not cataloged and currently make
  `python3 scripts/audit_test_matrix.py --fail-on-gaps` fail:
  - `frontend/src/components/__tests__/AppHeader.extra.test.ts`
  - `frontend/src/components/__tests__/Breadcrumb.extra.test.ts`
  - `frontend/src/components/admin/__tests__/LibraryDetailPage.extra.test.ts`
- Functional Playwright specs contain many `waitForTimeout()` calls that should
  become observable UI, network, or polling waits.
- Some component tests use `wrapper.vm` to mutate private component state or
  call private methods.
- Several tests rely on CSS classes where role, label, text, or test id
  selectors would be more stable.
- Large component tests sometimes mock too much of the app stack, creating
  brittle "mock universe" tests rather than integration tests around public
  behavior.

## Refactor Principles

- Preserve valuable behavior coverage; remove duplicate or implementation-only
  tests.
- Test public behavior: visible DOM, accessible controls, props, emitted events,
  observable store/composable state, request shape, and user-visible effects.
- Do not add `@pinia/testing`; keep the repo's current
  `setActivePinia(createPinia())` and `renderWithApp` patterns.
- Do not change production behavior except for semantically neutral
  accessibility or testability hooks, such as a stable `aria-label` or
  `data-testid` where no public selector exists.
- Keep Playwright CSS locators only when the class itself is the contract:
  visual/layout assertions, performance internals, or third-party PhotoSwipe
  DOM internals.

## Implementation Phases

### Phase 0 - Baseline And Guardrails

Run and record the current state before refactoring:

```bash
git status --short
cd frontend && pnpm lint:tests
cd frontend && pnpm test:unit
python3 scripts/audit_test_matrix.py --fail-on-gaps
```

Expected initial state:

- `audit_test_matrix.py --fail-on-gaps` fails because the three `.extra.test.ts`
  files listed above are uncataloged.
- Do not commit regenerated `docs/testing/test-gap-report.*` until the catalog
  state is intentionally fixed.

Acceptance:

- The implementer knows which failures are pre-existing.
- No production or generated docs files are changed in this phase.

### Phase 1 - Normalize The Three Extra Component Tests

Handle the three untracked test files first because they block docs/test catalog
health.

#### `Breadcrumb.extra.test.ts`

Merge unique behavior into `Breadcrumb.test.ts`, then delete the extra file.

Required changes:

- Replace `wrapper.vm.isExpanded = true` with the real user flow:
  click the ellipsis button, click `Show full path`, assert `Collapse path` is
  available, click `Collapse path`, and assert collapsed behavior.
- Replace `wrapper.vm.closeMenu()` with a real outside-click interaction only if
  the behavior can be expressed reliably through DOM events. Otherwise remove
  the test as implementation-only.
- Prefer button labels/text over `.ellipsis-menu`, `.ellipsis-btn`, and
  `.collapse-btn` where possible.

#### `AppHeader.extra.test.ts`

Merge unique behavior into `AppHeader.test.ts`, then delete the extra file.

Required changes:

- Replace `wrapper.vm.isAdvancedSearchOpen`, `handleAdvancedSearchClose`,
  `handleAdvancedSearchApply`, `handleRemoveFilter`, and `handleClearAll` with
  DOM interactions and emitted events.
- Stub `AdvancedSearchDrawer` as an interactive child test double that renders
  controls and emits `close` / `apply` from buttons.
- Assert `update:searchQuery`, route-specific visibility, search clearing, and
  theme menu behavior through visible controls and emitted events.
- Do not call parent private methods directly.

#### `LibraryDetailPage.extra.test.ts`

After cleanup, either keep it as a cataloged extra file or merge it into
`LibraryDetailPage.test.ts`.

Required changes:

- Replace `wrapper.vm.advancedOpen = true` with clicking the visible
  `Show advanced details` button.
- Keep only edge states that assert visible output or public effects:
  not found, loading, contract error, latest issue, runtime/lifecycle data,
  generated image status, jobs, copy path, scan action, and navigation.
- If the separate extra file remains, add it to
  `docs/testing/TEST_CATALOG.md`. If merged, delete the extra file.

Acceptance:

- No retained component test in these files mutates private refs or calls
  private methods through `wrapper.vm`.
- No uncataloged `.extra.test.ts` files remain.
- `cd frontend && pnpm test:unit` passes for the touched component tests.

### Phase 2 - Component Test Cleanup

Apply these rules across component tests under `frontend/src/components/**`.

Tasks:

- Remove direct `wrapper.vm` access except harmless `$nextTick` calls where no
  public interaction exists.
- Prefer DOM interaction, `setProps`, emitted events, visible text, roles,
  labels, and stable test ids.
- Keep class assertions only when style/layout is the actual contract, such as
  progress fill width or a specific visual state class.
- Use `renderWithApp` when the component needs Pinia, Router, and Vue Query
  together.
- For large components (`GalleryGrid`, `LibraryInspector`, `LibraryDetailPage`,
  `AppHeader`), avoid tests that mock every dependency and only assert that the
  component mounted. Move pure logic coverage to composable/store/unit tests.

Acceptance:

- `rg -n "wrapper\\.vm" frontend/src -g '*.test.ts'` has no private state or
  private method usage.
- `cd frontend && pnpm lint:tests` passes.
- `cd frontend && pnpm test:unit` passes.

### Phase 3 - Playwright Wait Refactor

Replace fixed sleeps in functional E2E specs with observable waits.

Priority files:

- `frontend/tests/e2e/advanced-search-drawer.spec.ts`
- `frontend/tests/e2e/search-fielded-ui.spec.ts`
- `frontend/tests/e2e/gallery-no-reload.spec.ts`
- `frontend/tests/e2e/gallery-cache-revisit.spec.ts`
- `frontend/tests/e2e/index-rebuild-flow.spec.ts`
- `frontend/tests/e2e/mobile-lightbox-sheet.spec.ts`
- `frontend/tests/e2e/tailwind-phase0.spec.ts`
- `frontend/tests/e2e/tailwind-preflight.spec.ts`

Replacement rules:

- After UI actions, wait for visible/hidden/text/value state with Playwright
  web-first assertions.
- After API-triggering actions, wait for `page.waitForResponse`,
  request-counter polling, or `expect.poll`.
- For debounce behavior, observe the resulting request or UI update instead of
  sleeping.
- Leave short sleeps only in performance or visual timing tests when the sleep
  is part of measurement. Add a comment explaining why the fixed wait is
  intentional.

Acceptance:

- Touched functional specs do not use `waitForTimeout()` when an observable
  condition exists.
- Touched specs pass individually on Chromium.

### Phase 4 - Locator Refactor

Replace brittle CSS selectors in workflow tests with semantic locators.

Tasks:

- Prefer `getByRole`, `getByLabel`, `getByText`, and `getByTestId`.
- Add stable `aria-label` or `data-testid` attributes only when no user-facing
  selector exists and the target is part of the test contract.
- Keep CSS locators for:
  - visual/layout contracts,
  - performance internals,
  - PhotoSwipe DOM internals,
  - classes where the class itself is the behavior under test.

Acceptance:

- New or refactored workflow tests avoid CSS selectors unless documented by the
  above exceptions.
- No user-facing workflow depends on utility class names such as `.flex-wrap` or
  `.gap-1`.

### Phase 5 - Catalog And Generated Reports

Update test documentation after inventory changes.

Tasks:

- Update `docs/testing/TEST_CATALOG.md` for any retained, renamed, merged, or
  removed important test file.
- Run:

```bash
python3 scripts/audit_test_matrix.py --fail-on-gaps
```

- Commit regenerated `docs/testing/test-gap-report.md` and
  `docs/testing/test-gap-report.json` only after the catalog is intentionally
  fixed and the command passes.

Acceptance:

- No uncataloged important frontend test files remain.
- Test catalog entries match files on disk.

## Validation Plan

Component/unit validation:

```bash
cd frontend && pnpm lint:tests
cd frontend && pnpm test:unit
```

Targeted Playwright validation for touched specs:

```bash
cd frontend && corepack pnpm exec playwright test tests/e2e/advanced-search-drawer.spec.ts --project=chromium
cd frontend && corepack pnpm exec playwright test tests/e2e/search-fielded-ui.spec.ts --project=chromium
cd frontend && corepack pnpm exec playwright test tests/e2e/gallery-no-reload.spec.ts tests/e2e/gallery-cache-revisit.spec.ts --project=chromium
```

Add any other touched E2E specs to the targeted command.

Final validation:

```bash
./test.sh docs
./test.sh fast
```

If E2E helpers, route stubs, or broad user workflows changed, also run:

```bash
./test.sh e2e
```

## Acceptance Criteria

- `python3 scripts/audit_test_matrix.py --fail-on-gaps` passes.
- `./test.sh docs` passes.
- `cd frontend && pnpm lint:tests` passes.
- `cd frontend && pnpm test:unit` passes.
- Touched Playwright specs pass on Chromium.
- Component tests no longer call private methods or mutate private refs through
  `wrapper.vm`.
- Functional E2E tests touched by the refactor no longer use fixed sleeps where
  an observable UI or network condition exists.
- Selectors in touched workflow tests follow role/label/text/test-id preference.
- Useful regression coverage is preserved; duplicate implementation-only tests
  are removed or rewritten.

## Notes For Opencode

- Work in small commits by phase.
- Do not include unrelated untracked files unless they are explicitly cleaned,
  merged, or cataloged by this plan.
- If a test becomes hard to express without `wrapper.vm`, treat that as a signal
  to add a small semantic label/test id or move the assertion to a composable or
  store test.
- If a fixed sleep appears necessary, first try `expect.poll`,
  `waitForResponse`, or a visible-state assertion. Keep the sleep only if it is
  part of visual/performance measurement.
