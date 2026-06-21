# VueUse Theme System Cleanup Plan

**Status:** Planning only
**Created:** 2026-06-14
**Source-of-truth companion doc:** `docs/plan/TAILWIND_MIGRATION_ANIMATION_PRESERVATION_PLAN.md`

This plan audits the current gallery theme implementation and proposes a practical migration to VueUse for cleaner Light / Dark / System theme management.

No runtime code, package files, CSS, components, tokens, or tests are changed by this document.

---

## 1. Goals And Non-Goals

### Goals

- Centralize theme state in a dedicated composable.
- Use VueUse to own persisted color-mode state, system preference tracking, and DOM attribute updates.
- Preserve the current `[data-theme="dark"]` compatibility contract.
- Support explicit `light`, explicit `dark`, and `system` user preference.
- Keep the DOM attribute resolved to `data-theme="light"` or `data-theme="dark"` so existing CSS selectors keep working.
- Avoid initial theme flash.
- Add an implementation path for smoother theme transitions while respecting `prefers-reduced-motion`.
- Protect shadcn-vue Stone tokens, Tailwind v4 `@theme inline`, the custom dark variant, Preflight, and frozen mobile/tablet/lightbox surfaces.

### Non-Goals

- Do not change shadcn-vue Stone token values.
- Do not replace `[data-theme="dark"]` with `.dark`.
- Do not require `.dark` as the dark-mode selector.
- Do not redesign mobile, tablet, or lightbox surfaces in this phase.
- Do not install `@vueuse/core`; it is already present in `frontend/package.json`.
- Do not merge this into the old root-level Tailwind plan path.

---

## 2. Audit Findings

### Current theme state storage

Current app theme state is local to `frontend/src/App.vue`.

- `theme` is a `ref<"light" | "dark">`.
- It initializes from `localStorage["gallery-theme"]` when the stored value is `light` or `dark`.
- If no valid stored value exists, it falls back to `window.matchMedia("(prefers-color-scheme: dark)")`.
- There is no first-class `system` or `auto` theme mode in Vue state.

Relevant current files:

- `frontend/src/App.vue`
- `frontend/index.html`
- `frontend/src/layouts/DesktopLayout.vue`
- `frontend/src/layouts/MobileLayout.vue`
- `frontend/src/layouts/TabletLayout.vue`
- `frontend/src/components/AppHeader.vue`
- `frontend/src/components/MobileHeader.vue`
- `frontend/src/components/TabletHeader.vue`

### Current DOM theme attribute writes

The DOM attribute is written in two places.

1. `frontend/index.html`
   - Inline script runs before the app bundle.
   - Reads `localStorage["gallery-theme"]`.
   - If valid, writes `document.documentElement.setAttribute("data-theme", theme)`.
   - Otherwise resolves the system preference and writes `data-theme="dark"` or `data-theme="light"`.

2. `frontend/src/App.vue`
   - A `watchEffect` writes `document.documentElement.setAttribute("data-theme", theme.value)` after Vue state is initialized.

This duplicated logic currently reduces flash risk, but it also creates a maintenance risk because both places must stay in sync.

### Current localStorage usage

Theme-specific key:

- `gallery-theme`
  - Used by `frontend/index.html`.
  - Used by `frontend/src/App.vue`.
  - Current values are only `light` or `dark`.

Other nearby storage keys are unrelated to app color mode:

- `gallery-root-path`
- `gallery-sort-preference`
- `gallery-lightbox-always-load-original`
- `intro_mode`
- `intro_theme`
- `gallery-albums-collapsed`
- debug keys such as `GALLERY_DEBUG_RELOAD`

`intro_theme` is for landing page selection, not app light/dark mode.

### Current system preference support

System preference is partially supported.

- On initial load, missing theme storage falls back to `prefers-color-scheme: dark`.
- `App.vue` installs a `matchMedia("(prefers-color-scheme: dark)")` listener.
- The listener only changes theme when `localStorage["gallery-theme"]` is absent.

