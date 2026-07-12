import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import { ref } from "vue";
import AppHeader from "../AppHeader.vue";

let currentRoutePath = "/gallery";
let currentResolvedTheme = "light";
const toggleThemeMock = vi.fn();
const fieldedFiltersRef = ref<unknown[]>([]);
const queryStringRef = ref("");
let fieldedSearchIsActive = false;
const removeFilterMock = vi.fn((index: number) => {
  fieldedFiltersRef.value.splice(index, 1);
  queryStringRef.value = "";
});
const clearAllMock = vi.fn();
const goBackMock = vi.fn();
const goForwardMock = vi.fn();
const browseIsLoadingRef = ref(false);
const browseIsFetchingRef = ref(false);
const browseIsFetchingNextPageRef = ref(false);
let galleryHistoryIndex = 0;
let galleryHistory = [""];

function routeMetaForPath(path: string) {
  if (path === "/metadata") {
    return { chromeSection: "metadata", chromeNav: "metadata", pageTitle: "Photo Details", showBackToGallery: true };
  }
  if (path.startsWith("/admin/libraries")) {
    return {
      chromeSection: "admin",
      chromeNav: "libraries",
      pageTitle: "Library administration",
      showBackToGallery: true,
    };
  }
  if (path.startsWith("/admin/maintenance")) {
    return { chromeSection: "admin", chromeNav: "maintenance", pageTitle: "Maintenance", showBackToGallery: true };
  }
  return { chromeSection: "gallery", chromeNav: "gallery", pageTitle: "Gallery", showBackToGallery: false };
}

vi.mock("vue-router", () => ({
  useRoute: () => ({ path: currentRoutePath, meta: routeMetaForPath(currentRoutePath) }),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/composables/useGalleryTheme", () => ({
  useGalleryTheme: () => ({
    mode: "light",
    resolvedTheme: currentResolvedTheme,
    toggleTheme: toggleThemeMock,
  }),
}));

vi.mock("@/composables/useFieldedSearch", () => ({
  useFieldedSearch: () => ({
    fieldedFilters: fieldedFiltersRef,
    isActive: fieldedSearchIsActive,
    queryString: queryStringRef,
    removeFilter: removeFilterMock,
    clearAll: clearAllMock,
  }),
}));

vi.mock("@/composables/useInfiniteBrowseQuery", () => ({
  useInfiniteBrowseQuery: () => ({
    isLoading: browseIsLoadingRef,
    isFetching: browseIsFetchingRef,
    isFetchingNextPage: browseIsFetchingNextPageRef,
  }),
}));

vi.mock("@/router", () => ({
  prefetchLibrariesRoute: vi.fn(),
  prefetchMetadataRoute: vi.fn(),
}));

vi.mock("@/query", () => ({
  queryClient: { prefetchQuery: vi.fn() },
}));

vi.mock("@/query/keys", () => ({
  normalizeQueryPath: vi.fn((p) => p || ""),
  queryKeys: { libraryInspector: vi.fn(() => ["inspector"]) },
}));

vi.mock("@/services/api", () => ({
  fetchLibraryInspector: vi.fn(),
}));

vi.mock("@/stores/gallery", () => ({
  useGalleryStore: () => ({
    activeLibraryId: null,
    currentBrowsePath: "",
    activeImportRootPath: "",
    historyIndex: galleryHistoryIndex,
    history: galleryHistory,
    sortField: "date",
    sortOrder: "desc",
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
    goBack: goBackMock,
    goForward: goForwardMock,
    selectFolder: vi.fn(),
    clearSearch: vi.fn(),
    submitSearch: vi.fn(),
    openInExplorer: vi.fn(),
    setSortField: vi.fn(),
    setSortOrder: vi.fn(),
    $id: "gallery",
  }),
}));

