import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchLibrary } from "@/services/api";
import { useLibraryQuery } from "../useLibraryQuery";

vi.mock("@/services/api", () => ({
  fetchLibrary: vi.fn(),
}));

const mockLibrary = {
  id: 1,
  name: "Test Library",
  root_path: "/test",
  state: "ready",
  import_paths: [],
  exclusion_patterns: [],
  watch_enabled: 1,
  warm_enabled: 1,
  asset_count: 10,
  created_at: Date.now(),
  updated_at: Date.now(),
  last_scan_at: null,
  last_error: null,
};

function setup(id: number | null | undefined) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  let result!: ReturnType<typeof useLibraryQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useLibraryQuery(() => id);
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchLibrary).mockResolvedValue(mockLibrary);
});

describe("useLibraryQuery", () => {
  it("fetches library when id is provided", async () => {
    const { result } = setup(1);
    await vi.waitFor(() => expect(result.data.value).toEqual(mockLibrary));
    expect(fetchLibrary).toHaveBeenCalledWith(1);
  });

  it("does not fetch when id is null", () => {
    setup(null);
    expect(fetchLibrary).not.toHaveBeenCalled();
  });

  it("has isPending true while loading", () => {
    vi.mocked(fetchLibrary).mockReturnValue(new Promise(() => {}));
    const { result } = setup(1);
    expect(result.isPending.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(fetchLibrary).mockRejectedValue(new Error("network error"));
    const { result } = setup(1);
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.error.value).toBeTruthy();
  });
});
