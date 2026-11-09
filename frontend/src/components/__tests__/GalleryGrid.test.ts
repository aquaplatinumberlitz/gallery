import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import { nextTick, ref } from "vue";
import { fuzzySearchFileNodes } from "@/utils/fuzzySearch";
import { GalleryAPIError } from "@/services/api";

// The grid mounts its rows in steps (one task each, see GalleryGrid "STAGE_*"): wait until the row count stops
// growing before asserting on the settled grid.
async function settleRowStaging(wrapper: { findAll: (selector: string) => unknown[] }) {
  let previous = -1;
  for (let i = 0; i < 80; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 5));
    const rows = wrapper.findAll(".tanstack-virtual-row").length;
    if (rows > 0 && rows === previous) return;
    previous = rows;
  }
}

let mockIsLoading = ref(false);
let mockIsFetching = ref(false);
let mockIsSuccess = ref(true);
let mockIsPending = ref(false);
let mockHasNextPage = ref(false);
let mockIsFetchingNextPage = ref(false);
let mockError = ref<Error | null>(null);
let mockFolders: any = ref([]);
let mockMedia: any = ref([]);
let mockActiveFolderPath: any = ref(null);
let mockHasActivePage = ref(true);
const mockRefetch = vi.fn();
const mockFetchNextPage = vi.fn();
const mockUseUnifiedSearchQuery = vi.hoisted(() => vi.fn());
const mockUseSearchMatchPreview = vi.hoisted(() => vi.fn());
const mockRouterPush = vi.hoisted(() => vi.fn());
const mockBrowseOptions = vi.hoisted(() => ({ current: undefined as undefined | Record<string, any> }));

vi.mock("@/composables/useInfiniteBrowseQuery", () => ({
  useInfiniteBrowseQuery: (_library: unknown, _path: unknown, _offline: unknown, options?: Record<string, any>) => {
    mockBrowseOptions.current = options;
    return {
      isLoading: mockIsLoading,
      isFetching: mockIsFetching,
      isSuccess: mockIsSuccess,
      isPending: mockIsPending,
      hasNextPage: mockHasNextPage,
      isFetchingNextPage: mockIsFetchingNextPage,
      error: mockError,
      refetch: mockRefetch,
      fetchNextPage: mockFetchNextPage,
      folders: mockFolders,
      media: mockMedia,
      activeFolderPath: mockActiveFolderPath,
      hasActivePage: mockHasActivePage,
    };
  },
}));

vi.mock("@/composables/useUnifiedSearchQuery", () => ({
  useUnifiedSearchQuery: mockUseUnifiedSearchQuery,
}));

mockUseUnifiedSearchQuery.mockImplementation(() => ({
  isLoading: { value: false },
  isFetching: { value: false },
  isFetchingNextPage: { value: false },
  isError: { value: false },
  isRefetchError: { value: false },
  isFetchNextPageError: { value: false },
  error: mockError,
  isPending: { value: false },
  isSuccess: mockIsSuccess,
  hasNextPage: { value: false },
  fetchNextPage: vi.fn(),
  debouncedQuery: { value: "" },
  albums: { value: [] },
  photos: { value: [] },
  videos: { value: [] },
  prompt: { value: [] },
  media: { value: [] },
}));

vi.mock("@/composables/useSearchMatchPreview", () => ({
  useSearchMatchPreview: mockUseSearchMatchPreview,
}));

mockUseSearchMatchPreview.mockImplementation(() => ({
  state: ref({ status: "idle", total: 0, hasMore: false }),
  isFetching: ref(false),
}));

vi.mock("@/composables/useColumnResize", () => ({
  useColumnResize: () => ({
    columnCount: ref(4),
    sliderLevel: ref(0),
    rowHeight: ref(200),
    setGridRef: vi.fn(),
  }),
  PHOTO_GRID_LEVELS: [{ level: 0, label: "Compact", columns: 4 }],
  GRID_COLUMN_MAP: { tablet: { 0: 3 } },
}));

