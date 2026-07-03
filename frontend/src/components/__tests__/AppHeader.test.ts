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
const applyFiltersMock = vi.fn();
const removeFilterMock = vi.fn((index: number) => {
  fieldedFiltersRef.value.splice(index, 1);
  queryStringRef.value = "";
});
const clearAllMock = vi.fn();

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
    applyFilters: applyFiltersMock,
    removeFilter: removeFilterMock,
    clearAll: clearAllMock,
  }),
}));

vi.mock("@/utils/serializeAdvancedSearchToQuery", () => ({
  parseFieldedQuery: vi.fn(() => []),
  serializeAdvancedSearchToQuery: vi.fn(() => ""),
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
        AdvancedSearchDrawer: {
          props: ["isOpen", "initialFilters"],
          template: `
            <div data-testid="advanced-search-drawer">
              <button v-if="isOpen" data-testid="adv-search-close" @click="$emit('close')">Close</button>
              <button v-if="isOpen" data-testid="adv-search-apply" @click="$emit('apply', [])">Apply</button>
            </div>
          `,
        },
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
    applyFiltersMock.mockClear();
    removeFilterMock.mockClear();
    clearAllMock.mockClear();
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

  it("emits update:searchQuery empty string on clear", async () => {
    const wrapper = createWrapper({ searchQuery: "test" });
    const clearBtn = wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Clear search")!;
    await clearBtn.trigger("click");
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

  it("opens and closes advanced search drawer", async () => {
    const wrapper = createWrapper();
    const advBtn = wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Advanced Search");
    expect(advBtn).toBeDefined();
    await advBtn!.trigger("click");
    expect(wrapper.find('[data-testid="adv-search-close"]').exists()).toBe(true);

    await wrapper.find('[data-testid="adv-search-close"]').trigger("click");
    expect(wrapper.find('[data-testid="adv-search-close"]').exists()).toBe(false);
  });

  it("applies advanced search filters via drawer", async () => {
    const wrapper = createWrapper();
    await wrapper
      .findAll("button")
      .find((b) => b.attributes("aria-label") === "Advanced Search")!
      .trigger("click");
    await wrapper.find('[data-testid="adv-search-apply"]').trigger("click");
    expect(wrapper.emitted("update:searchQuery")).toBeTruthy();
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
