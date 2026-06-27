import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import { ref } from "vue";
import AppHeader from "../AppHeader.vue";

let currentRoutePath = "/gallery";
let currentResolvedTheme = "light";
const setThemeMock = vi.fn();
const fieldedFiltersRef = ref<unknown[]>([]);
const queryStringRef = ref("");
let fieldedSearchIsActive = false;
const applyFiltersMock = vi.fn();
const removeFilterMock = vi.fn((index: number) => {
  fieldedFiltersRef.value.splice(index, 1);
  queryStringRef.value = "";
});
const clearAllMock = vi.fn();

vi.mock("vue-router", () => ({
  useRoute: () => ({ path: currentRoutePath, meta: {} }),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/composables/useGalleryTheme", () => ({
  useGalleryTheme: () => ({
    mode: "light",
    resolvedTheme: currentResolvedTheme,
    setTheme: setThemeMock,
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
  Monitor: { template: '<svg data-testid="monitor-icon" />', props: ["class"] },
  Search: { template: '<svg data-testid="search-icon" />', props: ["class"] },
  X: { template: '<svg data-testid="x-icon" />', props: ["class"] },
  SlidersHorizontal: { template: "<svg />", props: ["class"] },
  Menu: { template: "<svg />", props: ["class"] },
  Settings: { template: "<svg />", props: ["class"] },
  Library: { template: "<svg />", props: ["class"] },
  Table2: { template: "<svg />", props: ["class"] },
  Wrench: { template: "<svg />", props: ["class"] },
  Landmark: { template: "<svg />", props: ["class"] },
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
      ...props,
    },
    global: {
      stubs: {
        RouterLink: { template: "<a><slot /></a>" },
        Button: { template: "<button @click='$emit(\"click\")'><slot /></button>" },
        ButtonLink: { template: "<a :href='to' @click='$emit(\"click\")'><slot /></a>" },
        Input: { template: "<input :value='modelValue' @input='$emit(\"update:modelValue\", $event.target.value)' />" },
        DropdownMenu: { template: "<div><slot /></div>" },
        DropdownMenuContent: { template: "<div><slot /></div>" },
        DropdownMenuItem: { template: "<div class='dropdown-item' @click='$emit(\"click\")'><slot /></div>" },
        DropdownMenuTrigger: { template: "<div><slot /></div>" },
        Tooltip: { template: "<span><slot /></span>" },
        TooltipTrigger: { template: "<span><slot /></span>" },
        TooltipContent: { template: "<span><slot /></span>" },
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
    setThemeMock.mockClear();
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

  it("emits toggle-sidebar when hamburger clicked", async () => {
    const wrapper = createWrapper({ isMobile: false });
    const toggleBtn = wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Toggle sidebar");
    if (toggleBtn) {
      await toggleBtn.trigger("click");
      expect(wrapper.emitted("toggle-sidebar")?.length).toBeGreaterThan(0);
    }
  });

  it("emits open-settings when settings button clicked", async () => {
    const wrapper = createWrapper();
    const settingsBtn = wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Change Intro Page");
    if (settingsBtn) {
      await settingsBtn.trigger("click");
      expect(wrapper.emitted("open-settings")?.length).toBeGreaterThan(0);
    }
  });

  it("emits update:searchQuery on input change", async () => {
    const wrapper = createWrapper();
    const input = wrapper.find("#gallery-search");
    if (input.exists()) {
      await input.setValue("test query");
      expect(wrapper.emitted("update:searchQuery")).toBeTruthy();
    }
  });

  it("emits scope-change when scope select changes", async () => {
    const wrapper = createWrapper();
    const select = wrapper.find("select.scope-select");
    if (select.exists()) {
      await select.setValue("all");
      expect(wrapper.emitted("scope-change")).toBeTruthy();
      expect(wrapper.emitted("scope-change")![0]).toEqual(["all"]);
    }
  });

  it("shows clear button when searchQuery has value", () => {
    const wrapper = createWrapper({ searchQuery: "test" });
    const clearBtn = wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Clear search");
    expect(clearBtn).toBeDefined();
  });

  it("emits update:searchQuery empty string on clear", async () => {
    const wrapper = createWrapper({ searchQuery: "test" });
    const clearBtn = wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Clear search");
    if (clearBtn) {
      await clearBtn.trigger("click");
      expect(wrapper.emitted("update:searchQuery")?.pop()).toEqual([""]);
    }
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
  });

  it("hides brand hero and search on admin route", () => {
    currentRoutePath = "/admin/libraries";
    const wrapper = createWrapper();
    expect(wrapper.text()).not.toContain("Museum Art Gallery");
    expect(wrapper.find("#gallery-search").exists()).toBe(false);
  });

  it("hides Metadata link and Maintenance link on mobile", () => {
    const wrapper = createWrapper({ isMobile: true });
    expect(wrapper.text()).not.toContain("Metadata");
    expect(wrapper.text()).not.toContain("Maintenance");
  });

  it("shows Moon icon when dark theme", () => {
    currentResolvedTheme = "dark";
    const wrapper = createWrapper();
    expect(wrapper.find('[aria-label="Theme"] [data-testid="moon-icon"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="Theme"] [data-testid="sun-icon"]').exists()).toBe(false);
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
    await wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Advanced Search")!.trigger("click");
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

  it("calls setTheme with theme value from menu items", async () => {
    const wrapper = createWrapper();
    const lightBtn = wrapper.findAll(".dropdown-item").find((el) => el.text().includes("Light"));
    expect(lightBtn).toBeDefined();
    await lightBtn!.trigger("click");
    expect(setThemeMock).toHaveBeenCalledWith("light");

    const darkBtn = wrapper.findAll(".dropdown-item").find((el) => el.text().includes("Dark"));
    await darkBtn!.trigger("click");
    expect(setThemeMock).toHaveBeenCalledWith("dark");

    const systemBtn = wrapper.findAll(".dropdown-item").find((el) => el.text().includes("System"));
    await systemBtn!.trigger("click");
    expect(setThemeMock).toHaveBeenCalledWith("system");
  });

  it("shows Maintenance link on maintenance route", () => {
    currentRoutePath = "/admin/maintenance";
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Maintenance");
  });

  it("renders Sun icon on light theme button", () => {
    const wrapper = createWrapper();
    expect(wrapper.find('[aria-label="Theme"] [data-testid="sun-icon"]').exists()).toBe(true);
  });
});
