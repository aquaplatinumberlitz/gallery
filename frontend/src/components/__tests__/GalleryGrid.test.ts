import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import { nextTick, ref } from "vue";
import { fuzzySearchFileNodes } from "@/utils/fuzzySearch";
import { GalleryAPIError } from "@/services/api";

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
const mockRouterPush = vi.hoisted(() => vi.fn());

vi.mock("@/composables/useInfiniteBrowseQuery", () => ({
  useInfiniteBrowseQuery: () => ({
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
  }),
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
      await nextTick();

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
      await nextTick();

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
      await nextTick();

      const rows = wrapper.findAll(".tanstack-virtual-row");
      expect(rows[0].findAll("[data-priority='high']")).toHaveLength(4);
      for (const row of rows.slice(1)) {
        expect(row.findAll("[data-priority='high']")).toHaveLength(0);
      }
    });
  });
});
