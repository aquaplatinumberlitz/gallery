import { type MaybeRefOrGetter, type ShallowRef, toValue } from "vue";
import { useIntersectionObserver } from "@vueuse/core";

interface UseInfiniteLoadSentinelOptions {
  enabled: MaybeRefOrGetter<boolean>;
  loadMore: () => void | Promise<unknown>;
  rootMargin?: string;
}

export function useInfiniteLoadSentinel({
  sentinel,
  enabled,
  loadMore,
  rootMargin = "400px",
}: UseInfiniteLoadSentinelOptions & { sentinel: Readonly<ShallowRef<HTMLElement | null>> }) {
  useIntersectionObserver(
    sentinel,
    ([entry]) => {
      if (!entry?.isIntersecting || !toValue(enabled)) return;
      void loadMore();
    },
    {
      root: null,
      rootMargin,
      threshold: 0,
    },
  );
}
