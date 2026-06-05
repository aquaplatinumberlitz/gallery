# Debugging iPad Safari & Eruda

## Eruda Mobile Debug Console

Built-in debug console for mobile/tablet testing.

### Enable
```
http://<host>/?eruda=1
```

### Disable
```
http://<host>/?eruda=0
```

### How it works
- `frontend/src/utils/erudaDebug.ts` — lazy-loads Eruda from CDN
- Guarded by `import.meta.env.DEV` + query param `?eruda=1`
- Persists choice in `localStorage` so it stays on after page load
- `?eruda=0` clears localStorage and reloads

### Useful Eruda checks
| Check | How |
|-------|-----|
| Viewport width | `Elements` tab → `document.documentElement.clientWidth` |
| Current device breakpoint | Check `useDevice()` computed values |
| Rendered component path | `Console` → `$0.__vueParentComponent` on selected element |
| PhotoSwipe image dimensions | Select `.pswp__img` element → check `width`/`height` attributes |
| Computed CSS for icons | `Computed` tab → filter `gallery-icon`, check actual rendered size |
| Network requests | `Network` tab — verify `/api/scan`, `/api/thumbnail`, `/api/metadata` |
| localStorage | `Storage` tab — check `gallery-root-path`, `gallery-grid-size`, `gallery-sort` |

## Icon Debug Overlay

Dev-only overlay showing icon metrics for every Lucide icon on the page.

### Enable
```
http://<host>/?iconDebug=1
```

### Controls
- **Refresh** — re-scan DOM for icons
- **Copy** — copy report as JSON
- **Select** — click any icon to highlight it and show its details
- **Force Header/Toolbar SVG 40px** — override icon sizes for testing
- **Reset** — clear forced overrides
- **Close** — dismiss overlay

### How it works
- `frontend/src/utils/iconDebugOverlay.ts`
- Guards: `import.meta.env.DEV` + query param `?iconDebug=1`
- URL-only (no localStorage persistence) — refreshes on page reload
- Scans all candidate elements with icon classes, reads computed size and CSS variables

## iPad Safari Specific Quirks

| Issue | Workaround |
|-------|------------|
| `color-mix()` not supported | Use `rgba()` fallback before `color-mix()`, wrap modern in `@supports` |
| `backdrop-filter` causes animation delay | Remove `backdrop-filter` from animated elements (tablet sidebar) |
| Touch targets < 44px feel cramped | Minimum 44×44px for all interactive elements |
| Keyboard accessory bar appears on input focus | Use `enterkeyhint`, consider scroll-behavior on `focusin` |
| Viewport zoom on input focus | `maximum-scale=1, user-scalable=no` in viewport meta |
| Elastic overscroll conflicts with PhotoSwipe | `overscroll-behavior: contain` on gallery container |
| Hover states don't exist (no cursor) | Use `:active` + `-webkit-tap-highlight-color` for touch feedback |
