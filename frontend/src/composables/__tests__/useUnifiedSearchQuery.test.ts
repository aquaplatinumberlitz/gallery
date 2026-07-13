import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { unifiedSearch } from "@/services/api";
import { useUnifiedSearchQuery } from "../useUnifiedSearchQuery";
import { GALLERY_SEARCH_DEBOUNCE_MS } from "@/constants";
import type { SearchScope, UnifiedSearchResponse, UnifiedSearchResult } from "@/types";

vi.mock("@/services/api", () => ({
  unifiedSearch: vi.fn(),
}));

const makeSearchResult = (name: string): UnifiedSearchResult => ({
  name,
  path: `/photos/${name}`,
  type: "image" as const,
  parent_path: "/photos",
  relative_path: name,
  mtime: 1000,
  width: null,
  height: null,
  match_type: "exact",
  model: "",
  sampler: "",
  seed: "",
  prompt_snippet: "",
});

const makeMockResults = (overrides?: Partial<UnifiedSearchResponse>): UnifiedSearchResponse => ({
  albums: [makeSearchResult("album1"), makeSearchResult("album2")].map((r, i) => ({
    ...r,
    name: `Album ${i + 1}`,
    image_count: 5,
  })),
  photos: [makeSearchResult("1.png")],
  videos: [],
  prompt: [],
  media: [makeSearchResult("1.png")],
  query: "",
  scope: "all" as const,
  root: "",
  next_cursor: null,
  has_more: false,
  returned: 1,
  limit: 60,
  ...overrides,
});

function setup(query: string, scope: SearchScope, path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const queryRef = ref(query);
  const scopeRef = ref(scope);
  const pathRef = ref(path);
  let result!: ReturnType<typeof useUnifiedSearchQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useUnifiedSearchQuery(queryRef, scopeRef, pathRef);
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, queryClient, wrapper, queryRef, scopeRef, pathRef };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useUnifiedSearchQuery", () => {
  it("fetches search results when query is non-empty after debounce", async () => {
    vi.mocked(unifiedSearch).mockResolvedValue(makeMockResults());
    const { result } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);

    await vi.waitFor(() => expect(result.results.value.media).toEqual([makeSearchResult("1.png")]));
    expect(unifiedSearch).toHaveBeenCalledWith("cat", { scope: "all", path: "", limit: 60, cursor: undefined });
  });

  it("does not fetch when query is empty", () => {
    setup("", "all", "");
    expect(unifiedSearch).not.toHaveBeenCalled();
  });

  it("does not fetch when query is whitespace (trimmed to empty)", () => {
    setup("   ", "all", "");
    expect(unifiedSearch).not.toHaveBeenCalled();
  });

  it("returns empty results when query is empty", () => {
    const { result } = setup("", "all", "");
    expect(result.results.value).toEqual({ albums: [], photos: [], videos: [], prompt: [], media: [] });
  });

  it("returns empty results before debounce settles", () => {
    vi.mocked(unifiedSearch).mockResolvedValue(makeMockResults());
    const { result } = setup("cat", "all", "");
    expect(result.results.value).toEqual({ albums: [], photos: [], videos: [], prompt: [], media: [] });
  });

  it("debounces query changes before fetching", async () => {
    vi.mocked(unifiedSearch).mockResolvedValue(makeMockResults());
    const { queryRef } = setup("ca", "all", "");
    // On mount, trimmedDebounced = "ca" and debouncedQuery = "ca" (initial value)
    // So the query fires on mount. Let's first wait for that.
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);
    vi.mocked(unifiedSearch).mockClear();

    queryRef.value = "cat";
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS - 1);
    expect(unifiedSearch).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    await vi.waitFor(() => expect(unifiedSearch).toHaveBeenCalledWith("cat", expect.anything()));
  });

  it("clears previous results for a new query while the next fetch is pending", async () => {
    vi.mocked(unifiedSearch).mockResolvedValue(makeMockResults());
    const { result, queryRef } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);
    await vi.waitFor(() => expect(result.results.value.media).toEqual([makeSearchResult("1.png")]));

    // Keep second fetch pending so we can observe the new-key loading state.
    vi.mocked(unifiedSearch).mockReturnValue(new Promise(() => {}));
    queryRef.value = "dog";
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS - 1);

    expect(result.results.value).toEqual({ albums: [], photos: [], videos: [], prompt: [], media: [] });

    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);

    expect(result.results.value).toEqual({ albums: [], photos: [], videos: [], prompt: [], media: [] });
  });

  it("uses scope current to scope search within path", async () => {
    vi.mocked(unifiedSearch).mockResolvedValue(makeMockResults());
    const { result } = setup("cat", "current", "/photos");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);

    await vi.waitFor(() => expect(result.results.value.media).toEqual([makeSearchResult("1.png")]));
    expect(unifiedSearch).toHaveBeenCalledWith("cat", {
      scope: "current",
      path: "/photos",
      limit: 60,
      cursor: undefined,
    });
  });

  it("fetches the next page with the previous next_cursor", async () => {
    vi.mocked(unifiedSearch)
      .mockResolvedValueOnce(
        makeMockResults({ media: [makeSearchResult("1.png")], next_cursor: "cursor-1", has_more: true }),
      )
      .mockResolvedValueOnce(makeMockResults({ media: [makeSearchResult("2.png")], next_cursor: null }));
    const { result } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);
    await vi.waitFor(() => expect(result.hasNextPage.value).toBe(true));

    await result.fetchNextPage();

    await vi.waitFor(() => expect(result.results.value.media?.map((item) => item.name)).toEqual(["1.png", "2.png"]));
    expect(unifiedSearch).toHaveBeenLastCalledWith("cat", {
      scope: "all",
      path: "",
      limit: 60,
      cursor: "cursor-1",
    });
  });

  it("has isPending true while loading", () => {
    vi.mocked(unifiedSearch).mockReturnValue(new Promise(() => {}));
    const { result } = setup("cat", "all", "");
    expect(result.isPending.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(unifiedSearch).mockRejectedValue(new Error("network error"));
    const { result } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
  });
});
