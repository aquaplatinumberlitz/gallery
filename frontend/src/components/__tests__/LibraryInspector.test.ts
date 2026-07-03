import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount, type VueWrapper } from "@vue/test-utils";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import LibraryInspector from "../LibraryInspector.vue";

function mockInspectorData(overrides = {}) {
  return {
    rows: [
      {
        path: "/photos/img1.png",
        name: "img1.png",
        type: "image",
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
      {
        path: "/photos/img2.png",
        name: "img2.png",
        type: "image",
        mtime: 1700000001,
        width: 512,
        height: 512,
        seed: 67890,
        model: "SDXL",
        tool: "ComfyUI",
        has_prompt: false,
        has_negative: false,
        has_lora: true,
        lora_count: 2,
        prompt_preview: null,
        relative_path: "/photos",
        folder: "/photos",
      },
    ],
    returned: 2,
    total_indexed: 50,
    total: 2,
    generated_at: Date.now(),
    next_cursor: null,
    has_more: false,
    root: "/photos",
    ...overrides,
  };
}

const mockRowsData = mockInspectorData().rows;
let mockInspectorDataValue: any = { value: mockInspectorData() };
let mockInspectorIsLoading = { value: false };
let mockInspectorIsError = { value: false };
let mockInspectorIsPlaceholder = { value: false };
let mockInspectorHasNext = { value: false };
let mockInspectorIsFetchingNext = { value: false };
const mockInspectorRefetch = vi.fn();
const mockInspectorFetchNext = vi.fn();
const mockRowsRef = { value: mockRowsData };

vi.mock("@/composables/useInfiniteLibraryInspectorQuery", () => ({
  useInfiniteLibraryInspectorQuery: () => ({
    data: mockInspectorDataValue,
    isLoading: mockInspectorIsLoading,
    isError: mockInspectorIsError,
    isPlaceholderData: mockInspectorIsPlaceholder,
    hasNextPage: mockInspectorHasNext,
    isFetchingNextPage: mockInspectorIsFetchingNext,
    refetch: mockInspectorRefetch,
    fetchNextPage: mockInspectorFetchNext,
    rows: mockRowsRef,
    debouncedQuery: { value: "" },
  }),
}));

vi.mock("@/composables/useLibraryInspectorMetadataQuery", () => ({
  useLibraryInspectorMetadataQuery: () => ({
    data: { value: null },
    isLoading: { value: false },
    isError: { value: false },
    refetch: vi.fn(),
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
  fetchLibraryInspectorMetadata: vi.fn(),
  getThumbnailUrl: vi.fn((path) => `/thumb/${path}`),
}));

vi.mock("@/query", () => ({
  queryClient: { fetchQuery: vi.fn(), prefetchQuery: vi.fn() },
}));

vi.mock("@/query/keys", () => ({
  queryKeys: {
    libraryInspector: vi.fn(() => ["inspector"]),
    libraryInspectorMetadata: vi.fn((path) => ["inspector-metadata", path]),
  },
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

const defaultStubs = {
  RouterLink: { template: "<a><slot /></a>" },
  Button: { template: "<button><slot /></button>" },
  ButtonLink: { template: "<a><slot /></a>" },
  Input: { template: "<input />" },
  Badge: { template: "<span><slot /></span>" },
  Skeleton: { template: "<div data-testid='skeleton'>skeleton</div>" },
  Select: { template: "<div class='select-mock'><slot /></div>" },
  SelectTrigger: { template: "<button class='select-trigger'><slot /></button>" },
  SelectContent: { template: "<div class='select-content'><slot /></div>" },
  SelectGroup: { template: "<div class='select-group'><slot /></div>" },
  SelectItem: { template: "<div class='select-item'><slot /></div>" },
  SelectValue: { template: "<span class='select-value'><slot /></span>" },
  SortSelect: { template: "<select class='sort-select' />" },
  Popover: { template: "<div><slot /></div>" },
  PopoverTrigger: { template: "<div><slot /></div>" },
  PopoverContent: { template: "<div><slot /></div>" },
  Tooltip: { template: "<span><slot /></span>" },
  TooltipTrigger: { template: "<span><slot /></span>" },
  TooltipContent: { template: "<span><slot /></span>" },
  Table: { template: "<table><slot /></table>" },
  TableBody: { template: "<tbody><slot /></tbody>" },
  TableCell: { template: "<td><slot /></td>" },
  TableHead: { template: "<th><slot /></th>" },
  TableHeader: { template: "<thead><slot /></thead>" },
  TableRow: { template: "<tr><slot /></tr>" },
  DropdownMenu: { template: "<div><slot /></div>" },
  DropdownMenuCheckboxItem: { template: "<div><slot /></div>" },
  DropdownMenuContent: { template: "<div><slot /></div>" },
  DropdownMenuGroup: { template: "<div><slot /></div>" },
  DropdownMenuItem: { template: "<div><slot /></div>" },
  DropdownMenuLabel: { template: "<div><slot /></div>" },
  DropdownMenuSeparator: { template: "<hr />" },
  DropdownMenuTrigger: { template: "<div><slot /></div>" },
  ArrowLeft: { template: "<span>arrow-left</span>" },
  ArrowUpDown: { template: "<span>sort-icon</span>" },
  Columns3: { template: "<span>columns-icon</span>" },
  Copy: { template: "<span>copy-icon</span>" },
  Search: { template: "<span>search-icon</span>" },
  ExternalLink: { template: "<span>external-link</span>" },
  MoreHorizontal: { template: "<span>more-icon</span>" },
  X: { template: "<span>x-icon</span>" },
} as const;

function mountSubject(stubs: Record<string, unknown> = {}): VueWrapper {
  setActivePinia(createPinia());
  const queryClient = createIsolatedQueryClient();
  return mount(LibraryInspector, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
      stubs: { ...defaultStubs, ...stubs },
    },
  });
}

describe("LibraryInspector", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockInspectorDataValue = { value: mockInspectorData() };
    mockInspectorIsLoading = { value: false };
    mockInspectorIsError = { value: false };
    mockInspectorIsPlaceholder = { value: false };
    mockInspectorHasNext = { value: false };
    mockInspectorIsFetchingNext = { value: false };
    mockRowsRef.value = mockRowsData;
  });

  it("renders title, summary and indexed count", () => {
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Photo Details");
    expect(wrapper.text()).toContain("indexed photos");
    expect(wrapper.text()).toContain("Including subfolders");
  });

  it("shows loading skeletons when loading", () => {
    mockInspectorIsLoading = { value: true };
    const wrapper = mountSubject();
    const skeletons = wrapper.findAll('[data-testid="skeleton"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows error message when query has error", () => {
    mockInspectorIsError = { value: true };
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Unable to load metadata rows");
  });

  it("shows empty message when no rows", () => {
    mockInspectorDataValue = {
      value: mockInspectorData({ rows: [], returned: 0, total: 0, total_indexed: 0 }),
    };
    mockRowsRef.value = [];
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("No indexed metadata rows");
  });

  it("renders model filter select", () => {
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("All models");
  });

  it("renders prompt filter select", () => {
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("All prompts");
  });
});
