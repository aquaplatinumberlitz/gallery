import { describe, it, expect, beforeEach, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { useGalleryStore, findImportPathForPath, resolveActiveImportPath } from "../gallery";
import type { RegisteredLibrary } from "../../types";

const makeLib = (id: number, importPaths: Array<{ id: number; path: string; position: number }>): RegisteredLibrary =>
  ({
    id,
    name: `lib${id}`,
    import_paths: importPaths,
  }) as RegisteredLibrary;

describe("gallery store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("initializes with default state", () => {
    const store = useGalleryStore();
    expect(store.activeLibraryId).toBeNull();
    expect(store.searchQuery).toBe("");
    expect(store.searchScope).toBe("current");
    expect(store.sortField).toBe("name");
    expect(store.sortOrder).toBe("asc");
  });

  it("setSearchQuery updates search query", () => {
    const store = useGalleryStore();
    store.setSearchQuery("test");
    expect(store.searchQuery).toBe("test");
  });

  it("clearSearch resets search query", () => {
    const store = useGalleryStore();
    store.setSearchQuery("test");
    store.clearSearch();
    expect(store.searchQuery).toBe("");
  });

  it("setSearchScope updates scope", () => {
    const store = useGalleryStore();
    store.setSearchScope("all");
    expect(store.searchScope).toBe("all");
  });

  it("setSortField updates field", () => {
    const store = useGalleryStore();
    store.setSortField("date");
    expect(store.sortField).toBe("date");
  });

  it("setSortOrder updates order", () => {
    const store = useGalleryStore();
    store.setSortOrder("desc");
    expect(store.sortOrder).toBe("desc");
  });

  it("toggleSortOrder flips order", () => {
    const store = useGalleryStore();
    expect(store.sortOrder).toBe("asc");
    store.toggleSortOrder();
    expect(store.sortOrder).toBe("desc");
    store.toggleSortOrder();
    expect(store.sortOrder).toBe("asc");
  });

  it("clearError clears error state", () => {
    const store = useGalleryStore();
    store.errorMessage = "error";
    store.errorType = "server_error";
    store.clearError();
    expect(store.errorMessage).toBeNull();
    expect(store.errorType).toBeNull();
  });

  it("setSidebarTree normalizes nodes", () => {
    const store = useGalleryStore();
    store.setSidebarTree([
      { type: "folder", path: "/a", name: "A", children: [{ type: "folder", path: "/a/b", name: "B" }] },
    ]);
    expect(store.sidebarTree[0].children).toBeUndefined();
  });

  it("toggleFolderExpanded toggles expansion", () => {
    const store = useGalleryStore();
    expect(store.isFolderExpanded("/test")).toBe(false);
    store.toggleFolderExpanded("/test");
    expect(store.isFolderExpanded("/test")).toBe(true);
    store.toggleFolderExpanded("/test");
    expect(store.isFolderExpanded("/test")).toBe(false);
  });

  it("setFolderExpanded sets expansion state", () => {
    const store = useGalleryStore();
    store.setFolderExpanded("/test", true);
    expect(store.isFolderExpanded("/test")).toBe(true);
    store.setFolderExpanded("/test", false);
    expect(store.isFolderExpanded("/test")).toBe(false);
  });

  it("selectFolder updates browse path and history", () => {
    const store = useGalleryStore();
    store.selectFolder("/new/path");
    expect(store.currentBrowsePath).toBe("/new/path");
    expect(store.history).toContain("/new/path");
  });

  it("goBack and goForward navigate history", () => {
    const store = useGalleryStore();
    store.selectFolder("/first");
    store.selectFolder("/second");
    store.selectFolder("/third");
    expect(store.currentBrowsePath).toBe("/third");
    store.goBack();
    expect(store.currentBrowsePath).toBe("/second");
    store.goBack();
    expect(store.currentBrowsePath).toBe("/first");
    store.goForward();
    expect(store.currentBrowsePath).toBe("/second");
  });

  it("pushHistory does not add duplicates", () => {
    const store = useGalleryStore();
    store.pushHistory("/path");
    store.pushHistory("/path");
    expect(store.history.filter((p) => p === "/path").length).toBe(1);
  });

  it("resetBrowseState clears browse state", () => {
    const store = useGalleryStore();
    store.selectFolder("/test");
    store.resetBrowseState();
    expect(store.currentBrowsePath).toBe("");
    expect(store.history).toEqual([]);
    expect(store.historyIndex).toBe(-1);
  });

  it("clearActiveLibrary resets library and browse state", () => {
    const store = useGalleryStore();
    store.activeLibraryId = 1;
    store.activeImportPathId = 1;
    store.clearActiveLibrary();
    expect(store.activeLibraryId).toBeNull();
    expect(store.activeImportPathId).toBeNull();
  });

  it("setActiveLibrary returns false when import path invalid", () => {
    const store = useGalleryStore();
    const lib = makeLib(1, [{ id: 10, path: "/a", position: 0 }]);
    const result = store.setActiveLibrary(lib, { id: 99, library_id: 1, path: "/b", position: 0 });
    expect(result).toBe(false);
  });

  it("setActiveImportPath returns false for mismatched library", () => {
    const store = useGalleryStore();
    store.activeLibraryId = 1;
    const result = store.setActiveImportPath(
      { id: 10, library_id: 2, path: "/a", position: 0 },
      makeLib(1, [{ id: 10, path: "/a", position: 0 }]),
    );
    expect(result).toBe(false);
  });

  it("toggleFolder delegates to toggleFolderExpanded", () => {
    const store = useGalleryStore();
    store.toggleFolder({ path: "/test", type: "folder" } as any);
    expect(store.isFolderExpanded("/test")).toBe(true);
  });

  it("selectFolder accepts FileNode", () => {
    const store = useGalleryStore();
    store.selectFolder({ path: "/from-node", name: "test", type: "folder" } as any);
    expect(store.currentBrowsePath).toBe("/from-node");
  });

  it("openInExplorer no-ops when no path set", async () => {
    const store = useGalleryStore();
    store.currentBrowsePath = "";
    const before = store.errorMessage;
    await store.openInExplorer();
    expect(store.errorMessage).toBe(before);
  });
});

describe("resolveActiveImportPath", () => {
  const libraries = [
    makeLib(1, [
      { id: 10, path: "/photos", position: 0 },
      { id: 11, path: "/photos/vacation", position: 1 },
    ]),
  ];

  it("finds exact match", () => {
    const result = findImportPathForPath(libraries, "/photos");
    expect(result).not.toBeNull();
    expect(result!.importPath.path).toBe("/photos");
  });

  it("finds nested path", () => {
    const result = findImportPathForPath(libraries, "/photos/vacation/beach.jpg");
    expect(result).not.toBeNull();
    expect(result!.importPath.path).toBe("/photos/vacation");
  });

  it("returns null for non-matching path", () => {
    const result = findImportPathForPath(libraries, "/other");
    expect(result).toBeNull();
  });
});

describe("resolveActiveImportPath", () => {
  const libraries = [
    makeLib(1, [
      { id: 10, path: "/a", position: 0 },
      { id: 11, path: "/b", position: 1 },
    ]),
  ];

  it("resolves by library and path ids", () => {
    const result = resolveActiveImportPath(libraries, 1, 10);
    expect(result).not.toBeNull();
    expect(result!.path).toBe("/a");
  });

  it("returns null when library not found", () => {
    expect(resolveActiveImportPath(libraries, 999, 10)).toBeNull();
  });

  it("returns null when import path not found", () => {
    expect(resolveActiveImportPath(libraries, 1, 999)).toBeNull();
  });
});
