import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchMetadata } from "@/services/api";
import { queryKeys } from "@/query/keys";
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

function setup(isOpen: boolean, path: string, version: string | null = null, queryClient?: QueryClient) {
  const client = queryClient ?? new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const isOpenRef = ref(isOpen);
  const pathRef = ref(path);
  const versionRef = ref<string | null>(version);
  let result!: ReturnType<typeof usePhotoMetadataQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = usePhotoMetadataQuery(isOpenRef, pathRef, versionRef);
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
  );
  return { result, queryClient: client, wrapper, isOpenRef, pathRef, versionRef };
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

  it("refetches the same path when its content_version changes", async () => {
    const { result, versionRef } = setup(true, "/photos/test.png", "1-2");
    await vi.waitFor(() => expect(result.data.value).toEqual(makeMockMetadata()));
    expect(fetchMetadata).toHaveBeenCalledTimes(1);

    vi.mocked(fetchMetadata).mockResolvedValue(makeMockMetadata({ prompt: "edited prompt" }));
    versionRef.value = "2-2";
    await vi.waitFor(() => expect(result.data.value?.prompt).toBe("edited prompt"));
    expect(fetchMetadata).toHaveBeenCalledTimes(2);
    expect(fetchMetadata).toHaveBeenLastCalledWith("/photos/test.png");
  });

  it("reuses the cached entry for an unchanged content_version without refetching", async () => {
    const { result, isOpenRef } = setup(true, "/photos/test.png", "1-2");
    await vi.waitFor(() => expect(result.data.value).toEqual(makeMockMetadata()));

    isOpenRef.value = false;
    isOpenRef.value = true;
    await Promise.resolve();
    expect(fetchMetadata).toHaveBeenCalledTimes(1);
    expect(result.data.value).toEqual(makeMockMetadata());
  });

  it("shares the entry with a PhotoSwipe-style fetch of the same version", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    await queryClient.fetchQuery({
      queryKey: queryKeys.metadata("/photos/test.png", "1-2"),
      queryFn: () => fetchMetadata("/photos/test.png"),
      staleTime: 10 * 60_000,
    });
    expect(fetchMetadata).toHaveBeenCalledTimes(1);

    const { result } = setup(true, "/photos/test.png", "1-2", queryClient);
    await vi.waitFor(() => expect(result.data.value).toEqual(makeMockMetadata()));
    expect(fetchMetadata).toHaveBeenCalledTimes(1);
  });

  it("does not reuse a PhotoSwipe-style entry stored under a different version", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    await queryClient.fetchQuery({
      queryKey: queryKeys.metadata("/photos/test.png", "1-2"),
      queryFn: () => fetchMetadata("/photos/test.png"),
      staleTime: 10 * 60_000,
    });

    const { result } = setup(true, "/photos/test.png", "9-9", queryClient);
    await vi.waitFor(() => expect(fetchMetadata).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(result.data.value).toEqual(makeMockMetadata()));
  });
});
