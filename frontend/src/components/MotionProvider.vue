<script setup lang="ts">
/**
 * Purpose: App-wide motion-v setup: honour the user's reduced-motion setting and provide the animation feature bundle.
 * Guarantees: Every animated element in the app is an `m.*` component (never the full `motion.*` one), so it only runs
 * the features provided here. `domAnimation` covers `initial` / `animate` / `exit` / `transition` and the hover, press,
 * focus and in-view gestures, which is everything the app uses. The full `domMax` bundle would also ship layout
 * projection, drag and pan code (about 36 KB of the mount-critical JavaScript) for features nothing uses. The bundle is
 * passed as an object, not a loader, so the first render is identical to the old `motion.*` one. App.vue loads this
 * component through `loadMotionProvider` (own chunk, awaited by main.ts before the first mount) so the engine stays out
 * of the entry chunk.
 * Run when: Adding an animated element (use `m.*`), or using `layout`, `drag`, `pan` or shared-layout animations, which
 * need `domMax` here.
 */
import { LazyMotion, MotionConfig, domAnimation } from "motion-v";
</script>

<template>
  <MotionConfig reduced-motion="user">
    <LazyMotion :features="domAnimation">
      <slot />
    </LazyMotion>
  </MotionConfig>
</template>
