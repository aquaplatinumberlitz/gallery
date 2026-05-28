import { computed, ref, type ComputedRef, type Ref } from "vue";
import { useHaptic } from "./useHaptic";

export interface PullToRefreshOptions {
  /** Called when pull gesture completes and passes threshold */
  onRefresh: () => Promise<void>;
  /**
   * Optional: custom logic to determine if pull can start.
   * Default: scrollTop <= 5 and not a horizontal scroll target.
   */
  canStart?: (ctx: { target: EventTarget | null; scrollTop: number }) => boolean;
  /** Pull threshold in px (default: 80) */
  threshold?: number;
  /** Max pull distance (default: 120) */
  maxDistance?: number;
  /** Axis lock threshold (default: 8) */
  axisLockThreshold?: number;
}

export interface PullToRefreshState {
  pullDistance: Ref<number>;
  isPulling: Ref<boolean>;
  isRefreshing: Ref<boolean>;
  pullProgress: ComputedRef<number>;
  pullTransform: ComputedRef<string>;
  pullOpacity: ComputedRef<number>;
  showPullIndicator: ComputedRef<boolean>;
  onTouchStart: (e: TouchEvent) => void;
  onTouchMove: (e: TouchEvent) => void;
  onTouchEnd: () => void;
}

function isHorizontalScrollTarget(target: EventTarget | null) {
  if (!(target instanceof Element)) return false;
  return !!target.closest(".album-grid, .albums-grid");
}

function defaultCanStart({ target, scrollTop }: { target: EventTarget | null; scrollTop: number }) {
  return scrollTop <= 5 && !isHorizontalScrollTarget(target);
}

function getScrollTop() {
  const scrollEl = document.querySelector(".scroller") || document.querySelector(".folders-only-container");
  return scrollEl?.scrollTop ?? 0;
}

export function usePullToRefresh(options: PullToRefreshOptions): PullToRefreshState {
  const threshold = options.threshold ?? 80;
  const maxDistance = options.maxDistance ?? 120;
  const axisLockThreshold = options.axisLockThreshold ?? 8;
  const canStart = options.canStart ?? defaultCanStart;
  const { medium: hapticMedium } = useHaptic();

  const pullDistance = ref(0);
  const isPulling = ref(false);
  const isRefreshing = ref(false);
  const pullStartY = ref(0);
  const pullStartX = ref(0);
  const pullAxis = ref<"vertical" | "horizontal" | null>(null);

  function resetPullState() {
    pullDistance.value = 0;
    pullAxis.value = null;
    isPulling.value = false;
  }

  function onTouchStart(e: TouchEvent) {
    if (isRefreshing.value) return;
    if (!canStart({ target: e.target, scrollTop: getScrollTop() })) return;

    pullStartX.value = e.touches[0].clientX;
    pullStartY.value = e.touches[0].clientY;
    pullAxis.value = null;
    isPulling.value = true;
  }

  function onTouchMove(e: TouchEvent) {
    if (!isPulling.value || isRefreshing.value) return;

    const deltaX = e.touches[0].clientX - pullStartX.value;
    const deltaY = e.touches[0].clientY - pullStartY.value;
    const absX = Math.abs(deltaX);
    const absY = Math.abs(deltaY);

    if (!pullAxis.value && Math.max(absX, absY) >= axisLockThreshold) {
      pullAxis.value = absX > absY ? "horizontal" : "vertical";
    }

    if (pullAxis.value === "horizontal") {
      resetPullState();
      return;
    }

    if (deltaY <= 0) {
      pullDistance.value = 0;
      return;
    }

    pullDistance.value = Math.min(deltaY * 0.5, maxDistance);
  }

  function onTouchEnd() {
    if (!isPulling.value) return;
    isPulling.value = false;

    if (pullDistance.value < threshold) {
      pullDistance.value = 0;
      return;
    }

    isRefreshing.value = true;
    hapticMedium();

    options.onRefresh()
      .catch(() => {
        // Keep refresh cleanup local while allowing the caller to handle store errors.
      })
      .finally(() => {
        isRefreshing.value = false;
        pullDistance.value = 0;
      });
  }

  const pullProgress = computed(() => Math.min(pullDistance.value / threshold, 1));
  const pullTransform = computed(() => `translateY(${Math.min(pullDistance.value, maxDistance)}px)`);
  const pullOpacity = computed(() => Math.min(pullDistance.value / (threshold * 0.5), 1));
  const showPullIndicator = computed(() => pullDistance.value > 10 || isRefreshing.value);

  return {
    pullDistance,
    isPulling,
    isRefreshing,
    pullProgress,
    pullTransform,
    pullOpacity,
    showPullIndicator,
    onTouchStart,
    onTouchMove,
    onTouchEnd,
  };
}