Important issue:

- `App.vue` watches `theme` and always writes `gallery-theme`.
- That means a user with no explicit theme selection will usually get a resolved `light` or `dark` stored on first app run.
- After that, the `matchMedia` listener no longer treats the user as system-following.

Result: system preference works as an initial fallback, but it is not a durable user-selectable mode.

### Duplicate theme logic

Theme logic is duplicated across:

- `frontend/index.html`: early no-flash theme resolution.
- `frontend/src/App.vue`: initial state resolution, mount-time resolution, media query listener, DOM attribute write, and persistence.

Headers and layouts do not store theme state themselves. They pass a boolean `isDark` down from root state and emit `toggle-theme` events back up.

### Desktop, mobile, and tablet controls

Theme controls exist on all primary layouts.

- Desktop:
  - `DesktopLayout.vue` receives `theme: "light" | "dark"`.
  - It passes `:is-dark="theme === 'dark'"` to `AppHeader.vue`.
  - `AppHeader.vue` emits `toggle-theme`.

- Mobile:
  - `MobileLayout.vue` receives `theme: "light" | "dark"`.
  - It passes `:is-dark="theme === 'dark'"` to `MobileHeader.vue`.
  - `MobileHeader.vue` emits `toggle-theme`.

- Tablet:
  - `TabletLayout.vue` receives `theme: "light" | "dark"`.
  - It passes `:is-dark="theme === 'dark'"` to `TabletHeader.vue`.
  - `TabletHeader.vue` emits `toggle-theme`.

There is no separate mobile or tablet theme store. The risky surfaces are wired to root state and can stay behavior-only in the first migration phase.

### Current theme transition CSS

There is no global `theme-transitioning` class today.

Current transition behavior is incidental:

- `body` transitions `background-color` and `color` for 200ms in `frontend/src/styles/main.scss`.
- Many components have their own transitions for hover, focus, opacity, transforms, overlays, and search UI.
- Reduced motion media queries exist in several files, including `main.scss`, `MobileHeader.vue`, `TabletHeader.vue`, `GalleryGrid.vue`, `ToastItem.vue`, `ToastContainer.vue`, `Breadcrumb.vue`, and lightbox styles.

There is no dedicated theme-switch transition wrapper that:

- activates only during user-triggered theme changes,
- avoids layout properties,
- removes itself after the switch,
- disables itself for reduced-motion users.

### `.dark` dependency audit

The app should not require `.dark`, and no required runtime `.dark` class was found.

Important nuance:

- Some Vue templates use Tailwind `dark:` utilities, for example `dark:border-white/5` and `dark:shadow[...]`.
- This is acceptable because `frontend/src/styles/tailwind.css` defines:

```css
@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));
```

That means Tailwind `dark:` utilities are bound to `[data-theme="dark"]`, not the default `.dark` selector.

The migration must preserve this custom variant.

### shadcn-vue Stone token bridge

The shadcn-vue bridge is already compatible with `[data-theme="dark"]`.

- `frontend/src/styles/_shadcn-token-bridge.css` defines Stone-compatible shadcn variables on `:root`.
- Dark overrides are under `[data-theme="dark"]`.
- `frontend/src/styles/tailwind.css` maps Tailwind v4 `@theme inline` colors to the shadcn variables, not directly to warm gallery identity tokens.

VueUse should only manage the chosen mode and the DOM attribute. It must not alter token values.

### Tailwind v4 and Preflight state

`frontend/src/styles/tailwind.css` currently imports:

```css
@layer theme, base, components, utilities;

@import "tailwindcss/theme.css" layer(theme);
@import "tailwindcss/preflight.css" layer(base);
@import "tailwindcss/utilities.css" layer(utilities);
```

It also defines the custom `dark` variant against `[data-theme="dark"]`.

The VueUse migration should not touch Tailwind layer ordering, Preflight imports, `@theme inline`, or the custom dark variant.

### Potential initial flash or hydration issues

