import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import {
  ACTIVE_IMPORT_PATH_STORAGE_KEY,
  ACTIVE_LIBRARY_STORAGE_KEY,
  LEGACY_ROOT_PATH_STORAGE_KEY,
  findImportPathForPath,
  useGalleryStore,
} from "../gallery";
import type { FileNode, RegisteredLibrary } from "@/types";

const openFolderMock = vi.fn<(path: string) => Promise<void>>();
vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return { ...actual, openFolder: (...args: unknown[]) => openFolderMock(...(args as [string])) };
});

function library(id: number, paths: string[]): RegisteredLibrary {
  return {
    id,
    name: `Library ${id}`,
    root_path: paths[0] ?? "",
    state: "ready",
    watch_enabled: 1,
    warm_enabled: 1,
    asset_count: 0,
    created_at: 1,
    updated_at: 1,
    last_scan_at: null,
    last_error: null,
    exclusion_patterns: [],
    import_paths: paths.map((path, position) => ({
      id: id * 10 + position,
      library_id: id,
      path,
      position,
      created_at: 1,
      updated_at: 1,
    })),
  };
}

describe("useGalleryStore active library selection", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    openFolderMock.mockReset();
  });

  it("starts without a writable raw root path", () => {
    const store = useGalleryStore();
    expect(store.activeLibraryId).toBeNull();
    expect(store.activeImportPathId).toBeNull();
    expect(store.currentBrowsePath).toBe("");
    expect("rootPath" in store).toBe(false);
    expect("setRootPath" in store).toBe(false);
  });

  it("hydrates valid persisted IDs and removes a leftover legacy key", () => {
    const first = library(1, ["/photos/a", "/photos/b"]);
    localStorage.setItem(ACTIVE_LIBRARY_STORAGE_KEY, "1");
    localStorage.setItem(ACTIVE_IMPORT_PATH_STORAGE_KEY, "11");
    localStorage.setItem(LEGACY_ROOT_PATH_STORAGE_KEY, "/stale");
    const store = useGalleryStore();

    store.hydrateActiveLibrary([first]);

    expect(store.activeLibraryId).toBe(1);
    expect(store.activeImportPathId).toBe(11);
    expect(store.currentBrowsePath).toBe("/photos/b");
    expect(localStorage.getItem(LEGACY_ROOT_PATH_STORAGE_KEY)).toBeNull();
  });

  it("rejects malformed persisted IDs and migrates the most specific legacy subfolder", () => {
    const outer = library(2, ["/photos"]);
    const inner = library(1, ["/photos/events"]);
    localStorage.setItem(ACTIVE_LIBRARY_STORAGE_KEY, "1x");
    localStorage.setItem(ACTIVE_IMPORT_PATH_STORAGE_KEY, "-1");
    localStorage.setItem(LEGACY_ROOT_PATH_STORAGE_KEY, "/photos/events/wedding");
    const store = useGalleryStore();

    store.hydrateActiveLibrary([outer, inner]);

    expect(store.activeLibraryId).toBe(1);
    expect(store.activeImportPathId).toBe(10);
    expect(store.currentBrowsePath).toBe("/photos/events/wedding");
    expect(localStorage.getItem(ACTIVE_LIBRARY_STORAGE_KEY)).toBe("1");
    expect(localStorage.getItem(LEGACY_ROOT_PATH_STORAGE_KEY)).toBeNull();
  });

  it("removes an unusable legacy key and auto-selects the only eligible library", () => {
    localStorage.setItem(LEGACY_ROOT_PATH_STORAGE_KEY, "/missing");
    const only = library(4, ["/only"]);
    const store = useGalleryStore();
    store.hydrateActiveLibrary([only]);
    expect(store.activeLibraryId).toBe(4);
    expect(store.currentBrowsePath).toBe("/only");
    expect(localStorage.getItem(LEGACY_ROOT_PATH_STORAGE_KEY)).toBeNull();
  });

  it("leaves selection empty when several libraries exist without a migration match", () => {
    const store = useGalleryStore();
    store.hydrateActiveLibrary([library(1, ["/one"]), library(2, ["/two"])]);
    expect(store.activeLibraryId).toBeNull();
    expect(store.activeLibraryHydrated).toBe(true);
  });

  it("selection resets browse history, expansion, and search and persists only IDs", () => {
    const selected = library(3, ["/three", "/three/other"]);
    const store = useGalleryStore();
    store.searchQuery = "cats";
    store.expandedFolderPaths = { "/old": true };
    store.history = ["/old"];
    store.historyIndex = 0;

    expect(store.setActiveLibrary(selected, selected.import_paths[1])).toBe(true);
    expect(store.currentBrowsePath).toBe("/three/other");
    expect(store.history).toEqual(["/three/other"]);
    expect(store.expandedFolderPaths).toEqual({});
    expect(store.searchQuery).toBe("");
    expect(localStorage.getItem(ACTIVE_LIBRARY_STORAGE_KEY)).toBe("3");
    expect(localStorage.getItem(ACTIVE_IMPORT_PATH_STORAGE_KEY)).toBe("31");
    expect(localStorage.getItem(LEGACY_ROOT_PATH_STORAGE_KEY)).toBeNull();
  });

  it("clears active selection without writing a raw path", () => {
    const store = useGalleryStore();
    store.setActiveLibrary(library(1, ["/one"]));
    store.clearActiveLibrary();
    expect(store.activeLibraryId).toBeNull();
    expect(store.currentBrowsePath).toBe("");
    expect(localStorage.getItem(ACTIVE_LIBRARY_STORAGE_KEY)).toBeNull();
    expect(localStorage.getItem(ACTIVE_IMPORT_PATH_STORAGE_KEY)).toBeNull();
  });

  it("keeps browse navigation and explorer actions path-based", async () => {
    const store = useGalleryStore();
    store.setActiveLibrary(library(1, ["/one"]));
    store.selectFolder({ name: "album", path: "/one/album", type: "folder" } as FileNode);
    store.goBack();
    expect(store.currentBrowsePath).toBe("/one");
    store.goForward();
    expect(store.currentBrowsePath).toBe("/one/album");
    openFolderMock.mockResolvedValue();
    await store.openInExplorer();
    expect(openFolderMock).toHaveBeenCalledWith("/one/album");
  });

  it("uses deterministic tie-breaking for legacy path matches", () => {
    const match = findImportPathForPath([library(2, ["/same"]), library(1, ["/same"])], "/same/child");
    expect(match?.library.id).toBe(1);
  });
});
