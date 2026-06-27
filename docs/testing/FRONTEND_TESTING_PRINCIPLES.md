# Frontend Testing Principles

Status: Maintained

Last reviewed: 2026-06-27

This document records the frontend testing principles used in this repo, based
on the official Vue, Vue Test Utils, Pinia, and Playwright documentation:

- Vue testing guide: https://vuejs.org/guide/scaling-up/testing
- Vue Test Utils API: https://test-utils.vuejs.org/api/
- Pinia testing cookbook: https://pinia.vuejs.org/cookbook/testing.html
- Playwright best practices: https://playwright.dev/docs/best-practices

## Test Layers

Keep test layers clear:

- Static checks: TypeScript, ESLint, Prettier.
- Unit tests: pure utilities, contracts, and small state transitions.
- Component/integration tests: Vue rendering, props, emitted events, slots,
  Pinia/router/query integration, and browser API behavior in jsdom.
- E2E/browser tests: critical user workflows in a real browser with Playwright.

For Vue/Vite code, use Vitest for fast unit and component coverage. Use
Playwright for browser workflows, real DOM behavior, route navigation, and
regression tests that need browser APIs beyond jsdom.

Prefer tests that assert behavior and public interface:

- visible DOM output
- accessible labels and text
- props, events, and slots
- observable store/composable state
- API request shape and user-visible effects

Avoid tests that assert private component state, private methods, internal
implementation order, or large snapshots. Use snapshots only when they protect a
small stable contract and are easier to review than explicit assertions.

## Vue Test Utils

Use `mount` as the default component test API. Configure app dependencies
through the `global` mount option:

- `global.plugins` for Pinia, Router, Vue Query, or other app plugins
- `global.mocks` for mocked globals
- `global.provide` for injected values
- `global.stubs` for child components, `teleport`, `transition`, or expensive UI

Use `shallow` only when the child component tree is irrelevant and isolation is
the point of the test. Prefer realistic mounting when parent/child integration
is the behavior being protected.

Always `await` Vue Test Utils operations that can trigger asynchronous DOM
updates:

- `trigger`
- `setProps`
- `setValue`
- `setData`

Use `flushPromises` when assertions depend on promises outside Vue's normal
render tick, such as mocked API calls, Vue Query resolution, or async service
helpers.

In this repo, prefer shared helpers before repeating plugin setup:

- `frontend/src/test/setup.ts` provides jsdom shims and per-test cleanup.
- `frontend/src/test/renderWithApp.ts` mounts components with Pinia, Router, and
  Vue Query configured.
- `frontend/src/test/withSetup.ts` runs composables that need Vue lifecycle
  hooks.

## Pinia

For store unit tests, create a fresh active Pinia for each test:

```ts
beforeEach(() => {
  setActivePinia(createPinia());
});
```

This matches the current repo pattern and keeps store state isolated.

For component tests, install Pinia through `renderWithApp` when the component
also needs Router or Vue Query. If a component test mounts directly with
`mount`, install a fresh Pinia through `global.plugins` or call
`setActivePinia(createPinia())` before creating stores.

The Pinia cookbook documents `@pinia/testing` and `createTestingPinia`, but this
repo does not currently use that dependency. Do not add it for routine tests.
Consider it only if a future test group explicitly needs action stubbing as the
main behavior.

Keep ownership boundaries clear:

- Pinia owns UI/navigation state such as selected library, current path,
  lightbox state, toast state, and local preferences.
- TanStack Query owns server/API state and cache invalidation.

Do not copy server response state into Pinia just to make tests easier.

## Playwright

Playwright tests should exercise behavior users can observe or depend on:

- visible UI state
- navigation and workflow completion
- accessibility labels and controls
- network contracts with deterministic fixtures
- browser-only behavior such as focus, scrolling, media loading, and reloads

Keep tests isolated and deterministic. Each test should set up the state it
needs with `page.addInitScript`, route stubs, fixtures, or a managed backend
instead of depending on state from another test.

Avoid depending on third-party services in frontend E2E. Stub or control
external requests unless the test is explicitly a real-backend smoke path.

Prefer resilient locators:

- `getByRole`
- `getByLabel`
- `getByText`
- `getByTestId`

Avoid CSS selectors and XPath for user-facing behavior unless there is no stable
semantic target.

Use web-first assertions such as `toBeVisible`, `toHaveText`, `toHaveURL`, and
`toBeHidden`. Avoid fixed sleeps except when measuring performance or
intentionally waiting for debounced behavior to settle.

Use Playwright traces when debugging failures that only happen in CI. Add
cross-browser projects only when a feature needs browser diversity; current PR
coverage is intentionally Chromium-focused.

## Repo Commands

Run frontend checks from `frontend/` unless the command starts with `./test.sh`.

| Purpose | Command |
| --- | --- |
| Frontend unit/component tests | `pnpm test:unit` |
| Lint frontend tests | `pnpm lint:tests` |
| Targeted Playwright Chromium run | `corepack pnpm exec playwright test --project=chromium` |
| Fast local repo gate | `./test.sh fast` |
| Full CI-equivalent local suite | `./test.sh full` |

For targeted changes, choose the smallest test layer that can protect the
behavior. Add Playwright only when browser integration or user workflow
confidence is needed.