This is a Vite SPA, not SSR hydration. The main risk is visual flash between first HTML parse, CSS load, and Vue mount.

Current flash mitigation is good in principle because the inline script in `index.html` runs before app JS and before the app mounts.

Risks that remain:

- The inline script and `App.vue` duplicate the same decision logic.
- Introducing VueUse with a different storage key or different `auto` behavior could cause the inline script and VueUse to disagree.
- If VueUse is allowed to set `data-theme="auto"` or `data-theme="system"`, existing selectors would break.
- If VueUse's default transition suppression is left enabled while custom transition CSS is added, smooth theme transitions may appear not to work.

---

## 3. Recommended VueUse API

Use `useColorMode`, not `useDark`.

### Why `useColorMode`

`useColorMode` supports the needed model:

- user preference: `light | dark | auto`
- resolved current mode: `light | dark`
- system preference access
- localStorage persistence
- configurable DOM selector and attribute

The gallery wants `Light / Dark / System`, which maps naturally to:

- UI `light` -> VueUse `light`
- UI `dark` -> VueUse `dark`
- UI `system` -> VueUse `auto`

### Why not `useDark`

`useDark` returns a boolean dark-mode ref. It is useful for simple two-state toggles, but it does not expose a clean first-class `light | dark | system` user preference model. It can be customized to write `data-theme`, but the boolean API would force extra state beside VueUse to know whether the user selected System.

Using `useDark` would recreate part of the current problem: state would be split between a boolean resolved theme and another place that remembers the user's desired mode.

### VueUse behavior to account for

In VueUse 14.3.0, `useColorMode`:

- defaults to selector `html`,
- defaults to attribute `class`,
- defaults to storage key `vueuse-color-scheme`,
- defaults `initialValue` to `auto`,
- exposes `store`, `system`, and `state`,
- writes the resolved state to the DOM,
- can be configured to write an attribute instead of a class,
- has `disableTransition` enabled by default.

The gallery should override the defaults that conflict with current policy.

Recommended configuration shape:

```ts
const colorMode = useColorMode({
  selector: "html",
  attribute: "data-theme",
  modes: {
    light: "light",
    dark: "dark",
  },
  storageKey: "gallery-theme",
  initialValue: "auto",
  disableTransition: false,
});
```

Notes:

- Keep `storageKey: "gallery-theme"` for compatibility with existing users.
- Use VueUse `auto` internally for the persisted System choice.
- Expose `system` in the gallery API, not `auto`.
- Keep `data-theme` resolved to `light` or `dark`; do not write `auto` or `system` to the DOM.
- Set `disableTransition: false` if the implementation adds the custom transition class described below. VueUse's default transition suppression would otherwise fight smoother theme switching.

---

## 4. Proposed Architecture

Add a dedicated composable:

```txt
frontend/src/composables/useGalleryTheme.ts
```

This composable should become the single source of truth for app color-mode state.

### Public API

Proposed type model:

```ts
export type GalleryThemeMode = "light" | "dark" | "system";
export type GalleryResolvedTheme = "light" | "dark";

export function useGalleryTheme() {
  return {
    mode, // Ref<GalleryThemeMode>
    resolvedTheme, // ComputedRef<GalleryResolvedTheme>
    systemTheme, // ComputedRef<GalleryResolvedTheme>
    isDark, // ComputedRef<boolean>
    setTheme, // (mode: GalleryThemeMode) => void
    toggleTheme, // () => void
    cycleTheme, // optional: light -> dark -> system -> light
  };
}
```

Internal mapping:

```ts
const colorMode = useColorMode({
  selector: "html",
  attribute: "data-theme",
  modes: {
    light: "light",
    dark: "dark",
  },
  storageKey: "gallery-theme",
  initialValue: "auto",
  disableTransition: false,
});

const mode = computed<GalleryThemeMode>({
  get: () =>
    colorMode.store.value === "auto"
      ? "system"
      : (colorMode.store.value as "light" | "dark"),
  set: (next) => {
    colorMode.store.value = next === "system" ? "auto" : next;
  },
});

const resolvedTheme = computed<GalleryResolvedTheme>(
  () => colorMode.state.value as GalleryResolvedTheme,
);

const systemTheme = computed<GalleryResolvedTheme>(
  () => colorMode.system.value,
);

const isDark = computed(() => resolvedTheme.value === "dark");
```

