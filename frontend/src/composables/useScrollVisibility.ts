import { ref, onMounted, onBeforeUnmount, watch, type Ref } from "vue";
import { useEventListener, useMutationObserver } from "@vueuse/core";

const SCROLL_SELECTOR = ".scroller, .folders-only-container";

export function useScrollVisibility(containerRef?: Ref<HTMLElement | null>) {
  const barsVisible = ref(true);
  const isScrollingDown = ref(false);
  let lastScrollY = 0;
  let rafId = 0;
  let intervalId: ReturnType<typeof setInterval> | null = null;
  let cleanupScroll: (() => void) | null = null;
  let attachedElement: HTMLElement | null = null;
  const mutationTarget = ref<HTMLElement | null>(null);

  function attachToElement(el: HTMLElement) {
    const handler = () => {
      if (rafId) return;
      rafId = requestAnimationFrame(() => {
        rafId = 0;
        const st = el.scrollTop;

        // ★ BOTTOM GUARD: prevent toggle when near bottom
        // to avoid layout-shift / rubber-band feedback loop on iOS
        const nearBottom = el.scrollHeight - el.clientHeight - st < 150;
        if (nearBottom && st > 0) {
          lastScrollY = st;
          return;
        }

        if (st <= 0) {
          barsVisible.value = true;
          isScrollingDown.value = false;
        } else if (st > lastScrollY) {
          barsVisible.value = false;
          isScrollingDown.value = true;
        } else if (st < lastScrollY) {
          barsVisible.value = true;
          isScrollingDown.value = false;
        }
        lastScrollY = st;
      });
    };
    return useEventListener(el, "scroll", handler, { passive: true });
  }

  function cleanupAttachedElement() {
    cleanupScroll?.();
    cleanupScroll = null;
    attachedElement = null;
  }

  function attach(el: HTMLElement) {
    if (attachedElement === el) return;
    cleanupAttachedElement();
    attachedElement = el;
    lastScrollY = el.scrollTop;
    cleanupScroll = attachToElement(el);
  }

  // Watch for DOM re-creation within the scroller's parent container
  useMutationObserver(
    () => mutationTarget.value,
    () => {
      const newEl = document.querySelector<HTMLElement>(SCROLL_SELECTOR);
      if (newEl) {
        attach(newEl);
      }
    },
    { childList: true, subtree: true },
  );

  onMounted(() => {
    if (containerRef) {
      watch(
        containerRef,
        (el) => {
          if (el) {
            attach(el);
          } else {
            cleanupAttachedElement();
          }
        },
        { immediate: true },
      );
      return;
    }

    // Poll for the active scroll container when no injected ref is provided.
    intervalId = setInterval(() => {
      const el = document.querySelector<HTMLElement>(SCROLL_SELECTOR);
      if (el && el.scrollHeight > el.clientHeight) {
        clearInterval(intervalId!);
        intervalId = null;
        attach(el);
        const scrollerParent = el.parentElement;
        if (scrollerParent) {
          mutationTarget.value = scrollerParent;
        }
      }
    }, 200);
  });

  onBeforeUnmount(() => {
    if (intervalId !== null) {
      clearInterval(intervalId);
      intervalId = null;
    }
    cleanupAttachedElement();
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
  });

  return { barsVisible, isScrollingDown };
}
