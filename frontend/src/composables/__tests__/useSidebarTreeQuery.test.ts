import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { defineComponent, h, nextTick, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { IMAGE_PAGE_SIZE } from "@/constants";
import { browseDirectory } from "@/services/api";
import { useGalleryStore } from "@/stores/gallery";
import type { BrowseResponse } from "@/types";
import { useSidebarTreeQuery } from "../useSidebarTreeQuery";

vi.mock("@/services/api", () => ({
  browseDirectory: vi.fn(),
}));

const makeBrowseResponse = (overrides?: Partial<BrowseResponse>): BrowseResponse => ({
  folders: [
    {
      name: "Imports",
      path: "/photos/imports",
      type: "folder",
      children: [{ name: "nested", path: "/photos/imports/nested", type: "folder" }],
    },
  ],
  media: [],
  next_cursor: null,
  next_media_cursor: null,
  total_images: 0,
  total_videos: 0,
  total_assets: 0,
  request_path: "/photos",
  index_source: "catalog",
  library_id: 1,
  path: "/photos",
  ...overrides,
});

function setup(libraryId: number | null | undefined, path: string | null | undefined, seedSidebar = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const pinia = createPinia();
  setActivePinia(pinia);
  const store = useGalleryStore();
  if (seedSidebar) store.setSidebarTree([{ name: "stale", path: "/stale", type: "folder" }]);

  const libraryIdRef = ref(libraryId);
  const pathRef = ref(path);
  let result!: ReturnType<typeof useSidebarTreeQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useSidebarTreeQuery(libraryIdRef, pathRef);
        return () => h("div");
      },
    }),
    { global: { plugins: [pinia, [VueQueryPlugin, { queryClient }]] } },
  );

  return { result, wrapper, queryClient, libraryIdRef, pathRef, store };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(browseDirectory).mockResolvedValue(makeBrowseResponse());
});

describe("useSidebarTreeQuery", () => {
  it("loads the current browse folders into the gallery sidebar store", async () => {
    const { result, store } = setup(1, "/photos");

    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));

    expect(browseDirectory).toHaveBeenCalledWith(1, "/photos", { limit: IMAGE_PAGE_SIZE });
    expect(store.sidebarTree).toEqual([
      expect.objectContaining({
        name: "Imports",
        path: "/photos/imports",
        type: "folder",
        children: undefined,
      }),
    ]);
  });

  it("does not fetch and clears the sidebar when no active library is selected", async () => {
    const { store } = setup(null, "/photos", true);

    await nextTick();

    expect(browseDirectory).not.toHaveBeenCalled();
    expect(store.sidebarTree).toEqual([]);
    expect(store.isLoading).toBe(false);
  });

  it("tracks sidebar loading while the browse request is pending", () => {
    vi.mocked(browseDirectory).mockReturnValue(new Promise(() => {}));
    const { store } = setup(1, "/photos");

    expect(store.isLoading).toBe(true);
  });
});
