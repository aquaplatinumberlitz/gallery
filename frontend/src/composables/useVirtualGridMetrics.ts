import { computed, onBeforeUnmount, onMounted, ref, watch, type ComponentPublicInstance, type Ref } from "vue";

/** Ignore size changes below this, so layout rounding noise never re-measures the list. */
const SIZE_EPSILON = 0.01;

const blockSizeOf = (entry: ResizeObserverEntry): number => {
  const box = Array.isArray(entry.borderBoxSize) ? entry.borderBoxSize[0] : entry.borderBoxSize;
  return box?.blockSize ?? entry.contentRect.height;
};

/**
 * Row height for a virtual grid whose rows all have the same height but where that height comes from
 * CSS (square cards in a responsive grid) instead of a formula.
 *
 * TanStack Virtual's `measureElement` rounds to whole pixels, which would drift from the natural flow
 * (e.g. 184.5px rows) by half a pixel per row. Instead one rendered row is observed with a
 * ResizeObserver and its exact border-box height is used as the estimate for every row. Until the
 * first measurement `fallback` is used.
 *
 * `observeRow` is meant to be used as a template function ref on every rendered row; only one row is
 * observed at a time and the observer moves on when that row is unmounted.
 */
export function useUniformRowSize(fallback: () => number) {
  const measured = ref(0);
  let observer: ResizeObserver | null = null;
  let observedRow: Element | null = null;

  const ensureObserver = () => {
    if (observer || typeof ResizeObserver === "undefined") return observer;
    observer = new ResizeObserver((entries) => {
      const entry = entries[entries.length - 1];
      if (!entry) return;
      const size = blockSizeOf(entry);
      if (size > 0 && Math.abs(size - measured.value) > SIZE_EPSILON) measured.value = size;
    });
    return observer;
  };

  const observeRow = (target: Element | ComponentPublicInstance | null) => {
    const el = target instanceof Element ? target : null;
    if (!el || observedRow === el || observedRow?.isConnected) return;
    const ro = ensureObserver();
    if (!ro) return;
    if (observedRow) ro.unobserve(observedRow);
    observedRow = el;
    ro.observe(el);
  };

  onBeforeUnmount(() => {
    observer?.disconnect();
    observer = null;
    observedRow = null;
  });

  const rowSize = computed(() => measured.value || Math.max(1, fallback()));
  return { rowSize, observeRow };
}

/**
 * Offset of a virtualized list from the top of its scroll content, for TanStack Virtual's
 * `scrollMargin`, when other content (album strip, section header) precedes the list in the same
 * scroll element.
 *
 * `leadingElement` wraps that preceding content: its size changes (strip collapse animation, header
 * wrap, cover images) move the list, so it and the scroll element itself are observed.
 */
export function useVirtualScrollMargin(
  scrollElement: Ref<HTMLElement | null>,
  listElement: Ref<HTMLElement | null>,
  leadingElement: Ref<HTMLElement | null>,
) {
  const margin = ref(0);
  let observer: ResizeObserver | null = null;

  const update = () => {
    const scroller = scrollElement.value;
    const list = listElement.value;
    if (!scroller || !list) return;
    const next = list.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop;
    if (Math.abs(next - margin.value) > SIZE_EPSILON) margin.value = next;
  };

  const observe = () => {
    observer?.disconnect();
    observer = null;
    if (typeof ResizeObserver === "undefined") return;
    observer = new ResizeObserver(update);
    for (const el of [scrollElement.value, leadingElement.value]) {
      if (el) observer.observe(el);
    }
  };

  watch([scrollElement, listElement, leadingElement], () => {
    observe();
    update();
  });
  onMounted(() => {
    observe();
    update();
  });
  onBeforeUnmount(() => {
    observer?.disconnect();
    observer = null;
  });

  return { scrollMargin: margin, updateScrollMargin: update };
}
