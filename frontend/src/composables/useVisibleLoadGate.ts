import { onBeforeUnmount, onMounted, readonly, ref, toValue, watch, type MaybeRefOrGetter, type Ref } from "vue";

/** How long a card must stay intersecting before its image request may start. */
export const VISIBLE_LOAD_DWELL_MS = 120;

type ScrollAxis = "x" | "y";

const SCROLLING_OVERFLOW = new Set(["auto", "scroll", "overlay"]);
const CLIPPING_OVERFLOW = new Set(["auto", "scroll", "overlay", "hidden", "clip"]);

/**
 * Finds the element that clips `el` along `axis`.
 *
 * An IntersectionObserver `rootMargin` only grows the root's own box: any scroll container between the
 * target and the root still clips it. Observing against the nearest clipping ancestor instead of the
 * viewport is what lets the margin prefetch cards that are just outside the visible strip.
 *
 * - `y` returns the nearest vertically scrolling ancestor (the page/grid scroller).
 * - `x` returns the nearest ancestor that clips horizontally, which also covers overflow-hidden
 *   carousel viewports whose slides move by transform.
 *
 * Returns null when nothing matches so the caller falls back to the viewport.
 */
export function findScrollRoot(el: HTMLElement, axis: ScrollAxis): HTMLElement | null {
  const accepted = axis === "y" ? SCROLLING_OVERFLOW : CLIPPING_OVERFLOW;
  for (let node = el.parentElement; node && node !== document.body; node = node.parentElement) {
    const style = window.getComputedStyle(node);
    if (accepted.has(style.getPropertyValue(axis === "y" ? "overflow-y" : "overflow-x"))) return node;
  }
  return null;
}

export interface UseVisibleLoadGateOptions {
  /** Element observed for visibility (the card). */
  target: Readonly<Ref<HTMLElement | null>>;
  /** True once the load finished (or failed). A finished load is never cancelled. */
  settled: MaybeRefOrGetter<boolean>;
  /** Load right away without waiting for visibility, e.g. first-row cards or images already seen. */
  immediate?: MaybeRefOrGetter<boolean>;
  dwellMs?: number;
  /** Margin around the root that still counts as visible. */
  rootMargin?: string;
  axis?: ScrollAxis;
}

/**
 * Visibility-gated, cancellable image loading.
 *
 * `shouldLoad` turns true after the target has stayed intersecting for `dwellMs`, or at once when
 * `immediate` is true. It turns back to false when the target leaves before the load settled, so the
 * consumer clears `src` and the browser cancels the request. A fast scroll therefore only downloads
 * the images the user actually rests on.
 */
export function useVisibleLoadGate(options: UseVisibleLoadGateOptions) {
  const { target, dwellMs = VISIBLE_LOAD_DWELL_MS, rootMargin = "200px 0px", axis = "y" } = options;
  const isImmediate = () => Boolean(toValue(options.immediate));
  const isSettled = () => Boolean(toValue(options.settled));

  const shouldLoad = ref(isImmediate());
  let visible = false;
  let dwellTimer: ReturnType<typeof setTimeout> | null = null;
  let observer: IntersectionObserver | null = null;
  let observed: HTMLElement | null = null;

  const clearDwell = () => {
    if (dwellTimer) {
      clearTimeout(dwellTimer);
      dwellTimer = null;
    }
  };

  const startDwell = () => {
    if (shouldLoad.value || dwellTimer) return;
    dwellTimer = setTimeout(() => {
      dwellTimer = null;
      if (visible) shouldLoad.value = true;
    }, dwellMs);
  };

  const onIntersect = (entries: IntersectionObserverEntry[]) => {
    const latest = entries[entries.length - 1];
    if (!latest) return;
    visible = latest.isIntersecting;
    if (visible) {
      startDwell();
      return;
    }
    clearDwell();
    if (shouldLoad.value && !isSettled() && !isImmediate()) shouldLoad.value = false;
  };

  const detach = () => {
    observer?.disconnect();
    observer = null;
    observed = null;
    visible = false;
    clearDwell();
  };

  const attach = (el: HTMLElement | null) => {
    if (el && el === observed) return;
    detach();
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      // No visibility signal available: behave like an ungated image.
      shouldLoad.value = true;
      return;
    }
    observer = new IntersectionObserver(onIntersect, {
      root: findScrollRoot(el, axis),
      rootMargin,
      threshold: 0,
    });
    observed = el;
    observer.observe(el);
  };

  /** Re-arms the gate for a new image on the same card. */
  const reset = () => {
    clearDwell();
    shouldLoad.value = isImmediate();
    if (!shouldLoad.value && visible) startDwell();
  };

  watch(
    () => isImmediate(),
    (now) => {
      if (!now) return;
      clearDwell();
      shouldLoad.value = true;
    },
  );
  watch(target, attach, { flush: "post" });
  onMounted(() => attach(target.value));
  onBeforeUnmount(detach);

  return { shouldLoad: readonly(shouldLoad), reset };
}
