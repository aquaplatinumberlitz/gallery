import { onBeforeUnmount, onMounted, readonly, ref, watch, type Ref } from "vue";

// One ResizeObserver for every card: a virtual grid keeps ~100 cards mounted and an observer per card
// would be wasted work.
const callbacks = new WeakMap<Element, () => void>();
let sharedObserver: ResizeObserver | null = null;

function observe(el: Element, onResize: () => void) {
  if (typeof ResizeObserver === "undefined") return;
  sharedObserver ??= new ResizeObserver((entries) => {
    for (const entry of entries) callbacks.get(entry.target)?.();
  });
  callbacks.set(el, onResize);
  sharedObserver.observe(el);
}

function unobserve(el: Element) {
  callbacks.delete(el);
  sharedObserver?.unobserve(el);
}

/**
 * The rendered layout width of `target` in CSS pixels (0 until it is mounted and laid out).
 *
 * It is measured synchronously in `onMounted`, before the browser has finished choosing an image
 * candidate for a freshly inserted `<img>`, then kept current by a shared ResizeObserver. `clientWidth`
 * is the layout width: unlike `getBoundingClientRect()` it ignores hover/press transforms.
 */
export function useRenderedWidth(target: Readonly<Ref<HTMLElement | null>>) {
  const width = ref(0);
  let observed: HTMLElement | null = null;

  const measure = () => {
    width.value = observed?.clientWidth ?? 0;
  };

  const attach = (el: HTMLElement | null) => {
    if (el === observed) return;
    if (observed) unobserve(observed);
    observed = el;
    if (!el) {
      width.value = 0;
      return;
    }
    measure();
    observe(el, measure);
  };

  onMounted(() => attach(target.value));
  watch(target, attach, { flush: "post" });
  onBeforeUnmount(() => attach(null));

  return readonly(width);
}
