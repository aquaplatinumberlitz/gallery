import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { computed, defineComponent, h, ref } from "vue";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { unifiedSearchV2 } from "@/services/api";
import { useUnifiedSearchQuery } from "../useUnifiedSearchQuery";
import { GALLERY_SEARCH_DEBOUNCE_MS } from "@/constants";
import type { SearchQueryRequestV1, SearchScope, UnifiedSearchResponse, UnifiedSearchResult } from "@/types";

vi.mock("@/services/api", () => ({
  unifiedSearchV2: vi.fn(),
}));

vi.mock("../useSavedSearches", () => ({ recordRecentSearch: vi.fn() }));

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
  const requestRef = computed<SearchQueryRequestV1 | null>(() => {
    const text = queryRef.value.trim();
    if (!text) return null;
    const requestScope: SearchQueryRequestV1["scope"] =
      scopeRef.value === "all"
        ? { kind: "all" }
        : scopeRef.value === "library"
          ? { kind: "library", library_id: 2 }
          : {
              kind: "folder",
              library_id: 2,
              import_path_id: 7,
              relative_path: pathRef.value.replace(/^\/+/, ""),
            };
    return {
      schema_version: 1,
      mode: "lexical",
      text,
      scope: requestScope,
      filters: { prompt_groups: [], workflow_groups: [] },
      cursor: null,
      limit: 60,
    };
  });
  let result!: ReturnType<typeof useUnifiedSearchQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useUnifiedSearchQuery(requestRef);
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
    vi.mocked(unifiedSearchV2).mockResolvedValue(makeMockResults());
    const { result } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);

    await vi.waitFor(() => expect(result.results.value.media).toEqual([makeSearchResult("1.png")]));
    expect(unifiedSearchV2).toHaveBeenCalledWith(
      {
        schema_version: 1,
        mode: "lexical",
        text: "cat",
        scope: { kind: "all" },
        filters: { prompt_groups: [], workflow_groups: [] },
        cursor: null,
        limit: 60,
      },
      expect.any(AbortSignal),
    );
  });

  it("does not fetch when query is empty", () => {
    setup("", "all", "");
    expect(unifiedSearchV2).not.toHaveBeenCalled();
  });

  it("does not fetch when query is whitespace (trimmed to empty)", () => {
    setup("   ", "all", "");
    expect(unifiedSearchV2).not.toHaveBeenCalled();
  });

  it("returns empty results when query is empty", () => {
    const { result } = setup("", "all", "");
    expect(result.results.value).toEqual({ albums: [], photos: [], videos: [], prompt: [], media: [] });
  });

  it("returns empty results before debounce settles", () => {
    vi.mocked(unifiedSearchV2).mockResolvedValue(makeMockResults());
    const { result } = setup("cat", "all", "");
    expect(result.results.value).toEqual({ albums: [], photos: [], videos: [], prompt: [], media: [] });
  });

  it("debounces query changes before fetching", async () => {
    vi.mocked(unifiedSearchV2).mockResolvedValue(makeMockResults());
    const { queryRef } = setup("ca", "all", "");
    // On mount, trimmedDebounced = "ca" and debouncedQuery = "ca" (initial value)
    // So the query fires on mount. Let's first wait for that.
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);
    vi.mocked(unifiedSearchV2).mockClear();

    queryRef.value = "cat";
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS - 1);
    expect(unifiedSearchV2).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    await vi.waitFor(() =>
      expect(unifiedSearchV2).toHaveBeenCalledWith(expect.objectContaining({ text: "cat" }), expect.any(AbortSignal)),
    );
  });

  it("clears previous results for a new query while the next fetch is pending", async () => {
    vi.mocked(unifiedSearchV2).mockResolvedValue(makeMockResults());
    const { result, queryRef } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);
    await vi.waitFor(() => expect(result.results.value.media).toEqual([makeSearchResult("1.png")]));

    // Keep second fetch pending so we can observe the new-key loading state.
    vi.mocked(unifiedSearchV2).mockReturnValue(new Promise(() => {}));
    queryRef.value = "dog";
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS - 1);

    expect(result.results.value).toEqual({ albums: [], photos: [], videos: [], prompt: [], media: [] });

    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);

    expect(result.results.value).toEqual({ albums: [], photos: [], videos: [], prompt: [], media: [] });
  });

  it("uses scope current to scope search within path", async () => {
    vi.mocked(unifiedSearchV2).mockResolvedValue(makeMockResults());
    const { result } = setup("cat", "current", "/photos");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);

    await vi.waitFor(() => expect(result.results.value.media).toEqual([makeSearchResult("1.png")]));
    expect(unifiedSearchV2).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "cat",
        scope: { kind: "folder", library_id: 2, import_path_id: 7, relative_path: "photos" },
      }),
      expect.any(AbortSignal),
    );
  });

  it("fetches the next page with the previous next_cursor", async () => {
    vi.mocked(unifiedSearchV2)
      .mockResolvedValueOnce(
        makeMockResults({ media: [makeSearchResult("1.png")], next_cursor: "cursor-1", has_more: true }),
      )
      .mockResolvedValueOnce(makeMockResults({ media: [makeSearchResult("2.png")], next_cursor: null }));
    const { result } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);
    await vi.waitFor(() => expect(result.hasNextPage.value).toBe(true));

    await result.fetchNextPage();

    await vi.waitFor(() => expect(result.results.value.media?.map((item) => item.name)).toEqual(["1.png", "2.png"]));
    expect(unifiedSearchV2).toHaveBeenLastCalledWith(
      expect.objectContaining({ text: "cat", scope: { kind: "all" }, cursor: "cursor-1", limit: 60 }),
      expect.any(AbortSignal),
    );
  });

  it("has isPending true while loading", () => {
    vi.mocked(unifiedSearchV2).mockReturnValue(new Promise(() => {}));
    const { result } = setup("cat", "all", "");
    expect(result.isPending.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(unifiedSearchV2).mockRejectedValue(new Error("network error"));
    const { result } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
  });

  it("deduplicates by library and asset identity before path", async () => {
    const first = { ...makeSearchResult("A.png"), library_id: 4, asset_id: 9, path: "/A.png" };
    const duplicate = { ...first, path: "/renamed.png" };
    vi.mocked(unifiedSearchV2).mockResolvedValue(makeMockResults({ media: [first, duplicate] }));
    const { result } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);
    await vi.waitFor(() => expect(result.media.value).toEqual([first]));
  });

  it("keeps case-distinct compatibility paths", async () => {
    const upper = { ...makeSearchResult("A.png"), path: "/A.png" };
    const lower = { ...makeSearchResult("a.png"), path: "/a.png" };
    vi.mocked(unifiedSearchV2).mockResolvedValue(makeMockResults({ media: [upper, lower] }));
    const { result } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);
    await vi.waitFor(() => expect(result.media.value).toEqual([upper, lower]));
  });

  it("uses legacy arrays only when canonical media is absent", async () => {
    const photo = makeSearchResult("legacy.png");
    const response = makeMockResults({ photos: [photo], prompt: [], videos: [] });
    delete response.media;
    vi.mocked(unifiedSearchV2).mockResolvedValue(response);
    const { result } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);
    await vi.waitFor(() => expect(result.media.value).toEqual([photo]));

    vi.mocked(unifiedSearchV2).mockResolvedValue(makeMockResults({ media: [], photos: [photo] }));
    const second = setup("dog", "all", "");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);
    await vi.waitFor(() => expect(second.result.media.value).toEqual([]));
  });

  it("preserves earlier pages while retrying a failed next page", async () => {
    const first = makeSearchResult("1.png");
    const second = makeSearchResult("2.png");
    vi.mocked(unifiedSearchV2)
      .mockResolvedValueOnce(makeMockResults({ media: [first], next_cursor: "cursor-1", has_more: true }))
      .mockRejectedValueOnce(new Error("page failed"))
      .mockResolvedValueOnce(makeMockResults({ media: [second], next_cursor: null, has_more: false }));
    const { result } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(GALLERY_SEARCH_DEBOUNCE_MS);
    await vi.waitFor(() => expect(result.hasNextPage.value).toBe(true));

    await result.fetchNextPage();
    await vi.waitFor(() => expect(result.isFetchNextPageError.value).toBe(true));
    expect(result.media.value).toEqual([first]);

    await result.fetchNextPage();
    await vi.waitFor(() => expect(result.media.value).toEqual([first, second]));
  });
});
