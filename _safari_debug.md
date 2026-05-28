# Safari iOS Debug Report

## Bug 1: Dark Mode → Content still white (trắng)

### Root Cause: `localStorage` throws in Safari + `watchEffect` default override

**Primary Cause — Safari Private Browsing / restricted mode throws on localStorage:**

In `frontend/index.html` (lines 8-17), the FOUC-prevention script:
```js
(function() {
  var theme = localStorage.getItem('gallery-theme');  // ⚠️ THROWS on Safari Private Browsing
  ...
  document.documentElement.setAttribute('data-theme', theme);
})();
```

Safari iOS (especially Private Browsing / Intelligent Tracking Prevention) throws `SecurityError` or `QuotaExceededError` when accessing `localStorage.getItem()`. There is **no try/catch** wrapper. When this throws:
- The entire inline script crashes
- `data-theme` is **never set** on `<html>`
- CSS sees no matching `:root[data-theme="dark"]` rule
- Default `:root` (light mode) is applied → white content

**Secondary Cause — Vue `watchEffect` overrides inline script even if it works:**

In `App.vue` (line 39):
```ts
const theme = ref<"light" | "dark">("light");  // default is LIGHT
```

Line 103-105:
```ts
watchEffect(() => {
  document.documentElement.setAttribute("data-theme", theme.value); // runs during setup()
});
```

This `watchEffect` fires **during Vue's setup phase** (before `onMounted`) and immediately sets `data-theme="light"`, **overriding** whatever the inline script in index.html set. Then `onMounted` (line 78-96) reads localStorage and restores the correct value, but:
1. If localStorage throws → theme stays `"light"` forever
2. Even if it doesn't throw, there's a visible flash from dark → light → dark

**Tertiary Issue — No try/catch around any localStorage access:**

- `App.vue` line 81: `localStorage.getItem(THEME_STORAGE_KEY)` — no try/catch
- `App.vue` line 109: `localStorage.setItem(THEME_STORAGE_KEY, val)` — no try/catch
- `index.html` line 11: `localStorage.getItem('gallery-theme')` — no try/catch
- `useColumnResize.ts` line 26: `localStorage.getItem(GRID_SIZE_KEY)` — no try/catch

All of these throw on Safari Private Browsing mode.

### Fix:

1. **Wrap all `localStorage` calls in try/catch** — this is the most important fix
2. **Initialize `theme` ref from `localStorage` early** or at least make it reactive to `matchMedia` as fallback  
3. **Use `html[data-theme="dark"]` consistently** instead of `:root[data-theme="dark"]` in tokens.css (though both should work, consistency matters)

---

## Bug 2: Only 1 column photos instead of 3 columns

### Root Cause: Wrong breakpoint logic in `getDefaultCols()`

In `frontend/src/composables/useColumnResize.ts` (lines 9-16):
```ts
function getDefaultCols(): number {
  if (typeof window === 'undefined') return 4
  const w = window.innerWidth
  if (w >= BREAKPOINTS.tablet) return 4   // >= 1024
  if (w >= BREAKPOINTS.phone) return 3    // >= 768
  if (w >= BREAKPOINTS.compact) return 2  // >= 480
  return 1                                 // < 480 → iPhone = 1 column!
}
```

iPhone viewport widths: 375px (SE), 390px (14/15 Pro), 393px (16 Pro), 430px (Pro Max)

All iPhones are < 480px, so they all hit `return 1`.

**The fix:** Adjust breakpoints to give at least 2 columns on mobile:
- For viewports >= 375px (most iPhones): return 2 or 3
- For viewports < 375px (very old/small): return 1 or 2

Additionally:
- `MIN_COLS = 1` allows the grid slider (hidden on mobile) to go to 1 column
- The column slider is hidden on mobile (`display: none` at line 1139-1141), so users can't fix it

### Fix:
Change `getDefaultCols()` to return at least 2 for modern mobile viewports.

---

## CSS Selector Issues with scoped styles + `html[data-theme="dark"]`

In `PhotoCard.vue`, the pattern `html[data-theme="dark"] &` inside scoped `<style>` may have issues on Safari WebKit:

```scss
.photo-card {
  html[data-theme="dark"] & {
    background: var(--surface-color);
    border: 1px solid rgba(255, 255, 255, 0.06);
    ...
  }
}
```

This compiles to:
```css
html[data-theme="dark"] .photo-card[data-v-xxxxx] { ... }
```

Safari iOS has edge cases with scoped CSS attribute selectors combined with global `html` selectors. If this doesn't match, the PhotoCard won't get its dark mode background/border, making it look incorrect on dark mode.

**Recommendation:** Replace `html[data-theme="dark"] &` with a simpler dark mode class or use `:deep()` or global styles. Or use CSS variables exclusively for dark mode theming so the `html[data-theme="dark"]` selection happens at the token level, not the component level.

---

## Summary of Changes Needed

| File | Issue | Fix |
|------|-------|-----|
| `frontend/index.html` | `localStorage` throws on Safari | Wrap in try/catch |
| `frontend/src/App.vue` | `localStorage` throws; `watchEffect` overrides early | Wrap in try/catch; init theme from system preference first |
| `frontend/src/composables/useColumnResize.ts` | Wrong breakpoints → 1 column on iPhone | Fix `getDefaultCols()` for mobile |
| `frontend/src/components/PhotoCard.vue` | `html[data-theme="dark"] &` in scoped styles may fail on Safari WebKit | Replace with CSS-variable-only approach or make styles non-scoped for dark mode |
