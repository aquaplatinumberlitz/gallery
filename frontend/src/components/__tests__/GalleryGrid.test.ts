import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import { fuzzySearchFileNodes } from "@/utils/fuzzySearch";

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
let mockHasActivePage = { value: true };
const mockRefetch = vi.fn();
const mockFetchNextPage = vi.fn();
const mockUseUnifiedSearchQuery = vi.hoisted(() => vi.fn());

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
  isSuccess: { value: true },
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

const mockStore: Record<string, any> = {
  activeLibraryId: 1,
  activeImportPathId: 1,
  activeLibraryHydrated: true,
  currentBrowsePath: "/photos",
  searchQuery: "",
  submittedSearchQuery: "",
  searchScope: "current",
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

function defaultStoreValues() {
  return {
    errorMessage: "",
    errorType: null,
    isLoading: false,
    searchQuery: "",
    submittedSearchQuery: "",
  };
}

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
    mockHasActivePage = { value: true };
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
    mockIsLoading = { value: true };
    const wrapper = await mountSubject();
    expect(wrapper.text()).toContain("Loading");
  });

  it("shows error banner when error message exists", async () => {
    const wrapper = await mountSubject({ store: { errorMessage: "Failed to load" } });
    expect(wrapper.find("[role='alert']").exists()).toBe(true);
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
      "Choose a library from Active library to load albums and photos.",
    );
    expect(wrapper.get("[data-testid='empty-action']").text()).toBe("Choose Library");

    await wrapper.get("[data-testid='empty-action']").trigger("click");

    expect(wrapper.get("[data-testid='library-selector']").attributes("data-open")).toBe("true");
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
    mockFolders = {
      value: [{ name: "Mika", path: "/photos/mika", type: "folder", has_children: false }],
    };
    mockMedia = {
      value: [{ name: "mika.png", path: "/photos/mika.png", type: "image", mtime: 1 }],
    };

    await mountSubject({ store: { searchQuery: "" } });

    expect(fuzzySearchFileNodes).not.toHaveBeenCalled();
  });

  it("does not switch to search filtering for a one-character draft query", async () => {
    mockFolders = {
      value: [{ name: "Mika", path: "/photos/mika", type: "folder", has_children: false }],
    };
    mockMedia = {
      value: [{ name: "mika.png", path: "/photos/mika.png", type: "image", mtime: 1 }],
    };

    const wrapper = await mountSubject({ store: { searchQuery: "m", submittedSearchQuery: "" } });

    expect(fuzzySearchFileNodes).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Keep typing to search, or press Enter.");
  });

  it("keeps a two-character query as draft until debounce settles", async () => {
    mockFolders = {
      value: [{ name: "Mika", path: "/photos/mika", type: "folder", has_children: false }],
    };
    mockMedia = {
      value: [{ name: "mika.png", path: "/photos/mika.png", type: "image", mtime: 1 }],
    };

    const wrapper = await mountSubject({ store: { searchQuery: "mi", submittedSearchQuery: "" } });

    expect(mockUseUnifiedSearchQuery).toHaveBeenCalled();
    expect(mockUseUnifiedSearchQuery.mock.calls[0][0].value).toBe("mi");
    expect(fuzzySearchFileNodes).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Keep typing to search, or press Enter.");
  });

  it("allows a one-character query after explicit submit", async () => {
    mockFolders = {
      value: [{ name: "Mika", path: "/photos/mika", type: "folder", has_children: false }],
    };
    mockMedia = {
      value: [{ name: "mika.png", path: "/photos/mika.png", type: "image", mtime: 1 }],
    };

    await mountSubject({ store: { searchQuery: "m", submittedSearchQuery: "m" } });

    expect(mockUseUnifiedSearchQuery).toHaveBeenCalled();
    expect(mockUseUnifiedSearchQuery.mock.calls[0][0].value).toBe("m");
  });
});