### DOM contract

The DOM should always receive:

```html
<html data-theme="light"></html>
```

or:

```html
<html data-theme="dark"></html>
```

When the user mode is System, the DOM should still receive the resolved theme:

- system preference light -> `data-theme="light"`
- system preference dark -> `data-theme="dark"`

The DOM must not receive:

```html
<html data-theme="system">
  <html data-theme="auto"></html>
</html>
```

Existing CSS depends on resolved selectors.

### App integration

Replace the current `App.vue` theme block with the composable.

Current root responsibilities to remove from `App.vue`:

- manual localStorage read for `gallery-theme`,
- manual `matchMedia("(prefers-color-scheme: dark)")`,
- manual media query listener,
- manual `document.documentElement.setAttribute("data-theme", ...)`,
- manual theme persistence watcher.

Responsibilities to keep in `App.vue`:

- call `useGalleryTheme()`,
- pass `resolvedTheme` or `isDark` to existing layouts,
- wire existing `toggleTheme` emit to the composable,
- keep all sidebar, intro screen, query, and lightbox logic unchanged.

Short-term layout compatibility:

- Continue passing `theme: "light" | "dark"` to layouts, using `resolvedTheme`.
- Continue passing `isDark` to headers.
- Existing mobile/tablet buttons remain simple toggles.

Later UI cleanup:

- Allow headers to consume `useGalleryTheme()` directly only if that reduces prop drilling without mixing in unrelated layout state.
- Otherwise keep root-owned theme props for predictable surface area.

### Pinia/store decision

Do not add a Pinia theme store in this migration.

Reasoning:

- Theme state is browser/UI preference state, not app domain state.
- VueUse already provides the reactive storage and media query plumbing.
- Adding Pinia would duplicate VueUse state and create another synchronization point.

If a future settings screen needs staged Apply/Cancel behavior, it can use a local draft that commits through `setTheme(mode)`.

---

## 5. Persistence Strategy

Use the existing storage key:

```txt
gallery-theme
```

Supported stored values after migration:

- `light`
- `dark`
- `auto`

UI wording should use `system`, but persisted VueUse value should be `auto`.

Compatibility notes:

- Existing users with `gallery-theme=light` keep explicit Light.
- Existing users with `gallery-theme=dark` keep explicit Dark.
- Users who choose System will store `gallery-theme=auto`.
- Missing key should behave like System and resolve from `prefers-color-scheme`.
- Invalid values should be normalized to `auto`.

Do not introduce a second storage key such as `gallery-theme-mode` unless there is a migration reason. A second key would increase mismatch risk between early inline script and VueUse.

---

## 6. Initial Theme And No-Flash Strategy

Use a hybrid approach:

1. Keep a small inline script in `frontend/index.html`.
2. Update it to understand the same storage contract as the composable.
3. Let VueUse take over after app mount.

VueUse alone is not enough for the first paint because it runs from the app bundle. The current inline script is the right no-flash mechanism and should remain.

Proposed inline script behavior:

```html
<script>
  (() => {
    const key = "gallery-theme";
    let stored = null;

    try {
      stored = localStorage.getItem(key);
    } catch (_) {
      stored = null;
    }

    const explicit = stored === "light" || stored === "dark";
    const systemDark =
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;

    const theme = explicit ? stored : systemDark ? "dark" : "light";

    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  })();
</script>
```

Notes:

- Keep it minimal and dependency-free.
- It should only write resolved `light` or `dark`.
- It should tolerate Safari Private Browsing storage exceptions.
- It should support the future `auto` value.
- Supporting legacy `system` as an input is harmless, but the composable should persist `auto`.
- `color-scheme` can help browser-native controls match the chosen theme, but verify it does not alter shadcn form styling unexpectedly.

