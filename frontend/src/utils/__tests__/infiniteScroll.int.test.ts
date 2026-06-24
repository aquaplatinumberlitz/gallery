import { describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { shouldLoadMoreImages } from "../gallery";

/**
 * Integration test: infinite scroll observer + guard + fetchNextPage contract.
 *
 * This replicates the exact pattern used in GalleryGrid.vue:
 *   1. Reactive guard inputs → canLoadMoreImages computed (via shouldLoadMoreImages)
 *   2. Observer callback that checks canLoadMoreImages before calling fetchNextPage
 *   3. Verifies the complete data flow from guard state through to fetchNextPage
 *
 * The observer mechanics (useIntersectionObserver) are mocked — what matters
 * is that the callback reacts correctly to the reactive guard state.
 */
function createInfiniteScrollHarness() {
  const hasMoreImages = ref(false);
  const isLoadingMore = ref(false);
  const isFetching = ref(false);
  const hasSearchQuery = ref(false);

  const canLoadMoreImages = computed(() =>
    shouldLoadMoreImages({
      hasMoreImages: hasMoreImages.value,
      isLoadingMore: isLoadingMore.value,
      isFetching: isFetching.value,
      hasSearchQuery: hasSearchQuery.value,
    }),
  );

  const fetchNextPage = vi.fn();

  const onIntersect = (entry: { isIntersecting: boolean }) => {
    if (!entry.isIntersecting) return;
    if (!canLoadMoreImages.value) return;
    fetchNextPage();
  };

  return {
    guards: { hasMoreImages, isLoadingMore, isFetching, hasSearchQuery },
    fetchNextPage,
    onIntersect,
  };
}

const intersecting = { isIntersecting: true };
const notIntersecting = { isIntersecting: false };

describe("infinite scroll observer + guard integration", () => {
  it("calls fetchNextPage when sentinel is intersecting and all guards pass", () => {
    const h = createInfiniteScrollHarness();
    h.guards.hasMoreImages.value = true;

    h.onIntersect(intersecting);

    expect(h.fetchNextPage).toHaveBeenCalledTimes(1);
  });

  it("does NOT call fetchNextPage when sentinel is NOT intersecting", () => {
    const h = createInfiniteScrollHarness();
    h.guards.hasMoreImages.value = true;

    h.onIntersect(notIntersecting);

    expect(h.fetchNextPage).not.toHaveBeenCalled();
  });

  it.each([
    {
      guard: "hasMoreImages=false",
      setup: (h: ReturnType<typeof createInfiniteScrollHarness>) => {
        h.guards.hasMoreImages.value = false;
      },
    },
    {
      guard: "isLoadingMore=true",
      setup: (h: ReturnType<typeof createInfiniteScrollHarness>) => {
        h.guards.hasMoreImages.value = true;
        h.guards.isLoadingMore.value = true;
      },
    },
    {
      guard: "isFetching=true",
      setup: (h: ReturnType<typeof createInfiniteScrollHarness>) => {
        h.guards.hasMoreImages.value = true;
        h.guards.isFetching.value = true;
      },
    },
    {
      guard: "hasSearchQuery=true",
      setup: (h: ReturnType<typeof createInfiniteScrollHarness>) => {
        h.guards.hasMoreImages.value = true;
        h.guards.hasSearchQuery.value = true;
      },
    },
  ])("does NOT call fetchNextPage when $guard", ({ setup }) => {
    const h = createInfiniteScrollHarness();
    setup(h);

    h.onIntersect(intersecting);

    expect(h.fetchNextPage).not.toHaveBeenCalled();
  });

  it("does NOT call fetchNextPage when all guards block simultaneously", () => {
    const h = createInfiniteScrollHarness();

    h.onIntersect(intersecting);

    expect(h.fetchNextPage).not.toHaveBeenCalled();
  });

  it("transitions from blocked → allowed after guards change reactively", () => {
    const h = createInfiniteScrollHarness();
    h.guards.hasMoreImages.value = true;
    h.guards.isFetching.value = true; // blocked

    h.onIntersect(intersecting);
    expect(h.fetchNextPage).not.toHaveBeenCalled();

    // Fetch completes, now can load more
    h.guards.isFetching.value = false;
    h.onIntersect(intersecting);
    expect(h.fetchNextPage).toHaveBeenCalledTimes(1);
  });
});
