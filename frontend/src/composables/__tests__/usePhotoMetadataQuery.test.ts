import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchMetadata } from "@/services/api";
import { usePhotoMetadataQuery } from "../usePhotoMetadataQuery";

vi.mock("@/services/api", () => ({
  fetchMetadata: vi.fn(),
}));

const mockMetadata = {
  path: "/photos/test.png",
  prompt: "a beautiful landscape",
  width: 1024,
  height: 768,
  model: "sd-xl",
};

function setup(isOpen: boolean, path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const isOpenRef = ref(isOpen);
  const pathRef = ref(path);
  let result!: ReturnType<typeof usePhotoMetadataQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = usePhotoMetadataQuery(isOpenRef, pathRef);
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, queryClient, wrapper, isOpenRef, pathRef };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchMetadata).mockResolvedValue(mockMetadata);
});

describe("usePhotoMetadataQuery", () => {
  it("fetches metadata when open and path is provided", async () => {
    const { result } = setup(true, "/photos/test.png");
    await vi.waitFor(() => expect(result.data.value).toEqual(mockMetadata));
    expect(fetchMetadata).toHaveBeenCalledWith("/photos/test.png");
  });

  it("does not fetch when isOpen is false", () => {
    setup(false, "/photos/test.png");
    expect(fetchMetadata).not.toHaveBeenCalled();
  });

  it("does not fetch when path is empty", () => {
    setup(true, "");
    expect(fetchMetadata).not.toHaveBeenCalled();
  });

  it("does not fetch when path is whitespace", () => {
    setup(true, "  ");
    expect(fetchMetadata).not.toHaveBeenCalled();
  });

  it("has isPending true while loading", () => {
    vi.mocked(fetchMetadata).mockReturnValue(new Promise(() => {}));
    const { result } = setup(true, "/photos/test.png");
    expect(result.isPending.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(fetchMetadata).mockRejectedValue(new Error("network error"));
    const { result } = setup(true, "/photos/test.png");
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.error.value).toBeTruthy();
  });

  it("refetches when path changes and isOpen stays true", async () => {
    const { result, pathRef } = setup(true, "/photos/test.png");
    await vi.waitFor(() => expect(result.data.value).toEqual(mockMetadata));
    expect(fetchMetadata).toHaveBeenCalledWith("/photos/test.png");

    vi.mocked(fetchMetadata).mockResolvedValue({ ...mockMetadata, path: "/photos/other.png" });
    pathRef.value = "/photos/other.png";
    await vi.waitFor(() => expect(fetchMetadata).toHaveBeenCalledWith("/photos/other.png"));
  });
});