vi.mock("lucide-vue-next", () => ({
  Sun: { template: '<svg data-testid="sun-icon" />', props: ["class"] },
  Moon: { template: '<svg data-testid="moon-icon" />', props: ["class"] },
  Search: { template: '<svg data-testid="search-icon" />', props: ["class"] },
  X: { template: '<svg data-testid="x-icon" />', props: ["class"] },
  SlidersHorizontal: { template: "<svg />", props: ["class"] },
  Menu: { template: "<svg />", props: ["class"] },
  Settings: { template: "<svg />", props: ["class"] },
  Loader2: { template: "<svg data-testid='loader-icon' />", props: ["class"] },
  Library: { template: "<svg />", props: ["class"] },
  Table2: { template: "<svg />", props: ["class"] },
  Wrench: { template: "<svg />", props: ["class"] },
  Landmark: { template: "<svg />", props: ["class"] },
  ArrowLeft: { template: "<svg />", props: ["class"] },
  ArrowRight: { template: "<svg />", props: ["class"] },
  ArrowUpRight: { template: "<svg />", props: ["class"] },
  ChevronDown: { template: "<svg />", props: ["class"] },
  LayoutGrid: { template: "<svg />", props: ["class"] },
}));

function createWrapper(props: Record<string, unknown> = {}) {
  setActivePinia(createPinia());
  return mount(AppHeader, {
    props: {
      isMobile: false,
      isSidebarOpen: false,
      isDark: false,
      searchQuery: "",
      searchScope: "current",
      searchLoading: false,
      ...props,
    },
    global: {
      stubs: {
        RouterLink: { template: "<a><slot /></a>" },
        Button: { template: "<button @click='$emit(\"click\")'><slot /></button>" },
        ButtonLink: { template: "<a :href='to' @click='$emit(\"click\")'><slot /></a>" },
        Badge: { template: "<span><slot /></span>" },
        Input: { template: "<input :value='modelValue' @input='$emit(\"update:modelValue\", $event.target.value)' />" },
        Tooltip: { template: "<span><slot /></span>" },
        TooltipTrigger: { template: "<span><slot /></span>" },
        TooltipContent: { template: "<span><slot /></span>" },
        SearchScopeSelect: {
          props: ["modelValue"],
          template: `
            <button type="button" class="scope-select" aria-label="Search scope" @click="$emit('update:modelValue', 'all')">
              {{ modelValue }}
            </button>
          `,
        },
        Breadcrumb: { template: "<nav class='breadcrumb-stub'><slot /><slot name='actions' /></nav>" },
        SortSelect: { template: "<button type='button' aria-label='Sort gallery'>Sort</button>" },
        DropdownMenu: { template: "<div><slot /></div>" },
        DropdownMenuTrigger: { template: "<div><slot /></div>" },
        DropdownMenuContent: { template: "<div><slot /></div>" },
        DropdownMenuRadioGroup: { template: "<div><slot /></div>" },
        DropdownMenuRadioItem: { template: "<div><slot /></div>" },
        SearchFilterChips: {
          props: ["filters"],
          template: `
            <div data-testid="search-filter-chips">
              <button v-for="(f, i) in (filters || [])" :key="i" :data-testid="'remove-filter-' + i" @click="$emit('remove', i)">Remove filter</button>
              <button v-if="(filters || []).length > 1" data-testid="clear-all" @click="$emit('clear-all')">Clear all</button>
            </div>
          `,
        },
      },
    },
  });
}