Potential refinement:

- Use `document.documentElement.setAttribute("data-theme", theme)` instead of `dataset.theme` if consistency with current code is preferred. Both produce the same attribute.

---

## 7. Smooth Theme Transition Strategy

VueUse manages state and DOM updates. It does not provide the desired visual design by itself.

### VueUse transition setting

VueUse `useColorMode` has `disableTransition` enabled by default in the installed version. That injects temporary CSS to suppress transitions during theme changes.

If the migration adds custom smooth transitions, configure:

```ts
disableTransition: false;
```

Then own transition behavior explicitly through the gallery composable and CSS.

### CSS transition fallback

Add a global class in a later implementation phase:

```css
html.theme-transitioning,
html.theme-transitioning * {
  transition:
    background-color 180ms ease,
    color 180ms ease,
    border-color 180ms ease,
    box-shadow 180ms ease,
    fill 180ms ease,
    stroke 180ms ease;
}

@media (prefers-reduced-motion: reduce) {
  html.theme-transitioning,
  html.theme-transitioning * {
    transition: none !important;
  }
}
```

Implementation constraints:

- Add the class only for user-initiated changes, not initial app mount.
- Remove the class after roughly 220ms to 260ms.
- Do not animate layout properties such as width, height, margin, padding, grid, left, right, top, bottom, or transform.
- Avoid long durations; 160ms to 200ms should be enough.
- Exclude or avoid targeting media-heavy and frozen areas if the broad `*` selector causes jank:
  - PhotoSwipe DOM,
  - `.lightbox-overlay`,
  - `[data-vsbs-*]`,
  - images and videos,
  - virtualized grid item positioning.

### Composable transition wrapper

The composable should provide theme setters that own transition timing:

```ts
function setTheme(next: GalleryThemeMode) {
  applyThemeChange(() => {
    mode.value = next;
  });
}

function toggleTheme() {
  setTheme(resolvedTheme.value === "dark" ? "light" : "dark");
}
```

`applyThemeChange` should:

- return early if the resolved theme will not change,
- skip transitions when reduced motion is requested,
- add `theme-transitioning` before changing VueUse state,
- remove it after the transition window,
- clean up timers on unmount if the composable owns timers.

### Reduced motion

Use one or both of:

- CSS `@media (prefers-reduced-motion: reduce)`,
- VueUse `usePreferredReducedMotion()`.

When reduced motion is active:

- do not add `theme-transitioning`, or make it a no-op through CSS,
- do not call the View Transition API,
- keep the DOM attribute update immediate.

### Optional View Transition API

The View Transition API can be a progressive enhancement after the class-based transition works.

Potential shape:

```ts
function applyThemeChange(applyTheme: () => void) {
  if (
    "startViewTransition" in document &&
    prefersReducedMotion.value !== "reduce"
  ) {
    document.startViewTransition(() => {
      applyTheme();
    });
    return;
  }

  applyTheme();
}
```

Constraints:

- Progressive enhancement only.
- Must fallback cleanly on unsupported browsers.
- Do not rely on it for Safari or iOS.
- Gate it to desktop first if mobile snapshots or viewport transitions are unstable.
- Do not use it to change lightbox behavior.

---

## 8. shadcn-vue Stone Compatibility Plan

VueUse should not change token values. It should only write the already-supported DOM attribute.

Must preserve:

- `frontend/src/styles/_shadcn-token-bridge.css`
  - light Stone variables on `:root`,
  - dark Stone variables under `[data-theme="dark"]`.
- `frontend/src/styles/tailwind.css`
  - Tailwind v4 `@theme inline`,
  - shadcn token mappings,
  - `@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));`,
  - Preflight import state.
- `frontend/src/styles/tokens.css`
  - gallery legacy and brand tokens,
  - dark overrides under `:root[data-theme="dark"]`.
