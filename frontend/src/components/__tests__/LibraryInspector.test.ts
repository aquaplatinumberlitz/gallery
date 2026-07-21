import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount, type VueWrapper } from "@vue/test-utils";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import LibraryInspector from "../LibraryInspector.vue";

const clipboardMocks = vi.hoisted(() => ({
  copyText: vi.fn(),
  copyStatus: {} as Record<string, boolean>,
}));

const queryMocks = vi.hoisted(() => ({
  fetchQuery: vi.fn(),
  prefetchQuery: vi.fn(),
}));

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

vi.mock("@tanstack/vue-virtual", () => ({
  useVirtualizer: () => ({
    value: {
      getVirtualItems: () =>
        mockRowsRef.value.map((row, index) => ({
          index,
          key: row.path,
          size: 64,
          start: index * 64,
          end: (index + 1) * 64,
        })),
      getTotalSize: () => mockRowsRef.value.length * 64,
      measure: vi.fn(),
      scrollToOffset: vi.fn(),
    },
  }),
}));

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

vi.mock("@/composables/useFacetsQuery", () => ({
  useFacetsQuery: () => ({
    data: { value: { model: [{ value: "SDXL", count: 2 }] } },
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
  useClipboard: () => ({ copyStatus: clipboardMocks.copyStatus, copyText: clipboardMocks.copyText }),
}));

vi.mock("@/composables/useToast", () => ({
  useToast: () => ({ error: vi.fn() }),
}));

vi.mock("@/services/api", () => ({
  fetchLibraryInspectorMetadata: vi.fn(),
  getThumbnailUrl: vi.fn((path) => `/thumb/${path}`),
}));

vi.mock("@/query", () => ({
  queryClient: queryMocks,
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
  PopoverContent: { template: '<div data-slot="popover-content"><slot /></div>' },
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
  DropdownMenuContent: { template: '<div data-slot="dropdown-menu-content"><slot /></div>' },
  DropdownMenuGroup: { template: "<div><slot /></div>" },
  DropdownMenuItem: {
    emits: ["select"],
    template: '<div data-slot="dropdown-menu-item" tabindex="0" @click="$emit(\'select\', $event)"><slot /></div>',
  },
  DropdownMenuLabel: { template: "<div><slot /></div>" },
  DropdownMenuSeparator: { template: "<hr />" },
  DropdownMenuTrigger: { template: "<div><slot /></div>" },
  ArrowLeft: { template: "<span>arrow-left</span>" },
  ArrowUpDown: { template: "<span>sort-icon</span>" },
  EyeOff: { template: "<span>eye-off-icon</span>" },
  Copy: { template: "<span>copy-icon</span>" },
  Check: { template: "<span>check-icon</span>" },
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

function getDropdownItem(wrapper: VueWrapper, label: string) {
  const item = wrapper
    .findAll('[data-slot="dropdown-menu-item"]')
    .find((candidate) => candidate.text().includes(label));
  expect(item, `Expected dropdown item "${label}" to exist`).toBeTruthy();
  return item!;
}

describe("LibraryInspector", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clipboardMocks.copyText.mockResolvedValue(true);
    clipboardMocks.copyStatus = {};
    queryMocks.fetchQuery.mockResolvedValue({
      prompt: "full prompt",
      negative_prompt: "bad hands",
      loras: [{ name: "detailer", hash: "abc123", weight: "0.8" }],
      params: { Seed: 12345 },
    });
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

  it("only exposes server-supported File and Modified column sorting", () => {
    const wrapper = mountSubject();
    const sortButtons = wrapper.findAll("button[aria-label]").map((button) => button.attributes("aria-label"));

    expect(sortButtons.some((label) => label?.startsWith("File,"))).toBe(true);
    expect(sortButtons.some((label) => label?.startsWith("Modified,"))).toBe(true);
    expect(sortButtons.some((label) => label?.startsWith("Model,"))).toBe(false);
    expect(sortButtons.some((label) => label?.startsWith("Seed,"))).toBe(false);
    expect(sortButtons.some((label) => label?.startsWith("Size,"))).toBe(false);
  });

  it("maps copy status to distinct success labels", () => {
    clipboardMocks.copyStatus = {
      path: true,
      prompt: true,
      neg: true,
      loras: true,
      metadata: true,
    };
    const wrapper = mountSubject();

    for (const label of [
      "Path copied",
      "Prompt copied",
      "Negative prompt copied",
      "LoRA list copied",
      "Metadata copied",
    ]) {
      expect(wrapper.find(`button[aria-label="${label}"]`).exists(), `Expected "${label}" state`).toBe(true);
    }
  });

  it.each([
    ["Copy prompt", "full prompt", "prompt"],
    ["Copy negative", "bad hands", "neg"],
    ["Copy LoRA list", "detailer | abc123 | weight 0.8", "loras"],
  ])("maps the %s action to its clipboard handler", async (buttonLabel, expectedText, copyId) => {
    const wrapper = mountSubject();

    await wrapper.get(`button[aria-label="${buttonLabel}"]`).trigger("click");
    await vi.waitFor(() => {
      expect(clipboardMocks.copyText).toHaveBeenCalledWith(
        expectedText,
        copyId,
        expect.objectContaining({ fallbackRoot: expect.any(HTMLElement) }),
      );
    });
  });

  it("maps the full path action directly to the path clipboard handler", async () => {
    const wrapper = mountSubject();
    const firstVisibleRow = mockRowsData[0];

    await wrapper.get('button[aria-label="Copy full path"]').trigger("click");

    expect(clipboardMocks.copyText).toHaveBeenCalledWith(
      firstVisibleRow.path,
      "path",
      expect.objectContaining({ fallbackRoot: expect.any(HTMLElement) }),
    );
  });

  it("maps the metadata action to composed metadata copy", async () => {
    const wrapper = mountSubject();

    await wrapper.get('button[aria-label="Copy all metadata"]').trigger("click");
    await vi.waitFor(() => {
      expect(clipboardMocks.copyText).toHaveBeenCalledWith(
        expect.stringContaining("Negative prompt: bad hands"),
        "metadata",
        expect.objectContaining({ fallbackRoot: expect.any(HTMLElement) }),
      );
    });
  });

  it("copies row path from the actions menu with the dropdown content as fallback root", async () => {
    const wrapper = mountSubject();
    const copyPathItem = getDropdownItem(wrapper, "Copy path");
    const firstVisibleRow = mockRowsData[0];

    await copyPathItem.trigger("pointerdown");
    await copyPathItem.trigger("click");

    expect(clipboardMocks.copyText).toHaveBeenCalledWith(
      firstVisibleRow.path,
      "path",
      expect.objectContaining({
        fallbackRoot: expect.any(HTMLElement),
      }),
    );
    const options = clipboardMocks.copyText.mock.calls[0][2] as { fallbackRoot?: Element | null };
    expect(options.fallbackRoot).toBe(copyPathItem.element.closest('[data-slot="dropdown-menu-content"]'));
  });

  it("copies row seed from the actions menu with the dropdown content as fallback root", async () => {
    const wrapper = mountSubject();
    const copySeedItem = getDropdownItem(wrapper, "Copy seed");
    const firstVisibleRow = mockRowsData[0];

    await copySeedItem.trigger("pointerdown");
    await copySeedItem.trigger("click");

    expect(clipboardMocks.copyText).toHaveBeenCalledWith(
      firstVisibleRow.seed,
      `seed:${firstVisibleRow.path}`,
      expect.objectContaining({
        fallbackRoot: expect.any(HTMLElement),
      }),
    );
    const options = clipboardMocks.copyText.mock.calls[0][2] as { fallbackRoot?: Element | null };
    expect(options.fallbackRoot).toBe(copySeedItem.element.closest('[data-slot="dropdown-menu-content"]'));
  });
});
