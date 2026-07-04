import { computed, onScopeDispose, readonly, ref, toValue, watch, type MaybeRefOrGetter, type Ref } from "vue";

export const COLLAPSE_SCROLL_Y = 120;
export const EXPAND_SCROLL_Y = 48;

type HeaderScrollTarget = HTMLElement | Window | null;

interface UseCollapsibleHeaderOptions {
  enabled?: MaybeRefOrGetter<boolean>;
  collapseScrollY?: number;
  expandScrollY?: number;
}

function readScrollY(target: HeaderScrollTarget) {
  if (!target) return 0;

  if (typeof HTMLElement !== "undefined" && target instanceof HTMLElement) {
    return target.scrollTop;
  }

  return window.scrollY || window.pageYOffset || document.documentElement.scrollTop || 0;
}

export function useCollapsibleHeader(
  scrollContainerRef?: Ref<HTMLElement | null> | null,
  options: UseCollapsibleHeaderOptions = {},
) {
  const isHeaderCollapsed = ref(false);
  const collapseScrollY = options.collapseScrollY ?? COLLAPSE_SCROLL_Y;
  const expandScrollY = options.expandScrollY ?? EXPAND_SCROLL_Y;
  const isEnabled = computed(() => (options.enabled === undefined ? true : Boolean(toValue(options.enabled))));
  const scrollTarget = computed<HeaderScrollTarget>(() => {
    if (scrollContainerRef) return scrollContainerRef.value;
    return typeof window === "undefined" ? null : window;
  });

  let cleanupScrollListener: (() => void) | null = null;
  let scrollRafId = 0;

  function updateCollapseState(scrollY: number) {
    if (!isEnabled.value) {
      if (isHeaderCollapsed.value) {
        isHeaderCollapsed.value = false;
      }
      return;
    }

    if (!isHeaderCollapsed.value && scrollY > collapseScrollY) {
      isHeaderCollapsed.value = true;
    } else if (isHeaderCollapsed.value && scrollY <= expandScrollY) {
      isHeaderCollapsed.value = false;
    }
  }

  function cancelScrollFrame() {
    if (!scrollRafId || typeof window === "undefined") return;
    window.cancelAnimationFrame(scrollRafId);
    scrollRafId = 0;
  }

  function queueCollapseUpdate(target: HeaderScrollTarget) {
    if (scrollRafId) return;

    if (typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") {
      updateCollapseState(readScrollY(target));
      return;
    }

    scrollRafId = window.requestAnimationFrame(() => {
      scrollRafId = 0;
      updateCollapseState(readScrollY(target));
    });
  }

  function attachCollapseListener(target: HeaderScrollTarget) {
    cleanupScrollListener?.();
    cleanupScrollListener = null;
    cancelScrollFrame();

    updateCollapseState(readScrollY(target));
    if (!target) return;

    const handleScroll = () => {
      queueCollapseUpdate(target);
    };

    target.addEventListener("scroll", handleScroll, { passive: true });
    cleanupScrollListener = () => target.removeEventListener("scroll", handleScroll);
  }

  watch(
    [scrollTarget, isEnabled],
    () => {
      attachCollapseListener(scrollTarget.value);
    },
    { immediate: true, flush: "post" },
  );

  onScopeDispose(() => {
    cleanupScrollListener?.();
    cleanupScrollListener = null;
    cancelScrollFrame();
  });

  return {
    isHeaderCollapsed: readonly(isHeaderCollapsed),
  };
}