- `frontend/src/styles/main.scss`
  - brand hero dark animations,
  - existing body transition,
  - reduced motion handling.

Implementation rule:

- The theme refactor and Stone token work must stay separate unless a token bug is directly exposed by the refactor.

Verification:

- In light mode, computed shadcn variables should match Stone light values.
- In dark mode, computed shadcn variables should match Stone dark values.
- Tailwind `dark:` utilities should activate under `[data-theme="dark"]`.
- No `.dark` class should be required on `<html>`.

---

## 9. UI Controls Plan

### Short term

Wire existing controls to `useGalleryTheme()` with minimal surface changes.

- Desktop `AppHeader.vue`: keep current button and visual state.
- Mobile `MobileHeader.vue`: keep current button.
- Tablet `TabletHeader.vue`: keep current button.
- Layout prop type can remain resolved `"light" | "dark"` during the first phase.

Existing toggles should remain binary:

- If resolved theme is dark, click sets explicit Light.
- If resolved theme is light, click sets explicit Dark.

This avoids a confusing three-state cycle on buttons that visually communicate two states.

### System mode UI

To expose System cleanly, add a control that can show all modes.

Recommended path:

1. Desktop first:
   - Replace or augment the desktop theme toggle with a shadcn-vue `DropdownMenu` or `Select`.
   - Items: `Light`, `Dark`, `System`.
   - The current mode should be checked.
   - If mode is System, show `System (Light)` or `System (Dark)` in title/tooltip text.

2. Mobile/tablet:
   - Keep existing buttons behavior-only in the first implementation phase.
   - Later, expose the same three modes in a settings surface if mobile/tablet UX work is explicitly in scope.
   - Do not redesign header button order, search behavior, sort behavior, or lightbox controls as part of this migration.

Icon behavior:

- Use resolved theme for sun/moon icon so the visual state matches the current UI colors.
- If a System-capable dropdown is added, consider a small monitor icon or `System` label in the menu item, not in the compact button.

Accessibility:

- Binary buttons should announce the action, for example `Switch to light mode`.
- A three-mode menu should announce current selection and expose all choices.

---

## 10. Migration Steps

### Phase 0: Planning

Status: this document.

### Phase 1: Centralize state without UI redesign

1. Add `frontend/src/composables/useGalleryTheme.ts`.
2. Configure `useColorMode` with:
   - `selector: "html"`,
   - `attribute: "data-theme"`,
   - `storageKey: "gallery-theme"`,
   - `initialValue: "auto"`,
   - `modes: { light: "light", dark: "dark" }`.
3. Expose `mode`, `resolvedTheme`, `systemTheme`, `isDark`, `setTheme`, and `toggleTheme`.
4. Replace manual theme logic in `App.vue` with the composable.
5. Continue passing resolved `"light" | "dark"` to layouts.
6. Keep existing mobile/tablet/desktop buttons wired through their current emits.
7. Update `frontend/index.html` inline script to support `auto`.
8. Do not change tokens or component styling.

### Phase 2: Add System-capable UI

1. Add a desktop shadcn-vue menu/select for `Light / Dark / System`.
2. Keep the existing compact icon button if needed, but avoid making it the only way to access three modes.
3. Decide whether System belongs in SettingsModal before touching mobile/tablet controls.
4. Update tests for all three modes.

### Phase 3: Add smoother transitions

1. Set `disableTransition: false` in `useColorMode`.
2. Add `theme-transitioning` CSS.
3. Add reduced-motion guard.
4. Wrap `setTheme` and `toggleTheme` in transition timing logic.
5. Optional: add desktop-only View Transition API enhancement.

### Phase 4: Cleanup and hardening

1. Remove dead manual theme helpers from `App.vue`.
2. Add invalid stored-value normalization.
3. Add comments near the custom Tailwind dark variant explaining that `.dark` is intentionally not required.
4. Expand tests to cover persisted `auto` and no-flash behavior.

---

## 11. Required Tests

### Current test baseline

Current Playwright coverage already includes:

