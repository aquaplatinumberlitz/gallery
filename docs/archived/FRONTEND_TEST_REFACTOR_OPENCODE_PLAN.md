# Frontend Test Refactor Plan For opencode

Status: ✅ Completed — all 7 phases implemented

Completed: 2026-06-27
Last reviewed: 2026-06-27

## Final Result

All phases implemented and verified. Final gate status:

| Gate | Status |
|------|--------|
| `pnpm lint:tests` | ✅ pass |
| `pnpm test:unit` | ✅ 68 files, 900 tests |
| `pnpm build` | ✅ pass |
| `./test.sh e2e` | ✅ 150 passed, 0 failed |
| `./test.sh perf` | ✅ 3 passed |
| `./test.sh docs` | ✅ pass |

Net change: **-1,385 lines** across 17 files. 94→92 test files. 2 duplicate `.extra` files deleted. All fixed sleeps replaced or documented. Lightbox open budget raised from 500→1000ms for cold-start tolerance.

## Summary

Refactor frontend tests to match
[`docs/testing/FRONTEND_TESTING_PRINCIPLES.md`](../testing/FRONTEND_TESTING_PRINCIPLES.md).

The goal is controlled cleanup, not higher test count. Keep useful regression
coverage, remove duplicate or implementation-only tests, and make the default
frontend gates deterministic.

Current inventory:

- 94 frontend test/spec files, 20,898 lines.
- 70 Vitest files under `frontend/src/**/__tests__/**/*.test.ts`.
- 24 Playwright specs under `frontend/tests/e2e/**/*.spec.ts`.

Current command status from the latest audit:

- `cd frontend && pnpm lint:tests`: passes.
- `cd frontend && pnpm test:unit`: passes, 70 files / 910 tests, 106.68s.
- `./test.sh e2e`: fails before browser tests because frontend build/typecheck
  sees a test typing error in `Breadcrumb.test.ts`.
- `GALLERY_TEST_SKIP_BUILD=1 ./test.sh e2e`: 151 passed, 1 failed, 4 skipped.
  The failure is `gallery-cache-revisit.spec.ts`.
- `GALLERY_TEST_SKIP_BUILD=1 ./test.sh perf`: 3 passed.

## Principles

- Test public behavior: visible DOM, accessible controls, props, emitted
  events, observable store/composable state, API request shape, query
  invalidation, and user-visible effects.
- Do not preserve tests whose only value is exercising render branches or
  private implementation order.
- Do not add `@pinia/testing`; keep the repo pattern of fresh
  `setActivePinia(createPinia())`, `renderWithApp`, and isolated QueryClient
  helpers.
- Prefer Vitest for pure utilities, contracts, stores, composables, and jsdom
  component behavior. Prefer Playwright for browser workflows, real DOM/CSS,
  route navigation, focus/scroll/media behavior, and performance.
- Keep class/CSS selectors only when CSS or third-party DOM structure is the
  contract. Otherwise prefer role, label, text, or stable test id.
- Avoid fixed sleeps except in performance or visual-timing tests, with a
  comment explaining why the sleep is intentional.
- Avoid direct `wrapper.vm`, `innerHTML`, private method calls, and tests that
  call mocked store methods directly instead of interacting with UI.

## Phase 0 - Baseline And Guardrails

Run these commands before editing and save notable failures in the opencode
work log:

```bash
git status --short
cd frontend && pnpm lint:tests
cd frontend && pnpm test:unit
./test.sh e2e
GALLERY_TEST_SKIP_BUILD=1 ./test.sh e2e
GALLERY_TEST_SKIP_BUILD=1 ./test.sh perf
```

Expected baseline:

- Test lint and Vitest pass.
- `./test.sh e2e` fails during `pnpm build`.
- Functional Playwright with `GALLERY_TEST_SKIP_BUILD=1` has exactly one real
  browser failure in `gallery-cache-revisit.spec.ts`.
