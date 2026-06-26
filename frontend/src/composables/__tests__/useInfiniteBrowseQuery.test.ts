import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { browseDirectory } from "@/services/api";
import { useInfiniteBrowseQuery } from "../useInfiniteBrowseQuery";
import type { BrowseResponse } from "@/types";
import { IMAGE_PAGE_SIZE } from "@/constants";

vi.mock("@/services/api", () => ({
  browseDirectory: vi.fn(),
}));

const mockBrowseResponse: BrowseResponse = {
  folders: [{ name: "sub", path: "/photos/sub", type: "folder", has_children: false, cover_images: [], mtime: 1000 }],
  media: [
    { name: "img1.png", path: "/photos/img1.png", type: "image", mtime: 1000 },
    { name: "img2.png", path: "/photos/img2.png", type: "image", mtime: 1000 },
  ],
  next_cursor: null,
  next_media_cursor: null,
  total_images: 2,
  total_videos: 0,
  total_assets: 2,
  index_source: "catalog",
};

function setup(libraryId: number | null | undefined, path: string | null | undefined, includeOffline = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const libraryIdRef = ref(libraryId);
  const pathRef = ref(path);
  const includeOfflineRef = ref(includeOffline);
  let result!: ReturnType<typeof useInfiniteBrowseQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useInfiniteBrowseQuery(libraryIdRef, pathRef, includeOfflineRef);
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, queryClient, wrapper, libraryIdRef, pathRef };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(browseDirectory).mockResolvedValue(mockBrowseResponse);
});

describe("useInfiniteBrowseQuery", () => {
  it("fetches browse data when library id is provided", async () => {
    const { result } = setup(1, "/photos");
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(browseDirectory).toHaveBeenCalledWith(1, "/photos", {
      limit: IMAGE_PAGE_SIZE,
      cursor: 0,
      includeOffline: false,
    });
  });

  it("does not fetch when library id is null", () => {
    setup(null, "/photos");
    expect(browseDirectory).not.toHaveBeenCalled();
  });

  it("returns folders and media from response", async () => {
    const { result } = setup(1, "/photos");
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(result.folders.value).toHaveLength(1);
    expect(result.media.value).toHaveLength(2);
    expect(result.totalImages.value).toBe(2);
    expect(result.totalVideos.value).toBe(0);
    expect(result.totalAssets.value).toBe(2);
  });

  it("returns data with pages from the response", async () => {
    const { result } = setup(1, "/photos");
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(result.data.value?.pages).toHaveLength(1);
    expect(result.data.value?.pages[0].total_images).toBe(2);
  });

  it("has isPending true while loading", () => {
    vi.mocked(browseDirectory).mockReturnValue(new Promise(() => {}));
    const { result } = setup(1, "/photos");
    expect(result.isPending.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(browseDirectory).mockRejectedValue(new Error("network error"));
    const { result } = setup(1, "/photos");
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.error.value).toBeTruthy();
  });

  it("includes offline parameter when requested", async () => {
    const { result } = setup(1, "/photos", true);
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(browseDirectory).toHaveBeenCalledWith(1, "/photos", {
      limit: IMAGE_PAGE_SIZE,
      cursor: 0,
      includeOffline: true,
    });
  });

  it("returns nextMediaCursor from last page", async () => {
    const withCursor: BrowseResponse = { ...mockBrowseResponse, next_media_cursor: "cursor_abc" };
    vi.mocked(browseDirectory).mockResolvedValue(withCursor);
    const { result } = setup(1, "/photos");
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(result.nextMediaCursor.value).toBe("cursor_abc");
  });

  it("returns null nextMediaCursor when no cursor", async () => {
    const { result } = setup(1, "/photos");
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(result.nextMediaCursor.value).toBeNull();
  });
});
