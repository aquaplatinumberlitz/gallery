import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { fetchLibraryInspector } from "@/services/api";
import { useInfiniteLibraryInspectorQuery } from "../useInfiniteLibraryInspectorQuery";
import type {
  SearchScope,
  SortValue,
  LibraryInspectorResponse,
  LibraryInspectorRow,
  PromptPresenceFilter,
} from "@/types";

vi.mock("@/services/api", () => ({
  fetchLibraryInspector: vi.fn(),
}));

function makeRow(name: string, path: string): LibraryInspectorRow {
  return {
    path,
    name,
    folder: path.split("/").slice(0, -1).join("/"),
    relative_path: name,
    mtime: 1000,
    width: null,
    height: null,
    model: "",
    tool: "",
    sampler: "",
    seed: "",
    prompt_preview: "",
    has_prompt: false,
    has_negative: false,
    has_lora: false,
    lora_count: 0,
    lora_preview: "",
    metadata_detail_available: false,
  };
}

const makeMockPage = (overrides?: Partial<LibraryInspectorResponse>): LibraryInspectorResponse => ({
  root: "",
  scope: "current" as const,
  query: "",
  limit: 200,
  generated_at: 1000,
  total_indexed: 50,
  returned: 2,
  truncated: false,
  next_cursor: null,
  has_more: false,
  sort: "date_desc" as const,
  rows: [makeRow("img1.png", "/photos/img1.png"), makeRow("img2.png", "/photos/img2.png")],
  ...overrides,
});

function setup(
  query: string,
  scope: SearchScope,
  path: string,
  limit: number,
  sort: SortValue,
  model = "",
  prompt: PromptPresenceFilter = "all",
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const queryRef = ref(query);
  const scopeRef = ref(scope);
  const pathRef = ref(path);
  const limitRef = ref(limit);
  const sortRef = ref(sort);
  const modelRef = ref(model);
  const promptRef = ref(prompt);
  let result!: ReturnType<typeof useInfiniteLibraryInspectorQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useInfiniteLibraryInspectorQuery({
          query: queryRef,
          scope: scopeRef,
          path: pathRef,
          limit: limitRef,
          sort: sortRef,
          model: modelRef,
          prompt: promptRef,
        });
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, queryClient, wrapper, queryRef, scopeRef, pathRef, limitRef, sortRef, modelRef, promptRef };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
  vi.mocked(fetchLibraryInspector).mockResolvedValue(makeMockPage());
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useInfiniteLibraryInspectorQuery", () => {
  it("fetches inspector data when scope is current and path is provided", async () => {
    const { result } = setup("", "current", "/photos", 200, "date_desc");
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(fetchLibraryInspector).toHaveBeenCalledWith({
      q: "",
      scope: "current",
      path: "/photos",
      limit: 200,
      sort: "date_desc",
      cursor: undefined,
      model: "",
      prompt: "all",
    });
  });

  it("sends server-side model and prompt filters and refetches when they change", async () => {
    const { result, modelRef, promptRef } = setup("", "all", "", 200, "date_desc", "SDXL", "has_prompt");
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(fetchLibraryInspector).toHaveBeenLastCalledWith(
      expect.objectContaining({ model: "SDXL", prompt: "has_prompt" }),
    );

    vi.mocked(fetchLibraryInspector).mockClear();
    modelRef.value = "PonyXL";
    promptRef.value = "no_prompt";

    await vi.waitFor(() =>
      expect(fetchLibraryInspector).toHaveBeenCalledWith(
        expect.objectContaining({ model: "PonyXL", prompt: "no_prompt" }),
      ),
    );
  });

  it("fetches inspector data when scope is all (even without path)", async () => {
    const { result } = setup("", "all", "", 200, "date_desc");
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(fetchLibraryInspector).toHaveBeenCalled();
  });

  it("does not fetch when scope is current and path is empty", () => {
    setup("", "current", "", 200, "date_desc");
    expect(fetchLibraryInspector).not.toHaveBeenCalled();
  });

  it("returns rows from response", async () => {
    const { result } = setup("", "current", "/photos", 200, "date_desc");
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(result.rows.value).toHaveLength(2);
    expect(result.allRows.value).toHaveLength(2);
  });

  it("returns totalIndexed from response", async () => {
    const { result } = setup("", "current", "/photos", 200, "date_desc");
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(result.totalIndexed.value).toBe(50);
  });

  it("debounces query changes before fetching", async () => {
    const { queryRef } = setup("ca", "all", "", 200, "date_desc");
    // Initial fetch fires immediately (refDebounced returns initial value)
    await vi.waitFor(() => expect(fetchLibraryInspector).toHaveBeenCalledTimes(1));
    vi.mocked(fetchLibraryInspector).mockClear();

    queryRef.value = "cat";
    await vi.advanceTimersByTimeAsync(249);
    expect(fetchLibraryInspector).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    await vi.waitFor(() => expect(fetchLibraryInspector).toHaveBeenCalled());
  });

  it("has isPending true while loading", () => {
    vi.mocked(fetchLibraryInspector).mockReturnValue(new Promise(() => {}));
    const { result } = setup("test", "current", "/photos", 200, "date_desc");
    expect(result.isPending.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(fetchLibraryInspector).mockRejectedValue(new Error("network error"));
    const { result } = setup("test", "current", "/photos", 200, "date_desc");
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.error.value).toBeTruthy();
  });

  it("builds merged data from multiple pages", async () => {
    const page1 = makeMockPage({
      rows: [makeRow("img1.png", "/photos/img1.png")],
      next_cursor: "cursor2",
      has_more: true,
    });
    const page2 = makeMockPage({ rows: [makeRow("img2.png", "/photos/img2.png")], next_cursor: null, has_more: false });

    vi.mocked(fetchLibraryInspector).mockResolvedValueOnce(page1).mockResolvedValueOnce(page2);

    const { result } = setup("test", "all", "", 200, "date_desc");
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(result.rows.value).toHaveLength(1);

    // Fetch next page
    await result.fetchNextPage();
    await vi.waitFor(() => expect(result.rows.value).toHaveLength(2));
  });

  it("returns EMPTY_RESPONSE when no data available", () => {
    const { result } = setup("", "current", "/photos", 200, "date_desc");
    expect(result.data.value.rows).toEqual([]);
    expect(result.data.value.total_indexed).toBe(0);
    expect(result.data.value.returned).toBe(0);
  });
});
