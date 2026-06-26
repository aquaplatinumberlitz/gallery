import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";

let mockIsLoading = { value: false };
let mockIsFetching = { value: false };
let mockIsSuccess = { value: true };
let mockIsPending = { value: false };
let mockHasNextPage = { value: false };
let mockIsFetchingNextPage = { value: false };
let mockError = { value: null };
let mockFolders: any = { value: [] };
let mockMedia: any = { value: [] };
let mockActiveFolderPath: any = { value: null };
const mockRefetch = vi.fn();
const mockFetchNextPage = vi.fn();

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
  }),
}));

vi.mock("@/composables/useUnifiedSearchQuery", () => ({
  useUnifiedSearchQuery: () => ({
    isLoading: { value: false },
    isFetching: { value: false },
    isSuccess: { value: true },
    albums: { value: [] },
    photos: { value: [] },
    videos: { value: [] },
    prompt: { value: [] },
  }),
}));

vi.mock("@/composables/useColumnResize", () => ({
  useColumnResize: () => ({
    columnCount: { value: 4 },
    sliderLevel: { value: 0 },
    rowHeight: { value: 200 },
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

vi.mock("@/stores/gallery", () => {
  const mockStore = {
    activeLibraryId: 1,
    activeImportPathId: 1,
    activeLibraryHydrated: true,
    hasEverLoaded: true,
    currentBrowsePath: "/photos",
    searchQuery: "",
    searchScope: "current",
    sortField: "date",
    sortOrder: "desc",
    isLoading: false,
    errorMessage: "",
    errorType: null,
    history: [],
    historyIndex: 0,
    metadataInspector: { scope: "current", query: "", sort: "date_desc", modelFilter: "all", promptFilter: "all", selectedPath: "", scrollTop: 0, scrollPath: "" },
    setSortField: vi.fn(),
    setSortOrder: vi.fn(),
    selectFolder: vi.fn(),
    clearSearch: vi.fn(),
    clearError: vi.fn(),
    setSidebarTree: vi.fn(),
    setActiveLibrary: vi.fn(),
    openInExplorer: vi.fn(),
    goBack: vi.fn(),
    goForward: vi.fn(),
    $id: "gallery",
  };
  return {
    useGalleryStore: () => mockStore,
  };
});


describe("GalleryGrid", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    mockIsLoading = { value: false };
    mockIsFetching = { value: false };
    mockIsSuccess = { value: true };
    mockIsPending = { value: false };
    mockHasNextPage = { value: false };
    mockIsFetchingNextPage = { value: false };
    mockError = { value: null };
    mockFolders = { value: [] };
    mockMedia = { value: [] };
    mockActiveFolderPath = { value: null };
  });

  it("renders without crashing", async () => {
    const GalleryGrid = (await import("../GalleryGrid.vue")).default;
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(GalleryGrid, {
      props: { isMobile: false },
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          AlbumCard: { template: "<div class='album-card' />" },
          PhotoCard: { template: "<div class='photo-card' />" },
          VideoCard: { template: "<div class='video-card' />" },
          SkeletonLoader: { template: "<div class='skeleton-loader' />" },
          Breadcrumb: { template: "<div class='breadcrumb-stub' />" },
          EmptyState: { template: "<div class='empty-state' />" },
          SortSelect: { template: "<select />" },
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
        },
      },
    });
    expect(wrapper.find(".gallery-grid").exists()).toBe(true);
  });

  it("shows loading badge when loading", async () => {
    mockIsLoading = { value: true };
    const GalleryGrid = (await import("../GalleryGrid.vue")).default;
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(GalleryGrid, {
      props: { isMobile: false },
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          AlbumCard: { template: "<div class='album-card' />" },
          PhotoCard: { template: "<div class='photo-card' />" },
          VideoCard: { template: "<div class='video-card' />" },
          SkeletonLoader: { template: "<div class='skeleton-loader' />" },
          Breadcrumb: { template: "<div class='breadcrumb-stub' />" },
          EmptyState: { template: "<div class='empty-state' />" },
          SortSelect: { template: "<select />" },
          Button: { template: "<button><slot /></button>" },
          Badge: { template: "<span class='badge'><slot /></span>" },
          Tooltip: { template: "<span><slot /></span>" },
          TooltipTrigger: { template: "<span><slot /></span>" },
          TooltipContent: { template: "<span><slot /></span>" },
          DropdownMenu: { template: "<div><slot /></div>" },
          DropdownMenuContent: { template: "<div><slot /></div>" },
          DropdownMenuRadioGroup: { template: "<div><slot /></div>" },
          DropdownMenuRadioItem: { template: "<div><slot /></div>" },
          DropdownMenuTrigger: { template: "<div><slot /></div>" },
        },
      },
    });
    expect(wrapper.text()).toContain("Loading");
  });

  it("shows error banner when error message exists", async () => {
    const GalleryGridModule = await import("../GalleryGrid.vue");
    const GalleryGrid = GalleryGridModule.default;
    setActivePinia(createPinia());
    const store = (await import("@/stores/gallery")).useGalleryStore();
    store.errorMessage = "Failed to load";
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(GalleryGrid, {
      props: { isMobile: false },
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          AlbumCard: { template: "<div class='album-card' />" },
          PhotoCard: { template: "<div class='photo-card' />" },
          VideoCard: { template: "<div class='video-card' />" },
          SkeletonLoader: { template: "<div class='skeleton-loader' />" },
          Breadcrumb: { template: "<div class='breadcrumb-stub' />" },
          EmptyState: { template: "<div class='empty-state' />" },
          SortSelect: { template: "<select />" },
          Button: { template: "<button><slot /></button>" },
          Badge: { template: "<span class='badge'><slot /></span>" },
          Tooltip: { template: "<span><slot /></span>" },
          TooltipTrigger: { template: "<span><slot /></span>" },
          TooltipContent: { template: "<span><slot /></span>" },
          DropdownMenu: { template: "<div><slot /></div>" },
          DropdownMenuContent: { template: "<div><slot /></div>" },
          DropdownMenuRadioGroup: { template: "<div><slot /></div>" },
          DropdownMenuRadioItem: { template: "<div><slot /></div>" },
          DropdownMenuTrigger: { template: "<div><slot /></div>" },
        },
      },
    });
    expect(wrapper.find(".error-banner").exists() || wrapper.find("[role='alert']").exists()).toBe(true);
  });

  it("renders breadcrumb on desktop", async () => {
    const GalleryGrid = (await import("../GalleryGrid.vue")).default;
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(GalleryGrid, {
      props: { isMobile: false },
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          AlbumCard: { template: "<div class='album-card' />" },
          PhotoCard: { template: "<div class='photo-card' />" },
          VideoCard: { template: "<div class='video-card' />" },
          SkeletonLoader: { template: "<div class='skeleton-loader' />" },
          Breadcrumb: { template: "<div class='breadcrumb-stub'>breadcrumb</div>" },
          EmptyState: { template: "<div class='empty-state' />" },
          SortSelect: { template: "<select />" },
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
        },
      },
    });
    expect(wrapper.text()).toContain("breadcrumb");
  });

  it("shows density dropdown trigger on desktop", async () => {
    const GalleryGrid = (await import("../GalleryGrid.vue")).default;
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(GalleryGrid, {
      props: { isMobile: false },
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          AlbumCard: { template: "<div class='album-card' />" },
          PhotoCard: { template: "<div class='photo-card' />" },
          VideoCard: { template: "<div class='video-card' />" },
          SkeletonLoader: { template: "<div class='skeleton-loader' />" },
          Breadcrumb: { template: "<div class='breadcrumb-stub' />" },
          EmptyState: { template: "<div class='empty-state' />" },
          SortSelect: { template: "<select />" },
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
        },
      },
    });
    expect(wrapper.text()).toContain("cols");
  });

  it("shows open-in-explorer button on desktop", async () => {
    const GalleryGrid = (await import("../GalleryGrid.vue")).default;
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(GalleryGrid, {
      props: { isMobile: false },
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          AlbumCard: { template: "<div class='album-card' />" },
          PhotoCard: { template: "<div class='photo-card' />" },
          VideoCard: { template: "<div class='video-card' />" },
          SkeletonLoader: { template: "<div class='skeleton-loader' />" },
          Breadcrumb: { template: "<div class='breadcrumb-stub' />" },
          EmptyState: { template: "<div class='empty-state' />" },
          SortSelect: { template: "<select />" },
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
        },
      },
    });
    expect(wrapper.text()).toContain("Open");
  });

  it("shows SortSelect on desktop toolbar", async () => {
    const GalleryGrid = (await import("../GalleryGrid.vue")).default;
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(GalleryGrid, {
      props: { isMobile: false },
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          AlbumCard: { template: "<div class='album-card' />" },
          PhotoCard: { template: "<div class='photo-card' />" },
          VideoCard: { template: "<div class='video-card' />" },
          SkeletonLoader: { template: "<div class='skeleton-loader' />" },
          Breadcrumb: { template: "<div class='breadcrumb-stub' />" },
          EmptyState: { template: "<div class='empty-state' />" },
          SortSelect: { template: "<select class='sort-select'>Sort</select>" },
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
        },
      },
    });
    expect(wrapper.find(".sort-select").exists()).toBe(true);
  });
});
