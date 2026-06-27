import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import LibraryInspector from "../LibraryInspector.vue";

const mockRows = [
  {
    path: "/photos/img1.png",
    name: "img1.png",
    type: "image" as const,
    mtime: 1700000000,
    width: 1024,
    height: 768,
    seed: 12345,
    model: "SDXL",
    tool: "ComfyUI",
    has_prompt: true,
    has_negative: false,
    has_lora: false,
    lora_count: 0,
    prompt_preview: "a beautiful landscape",
    relative_path: "/photos",
    folder: "/photos",
  },
];

vi.mock("@/composables/useInfiniteLibraryInspectorQuery", () => ({
  useInfiniteLibraryInspectorQuery: () => ({
    data: {
      value: {
        rows: mockRows,
        returned: 1,
        total_indexed: 50,
        total: 1,
        generated_at: Date.now(),
        next_cursor: null,
        has_more: false,
        root: "/photos",
      },
    },
    isLoading: { value: false },
    isError: { value: false },
    isPlaceholderData: { value: false },
    hasNextPage: { value: false },
    isFetchingNextPage: { value: false },
    refetch: vi.fn(),
    fetchNextPage: vi.fn(),
    rows: { value: mockRows },
    debouncedQuery: { value: "" },
  }),
}));

vi.mock("@/composables/useCatalogStatusQuery", () => ({
  useCatalogStatusQuery: () => ({
    data: { value: null },
    isLoading: { value: false },
    refetch: vi.fn(),
  }),
}));

vi.mock("@/composables/useClipboard", () => ({
  useClipboard: () => ({ copyText: vi.fn() }),
}));

vi.mock("@/composables/useToast", () => ({
  useToast: () => ({ error: vi.fn() }),
}));

vi.mock("@/services/api", () => ({
  getThumbnailUrl: vi.fn((path) => `/thumb/${path}`),
  fetchLibraryInspectorMetadata: vi.fn(),
}));

vi.mock("@/query", () => ({
  queryClient: { fetchQuery: vi.fn(), prefetchQuery: vi.fn() },
}));

vi.mock("@/query/keys", () => ({
  queryKeys: { libraryInspector: vi.fn(() => ["inspector"]), libraryInspectorMetadata: vi.fn(() => ["meta"]) },
}));

vi.mock("@/utils/indexMaintenance", () => ({
  clearScopeRebuildMarker: vi.fn(),
  getScopeRebuildStartedAt: vi.fn(() => 0),
}));

vi.mock("@/debug/indexRebuildDebug", () => ({
  logIndexRebuildDebug: vi.fn(),
}));

vi.mock("@/debug/lightboxNavDebug", () => ({
  logLightboxNavDebug: vi.fn(),
  summarizeLightboxItems: vi.fn(() => ""),
}));

function createWrapper() {
  setActivePinia(createPinia());
  const queryClient = createIsolatedQueryClient();
  return mount(LibraryInspector, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
      stubs: {
        RouterLink: { template: "<a><slot /></a>" },
        Button: { template: "<button @click='$attrs.onClick?.()'><slot /></button>" },
        ButtonLink: { template: "<a :href='to'><slot /></a>" },
        Input: {
          template:
            "<input :value='$attrs.modelValue ?? modelValue' @input='$emit(\"update:modelValue\", $event.target.value)' />",
        },
        Badge: { template: "<span class='badge'><slot /></span>" },
        Skeleton: { template: "<div class='skeleton' />" },
        Select: { template: "<div class='select-mock'><slot /></div>" },
        SelectTrigger: { template: "<button class='select-trigger'><slot /></button>" },
        SelectContent: { template: "<div class='select-content'><slot /></div>" },
        SelectItem: { template: "<div class='select-item'><slot /></div>" },
        SelectValue: { template: "<span class='select-value'><slot /></span>" },
        SortSelect: { template: "<select class='sort-select'><slot /></select>" },
        Popover: { template: "<div><slot /></div>" },
        PopoverTrigger: { template: "<div><slot /></div>" },
        PopoverContent: { template: "<div class='popover-content'><slot /></div>" },
        Table: { template: "<table><slot /></table>" },
        TableBody: { template: "<tbody><slot /></tbody>" },
        TableCell: { template: "<td><slot /></td>" },
        TableHead: { template: "<th><slot /></th>" },
        TableHeader: { template: "<thead><slot /></thead>" },
        TableRow: { template: "<tr><slot /></tr>" },
      },
    },
  });
}

describe("LibraryInspector extra", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("renders model label for rows", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("SDXL");
  });

  it("renders prompt select options", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("All prompts");
    expect(wrapper.text()).toContain("Has prompt");
    expect(wrapper.text()).toContain("No prompt");
  });

  it("renders model options", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("All models");
  });

  it("renders Gallery link", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Gallery");
  });

  it("shows indexed photos count", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("indexed photos");
  });

  it("renders page summary with root path", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Including subfolders");
  });

  it("renders sort select", () => {
    const wrapper = createWrapper();
    expect(wrapper.find('[aria-label="Sort metadata table"]').exists()).toBe(true);
  });
});