- desktop theme toggle changes `data-theme`,
- mobile theme toggle changes `data-theme`,
- tablet theme button visibility,
- light/dark layout preservation,
- custom Tailwind dark variant behavior through `[data-theme="dark"]`,
- Preflight regression coverage.

No unit test runner was found in `frontend/package.json`. Existing automated tests are Playwright-based.

### Unit or composable tests

If a unit/composable test harness is available or added later, cover:

- default missing storage resolves from system preference,
- existing stored `light` maps to mode `light` and DOM `data-theme="light"`,
- existing stored `dark` maps to mode `dark` and DOM `data-theme="dark"`,
- stored `auto` maps to UI mode `system`,
- system mode follows mocked system light/dark,
- `setTheme("light")` stores `light`,
- `setTheme("dark")` stores `dark`,
- `setTheme("system")` stores `auto`,
- `resolvedTheme` is always `light` or `dark`,
- invalid storage normalizes to `system` or `auto`,
- no `.dark` class is needed.

If no unit harness is added, cover these with Playwright init scripts and page evaluation.

### Playwright tests

Add or update tests for:

- initial load with persisted `gallery-theme=light` writes `data-theme="light"` before app interaction,
- initial load with persisted `gallery-theme=dark` writes `data-theme="dark"` before app interaction,
- initial load with persisted `gallery-theme=auto` follows mocked `prefers-color-scheme`,
- missing `gallery-theme` behaves as System,
- changing mocked system preference updates `data-theme` while mode is System,
- changing mocked system preference does not update `data-theme` while mode is explicit Light or Dark,
- desktop theme control changes `data-theme`,
- mobile theme button still changes `data-theme`,
- tablet theme button still changes `data-theme`,
- no console errors on desktop, mobile, or tablet,
- shadcn token values change correctly between light and dark,
- `dark:` Tailwind utilities activate without `.dark`,
- brand hero remains scoped to warm identity,
- standard shadcn controls remain Stone neutral,
- lightbox remains visually dark and operational,
- no `.dark` class is required on `<html>`.

Useful checks:

```ts
expect(
  await page.evaluate(() =>
    document.documentElement.getAttribute("data-theme"),
  ),
).toBe("dark");

expect(
  await page.evaluate(() =>
    document.documentElement.classList.contains("dark"),
  ),
).toBe(false);
```

### No-flash tests

Add a Playwright test that injects storage before navigation:

```ts
await page.addInitScript(() => {
  localStorage.setItem("gallery-theme", "dark");
});
await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe(
  "dark",
);
```

For stronger coverage:

- check `data-theme` at `domcontentloaded`,
- check it again after app mount,
- assert it does not flip unexpectedly.

### Transition tests

When transition support is implemented, test:

- `theme-transitioning` is added during a user-triggered switch,
- `theme-transitioning` is removed after the expected duration,
- reduced motion disables the transition class or makes it a no-op,
- unsupported View Transition API path does not throw,
- View Transition API path is skipped for reduced motion,
- switching themes during a lightbox session does not break lightbox controls.

### Manual visual QA

Run desktop, tablet, and mobile smoke passes:

- desktop 1440x900,
- tablet 768x1024,
- mobile 390x844,
- dark persisted load,
- light persisted load,
- system dark load,
- system light load,
- theme switch with gallery grid loaded,
- theme switch with header search focused,
- theme switch with sidebar open,
- theme switch with lightbox open.

---

## 12. Risk Analysis

### Theme flash on initial load

Risk:

- VueUse runs too late for first paint if used alone.

Mitigation:

- Keep and update the inline `index.html` script.
- Ensure it uses the same storage key and same `auto` semantics as the composable.

### Duplicate localStorage keys

Risk:

- A new key such as `vueuse-color-scheme` or `gallery-theme-mode` could diverge from `gallery-theme`.

Mitigation:

- Configure VueUse with `storageKey: "gallery-theme"`.
- Do not introduce another key unless a migration document explains why.

### Stored mode versus resolved theme mismatch