describe("AppHeader", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    currentRoutePath = "/gallery";
    currentResolvedTheme = "light";
    toggleThemeMock.mockClear();
    fieldedFiltersRef.value = [];
    queryStringRef.value = "";
    fieldedSearchIsActive = false;
    removeFilterMock.mockClear();
    clearAllMock.mockClear();
    goBackMock.mockClear();
    goForwardMock.mockClear();
    browseIsLoadingRef.value = false;
    browseIsFetchingRef.value = false;
    browseIsFetchingNextPageRef.value = false;
    galleryHistoryIndex = 0;
    galleryHistory = [""];
  });

  it("renders the brand hero on non-metadata routes", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Museum Art Gallery");
  });

  it("renders search box on non-metadata routes", () => {
    const wrapper = createWrapper();
    expect(wrapper.find("#gallery-search").exists()).toBe(true);
  });

  it("shows loader icon while search is loading", () => {
    const wrapper = createWrapper({ searchLoading: true });
    expect(wrapper.find("[data-testid='loader-icon']").exists()).toBe(true);
  });

  it("emits toggle-sidebar when hamburger clicked", async () => {
    const wrapper = createWrapper({ isMobile: false });
    const toggleBtn = wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Toggle sidebar")!;
    await toggleBtn.trigger("click");
    expect(wrapper.emitted("toggle-sidebar")?.length).toBeGreaterThan(0);
  });

  it("emits open-settings when settings button clicked", async () => {
    const wrapper = createWrapper();
    const settingsBtn = wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Change Intro Page")!;
    await settingsBtn.trigger("click");
    expect(wrapper.emitted("open-settings")?.length).toBeGreaterThan(0);
  });

  it("emits update:searchQuery on input change", async () => {
    const wrapper = createWrapper();
    const input = wrapper.find("#gallery-search");
    await input.setValue("test query");
    expect(wrapper.emitted("update:searchQuery")).toBeTruthy();
  });

  it("emits scope-change when scope select changes", async () => {
    const wrapper = createWrapper();
    const select = wrapper.find('[aria-label="Search scope"]');
    await select.trigger("click");
    expect(wrapper.emitted("scope-change")).toBeTruthy();
    expect(wrapper.emitted("scope-change")![0]).toEqual(["all"]);
  });

  it("shows clear button when searchQuery has value", () => {
    const wrapper = createWrapper({ searchQuery: "test" });
    const clearBtn = wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Clear search");
    expect(clearBtn).toBeDefined();
  });

  it("shows clear buttons in both expanded and compact gallery search boxes", () => {
    const wrapper = createWrapper({ searchQuery: "test" });
    const clearButtons = wrapper.findAll("button").filter((b) => b.attributes("aria-label") === "Clear search");
    const expandedClear = clearButtons.find((b) => b.element.closest(".header-search-area"));
    const compactClear = clearButtons.find((b) => b.element.closest(".compact-search-box"));

    expect(expandedClear).toBeDefined();
    expect(compactClear).toBeDefined();
  });

  it("emits update:searchQuery empty string on clear", async () => {
    const wrapper = createWrapper({ searchQuery: "test" });
    const clearBtn = wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Clear search")!;
    await clearBtn.trigger("click");
    expect(wrapper.emitted("update:searchQuery")?.pop()).toEqual([""]);
  });

  it("emits update:searchQuery empty string from compact clear", async () => {
    const wrapper = createWrapper({ searchQuery: "test" });
    const compactClearBtn = wrapper
      .findAll("button")
      .find((b) => b.attributes("aria-label") === "Clear search" && b.element.closest(".compact-search-box"))!;

    await compactClearBtn.trigger("click");

    expect(wrapper.emitted("update:searchQuery")?.pop()).toEqual([""]);
  });

  it("renders Libraries link", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Libraries");
  });

  it("renders Metadata link on desktop", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Metadata");
  });

  it("renders Maintenance link on desktop", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Maintenance");
  });

  it("renders advanced search button", () => {
    const wrapper = createWrapper();
    const advBtn = wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Advanced Search");
    expect(advBtn).toBeDefined();
  });

  it("restores forward navigation in the desktop gallery header", async () => {
    galleryHistory = ["/library", "/library/album"];
    galleryHistoryIndex = 0;
    const wrapper = createWrapper();
    const forwardBtn = wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Go forward");

    expect(forwardBtn).toBeDefined();
    expect(forwardBtn!.attributes("disabled")).toBeUndefined();
    await forwardBtn!.trigger("click");
    expect(goForwardMock).toHaveBeenCalled();
  });

  it("marks the inactive compact header inert while expanded", () => {
    const wrapper = createWrapper();
    const compactHeader = wrapper.find(".compact-header");

    expect(compactHeader.attributes("aria-hidden")).toBe("true");
    expect(compactHeader.attributes("inert")).toBeDefined();
  });

  it("shows the browse loading badge in the desktop gallery header", () => {
    browseIsLoadingRef.value = true;
    const wrapper = createWrapper();

    expect(wrapper.text()).toContain("Loading");
  });

  it("hides brand hero and search on metadata route", () => {
    currentRoutePath = "/metadata";
    const wrapper = createWrapper();
    expect(wrapper.text()).not.toContain("Museum Art Gallery");
    expect(wrapper.find("#gallery-search").exists()).toBe(false);
    expect(wrapper.text()).toContain("Gallery");
  });

  it("hides brand hero and search on admin route", () => {
    currentRoutePath = "/admin/libraries";
    const wrapper = createWrapper();
    expect(wrapper.text()).not.toContain("Museum Art Gallery");
    expect(wrapper.find("#gallery-search").exists()).toBe(false);
    expect(wrapper.text()).toContain("Gallery");
  });

  it("hides Metadata link and Maintenance link on mobile", () => {
    const wrapper = createWrapper({ isMobile: true });
    expect(wrapper.text()).not.toContain("Metadata");
    expect(wrapper.text()).not.toContain("Maintenance");
  });

  it("shows the light-mode action when dark theme is active", () => {
    currentResolvedTheme = "dark";
    const wrapper = createWrapper();
    const themeButton = wrapper.find('[aria-label="Switch to light mode"]');
    expect(themeButton.exists()).toBe(true);
    expect(themeButton.classes()).toContain("is-dark");
  });

  it("requests the shared advanced search drawer", async () => {
    const wrapper = createWrapper();
    const advBtn = wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Advanced Search");
    expect(advBtn).toBeDefined();
    await advBtn!.trigger("click");
    expect(wrapper.emitted("open-advanced-search")?.length).toBeGreaterThan(0);
  });

  it("exposes Advanced Search from the compact header", async () => {
    const wrapper = createWrapper();
    const buttons = wrapper.findAll('button[aria-label="Advanced Search"]');
    expect(buttons).toHaveLength(2);
    await buttons[1]!.trigger("click");
    expect(wrapper.emitted("open-advanced-search")?.length).toBeGreaterThan(0);
  });

  it("handles remove filter", async () => {
    fieldedFiltersRef.value = [{ field: "model", operator: "eq", value: "v1" }];
    queryStringRef.value = "model:eq:v1";
    const wrapper = createWrapper();
    const removeBtn = wrapper.find('[data-testid="remove-filter-0"]');
    expect(removeBtn.exists()).toBe(true);
    await removeBtn.trigger("click");
    expect(removeFilterMock).toHaveBeenCalledWith(0);
    expect(wrapper.emitted("update:searchQuery")?.pop()).toEqual([queryStringRef.value]);
  });

  it("handles clear all filters", async () => {
    fieldedFiltersRef.value = [
      { field: "model", operator: "eq", value: "v1" },
      { field: "prompt", operator: "contains", value: "cat" },
    ];
    const wrapper = createWrapper();
    const clearBtn = wrapper.find('[data-testid="clear-all"]');
    expect(clearBtn.exists()).toBe(true);
    await clearBtn.trigger("click");
    expect(clearAllMock).toHaveBeenCalled();
  });

  it("toggles theme from the pill button", async () => {
    const wrapper = createWrapper();
    await wrapper.find('[aria-label="Switch to dark mode"]').trigger("click");
    expect(toggleThemeMock).toHaveBeenCalledTimes(1);
  });

  it("does not render a native title tooltip on the theme button", () => {
    const wrapper = createWrapper();
    expect(wrapper.find('[aria-label="Switch to dark mode"]').attributes("title")).toBeUndefined();
  });

  it("shows Maintenance link on maintenance route", () => {
    currentRoutePath = "/admin/maintenance";
    const wrapper = createWrapper();
    expect(wrapper.find("#gallery-search").exists()).toBe(false);
    expect(wrapper.text()).toContain("Gallery");
    expect(wrapper.text()).toContain("Maintenance");
  });

  it("renders Sun icon on light theme button", () => {
    const wrapper = createWrapper();
    expect(wrapper.find('[aria-label="Switch to dark mode"] [data-testid="sun-icon"]').exists()).toBe(true);
  });
});
