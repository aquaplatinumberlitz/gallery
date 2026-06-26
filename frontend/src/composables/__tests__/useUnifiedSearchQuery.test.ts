import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { unifiedSearch } from "@/services/api";
import { useUnifiedSearchQuery } from "../useUnifiedSearchQuery";
import type { SearchScope } from "@/types";

vi.mock("@/services/api", () => ({
  unifiedSearch: vi.fn(),
}));

const mockResults = {
  albums: [{ id: 1, name: "Album 1", count: 5 }],
  photos: [{ path: "/photos/1.png", name: "1.png", type: "image" as const, mtime: 1000 }],
  videos: [],
  prompt: [],
};

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
    vi.mocked(unifiedSearch).mockResolvedValue(mockResults);
    const { result } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(300);

    await vi.waitFor(() => expect(result.data.value).toEqual(mockResults));
    expect(unifiedSearch).toHaveBeenCalledWith("cat", { scope: "all", path: "", limit: 100 });
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
    expect(result.results.value).toEqual({ albums: [], photos: [], videos: [], prompt: [] });
  });

  it("returns empty results before debounce settles", () => {
    vi.mocked(unifiedSearch).mockResolvedValue(mockResults);
    const { result } = setup("cat", "all", "");
    expect(result.results.value).toEqual({ albums: [], photos: [], videos: [], prompt: [] });
  });

  it("debounces query changes before fetching", async () => {
    vi.mocked(unifiedSearch).mockResolvedValue(mockResults);
    const { queryRef } = setup("ca", "all", "");
    // On mount, trimmedDebounced = "ca" and debouncedQuery = "ca" (initial value)
    // So the query fires on mount. Let's first wait for that.
    await vi.advanceTimersByTimeAsync(300);
    vi.mocked(unifiedSearch).mockClear();

    queryRef.value = "cat";
    await vi.advanceTimersByTimeAsync(299);
    expect(unifiedSearch).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    await vi.waitFor(() => expect(unifiedSearch).toHaveBeenCalledWith("cat", expect.anything()));
  });

  it("uses placeholder data from previous query", async () => {
    vi.mocked(unifiedSearch).mockResolvedValue(mockResults);
    const { result, queryRef } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(300);
    await vi.waitFor(() => expect(result.data.value).toEqual(mockResults));

    // Keep second fetch pending so we can observe placeholder data
    vi.mocked(unifiedSearch).mockReturnValue(new Promise(() => {}));
    queryRef.value = "dog";
    await vi.advanceTimersByTimeAsync(300);

    // placeholderData keeps the previous result while refetching
    expect(result.data.value).toEqual(mockResults);
  });

  it("uses scope current to scope search within path", async () => {
    vi.mocked(unifiedSearch).mockResolvedValue(mockResults);
    const { result } = setup("cat", "current", "/photos");
    await vi.advanceTimersByTimeAsync(300);

    await vi.waitFor(() => expect(result.data.value).toEqual(mockResults));
    expect(unifiedSearch).toHaveBeenCalledWith("cat", { scope: "current", path: "/photos", limit: 100 });
  });

  it("has isPending true while loading", () => {
    vi.mocked(unifiedSearch).mockReturnValue(new Promise(() => {}));
    const { result } = setup("cat", "all", "");
    expect(result.isPending.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(unifiedSearch).mockRejectedValue(new Error("network error"));
    const { result } = setup("cat", "all", "");
    await vi.advanceTimersByTimeAsync(300);
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
  });
});