Risk:

- System mode requires storing one value while writing another to the DOM.

Mitigation:

- Persist `auto`.
- Expose UI mode as `system`.
- Write only resolved `light | dark` to `data-theme`.
- Use `colorMode.store` for user preference and `colorMode.state` for resolved theme.

### Accidental `.dark` dependency

Risk:

- Default VueUse and Tailwind examples often use `<html class="dark">`.

Mitigation:

- Configure `attribute: "data-theme"`.
- Preserve Tailwind `@custom-variant dark`.
- Add tests that remove/check absence of `.dark`.

### Breaking Tailwind custom dark variant

Risk:

- If `@custom-variant dark` is removed or changed, `dark:` utilities no longer follow `[data-theme="dark"]`.

Mitigation:

- Do not edit `tailwind.css` during theme state migration except for targeted comments if needed.
- Add a test using a known `dark:` utility.

### Breaking shadcn Stone tokens

Risk:

- Theme refactor could get mixed with token refactor.

Mitigation:

- Treat VueUse as state and DOM attribute management only.
- Do not change `_shadcn-token-bridge.css` token values.

### Mobile/tablet header regressions

Risk:

- Three-mode UI changes could alter frozen touch surfaces.

Mitigation:

- Phase 1 wires behavior only.
- Keep existing mobile/tablet button markup and layout.
- Add mobile and tablet Playwright checks before expanding UI.

### Safari and iOS transition quirks

Risk:

- View Transition API support is limited.
- Broad transitions can cause jank.
- Mobile Safari can expose background gaps during transitions.

Mitigation:

- Treat View Transition API as desktop-first progressive enhancement.
- Keep CSS transition fallback short.
- Respect reduced motion.
- Exclude lightbox and heavy media if needed.

### VueUse default transition suppression

Risk:

- VueUse `disableTransition` defaults to true and can suppress custom theme transitions.

Mitigation:

- Set `disableTransition: false` once custom transition handling is introduced.
- Add a transition test to prove the class takes effect.

---

## 13. Rollout Plan

Recommended rollout order:

1. Add `useGalleryTheme.ts` and replace `App.vue` manual theme logic.
2. Update the inline no-flash script for `auto`.
3. Keep existing toggle UI and layout props unchanged except for using resolved theme.
4. Add Playwright coverage for persisted `light`, persisted `dark`, and `auto`.
5. Add desktop System-capable UI.
6. Add transition wrapper and reduced-motion coverage.
7. Evaluate View Transition API as a separate optional enhancement.

Each phase should be independently reversible.

---

## 14. Rollback Plan

If the VueUse migration causes regressions:

1. Revert `useGalleryTheme.ts`.
2. Restore the previous `App.vue` local `theme` ref, media query listener, DOM writer, and persistence watcher.
3. Restore the previous `index.html` inline script if changed.
4. Leave token files untouched.
5. Leave `gallery-theme` storage key in place.

Storage compatibility:

- Old code already accepts `light` and `dark`.
- If `gallery-theme=auto` exists after rollback, old code will ignore it as invalid, fall back to system preference, and then write resolved `light` or `dark`.
- That is acceptable for rollback, though it loses the user's explicit System setting.

---

## 15. Final Recommendation

Adopt `useColorMode` through a gallery-specific composable.

Use this model:

- VueUse storage value: `light | dark | auto`
- Gallery UI mode: `light | dark | system`
- DOM attribute: resolved `data-theme="light" | "dark"`
- Storage key: `gallery-theme`
- Selector: `html`
- Attribute: `data-theme`
- Tailwind dark variant: keep `[data-theme="dark"]`
- shadcn token values: unchanged

Do not use `useDark` for this migration. It is too boolean for the required Light / Dark / System UX.

---

## 16. References

- VueUse `useColorMode`: https://vueuse.org/core/usecolormode/
- VueUse `useDark`: https://vueuse.org/core/usedark/
- Installed package audited locally: `@vueuse/core@14.3.0`
