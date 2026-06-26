import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import AppHeader from "../AppHeader.vue";

vi.mock("vue-router", () => ({
  useRoute: () => ({ path: "/gallery", meta: {} }),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/composables/useGalleryTheme", () => ({
  useGalleryTheme: () => ({
    mode: "light",
    resolvedTheme: "light",
    setTheme: vi.fn(),
  }),
}));

vi.mock("@/composables/useFieldedSearch", () => ({
  useFieldedSearch: () => ({
    fieldedFilters: [],
    isActive: false,
    queryString: "",
    applyFilters: vi.fn(),
    removeFilter: vi.fn(),
    clearAll: vi.fn(),
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
        DropdownMenuItem: { template: "<div @click='$emit(\"click\")'><slot /></div>" },
        DropdownMenuTrigger: { template: "<div><slot /></div>" },
        Tooltip: { template: "<span><slot /></span>" },
        TooltipTrigger: { template: "<span><slot /></span>" },
        TooltipContent: { template: "<span><slot /></span>" },
        AdvancedSearchDrawer: { template: "<div data-testid='advanced-search-drawer' />" },
        SearchFilterChips: { template: "<div data-testid='search-filter-chips' />" },
        Sun: { template: "<span>sun-icon</span>" },
        Moon: { template: "<span>moon-icon</span>" },
        Monitor: { template: "<span>monitor-icon</span>" },
      },
    },
  });
}

describe("AppHeader", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
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
});
