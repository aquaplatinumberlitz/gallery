# Integrate PhotoSwipe 5 as Mobile Image Viewer + Existing Metadata Sheet

## Context
Project at /home/ubuntu/gallery-repo/frontend, commit 2e4055e (stable base)
Current lightbox is custom Vue 3 implementation with 3-slide track

## Goal
Replace the custom mobile swipe/track logic with **PhotoSwipe 5** (battle-tested, handles iOS Safari swipe/compositing correctly), while **keeping our existing metadata sheet** (LightboxMobileSheet.vue) on top.

## Architecture
Lightbox.vue stays as the container. On mobile:
- PhotoSwipe handles: image loading, swipe gesture, zoom, preload
- We handle: metadata fetching, metadata sheet UI, copy button, close button

On desktop: keep existing behavior (no change).

## Files to modify
1. Install `photoswipe` npm package
2. Modify `Lightbox.vue` — add PhotoSwipe for mobile, keep desktop as-is
3. Possibly create `LightboxPhotoSwipe.vue` component to keep things clean

## Implementation Plan

### Step 1: Install PhotoSwipe
```bash
cd /home/ubuntu/gallery-repo/frontend && npm install photoswipe
```

### Step 2: Create a MobilePhotoSwipe.vue component

This component replaces the current 3-slide track + swipe logic on mobile.
It uses PhotoSwipe internally and emits events when image changes (for metadata).

```vue
<script setup lang="ts">
import PhotoSwipe from 'photoswipe';
import 'photoswipe/dist/photoswipe.css';
import type { FileNode } from '../types';
import { getThumbnailUrl } from '../services/api';

const props = defineProps<{
  items: FileNode[];
  currentIndex: number;
  isMobile: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'indexChange', index: number): void;
}>();

// ... PhotoSwipe lifecycle
</script>
```

### Step 3: PhotoSwipe data source

PhotoSwipe needs an array of items with `src` and `width`/`height`:
```typescript
const pswpItems = computed(() => props.items.map((item, i) => ({
  src: getThumbnailUrl(item.path, 1600), // use mobile variant
  width: item.width || 1200,
  height: item.height || 1600,
  alt: item.name || '',
  // Store original path for metadata lookup
  path: item.path,
})));
```

### Step 4: Integrate with metadata sheet

PhotoSwipe has events:
- `afterChange` — fires when current slide changes
- `close` — fires when viewer closes
- `uiRegister` — lets you add custom UI elements

On `afterChange`:
```typescript
pswp.on('afterChange', () => {
  const slideData = pswp.currSlide?.data;
  const path = slideData?.path;
  if (path) {
    emit('indexChange', pswp.currIndex);
    // Parent Lightbox.vue will fetch metadata for this path
  }
});
```

On `close`:
```typescript
pswp.on('close', () => {
  emit('close');
});
```

### Step 5: Prevent PhotoSwipe close on metadata sheet open

PhotoSwipe closes when clicking outside the image. We need to prevent this when the metadata sheet is open. This can be done by stopping propagation on the sheet's backdrop or by using PhotoSwipe's `closeOnVerticalDrag` and `closeOnScroll` options.

Actually, the simplest approach: PhotoSwipe has a `close` event that we can intercept. When the metadata sheet is visible, we can check and prevent close.

But actually, PhotoSwipe handles swipe-down-to-close natively. The metadata sheet opens on tap of the info button. These are different gestures — PhotoSwipe handles vertical swipe dismiss, we handle info button tap. They shouldn't conflict.

### Step 6: Keep existing metadata sheet and copy button

The existing `LightboxMobileSheet.vue` and `useClipboard.ts` composable should remain unchanged. They receive `meta` (MetadataResponse) and `copyStatus`/`copyText` from the parent. The parent just needs to fetch metadata when PhotoSwipe fires `afterChange`.

### Step 7: CSS for PhotoSwipe

PhotoSwipe 5's default CSS is clean. We just need:
- Ensure it doesn't conflict with our theme (z-index, background color)
- Position our metadata sheet ABOVE PhotoSwipe's UI (z-index adjustment)

```scss
// Override PhotoSwipe theme to match gallery dark theme
.pswp {
  --pswp-bg: #000;
  // Keep default PhotoSwipe behavior
}

// Our metadata sheet sits on top
.mobile-sheet {
  z-index: 10000; // above PhotoSwipe's 9999
}
```

### Step 8: Feature flag / conditional

Use a feature flag or conditional rendering:
```vue
<template>
  <!-- Mobile: PhotoSwipe -->
  <MobilePhotoSwipe
    v-if="isMobile && usePhotoSwipe"
    :items="lightbox.galleryItems"
    :current-index="lightbox.currentIndex"
    @close="handleClose"
    @index-change="handlePhotoSwipeIndexChange"
  />
  
  <!-- Mobile: custom track (fallback) -->
  <MobileImageViewer
    v-else-if="isMobile"
    ...
  />
  
  <!-- Desktop: keep existing -->
  <template v-else>
    ... existing desktop panel ...
  </template>
</template>
```

Actually, simpler: just have Lightbox.vue switch behavior based on isMobile. Desktop keeps existing code entirely. Mobile uses PhotoSwipe.

## What to keep from existing code
- Lightbox.vue as the container (show/hide, Teleport, Transition)
- LightboxMobileSheet.vue (metadata sheet) — UNCHANGED
- useClipboard.ts (copy button) — UNCHANGED
- useDevice.ts (breakpoints) — UNCHANGED
- Desktop lightbox — UNCHANGED
- Metadata fetching (lightbox store, fetchMetadata) — UNCHANGED

## What to replace (mobile only)
- ~~3-slide track~~ → PhotoSwipe handles swipe/image display
- ~~handleSwipeStart/Move/End~~ → PhotoSwipe handles gestures
- ~~prevSrc/nextSrc computed~~ → PhotoSwipe manages prev/next
- ~~preloadAdjacent()~~ → PhotoSwipe handles preloading
- ~~resetTrackPosition()~~ → Not needed
- ~~is-animating class~~ → Not needed
- ~~transitionend handler~~ → PhotoSwipe handles timing
- ~~two-frame commit~~ → Not needed

## What to add
- photoswipe npm dependency
- MobilePhotoSwipe.vue component
- PhotoSwipe CSS overrides in _lightbox-mobile.scss
- Integration between PhotoSwipe index changes and metadata fetching

## Do NOT break
- Desktop lightbox behavior
- Mobile metadata sheet
- Copy button + clipboard
- Theme colors and dark mode
- Close animation
- Fullscreen
- Keyboard navigation (arrows, escape)
- Navigation history (browser back button — if used)

## Verification
1. `npm run build` — passes
2. Test on desktop: navigation still works (arrows, keyboard)
3. Test on mobile: swipe between images, check for flash
4. Test metadata sheet: opens, shows metadata for current image
5. Test copy button: copies text
6. Test close: swipe-down-to-close, X button
7. Test at gallery boundaries (first/last image)
8. Test rapid swipes

## CRITICAL
- Do NOT remove or modify LightboxMobileSheet.vue
- Do NOT modify useClipboard.ts
- Do NOT modify desktop lightbox logic
- Do NOT modify lightbox store (except possibly minor changes)
- Run npm run build after all changes
- Add temporary console.log for nativeWidth/nativeHeight to confirm PhotoSwipe uses variant URLs
