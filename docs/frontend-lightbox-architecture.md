# Frontend Lightbox Architecture

## Architecture Overview

```
Lightbox.vue (orchestrator, per-device dispatch)
├── Desktop/Wide → PhotoSwipeViewer.vue + LightboxDesktopPanel.vue
├── Tablet       → TabletPhotoSwipe.vue + LightboxTabletPanel.vue
└── Mobile       → MobilePhotoSwipe.vue + LightboxMobileSheet.vue
```

All PhotoSwipe wrappers share the same composable: `usePhotoSwipe.ts`.

---

## Shared Composable: `usePhotoSwipe.ts`

Location: `frontend/src/composables/usePhotoSwipe.ts`

### Lifecycle

| Event | Behavior |
|-------|----------|
| `isOpen` becomes `true` | `setTimeout(() => initPhotoSwipe(), 0)` — deferred to ensure container ref is mounted |
| `isOpen` becomes `false` | `destroyPhotoSwipe()` — cleans up PS5 instance |
| Component mounted + `isOpen=true` | `initPhotoSwipe()` (in case open was already set) |
| Component unmounted | `destroyPhotoSwipe()` — cleanup guard |

### Init Guard

```typescript
if (!containerRef.value || !isOpen.value || pswp.value) return;
```
Prevents duplicate initialization — only one PhotoSwipe instance at a time. If `pswp.value` is already set, init is skipped.

### Index Sync

```typescript
watch(() => currentIndex.value, (index) => {
  if (pswp.value && pswp.value.currIndex !== index) {
    pswp.value.goTo(index);
  }
});
```
The `pswp.currIndex !== index` guard prevents infinite loops: PS5 `change` event → Lightbox handler updates store → watcher would fire again, but `currIndex` already equals `index`.

### Shared Item Building

`buildPhotoSwipeItem()` in `frontend/src/utils/lightbox.ts` is shared by all three wrapper components:
- When `thumbnailSize` is provided: uses thumbnail URL at that size
- When `thumbnailSize` is `null` (desktop full-res): uses original image URL
- Uses real `item.width` / `item.height` from backend scan (see [Image Scan & Dimensions](image-scan-and-dimensions.md))
- Falls back to 1200×1200 neutral square when dimensions are missing

### Return Value

Exposes `pswp` ref for component-specific operations (e.g., TabletPhotoSwipe zoom toggle).

---

## Device-Specific Wrappers

### Desktop/Wide: `PhotoSwipeViewer.vue`

**Purpose**: Thin wrapper — no custom controls, no extra UI.

```
Props:
  items, currentIndex, isOpen, closeOnVerticalDrag, allowPanToNext, thumbnailSize
Emits:
  close, indexChange
```

- `closeOnVerticalDrag: false`, `allowPanToNext: false`
- `thumbnailSize: 2400` (high-quality resized thumbnail)
- PS5 default arrows work (right arrow offset via CSS to avoid sidebar)
- Hides PS5's own close/zoom/top-bar (our overlay handles these)

**Template**: Single `<div ref="containerRef">` — PS5 appends its DOM inside.

### Tablet: `TabletPhotoSwipe.vue`

**Purpose**: Dedicated component with custom toolbar overlay.

```
Props:
  items, currentIndex, isOpen, metadataOpen (for info button active state)
Emits:
  close, indexChange, toggleMetadata
```

**Why dedicated?** Tablet needs:
1. A counter pill (`3 / 12`) centered at top
2. A floating bottom toolbar with close, zoom toggle, and info buttons
3. Direct access to `pswp` ref for zoom toggle (`pswp.zoomTo()`)
4. Different config: `closeOnVerticalDrag: true`, `allowPanToNext: true`
5. Different thumbnail size: `2048px`

**Zoom toggle**: Checks `slide.currZoomLevel > slide.zoomLevels.initial + 0.01` to determine state. Uses `pswp.getViewportCenterPoint()` as zoom center.

**Component-owned state**: `isZoomed` ref tracks zoom state for icon swap (ZoomIn/ZoomOut).

### Mobile: `MobilePhotoSwipe.vue`

**Purpose**: PhotoSwipe 5 wrapper with self-registered metadata info button.

```
Props:
  items, currentIndex, isOpen, metadataOpen
Emits:
  close, indexChange, toggleMetadata
```

**Info button**: Registered into PS5's UI system via `onRegisterUi` callback:
- Creates a `metadata-info` custom button at order 9
- Inline SVG circle/line icon
- Moves button from PS5 DOM to `.lightbox-overlay` in `onAfterInit` to avoid PS5 `hide-on-close` class
- Watches `metadataOpen` prop to toggle `active` and `hidden` CSS classes

**Config**: `closeOnVerticalDrag: true`, `allowPanToNext: true`, `thumbnailSize: 1600px`.

---

