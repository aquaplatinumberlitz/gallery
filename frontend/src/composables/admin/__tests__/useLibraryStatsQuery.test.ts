import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchLibraryStats } from "@/services/api";
import { useLibraryStatsQuery } from "../useLibraryStatsQuery";

vi.mock("@/services/api", () => ({
  fetchLibraryStats: vi.fn(),
}));

const mockStats = {
  photos: 10,
  videos: 5,
  total_assets: 15,
  active_assets: 12,
  offline_assets: 3,
  usage_bytes: 1048576,
  import_path_count: 1,
};

function setup(id: number | null | undefined) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  let result!: ReturnType<typeof useLibraryStatsQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useLibraryStatsQuery(() => id);
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchLibraryStats).mockResolvedValue(mockStats);
});

describe("useLibraryStatsQuery", () => {
  it("fetches stats when id is provided", async () => {
    const { result } = setup(1);
    await vi.waitFor(() => expect(result.data.value).toEqual(mockStats));
    expect(fetchLibraryStats).toHaveBeenCalledWith(1);
  });

  it("does not fetch when id is null", () => {
    setup(null);
    expect(fetchLibraryStats).not.toHaveBeenCalled();
  });

  it("has isPending true while loading", () => {
    vi.mocked(fetchLibraryStats).mockReturnValue(new Promise(() => {}));
    const { result } = setup(1);
    expect(result.isPending.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(fetchLibraryStats).mockRejectedValue(new Error("network error"));
    const { result } = setup(1);
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.error.value).toBeTruthy();
  });
});
