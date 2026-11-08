/**
 * Purpose: Lock the "Media" header count of the search results panel (UX review SR-02).
 * Guarantees: The header shows the total from the count query (with the drawer's `+` convention when more exist),
 * falls back to the loaded count while the total is pending, and shows the exact loaded count once every page is
 * loaded; `formatSearchMediaCount` implements that rule.
 * Run when: Changing the results header, `utils/searchResultCount.ts`, or the count endpoint contract.
 */
import { mount } from "@vue/test-utils";
import { computed } from "vue";
import { describe, expect, it, vi } from "vitest";
import type { UnifiedSearchResult } from "@/types";
import { formatSearchMediaCount } from "@/utils/searchResultCount";
import SearchResultsPanelImpl from "../SearchResultsPanelImpl.vue";

// jsdom has no layout, so the virtualizer would render no rows; render every row instead.
vi.mock("@/composables/useVirtualGridRows", async () => {
  const actual = await vi.importActual<typeof import("@/composables/useVirtualGridRows")>(
    "@/composables/useVirtualGridRows",
  );
  return {
    ...actual,
    useVirtualGridRows: ({ rows }: { rows: { value: unknown[] } }) => ({
      virtualizer: computed(() => ({ measureElement: () => {} })),
      virtualItems: computed(() => rows.value.map((_, index) => ({ index, key: index, start: index * 48 }))),
      virtualSpacerStyle: computed(() => ({})),
      totalSize: computed(() => rows.value.length * 48),
      getVirtualRowStyle: () => ({}),
    }),
  };
});

const media = (count: number): UnifiedSearchResult[] =>
  Array.from({ length: count }, (_, index) => ({
    path: `/lib/img-${index}.png`,
    name: `img-${index}.png`,
    type: "image",
    parent_path: "/lib",
    relative_path: `lib/img-${index}.png`,
    asset_id: index + 1,
    library_id: 1,
    library_name: "Lib",
  })) as unknown as UnifiedSearchResult[];

const mountPanel = (props: Record<string, unknown>) =>
  mount(SearchResultsPanelImpl, {
    props: {
      albums: [],
      media: media(60),
      fallbackFolders: [],
      isMobile: false,
      isTablet: false,
      columnCount: 4,
      rowHeight: 200,
      initialPending: false,
      blockingError: false,
      staleError: false,
      paginationError: false,
      successfulEmpty: false,
      hasNextPage: true,
      fetchingNextPage: false,
      showAllIndexedHint: false,
      ...props,
    },
    global: { stubs: { PhotoCard: true, VideoCard: true, AlbumCard: true, SearchResultMetadata: true } },
  });

const mediaBadge = (wrapper: ReturnType<typeof mountPanel>) =>
  wrapper.get(".search-row-header .section-count-badge").text();

describe("search results Media header count", () => {
  it("shows the total from the count query with the drawer's + convention instead of the loaded page size", () => {
    const wrapper = mountPanel({ mediaTotal: { total: 237, hasMore: true } });
    expect(mediaBadge(wrapper)).toBe("237+");
  });

  it("shows an exact total when the count query says nothing more exists", () => {
    const wrapper = mountPanel({ mediaTotal: { total: 75, hasMore: false } });
    expect(mediaBadge(wrapper)).toBe("75");
  });

  it("falls back to the loaded count while the total is pending", () => {
    const wrapper = mountPanel({ mediaTotal: null });
    expect(mediaBadge(wrapper)).toBe("60");
  });

  it("shows the exact loaded count, without +, once every page is loaded", () => {
    const wrapper = mountPanel({ media: media(2), hasNextPage: false, mediaTotal: { total: 2, hasMore: true } });
    expect(mediaBadge(wrapper)).toBe("2");
  });
});

describe("formatSearchMediaCount", () => {
  it("never reports fewer than the loaded count", () => {
    expect(formatSearchMediaCount(60, { total: 10, hasMore: false }, true)).toBe(60);
  });

  it("uses the loaded count when no total is available", () => {
    expect(formatSearchMediaCount(60, undefined, true)).toBe(60);
  });
});