## Metadata Panels

### Desktop: `LightboxDesktopPanel.vue`

- Fixed right sidebar, 400px wide (min 320px, max 450px)
- `z-index: 10000` (above overlay at 9999)
- Accordion sections: Generation Data, Resources, Advanced
- Fullscreen toggle, copy buttons, close button
- Visibility: hidden when `isFullscreen` is true

### Tablet: `LightboxTabletPanel.vue`

- Bottom sheet, 2-column layout
- `max-height: 65vh`, expandable to 80vh
- Touch-based expand/collapse (swipe up/down)
- Accordion for Advanced section only

### Mobile: `LightboxMobileSheet.vue`

- Bottom sheet, tabbed (Prompt / Params / Advanced)
- `height: 44dvh`, expandable to 80dvh
- Haptic feedback on tab switch
- Draggable handle, touch-to-expand/collapse

---

## Index Change / Close / Toggle Flows

### Index Change

```
PS5 "change" event → usePhotoSwipe onIndexChange callback
→ emit("indexChange", index) [in wrapper component]
→ Lightbox.handleIndexChange / handlePhotoSwipeIndexChange
→ lightboxStore.currentIndex = newIndex; itemPath = item.path; itemName = item.name
→ lightboxStore.loadMetadata(item.path)
→ GET /api/metadata?path=...
→ metadata panel reactively updates
```

### Close

```
PS5 "close" event → usePhotoSwipe destroyPhotoSwipe() + onClose callback
OR Escape key → Lightbox.handleClose()
OR Close button in panel → emit close → handleClose()
→ lightboxStore.close() (resets all state, invalidates in-flight requests)
→ Transition "fade" out
```

### Toggle Metadata (Tablet + Mobile)

```
Info button → emit("toggleMetadata")
→ Lightbox.toggleSheet() → showSheet.value = !showSheet.value
→ Tablet: LightboxTabletPanel v-if="showSheet && !isFullscreen"
→ Mobile: LightboxMobileSheet v-if="showSheet && !isFullscreen"
→ Close: panel emits close → handleSheetClosed() → showSheet = false
```

---

## Regression Boundaries

When modifying lightbox code, test these cross-device boundaries:

| Change | Desktop Test | Tablet Test | Mobile Test |
|--------|-------------|-------------|-------------|
| `usePhotoSwipe.ts` | PS5 init, arrows, close | PS5 init, zoom toggle, toolbar | PS5 init, info button, swipe |
| `buildPhotoSwipeItem()` | Full-res URL, real dims | 2048px thumb URL | 1600px thumb URL |
| `Lightbox.vue` template | `v-if="isDesktop \|\| isWide"` | `v-if="isTablet"` | `v-if="isMobile"` |
| Arrow offset CSS | `.pswp__button--arrow--next` | N/A (tablet uses swipe) | N/A (mobile uses swipe) |
| Metadata panel styles | `_lightbox-desktop.scss` | `_lightbox-tablet.scss` | `_lightbox-mobile.scss` |

### Do / Don't

- **Do** share `buildPhotoSwipeItem()` — it's the single source of truth for item construction
- **Do** keep `usePhotoSwipe` generic — component-specific behavior goes in the wrapper
- **Don't** remove the `pswp.currIndex !== index` guard in the index watcher
- **Don't** change thumbnail sizes without testing banding/quality on each device
- **Don't** assume `pswp.value` is always set when accessing it (TabletPhotoSwipe checks this)
- **Don't** remove `defineAsyncComponent` for Lightbox — it enables code-splitting

---

## File Index

| File | Role |
|------|------|
| `components/Lightbox.vue` | Device-dispatch orchestrator, keyboard handling, fullscreen |
| `components/PhotoSwipeViewer.vue` | Desktop/wide thin PS5 wrapper |
| `components/TabletPhotoSwipe.vue` | Tablet PS5 wrapper with toolbar + zoom |
| `components/MobilePhotoSwipe.vue` | Mobile PS5 wrapper with registered info button |
| `components/LightboxDesktopPanel.vue` | Desktop metadata right sidebar |
| `components/LightboxTabletPanel.vue` | Tablet 2-column bottom sheet |
| `components/LightboxMobileSheet.vue` | Mobile tabbed bottom sheet |
| `composables/usePhotoSwipe.ts` | Shared PS5 lifecycle composable |
| `utils/lightbox.ts` | Shared `buildPhotoSwipeItem()` |
| `stores/lightbox.ts` | Lightbox state + navigation + metadata fetch |
| `styles/_lightbox-shared.scss` | Shared loading/error, LoRA, param-pill |
| `styles/_lightbox-desktop.scss` | Desktop panel styles |
| `styles/_lightbox-tablet.scss` | Tablet panel styles |
| `styles/_lightbox-mobile.scss` | Mobile sheet styles |
