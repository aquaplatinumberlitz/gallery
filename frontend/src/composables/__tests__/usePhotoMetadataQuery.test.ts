import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchMetadata } from "@/services/api";
import { usePhotoMetadataQuery } from "../usePhotoMetadataQuery";
import type { MetadataResponse } from "@/types";

vi.mock("@/services/api", () => ({
  fetchMetadata: vi.fn(),
}));

const makeMockMetadata = (overrides?: Partial<MetadataResponse>): MetadataResponse => ({
  tool: "sd-webui",
  prompt: "a beautiful landscape",
  negative_prompt: "",
  params: { Seed: "12345", Steps: "30", CFG: "7.5", Sampler: "Euler a", Scheduler: "Karras", Model: "sd-xl" },
  width: 1024,
  height: 768,
  name: "/photos/test.png",
  ...overrides,
});

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
  vi.mocked(fetchMetadata).mockResolvedValue(makeMockMetadata());
});

describe("usePhotoMetadataQuery", () => {
  it("fetches metadata when open and path is provided", async () => {
    const { result } = setup(true, "/photos/test.png");
    await vi.waitFor(() => expect(result.data.value).toEqual(makeMockMetadata()));
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
    await vi.waitFor(() => expect(result.data.value).toEqual(makeMockMetadata()));
    expect(fetchMetadata).toHaveBeenCalledWith("/photos/test.png");

    vi.mocked(fetchMetadata).mockResolvedValue(makeMockMetadata({ name: "/photos/other.png" }));
    pathRef.value = "/photos/other.png";
    await vi.waitFor(() => expect(fetchMetadata).toHaveBeenCalledWith("/photos/other.png"));
  });
});
