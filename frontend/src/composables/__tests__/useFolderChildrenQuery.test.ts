import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { listFolderChildren } from "@/services/api";
import { useFolderChildrenQuery } from "../useFolderChildrenQuery";
import type { FolderTreeNode } from "@/types";

vi.mock("@/services/api", () => ({
  listFolderChildren: vi.fn(),
}));

const mockFolders: FolderTreeNode[] = [
  { name: "subfolder1", path: "/photos/subfolder1", type: "folder" },
  { name: "subfolder2", path: "/photos/subfolder2", type: "folder" },
];

function setup(path: string, enabled: boolean) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const pathRef = ref(path);
  const enabledRef = ref(enabled);
  let result!: ReturnType<typeof useFolderChildrenQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useFolderChildrenQuery(pathRef, enabledRef);
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, queryClient, wrapper, pathRef, enabledRef };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listFolderChildren).mockResolvedValue(mockFolders);
});

describe("useFolderChildrenQuery", () => {
  it("fetches folder children when path and enabled are provided", async () => {
    const { result } = setup("/photos", true);
    await vi.waitFor(() => expect(result.isFetched.value).toBe(true));
    expect(listFolderChildren).toHaveBeenCalledWith("/photos");
  });

  it("returns filtered folders", async () => {
    const mixed: FolderTreeNode[] = [
      { name: "folder1", path: "/photos/folder1", type: "folder" },
      { name: "file1", path: "/photos/file1.png", type: "image" as any, has_children: false },
      { name: "folder2", path: "/photos/folder2", type: "folder" },
    ];
    vi.mocked(listFolderChildren).mockResolvedValue(mixed);
    const { result } = setup("/photos", true);
    await vi.waitFor(() => expect(result.isFetched.value).toBe(true));
    expect(result.folders.value).toHaveLength(2);
    expect(result.folders.value.every((f) => f.type === "folder")).toBe(true);
  });

  it("does not fetch when path is empty", () => {
    setup("", true);
    expect(listFolderChildren).not.toHaveBeenCalled();
  });

  it("does not fetch when enabled is false", () => {
    setup("/photos", false);
    expect(listFolderChildren).not.toHaveBeenCalled();
  });

  it("has isPending true while loading", () => {
    vi.mocked(listFolderChildren).mockReturnValue(new Promise(() => {}));
    const { result } = setup("/photos", true);
    expect(result.isLoading.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(listFolderChildren).mockRejectedValue(new Error("network error"));
    const { result } = setup("/photos", true);
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.error.value).toBeTruthy();
  });

  it("refetches when path changes", async () => {
    const { result, pathRef } = setup("/photos", true);
    await vi.waitFor(() => expect(result.isFetched.value).toBe(true));
    expect(listFolderChildren).toHaveBeenCalledWith("/photos");

    vi.mocked(listFolderChildren).mockResolvedValue([{ name: "new", path: "/other/new", type: "folder" }]);
    pathRef.value = "/other";
    await vi.waitFor(() => expect(listFolderChildren).toHaveBeenCalledWith("/other"));
  });
});