vi.mock("@/composables/useDevice", () => ({
  useDevice: () => ({
    isTablet: { value: false },
  }),
}));

vi.mock("@/composables/usePullToRefresh", () => ({
  usePullToRefresh: () => ({
    pullDistance: { value: 0 },
    isRefreshing: { value: false },
    showPullIndicator: { value: false },
    pullProgress: { value: 0 },
    pullTransform: { value: "" },
    pullOpacity: { value: 1 },
    onTouchStart: vi.fn(),
    onTouchMove: vi.fn(),
    onTouchEnd: vi.fn(),
  }),
}));

vi.mock("@/composables/useDelayedBoolean", () => ({
  useDelayedBoolean: () => false,
}));

vi.mock("@/composables/useNaturalSort", () => ({
  compareNatural: vi.fn(() => 0),
}));

vi.mock("@/utils/fuzzySearch", () => ({
  fuzzySearchFileNodes: vi.fn((items) => items),
}));

vi.mock("@/utils/gallery", () => ({
  shouldLoadMoreImages: vi.fn(() => false),
}));

const mockStore: Record<string, any> = {
  activeLibraryId: 1,
  activeImportPathId: 1,
  activeImportRootPath: "/photos",
  activeLibraryHydrated: true,
  currentBrowsePath: "/photos",
  searchQuery: "",
  submittedSearchQuery: "",
  searchScope: "current",
  searchMode: "lexical",
  searchFilters: { prompt_groups: [], workflow_groups: [] },
  searchFieldErrors: {},
  sortField: "date",
  sortOrder: "desc",
  isLoading: false,
  errorMessage: "",
  errorType: null,
  history: [],
  historyIndex: 0,
  metadataInspector: {
    scope: "current",
    query: "",
    sort: "date_desc",
    modelFilter: "all",
    promptFilter: "all",
    selectedPath: "",
    scrollTop: 0,
    scrollPath: "",
  },
  setSortField: vi.fn(),
  setSortOrder: vi.fn(),
  setSearchLoading: vi.fn(),
  setSearchFieldErrors: vi.fn(),
  clearSearchFieldErrors: vi.fn(),
  selectFolder: vi.fn(),
  clearSearch: vi.fn(),
  clearError: vi.fn(),
  setActiveLibrary: vi.fn(),
  openInExplorer: vi.fn(),
  goBack: vi.fn(),
  goForward: vi.fn(),
  $id: "gallery",
};

vi.mock("@/stores/gallery", () => ({
  useGalleryStore: () => mockStore,
}));

vi.mock("vue-router", () => ({
  useRouter: () => ({
    push: mockRouterPush,
  }),
}));

function defaultStoreValues() {
  return {
    activeLibraryId: 1,
    activeImportPathId: 1,
    activeImportRootPath: "/photos",
    errorMessage: "",
    errorType: null,
    isLoading: false,
    searchQuery: "",
    submittedSearchQuery: "",
    searchScope: "current",
    searchMode: "lexical",
    searchFilters: { prompt_groups: [], workflow_groups: [] },
    searchFieldErrors: {},
  };
}

