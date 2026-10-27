import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { queryKeys } from "@/query/keys";
import { fetchLandingPages } from "@/services/api";
import { normalizeLandingPages, useLandingPagesQuery } from "../useLandingPagesQuery";

vi.mock("@/services/api", () => ({
  fetchLandingPages: vi.fn(),
}));

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  let result!: ReturnType<typeof useLandingPagesQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useLandingPagesQuery();
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, queryClient, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("normalizeLandingPages", () => {
  it("indexes pages by their position in the API response", () => {
    expect(normalizeLandingPages(["/landpage/a/index.html", "/landpage/b/index.html"])).toEqual([
      { url: "/landpage/a/index.html", index: 0 },
      { url: "/landpage/b/index.html", index: 1 },
    ]);
  });

  it("keeps the first occurrence of a duplicated URL and its original index", () => {
    expect(normalizeLandingPages(["/a", "/b", "/a", "/c", "/b"])).toEqual([
      { url: "/a", index: 0 },
      { url: "/b", index: 1 },
      { url: "/c", index: 3 },
    ]);
  });

  it("returns an empty list for an empty response", () => {
    expect(normalizeLandingPages([])).toEqual([]);
  });
});

describe("useLandingPagesQuery", () => {
  it("starts in the loading state before the request settles", async () => {
    let resolve!: (value: string[]) => void;
    vi.mocked(fetchLandingPages).mockReturnValue(new Promise<string[]>((r) => (resolve = r)));

    const { result } = setup();

    expect(result.isLoading.value).toBe(true);
    expect(result.data.value).toBeUndefined();

    resolve(["/landpage/a/index.html"]);
    await vi.waitFor(() => expect(result.isLoading.value).toBe(false));
  });

  it("exposes de-duplicated landing pages in API order", async () => {
    vi.mocked(fetchLandingPages).mockResolvedValue([
      "/landpage/a/index.html",
      "/landpage/b/index.html",
      "/landpage/a/index.html",
    ]);

    const { result } = setup();

    await vi.waitFor(() =>
      expect(result.data.value).toEqual([
        { url: "/landpage/a/index.html", index: 0 },
        { url: "/landpage/b/index.html", index: 1 },
      ]),
    );
    expect(fetchLandingPages).toHaveBeenCalledTimes(1);
  });

  it("exposes an empty list when the API returns no pages", async () => {
    vi.mocked(fetchLandingPages).mockResolvedValue([]);

    const { result } = setup();

    await vi.waitFor(() => expect(result.data.value).toEqual([]));
    expect(result.isError.value).toBe(false);
  });

  it("caches the result under the shared landing-pages query key", async () => {
    vi.mocked(fetchLandingPages).mockResolvedValue(["/landpage/a/index.html"]);

    const { result, queryClient } = setup();

    await vi.waitFor(() => expect(result.data.value).toHaveLength(1));
    expect(queryClient.getQueryData(queryKeys.landingPages())).toEqual([{ url: "/landpage/a/index.html", index: 0 }]);
  });

  it("reports a failed request through isError without data", async () => {
    vi.mocked(fetchLandingPages).mockRejectedValue(new Error("boom"));

    const { result } = setup();

    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.data.value).toBeUndefined();
  });
});
