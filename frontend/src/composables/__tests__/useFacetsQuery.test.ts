import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchFacets } from "@/services/api";
import { useFacetsQuery } from "../useFacetsQuery";

vi.mock("@/services/api", () => ({
  fetchFacets: vi.fn(),
}));

const mockFacets = {
  tool: [{ value: "sd-webui", count: 50 }],
  model: [{ value: "sd-v1.5", count: 30 }],
};

function setup(path: string | null | undefined, enabled = true) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  let result!: ReturnType<typeof useFacetsQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useFacetsQuery(() => path, () => enabled);
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, queryClient, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchFacets).mockResolvedValue(mockFacets);
});

describe("useFacetsQuery", () => {
  it("fetches facets when path is provided", async () => {
    const { result } = setup("/photos");
    await vi.waitFor(() => expect(result.data.value).toEqual(mockFacets));
    expect(fetchFacets).toHaveBeenCalledWith("/photos");
  });

  it("does not fetch when path is empty or null", () => {
    setup("");
    expect(fetchFacets).not.toHaveBeenCalled();
    setup(null);
    expect(fetchFacets).not.toHaveBeenCalled();
  });

  it("does not fetch when enabled is false", () => {
    setup("/photos", false);
    expect(fetchFacets).not.toHaveBeenCalled();
  });

  it("has correct query key", async () => {
    const { result } = setup("/photos");
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(fetchFacets).toHaveBeenCalledWith("/photos");
  });

  it("has isPending true while loading", () => {
    vi.mocked(fetchFacets).mockReturnValue(new Promise(() => {}));
    const { result } = setup("/photos");
    expect(result.isPending.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(fetchFacets).mockRejectedValue(new Error("network error"));
    const { result } = setup("/photos");
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.error.value).toBeTruthy();
  });
});
