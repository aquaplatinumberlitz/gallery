import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchLibraries } from "@/services/api";
import { useGalleryStore } from "@/stores/gallery";
import { useActiveLibrarySelection } from "../useActiveLibrarySelection";
import { makeLibrary } from "@/test/factories";

vi.mock("@/services/api", () => ({
  fetchLibraries: vi.fn(),
}));

const mockLibraries = [
  makeLibrary({ id: 1, name: "Library 1", root_path: "/lib1", import_paths: [{ id: 10, library_id: 1, path: "/lib1/sub", position: 0, created_at: Date.now(), updated_at: Date.now() }] }),
  makeLibrary({ id: 2, name: "Library 2", root_path: "/lib2", import_paths: [{ id: 20, library_id: 2, path: "/lib2/sub", position: 0, created_at: Date.now(), updated_at: Date.now() }] }),
];

function setup(libraryId: number | null, importPathId: number | null) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const pinia = createPinia();
  setActivePinia(pinia);

  const gallery = useGalleryStore();
  gallery.activeLibraryId = libraryId;
  gallery.activeImportPathId = importPathId;

  let result!: ReturnType<typeof useActiveLibrarySelection>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useActiveLibrarySelection();
        return () => h("div");
      },
    }),
    { global: { plugins: [pinia, [VueQueryPlugin, { queryClient }]] } },
  );
  return { result, queryClient, wrapper, gallery };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchLibraries).mockResolvedValue(mockLibraries);
});

describe("useActiveLibrarySelection", () => {
  it("returns active library matching gallery store id", async () => {
    const { result } = setup(1, 10);
    await vi.waitFor(() => expect(result.libraries.value.length).toBeGreaterThan(0));
    expect(result.activeLibrary.value?.id).toBe(1);
    expect(result.activeLibrary.value?.name).toBe("Library 1");
  });

  it("returns null active library when id does not match", async () => {
    const { result } = setup(999, null);
    await vi.waitFor(() => expect(result.libraries.value.length).toBeGreaterThan(0));
    expect(result.activeLibrary.value).toBeNull();
  });

  it("returns null active library when no id is set", async () => {
    const { result } = setup(null, null);
    await vi.waitFor(() => expect(result.libraries.value.length).toBeGreaterThan(0));
    expect(result.activeLibrary.value).toBeNull();
  });

  it("returns active import path matching store ids", async () => {
    const { result } = setup(1, 10);
    await vi.waitFor(() => expect(result.libraries.value.length).toBeGreaterThan(0));
    expect(result.activeImportPath.value?.id).toBe(10);
    expect(result.activeImportPath.value?.path).toBe("/lib1/sub");
  });

  it("returns null import path when no match", async () => {
    const { result } = setup(1, 999);
    await vi.waitFor(() => expect(result.libraries.value.length).toBeGreaterThan(0));
    expect(result.activeImportPath.value).toBeNull();
  });

  it("returns active import root path", async () => {
    const { result } = setup(1, 10);
    await vi.waitFor(() => expect(result.libraries.value.length).toBeGreaterThan(0));
    expect(result.activeImportRootPath.value).toBe("/lib1/sub");
  });

  it("returns empty string root path when no import path", async () => {
    const { result } = setup(1, 999);
    await vi.waitFor(() => expect(result.libraries.value.length).toBeGreaterThan(0));
    expect(result.activeImportRootPath.value).toBe("");
  });

  it("exposes the underlying librariesQuery", () => {
    const { result } = setup(1, 10);
    expect(result.librariesQuery).toBeDefined();
    expect("data" in result.librariesQuery).toBe(true);
  });
});
