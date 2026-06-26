import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchLibraryInspectorMetadata } from "@/services/api";
import { useLibraryInspectorMetadataQuery } from "../useLibraryInspectorMetadataQuery";
import type { LibraryInspectorMetadataResponse } from "@/types";

vi.mock("@/services/api", () => ({
  fetchLibraryInspectorMetadata: vi.fn(),
}));

const makeMockMetadata = (overrides?: Partial<LibraryInspectorMetadataResponse>): LibraryInspectorMetadataResponse => ({
  path: "/photos/test.png",
  prompt: "a cat",
  negative_prompt: "",
  raw_metadata: null,
  model: "sd-v1.5",
  tool: "sd-webui",
  sampler: "euler_a",
  seed: "42",
  width: 512,
  height: 512,
  mtime: 1000,
  loras: [],
  resources: [],
  metadata_detail_available: true,
  ...overrides,
});

function setup(path: string, enabled: boolean) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const pathRef = ref(path);
  const enabledRef = ref(enabled);
  let result!: ReturnType<typeof useLibraryInspectorMetadataQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useLibraryInspectorMetadataQuery(pathRef, enabledRef);
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, queryClient, wrapper, pathRef, enabledRef };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchLibraryInspectorMetadata).mockResolvedValue(makeMockMetadata());
});

describe("useLibraryInspectorMetadataQuery", () => {
  it("fetches metadata when path and enabled are provided", async () => {
    const { result } = setup("/photos/test.png", true);
    await vi.waitFor(() => expect(result.data.value).toEqual(makeMockMetadata()));
    expect(fetchLibraryInspectorMetadata).toHaveBeenCalledWith("/photos/test.png");
  });

  it("does not fetch when path is empty", () => {
    setup("", true);
    expect(fetchLibraryInspectorMetadata).not.toHaveBeenCalled();
  });

  it("does not fetch when enabled is false", () => {
    setup("/photos/test.png", false);
    expect(fetchLibraryInspectorMetadata).not.toHaveBeenCalled();
  });

  it("has isPending true while loading", () => {
    vi.mocked(fetchLibraryInspectorMetadata).mockReturnValue(new Promise(() => {}));
    const { result } = setup("/photos/test.png", true);
    expect(result.isPending.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(fetchLibraryInspectorMetadata).mockRejectedValue(new Error("network error"));
    const { result } = setup("/photos/test.png", true);
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.error.value).toBeTruthy();
  });
});