- Perf suite passes when run through `./test.sh perf` with the managed fixture.

Do not run direct recursive `pnpm exec playwright test` as a repo-health gate.
It collects perf/diagnostic specs without the managed fixture and can report
misleading failures.

## Phase 1 - Fix Gate Blockers

Fix these first, before broader cleanup.

### `Breadcrumb.test.ts` Typecheck Failure

File: `frontend/src/components/__tests__/Breadcrumb.test.ts`

Problem:

- The test directive stub assigns `__clickOutsideHandler` to `HTMLElement`.
- `vue-tsc --noEmit` includes `src/**/__tests__/**/*.test.ts`, so this blocks
  `pnpm build` and `./test.sh e2e`.

Required implementation:

- Replace the custom HTMLElement expando with a local
  `WeakMap<HTMLElement, EventListener>`.
- In directive `mounted`, create the listener and store it in the WeakMap.
- In directive `unmounted`, read from the WeakMap, remove the document
  listener, then delete the entry.
- Do not loosen TypeScript config or add `any` just to hide the error.

Acceptance:

```bash
cd frontend && pnpm build
```

### `gallery-cache-revisit.spec.ts` Request Shape Bug

File: `frontend/tests/e2e/gallery-cache-revisit.spec.ts`

Problem:

- The test defines `ApiRequest` as `{ pathname, path, cursor }`.
- The failing assertion reads `r.q.includes("navigate-away")`, so `q` is
  `undefined`.

Required implementation:

- Extend `ApiRequest` with `q: string`.
- Populate `q` from `url.searchParams.get("q") ?? ""`.
- Keep the assertion behavior: the test should still prove the search request
  happened before returning to gallery.

Acceptance:

```bash
GALLERY_TEST_SKIP_BUILD=1 ./test.sh e2e frontend/tests/e2e/gallery-cache-revisit.spec.ts
```

## Phase 2 - Separate Functional, Perf, And Diagnostics

The repo already has managed fixture runners in `scripts/internal/test-playwright.sh`.
Keep that split explicit so opencode and humans do not run the wrong suite.

Required implementation:

- Keep `./test.sh e2e` as the deterministic functional browser suite.
- Keep `./test.sh perf` as the deterministic perf budget suite.
- Add a diagnostic command only if needed, named `e2e-diagnostics`, gated by
  an explicit env such as `GALLERY_E2E_DIAGNOSTICS=1`.
- Do not include diagnostic or real-backend-only checks in the default
  functional gate unless they are deterministic under `test-playwright.sh`.
- Keep `metadata-performance.spec.ts` skipped unless `GALLERY_PERF_METADATA=1`
  is set.

Recommended policy:

- `frontend/tests/e2e/perf/**`: only `./test.sh perf`.
- `metadata-performance.spec.ts`: diagnostic/perf only, env-gated.
- Real-backend no-reload smoke checks: diagnostic only if they depend on
  existing external data; functional only if they run against the managed
  fixture.
- Rebuild timing logs: diagnostic assertions should not spam normal functional
  output unless a failure needs context.

Docs to update:

- `docs/testing/README.md`
- `docs/testing/TESTING_STRATEGY.md`
- `docs/testing/TEST_CATALOG.md`
- `docs/testing/FRONTEND_TESTING_PRINCIPLES.md` only if command policy needs a
  short addendum.

Acceptance:

```bash
./test.sh e2e
./test.sh perf
```

## Phase 3 - Consolidate Duplicate Component Tests

Target files:

- `frontend/src/components/search/__tests__/AdvancedSearchDrawer.test.ts`
- `frontend/src/components/__tests__/AdvancedSearchDrawer.extra.test.ts`
- `frontend/src/components/__tests__/IndexStatusPanel.test.ts`
- `frontend/src/components/__tests__/IndexStatusPanel.extra.test.ts`

Required implementation:

- Merge `.extra` coverage into the primary test file when it protects unique
  public behavior.