describe("GalleryGrid", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    mockIsLoading = ref(false);
    mockIsFetching = ref(false);
    mockIsSuccess = ref(true);
    mockIsPending = ref(false);
    mockHasNextPage = ref(false);
    mockIsFetchingNextPage = ref(false);
    mockError = ref(null);
    mockFolders = ref([]);
    mockMedia = ref([]);
    mockActiveFolderPath = ref(null);
    mockHasActivePage = ref(true);
    mockUseUnifiedSearchQuery.mockClear();
    Object.assign(mockStore, defaultStoreValues());
  });

  async function mountSubject(overrides?: {
    props?: Record<string, any>;
    store?: Record<string, any>;
    stubs?: Record<string, any>;
  }) {
    if (overrides?.store) {
      Object.assign(mockStore, overrides.store);
    }
    const GalleryGrid = (await import("../GalleryGrid.vue")).default;
    const queryClient = createIsolatedQueryClient();
    return mount(GalleryGrid, {
      props: { isMobile: false, ...overrides?.props },
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          AlbumCard: { template: "<div class='album-card' />" },
          PhotoCard: { template: "<div class='photo-card' />" },
          VideoCard: { template: "<div class='video-card' />" },
          SkeletonLoader: { template: "<div class='skeleton-loader' />" },
          Breadcrumb: { template: "<div class='breadcrumb-stub'><slot /><slot name='actions' /></div>" },
          EmptyState: {
            props: ["title", "description", "actionLabel", "actionIcon"],
            emits: ["action"],
            template:
              "<div class='empty-state'><p data-testid='empty-title'>{{ title }}</p><p data-testid='empty-description'>{{ description }}</p><button v-if='actionLabel' data-testid='empty-action' @click=\"$emit('action')\">{{ actionLabel }}</button><span data-testid='empty-action-icon'>{{ actionIcon }}</span></div>",
          },
          ResponsiveLibrarySelector: {
            props: ["modelValue"],
            template: "<div data-testid='library-selector' :data-open='String(modelValue)' />",
          },
          SortSelect: {
            props: ["modelValue", "ariaLabel", "prefix", "triggerLabel", "triggerClass"],
            template: "<select :aria-label='ariaLabel' />",
          },
          Button: { template: "<button><slot /></button>" },
          Badge: { template: "<span><slot /></span>" },
          Tooltip: { template: "<span><slot /></span>" },
          TooltipTrigger: { template: "<span><slot /></span>" },
          TooltipContent: { template: "<span><slot /></span>" },
          DropdownMenu: { template: "<div><slot /></div>" },
          DropdownMenuContent: { template: "<div><slot /></div>" },
          DropdownMenuRadioGroup: { template: "<div><slot /></div>" },
          DropdownMenuRadioItem: { template: "<div><slot /></div>" },
          DropdownMenuTrigger: { template: "<div><slot /></div>" },
          ...overrides?.stubs,
        },
      },
    });
  }

  it("shows loading badge when loading", async () => {
    mockIsLoading = ref(true);
    const wrapper = await mountSubject();
    expect(wrapper.text()).toContain("Loading");
  });

  it("shows error banner when error message exists", async () => {
    const wrapper = await mountSubject({ store: { errorMessage: "Failed to load" } });
    expect(wrapper.find("[role='alert']").exists()).toBe(true);
  });

  it("publishes exact workflow field errors from the search query", async () => {
    mockError = ref(
      new GalleryAPIError("bad_request", "Invalid request", "Check fields", false, {
        "filters.workflow_groups[0].predicates[0].value": "Invalid integer",
      }),
    );
    mockIsSuccess = ref(false);
    await mountSubject({ store: { searchQuery: "workflow", submittedSearchQuery: "workflow" } });
    expect(mockStore.setSearchFieldErrors).toHaveBeenCalledWith({
      "filters.workflow_groups[0].predicates[0].value": "Invalid integer",
    });
  });

  it("renders breadcrumb on desktop", async () => {
    const wrapper = await mountSubject({
      stubs: { Breadcrumb: { template: "<div class='breadcrumb-stub'>breadcrumb</div>" } },
    });
    expect(wrapper.text()).toContain("breadcrumb");
  });

  it("shows density dropdown trigger on desktop", async () => {
    const wrapper = await mountSubject();
    expect(wrapper.text()).toContain("View");
  });

  it("shows open-in-explorer button on desktop", async () => {
    const wrapper = await mountSubject();
    expect(wrapper.find('[aria-label="Open current folder in file explorer"]').exists()).toBe(true);
  });

  it("opens the library selector from the no-library empty state", async () => {
    const wrapper = await mountSubject({
      store: {
        activeLibraryId: null,
        activeImportPathId: null,
        activeLibraryHydrated: true,
        currentBrowsePath: "",
      },
    });

    expect(wrapper.get("[data-testid='empty-title']").text()).toBe("No library selected");
    expect(wrapper.get("[data-testid='empty-description']").text()).toBe(
      "Add or choose a registered library before browsing albums and photos.",
    );
    expect(wrapper.get("[data-testid='empty-action']").text()).toBe("Choose Library");
    expect(wrapper.get("[data-testid='library-selector']").attributes("data-open")).toBe("false");

    await wrapper.get("[data-testid='empty-action']").trigger("click");

    expect(wrapper.get("[data-testid='library-selector']").attributes("data-open")).toBe("true");
    expect(mockRouterPush).not.toHaveBeenCalled();
  });

  it("shows SortSelect on desktop toolbar", async () => {
    const wrapper = await mountSubject();
    expect(wrapper.find('[aria-label="Sort gallery"]').exists()).toBe(true);
  });

  it("shows desktop toolbar", async () => {
    const wrapper = await mountSubject();
    expect(wrapper.find("[aria-label='Go back']").exists()).toBe(true);
  });

  it("renders back and forward navigation buttons", async () => {
    const wrapper = await mountSubject();
    expect(wrapper.find('[aria-label="Go back"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="Go forward"]').exists()).toBe(true);
  });

  it("does not run client fuzzy search when the search query is empty", async () => {
    mockFolders = ref([{ name: "Mika", path: "/photos/mika", type: "folder", has_children: false }]);
    mockMedia = ref([{ name: "mika.png", path: "/photos/mika.png", type: "image", mtime: 1 }]);

    await mountSubject({ store: { searchQuery: "" } });

    expect(fuzzySearchFileNodes).not.toHaveBeenCalled();
  });

  it("does not switch to search filtering for a one-character draft query", async () => {
    mockFolders = ref([{ name: "Mika", path: "/photos/mika", type: "folder", has_children: false }]);
    mockMedia = ref([{ name: "mika.png", path: "/photos/mika.png", type: "image", mtime: 1 }]);

    const wrapper = await mountSubject({ store: { searchQuery: "m", submittedSearchQuery: "" } });

    expect(fuzzySearchFileNodes).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Keep typing to search, or press Enter.");
  });

  it("keeps a two-character query as draft until debounce settles", async () => {
    mockFolders = ref([{ name: "Mika", path: "/photos/mika", type: "folder", has_children: false }]);
    mockMedia = ref([{ name: "mika.png", path: "/photos/mika.png", type: "image", mtime: 1 }]);

    const wrapper = await mountSubject({ store: { searchQuery: "mi", submittedSearchQuery: "" } });

    expect(mockUseUnifiedSearchQuery).toHaveBeenCalled();
    expect(mockUseUnifiedSearchQuery.mock.calls[0][0].value?.text).toBe("mi");
    expect(fuzzySearchFileNodes).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Keep typing to search, or press Enter.");
  });

  // SE-01: a shown search stays shown while the next query settles (no browse fallback or "Keep typing" hint).
  it("keeps the search panel while a shown search settles to a longer query (SE-01)", async () => {
    mockUseUnifiedSearchQuery.mockImplementation(() => ({
      isLoading: { value: false },
      isFetching: { value: true },
      isFetchingNextPage: { value: false },
      isError: { value: false },
      isRefetchError: { value: false },
      isFetchNextPageError: { value: false },
      error: mockError,
      isPending: { value: false },
      isPlaceholderData: { value: true },
      isSuccess: mockIsSuccess,
      hasNextPage: { value: false },
      fetchNextPage: vi.fn(),
      debouncedQuery: { value: "ni" },
      albums: { value: [] },
      photos: { value: [] },
      videos: { value: [] },
      prompt: { value: [] },
      media: { value: [{ name: "night.png", path: "/photos/night.png", type: "image", mtime: 1 }] },
    }));
    const wrapper = await mountSubject({
      store: { searchQuery: "nig", submittedSearchQuery: "" },
      stubs: { SearchResultsPanel: { props: ["media"], template: "<div class='search-panel-stub' />" } },
    });

    expect(wrapper.find(".search-panel-stub").exists()).toBe(true);
    expect(wrapper.find(".search-warmup-hint").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Keep typing to search, or press Enter.");
  });

  // SE-01: while a newer query settles, the header keeps the total of the results still on screen (no flicker to the
  // loaded count and back).
  it("keeps the last search total in the header while a newer query settles (SE-01)", async () => {
    mockUseSearchMatchPreview.mockImplementationOnce(() => ({
      state: ref({ status: "done", total: 298, hasMore: true }),
      isFetching: ref(false),
    }));
    mockUseUnifiedSearchQuery.mockImplementation(() => ({
      isLoading: { value: false },
      isFetching: { value: true },
      isFetchingNextPage: { value: false },
      isError: { value: false },
      isRefetchError: { value: false },
      isFetchNextPageError: { value: false },
      error: mockError,
      isPending: { value: false },
      isPlaceholderData: { value: true },
      isSuccess: mockIsSuccess,
      hasNextPage: { value: true },
      fetchNextPage: vi.fn(),
      debouncedQuery: { value: "ni" },
      albums: { value: [] },
      photos: { value: [] },
      videos: { value: [] },
      prompt: { value: [] },
      media: { value: [{ name: "night.png", path: "/photos/night.png", type: "image", mtime: 1 }] },
    }));
    const wrapper = await mountSubject({
      store: { searchQuery: "nig", submittedSearchQuery: "" },
      stubs: {
        SearchResultsPanel: {
          props: ["mediaTotal", "settling"],
          template: "<div class='search-panel-stub' :data-total='JSON.stringify(mediaTotal)' :data-settling='String(settling)' />",
        },
      },
    });

    const panel = wrapper.get(".search-panel-stub");
    expect(panel.attributes("data-settling")).toBe("true");
    expect(JSON.parse(panel.attributes("data-total") ?? "null")).toEqual({ total: 298, hasMore: true });
  });

  // SE-05: the count request is only sent for settled, non-empty text (never the Enter-time empty text).
  it("sends no search-count request for empty or unsettled text (SE-05)", async () => {
    await mountSubject({ store: { searchQuery: "nig", submittedSearchQuery: "nig" } });
    const request = mockUseSearchMatchPreview.mock.calls.at(-1)?.[0];
    const value = typeof request === "function" ? request() : request;
    expect(value).toBeNull();
  });

  it("allows a one-character query after explicit submit", async () => {
    mockFolders = ref([{ name: "Mika", path: "/photos/mika", type: "folder", has_children: false }]);
    mockMedia = ref([{ name: "mika.png", path: "/photos/mika.png", type: "image", mtime: 1 }]);

    await mountSubject({ store: { searchQuery: "m", submittedSearchQuery: "m" } });

    expect(mockUseUnifiedSearchQuery).toHaveBeenCalled();
    expect(mockUseUnifiedSearchQuery.mock.calls[0][0].value?.text).toBe("m");
  });

  describe("content versions", () => {
    const versioned = [
      {
        name: "a.png",
        path: "/photos/a.png",
        type: "image",
        mtime: 2,
        content_version: "11-12",
        width: 640,
        height: 480,
      },
      { name: "b.png", path: "/photos/b.png", type: "image", mtime: 1 },
    ];
    // jsdom has no layout: give every element a viewport-sized box so the virtualizer renders rows.
    beforeEach(() => {
      vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(800);
      vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(1000);
    });
    const versionProbe = {
      PhotoCard: {
        props: ["src", "version", "imageWidth", "imageHeight"],
        template:
          "<div class='photo-card' :data-src='src' :data-version='version' :data-w='imageWidth' :data-h='imageHeight' />",
      },
    };

    it.each([
      ["desktop", false],
      ["mobile", true],
    ])("passes each item's content_version and dimensions to its %s PhotoCard", async (_name, isMobile) => {
      mockMedia = ref(versioned);

      const wrapper = await mountSubject({ props: { isMobile }, stubs: versionProbe });
      await settleRowStaging(wrapper);

      const cards = wrapper.findAll(".photo-card");
      expect(cards.map((c) => [c.attributes("data-src"), c.attributes("data-version")])).toEqual([
        ["/photos/a.png", "11-12"],
        ["/photos/b.png", undefined],
      ]);
      expect(cards[0]!.attributes("data-w")).toBe("640");
      expect(cards[0]!.attributes("data-h")).toBe("480");
    });
  });

  it("keeps the content_version of search results in the lightbox items", async () => {
    const searchResult = {
      asset_id: 5,
      library_id: 1,
      name: "hit.png",
      path: "/photos/hit.png",
      type: "image",
      mtime: 1,
      content_version: "31-32",
      cover_versions: [],
    };
    mockUseUnifiedSearchQuery.mockImplementationOnce(() => ({
      isLoading: { value: false },
      isFetching: { value: false },
      isFetchingNextPage: { value: false },
      isError: { value: false },
      isRefetchError: { value: false },
      isFetchNextPageError: { value: false },
      error: mockError,
      isPending: { value: false },
      isSuccess: mockIsSuccess,
      hasNextPage: { value: false },
      fetchNextPage: vi.fn(),
      debouncedQuery: { value: "hit" },
      albums: { value: [] },
      photos: { value: [searchResult] },
      videos: { value: [] },
      prompt: { value: [] },
      media: { value: [searchResult] },
    }));
    const wrapper = await mountSubject({
      store: { searchQuery: "hit", submittedSearchQuery: "hit" },
      stubs: {
        SearchResultsPanel: {
          props: ["media"],
          emits: ["openMedia"],
          template: "<button class='open-hit' @click=\"$emit('openMedia', media[0])\" />",
        },
      },
    });

    await wrapper.get(".open-hit").trigger("click");

    const lightbox = (await import("@/stores/lightbox")).useLightboxStore();
    expect(lightbox.galleryItems.map((node) => [node.path, node.content_version])).toEqual([
      ["/photos/hit.png", "31-32"],
    ]);
  });

  describe("mobile virtual grid", () => {
    const manyImages = (count: number) =>
      Array.from({ length: count }, (_, i) => ({
        name: `img-${i}.png`,
        path: `/photos/img-${i}.png`,
        type: "image",
        mtime: count - i,
      }));
    // jsdom has no layout: give every element a viewport-sized box so the virtualizer renders rows.
    beforeEach(() => {
      vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(800);
      vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(390);
    });
    const priorityProbe = {
      PhotoCard: {
        props: ["src", "fetchPriority"],
        template: "<div class='photo-card' :data-src='src' :data-priority='fetchPriority' />",
      },
    };

    it("renders only the rows near the viewport instead of every card", async () => {
      mockMedia = ref(manyImages(400));

      const wrapper = await mountSubject({ props: { isMobile: true }, stubs: priorityProbe });
      await settleRowStaging(wrapper);

      const rows = wrapper.findAll(".tanstack-virtual-row");
      const cards = wrapper.findAll(".photo-card");
      // 400 images in 4 columns are 100 rows; the previous native-flow grid rendered all 400 cards.
      expect(rows.length).toBeGreaterThan(0);
      expect(rows.length).toBeLessThan(100);
      expect(cards.length).toBe(rows.length * 4);
      expect(wrapper.find(".mobile-scroller .tanstack-virtual-spacer").exists()).toBe(true);
    });

    it("keeps the album strip, media header and load-more sentinel around the virtual rows", async () => {
      mockFolders = ref([{ name: "Mika", path: "/photos/mika", type: "folder", has_children: false }]);
      mockMedia = ref(manyImages(40));

      const wrapper = await mountSubject({
        props: { isMobile: true },
        stubs: { AlbumScroller: { template: "<div class='album-strip-stub' />" } },
      });

      const scroller = wrapper.get(".mobile-scroller");
      const children = Array.from(scroller.element.children).map((el) => el.className);
      expect(children).toEqual([
        "mobile-grid-leading",
        "tanstack-virtual-spacer",
        expect.stringContaining("scroller-footer"),
      ]);
      expect(scroller.find(".mobile-grid-leading .album-strip-stub").exists()).toBe(true);
      expect(scroller.find(".scroller-footer .load-more-sentinel").exists()).toBe(true);
    });

    it("loads only first-row thumbnails at high priority", async () => {
      mockMedia = ref(manyImages(40));

      const wrapper = await mountSubject({ props: { isMobile: true }, stubs: priorityProbe });
      await settleRowStaging(wrapper);

      const rows = wrapper.findAll(".tanstack-virtual-row");
      expect(rows[0].findAll("[data-priority='high']")).toHaveLength(4);
      for (const row of rows.slice(1)) {
        expect(row.findAll("[data-priority='high']")).toHaveLength(0);
      }
    });
  });

  describe("album open: staged rows and thumbnail warm-up", () => {
    const images = (count: number, prefix = "stage") =>
      Array.from({ length: count }, (_, i) => ({
        name: `${prefix}-${i}.png`,
        path: `/photos/${prefix}-${i}.png`,
        type: "image",
        mtime: count - i,
      }));
    beforeEach(() => {
      vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(800);
      vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(390);
      document.head.querySelectorAll("link[rel='preload']").forEach((link) => link.remove());
    });

    const rowCountsUntilSettled = async (wrapper: { findAll: (selector: string) => unknown[] }) => {
      const counts: number[] = [];
      for (let i = 0; i < 60; i += 1) {
        counts.push(wrapper.findAll(".tanstack-virtual-row").length);
        await new Promise((resolve) => setTimeout(resolve, 0));
        if (counts.length > 8 && counts.slice(-6).every((count) => count === counts[counts.length - 1])) break;
      }
      return counts;
    };

    it("mounts the grid container first and then adds rows in steps until the range is complete", async () => {
      mockMedia = ref(images(400));

      const wrapper = await mountSubject({ props: { isMobile: true } });
      await nextTick();
      const counts = await rowCountsUntilSettled(wrapper);

      const settled = counts[counts.length - 1];
      expect(wrapper.find(".mobile-scroller").exists()).toBe(true);
      // First task: the container without rows. Then growth in steps, never shrinking, to the full range.
      expect(counts[0]).toBe(0);
      expect(settled).toBeGreaterThan(2);
      expect(counts.every((count, i) => i === 0 || count >= counts[i - 1])).toBe(true);
      const firstRows = counts.find((count) => count > 0)!;
      expect(firstRows).toBe(1);
      expect(new Set(counts.filter((count) => count > 0 && count < settled)).size).toBeGreaterThan(0);
    });

    it("takes bigger steps when a step finishes quickly, so a fast CPU needs fewer of them", async () => {
      const distinctRowCounts = async (msPerClockRead: number) => {
        let clock = 0;
        const now = vi.spyOn(performance, "now").mockImplementation(() => (clock += msPerClockRead));
        mockMedia = ref(images(400));
        const wrapper = await mountSubject({ props: { isMobile: true } });
        await nextTick();
        const counts = await rowCountsUntilSettled(wrapper);
        now.mockRestore();
        wrapper.unmount();
        return new Set(counts.filter((count) => count > 0)).size;
      };

      const slowSteps = await distinctRowCounts(100);
      const fastSteps = await distinctRowCounts(0.01);

      expect(slowSteps).toBeGreaterThan(2);
      expect(fastSteps).toBeLessThan(slowSteps);
    });

    it("ends the staging as soon as the user scrolls, so every row in range is mounted", async () => {
      mockMedia = ref(images(400));

      const wrapper = await mountSubject({ props: { isMobile: true } });
      await nextTick();
      // Wait for the first rows, then scroll before the staging has finished.
      for (let i = 0; i < 20 && wrapper.findAll(".tanstack-virtual-row").length === 0; i += 1) {
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
      const before = wrapper.findAll(".tanstack-virtual-row").length;
      wrapper.get(".mobile-scroller").element.scrollTop = 40;
      await new Promise((resolve) => setTimeout(resolve, 20));

      expect(before).toBeGreaterThan(0);
      expect(wrapper.findAll(".tanstack-virtual-row").length).toBeGreaterThan(before);
    });

    describe("thumbnail warm-up on first page", () => {
      const skeletonRect = (width: number, height: number, top = 100) =>
        ({ width, height, top, left: 0, right: width, bottom: top + height, x: 0, y: top }) as DOMRect;

      const mountSkeleton = async () => {
        mockHasActivePage = ref(false);
        mockIsLoading = ref(true);
        mockIsPending = ref(true);
        mockIsSuccess = ref(false);
        const wrapper = await mountSubject({ props: { isMobile: true } });
        await nextTick();
        expect(wrapper.find(".skeleton-grid").exists()).toBe(true);
        return wrapper;
      };

      const originalDpr = window.devicePixelRatio;
      afterEach(() => {
        Object.defineProperty(window, "devicePixelRatio", { value: originalDpr, configurable: true });
      });
      beforeEach(() => {
        Object.defineProperty(window, "devicePixelRatio", { value: 2, configurable: true });
        vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
          return this.classList.contains("skeleton-grid") ? skeletonRect(390, 400) : skeletonRect(180, 180);
        });
      });

      it("starts the first viewport's thumbnails from the query function, before the grid renders", async () => {
        const wrapper = await mountSkeleton();
        const page = { library_id: 1, request_path: "/photos", media: images(30, "warm"), folders: [] };

        const handler = mockBrowseOptions.current?.onFirstPageFetched;
        expect(handler).toBeTypeOf("function");
        const result = handler!(page);

        const links = [...document.head.querySelectorAll<HTMLLinkElement>("link[rel='preload'][as='image']")];
        // 4 columns, rows that start above the 768px viewport: ceil((768 - (100 + 64)) / 180) = 4 rows.
        expect(links).toHaveLength(16);
        expect(links[0].href).toContain("/api/thumbnail");
        expect(links[0].href).toContain("warm-0.png");
        expect(links[0].getAttribute("imagesrcset")).toContain("256w");
        expect(links[0].getAttribute("imagesizes")).toBe("360px");
        expect(links.slice(0, 4).every((link) => link.getAttribute("fetchpriority") === "high")).toBe(true);
        expect(links.slice(4).every((link) => link.getAttribute("fetchpriority") === "auto")).toBe(true);
        // The query function awaits this, so the render that mounts the grid runs in the next task.
        expect(result).toBeInstanceOf(Promise);
        await result;
        wrapper.unmount();
      });

      it("warms the same page only once", async () => {
        const wrapper = await mountSkeleton();
        const page = { library_id: 1, request_path: "/photos", media: images(8, "once"), folders: [] };
        const handler = mockBrowseOptions.current!.onFirstPageFetched;

        await handler(page);
        const first = document.head.querySelectorAll("link[rel='preload']").length;
        const second = handler(page);

        expect(first).toBeGreaterThan(0);
        expect(second).toBeUndefined();
        expect(document.head.querySelectorAll("link[rel='preload']")).toHaveLength(first);
        wrapper.unmount();
      });

      it("does nothing without a skeleton to measure", async () => {
        mockMedia = ref(images(8, "noskel"));
        const wrapper = await mountSubject({ props: { isMobile: true } });
        await nextTick();

        const result = mockBrowseOptions.current!.onFirstPageFetched({
          library_id: 1,
          request_path: "/photos",
          media: images(8, "noskel"),
          folders: [],
        });

        expect(result).toBeUndefined();
        expect(document.head.querySelectorAll("link[rel='preload']")).toHaveLength(0);
        wrapper.unmount();
      });
    });
  });
});
