/**
 * Purpose: One loader for the motion-v setup chunk (`MotionProvider.vue`), shared by App.vue and main.ts.
 * Guarantees: The motion animation engine (about 20 KB gzip) is not part of the entry chunk. The entry chunk is what
 * starts the first API requests when it executes, so every byte in it delays them; the engine downloads in parallel
 * with the route chunks instead (it is also in the early chunk preload list), and main.ts waits for it before the first
 * mount, so the first render has the animation features exactly as before.
 * Run when: Changing how the motion provider is loaded.
 */
export const loadMotionProvider = () => import("./MotionProvider.vue");