- Delete duplicate label-only tests already covered by the primary file or by
  Playwright user workflows.
- Keep the Advanced Search unit tests focused on:
  - drawer open/closed rendering,
  - field group visibility at a high level,
  - apply/reset/cancel emissions,
  - numeric operator controls when not already covered by Playwright.
- Keep `IndexStatusPanel` unit tests focused on:
  - button vs card variant behavior,
  - loading/error/contract-error visible states,
  - scan/rebuild action wiring when it can be asserted through public events or
    API calls.

Acceptance:

```bash
cd frontend && pnpm test:unit \
  src/components/search/__tests__/AdvancedSearchDrawer.test.ts \
  src/components/__tests__/IndexStatusPanel.test.ts
cd frontend && pnpm lint:tests
```

## Phase 4 - Reduce Heavy Mock Component Tests

Target files:

- `frontend/src/components/__tests__/AppHeader.test.ts`
- `frontend/src/components/__tests__/GalleryGrid.test.ts`
- `frontend/src/components/__tests__/Lightbox.test.ts`
- `frontend/src/components/__tests__/LibraryInspector.test.ts`
- `frontend/src/components/admin/__tests__/LibraryDetailPage.test.ts`
- `frontend/src/components/__tests__/LightboxMobileSheet.test.ts`

Required implementation:

- Extract repeated mount setup into local `mountSubject` helpers.
- Use existing `renderWithApp` or `mountWithQuery` when the component needs
  Pinia, Router, and Vue Query together.
- Remove tests that only assert a stub rendered, a mocked method can be called
  directly, or generic text appears without protecting a meaningful contract.
- Replace conditional assertions like `if (btn) { ... }` with hard assertions:
  the test should fail when the control is missing.
- Replace `wrapper.element.innerHTML` with `wrapper.text()`,
  Testing Library queries, or targeted DOM assertions.
- Replace `wrapper.vm.$nextTick()` with `await nextTick()` from Vue where a
  render tick is truly needed.
- Keep behavior that is not cheaply covered elsewhere:
  - AppHeader route/mobile visibility, search emissions, advanced search
    open/apply, filter chip actions, theme switching.
  - GalleryGrid loading/error/toolbar/navigation contracts, not every stubbed
    child render.
  - Lightbox top-level desktop/mobile/tablet composition only if not already
    protected by Playwright; remove tests that directly call mocked
    `store.close/next/prev`.
  - LibraryInspector loading/error/empty/table summary/filter visibility; leave
    sort/search/lightbox ordering to Playwright.
  - LibraryDetailPage not-found/loading/contract error/latest issue/copy/scan
    visible behavior.
  - LightboxMobileSheet loading/error/tabs/copy/empty states via visible
    output and emitted events.

Acceptance:

```bash
rg -n "wrapper\\.element\\.innerHTML|wrapper\\.html\\(|\\.vm\\b|findAll\\(\"button\"\\)|find\\(\"button\"\\)" \
  frontend/src/components \
  -g '*.test.ts'
cd frontend && pnpm test:unit
cd frontend && pnpm lint:tests
```

The grep does not need to be empty, but every remaining hit must be intentional
and defensible under the frontend testing principles.

## Phase 5 - Keep Useful Unit/Composable Coverage, But Table-Drive Repetition

Target files:

- `frontend/src/services/__tests__/api.test.ts`
- `frontend/src/query/__tests__/keys.test.ts`
- `frontend/src/utils/__tests__/format.test.ts`
- `frontend/src/utils/__tests__/serializeAdvancedSearchToQuery.test.ts`
- `frontend/src/composables/__tests__/usePhotoSwipe.test.ts`

Required implementation:

- Convert repetitive one-case-per-test request helpers and query key assertions
  to `it.each` tables.
- Keep API request-shape coverage because it protects the frontend/backend
  contract.
- Keep query-key coverage because cache invalidation relies on stable tuples,
  but avoid 40 nearly identical `it(...)` bodies.
