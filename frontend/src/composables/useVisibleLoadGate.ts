import { onBeforeUnmount, onMounted, readonly, ref, toValue, watch, type MaybeRefOrGetter, type Ref } from "vue";

/** While the scroll root is scrolling, how long a card must stay intersecting before its request may start. */
export const VISIBLE_LOAD_DWELL_MS = 120;
/** The scroll root counts as scrolling until this long after its last scroll event. */
export const SCROLL_IDLE_MS = 150;

interface ScrollActivity {
  scrolling: boolean;
  idleTimer: ReturnType<typeof setTimeout> | null;
  idleListeners: Set<() => void>;
  stop: () => void;
}

// One scroll listener per scroll root, shared by every card inside it.
const scrollActivities = new WeakMap<EventTarget, ScrollActivity>();

/**
 * Tracks whether `root` (or the window when null) scrolled within the last SCROLL_IDLE_MS.
 * `onIdle` runs when scrolling stops. Returns `isScrolling` and a `release` that detaches the card.
 */
function trackScrollActivity(root: HTMLElement | null, onIdle: () => void) {
  const target: EventTarget = root ?? window;
  let activity = scrollActivities.get(target);
  if (!activity) {
    const created: ScrollActivity = {
      scrolling: false,
      idleTimer: null,
      idleListeners: new Set(),
      stop: () => {},
    };
    const onScroll = () => {
      created.scrolling = true;
      if (created.idleTimer) clearTimeout(created.idleTimer);
      created.idleTimer = setTimeout(() => {
        created.idleTimer = null;
        created.scrolling = false;
        for (const listener of [...created.idleListeners]) listener();
      }, SCROLL_IDLE_MS);
    };
    target.addEventListener("scroll", onScroll, { passive: true });
    created.stop = () => {
      target.removeEventListener("scroll", onScroll);
      if (created.idleTimer) clearTimeout(created.idleTimer);
      scrollActivities.delete(target);
    };
    scrollActivities.set(target, created);
    activity = created;
  }
  const shared = activity;
  shared.idleListeners.add(onIdle);
  return {
    isScrolling: () => shared.scrolling,
    release: () => {
      shared.idleListeners.delete(onIdle);
      if (shared.idleListeners.size === 0) shared.stop();
    },
  };
}

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
 * `shouldLoad` turns true as soon as the target is in range while its scroll root is at rest (album
 * open, settling after a scroll, tab switch, resize). While the root is actively scrolling (a scroll
 * event within SCROLL_IDLE_MS) the target must stay in range for `dwellMs` first, and a card still
 * pending when scrolling stops starts at once. `immediate` skips the gate. `shouldLoad` turns back to
 * false when the target leaves before the load settled, so the consumer clears `src` and the browser
 * cancels the request. A fast scroll therefore only downloads the images the user actually rests on.
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
  let scrollActivity: ReturnType<typeof trackScrollActivity> | null = null;

  const clearDwell = () => {
    if (dwellTimer) {
      clearTimeout(dwellTimer);
      dwellTimer = null;
    }
  };

  /** Loads at once when the root is at rest, otherwise after the dwell. */
  const startLoad = () => {
    if (shouldLoad.value || dwellTimer) return;
    if (!scrollActivity?.isScrolling()) {
      shouldLoad.value = true;
      return;
    }
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
      startLoad();
      return;
    }
    clearDwell();
    if (shouldLoad.value && !isSettled() && !isImmediate()) shouldLoad.value = false;
  };

  /** Scrolling stopped: a card still in range must not wait out the rest of its dwell. */
  const onScrollIdle = () => {
    if (!visible || shouldLoad.value) return;
    clearDwell();
    shouldLoad.value = true;
  };

  const detach = () => {
    scrollActivity?.release();
    scrollActivity = null;
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
    const root = findScrollRoot(el, axis);
    scrollActivity = trackScrollActivity(root, onScrollIdle);
    observer = new IntersectionObserver(onIntersect, {
      root,
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
    if (!shouldLoad.value && visible) startLoad();
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
