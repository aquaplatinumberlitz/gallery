import { computed, readonly, ref, toValue, watch, type MaybeRefOrGetter, type Ref } from "vue";
import { useScroll } from "@vueuse/core";

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

  const { y, measure } = useScroll(scrollTarget, {
    eventListenerOptions: { passive: true },
  });

  function updateCollapseState(scrollY: number) {
    if (!isEnabled.value) {
      isHeaderCollapsed.value = false;
      return;
    }

    if (!isHeaderCollapsed.value && scrollY > collapseScrollY) {
      isHeaderCollapsed.value = true;
    } else if (isHeaderCollapsed.value && scrollY < expandScrollY) {
      isHeaderCollapsed.value = false;
    }
  }

  watch(
    y,
    (scrollY) => {
      updateCollapseState(scrollY);
    },
    { immediate: true },
  );

  watch(
    [scrollTarget, isEnabled],
    () => {
      measure();
      updateCollapseState(readScrollY(scrollTarget.value));
    },
    { immediate: true, flush: "post" },
  );

  return {
    isHeaderCollapsed: readonly(isHeaderCollapsed),
  };
}