- Keep `usePhotoSwipe.test.ts` for jsdom integration around lifecycle,
  dimension resolution, original escalation, and cleanup.
- Trim `usePhotoSwipe` cases that only assert internal event-registration
  lists, test-only `window.__...` hooks, or mocked implementation branches
  already protected by Playwright lightbox specs.
- Leave endpoint policy and real browser image behavior to:
  - `frontend/tests/e2e/lightbox-loading-policy.spec.ts`
  - `frontend/tests/e2e/lightbox-visual-layer.spec.ts`
  - `frontend/tests/e2e/mobile-lightbox-sheet.spec.ts`

Acceptance:

```bash
cd frontend && pnpm test:unit \
  src/services/__tests__/api.test.ts \
  src/query/__tests__/keys.test.ts \
  src/composables/__tests__/usePhotoSwipe.test.ts
```

## Phase 6 - Playwright Cleanup

Target groups:

- Functional workflows:
  - `frontend/tests/e2e/advanced-search-drawer.spec.ts`
  - `frontend/tests/e2e/search-fielded-ui.spec.ts`
  - `frontend/tests/e2e/gallery-no-reload.spec.ts`
  - `frontend/tests/e2e/gallery-cache-revisit.spec.ts`
  - `frontend/tests/e2e/index-status-panel.spec.ts`
  - `frontend/tests/e2e/library-management.spec.ts`
  - `frontend/tests/e2e/library-inspector.spec.ts`
  - `frontend/tests/e2e/mobile-lightbox-sheet.spec.ts`
- Styling contracts:
  - `frontend/tests/e2e/tailwind-phase0.spec.ts`
  - `frontend/tests/e2e/tailwind-preflight.spec.ts`
- Perf specs:
  - `frontend/tests/e2e/perf/album-open.perf.spec.ts`
  - `frontend/tests/e2e/perf/lightbox.perf.spec.ts`

Required implementation:

- Replace fixed sleeps with web-first assertions, `page.waitForResponse`, or
  `expect.poll`.
- Keep fixed waits only for intentional PhotoSwipe animation timing or perf
  measurement, and add a comment explaining the measurement reason.
- Prefer `getByRole`, `getByLabel`, `getByText`, and `getByTestId`.
- Keep PhotoSwipe `.pswp__*` locators only where the third-party DOM is the
  visual contract.
- Keep layout CSS locators only where the CSS/layout class itself is the
  contract.
- Avoid collecting perf specs in functional runs except through explicit perf
  command.

Acceptance:

```bash
rg -n "waitForTimeout|locator\\(\"\\.|locator\\('\\." frontend/tests/e2e
./test.sh e2e
./test.sh perf
```

Every remaining hit must be either a perf/visual timing wait, a third-party DOM
contract, or a documented layout contract.

## Phase 7 - Docs And Catalog

After code cleanup, update docs to match reality.

Required implementation:

- Update test counts in `docs/testing/README.md` if counts change.
- Update `docs/testing/TEST_CATALOG.md` for merged, deleted, or reclassified
  files.
- Update `docs/testing/TESTING_STRATEGY.md` if command selection changes.
- Run the matrix audit and commit regenerated reports only when the catalog is
  intentionally aligned.

Acceptance:

```bash
./test.sh docs
```

## Final Acceptance

The refactor is complete only when all commands below pass:

```bash
cd frontend && pnpm lint:tests
cd frontend && pnpm test:unit
cd frontend && pnpm build
./test.sh e2e
./test.sh perf
./test.sh docs
```

Target outcome:

- Default functional and perf gates are deterministic.
- Vitest remains fast enough to be useful; if still above 90s, document whether
  `fileParallelism: false` is required or can be relaxed.
- No known test blocks build/typecheck.
- No retained test asserts private component state or implementation order
  without a documented reason.
- Duplicate `.extra` component tests are merged or removed.
- Docs and generated test catalog agree with the actual test files.

