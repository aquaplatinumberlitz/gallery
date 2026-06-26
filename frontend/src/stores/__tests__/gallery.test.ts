import { describe, it, expect, beforeEach, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { useGalleryStore, findImportPathForPath, resolveActiveImportPath } from "../gallery";
import type { RegisteredLibrary } from "../../types";

vi.mock("../../services/api", async () => {
  const actual = await vi.importActual("../../services/api");
  return {
    ...actual,
    openFolder: vi.fn().mockResolvedValue(undefined),
  };
});

const makeLib = (id: number, importPaths: Array<{ id: number; path: string; position: number }>): RegisteredLibrary =>
  ({
    id,
    name: `lib${id}`,
    import_paths: importPaths.map((p) => ({ ...p, library_id: id, created_at: 1, updated_at: 1 })),
    exclusion_patterns: [],
    root_path: importPaths[0]?.path ?? "",
    asset_count: 0,
    created_at: 1,
    updated_at: 1,
    last_scan_at: null,
    last_error: null,
    state: "ready",
    watch_enabled: 1,
    warm_enabled: 1,
  }) as unknown as RegisteredLibrary;

beforeEach(() => {
  setActivePinia(createPinia());
  vi.stubGlobal(
    "localStorage",
    (() => {
      const store: Record<string, string> = {};
      return {
        getItem: (k: string) => store[k] ?? null,
        setItem: (k: string, v: string) => {
          store[k] = v;
        },
        removeItem: (k: string) => {
          delete store[k];
        },
        clear: () => {
          Object.keys(store).forEach((k) => delete store[k]);
        },
        get length() {
          return Object.keys(store).length;
        },
        key: (i: number) => Object.keys(store)[i] ?? null,
      };
    })(),
  );
  localStorage.clear();
});

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

describe("initial state", () => {
  it("sets default values", () => {
    const store = useGalleryStore();
    expect(store.activeLibraryId).toBeNull();
    expect(store.searchQuery).toBe("");
    expect(store.searchScope).toBe("current");
    expect(store.sortField).toBe("name");
    expect(store.sortOrder).toBe("asc");
    expect(store.activeLibraryHydrated).toBe(false);
    expect(store.hasEverLoaded).toBe(false);
    expect(store.historyIndex).toBe(-1);
  });
});

// ---------------------------------------------------------------------------
// Search and sort actions
// ---------------------------------------------------------------------------

describe("search and sort", () => {
  it("setSearchQuery and clearSearch", () => {
    const store = useGalleryStore();
    store.setSearchQuery("cat");
    expect(store.searchQuery).toBe("cat");
    store.clearSearch();
    expect(store.searchQuery).toBe("");
  });

  it("setSearchScope", () => {
    const store = useGalleryStore();
    store.setSearchScope("all");
    expect(store.searchScope).toBe("all");
  });

  it("setSortField and setSortOrder", () => {
    const store = useGalleryStore();
    store.setSortField("date");
    expect(store.sortField).toBe("date");
    store.setSortOrder("desc");
    expect(store.sortOrder).toBe("desc");
  });

  it("toggleSortOrder flips asc↔desc", () => {
    const store = useGalleryStore();
    expect(store.sortOrder).toBe("asc");
    store.toggleSortOrder();
    expect(store.sortOrder).toBe("desc");
    store.toggleSortOrder();
    expect(store.sortOrder).toBe("asc");
  });
});

// ---------------------------------------------------------------------------
// Error state
// ---------------------------------------------------------------------------

describe("error state", () => {
  it("clearError clears errorMessage and errorType", () => {
    const store = useGalleryStore();
    store.errorMessage = "something broke";
    store.errorType = "server_error";
    store.clearError();
    expect(store.errorMessage).toBeNull();
    expect(store.errorType).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Folder expansion
// ---------------------------------------------------------------------------

describe("folder expansion", () => {
  it("isFolderExpanded defaults to false", () => {
    const store = useGalleryStore();
    expect(store.isFolderExpanded("/test")).toBe(false);
  });

  it("toggleFolderExpanded toggles", () => {
    const store = useGalleryStore();
    store.toggleFolderExpanded("/test");
    expect(store.isFolderExpanded("/test")).toBe(true);
    store.toggleFolderExpanded("/test");
    expect(store.isFolderExpanded("/test")).toBe(false);
  });

  it("setFolderExpanded sets state", () => {
    const store = useGalleryStore();
    store.setFolderExpanded("/test", true);
    expect(store.isFolderExpanded("/test")).toBe(true);
    store.setFolderExpanded("/test", false);
    expect(store.isFolderExpanded("/test")).toBe(false);
  });

  it("toggleFolder delegates with FileNode", () => {
    const store = useGalleryStore();
    store.toggleFolder({ path: "/f", type: "folder" } as any);
    expect(store.isFolderExpanded("/f")).toBe(true);
  });

  it("toggleFolderExpanded no-ops on empty path", () => {
    const store = useGalleryStore();
    store.toggleFolderExpanded("");
    expect(store.isFolderExpanded("")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Sidebar tree
// ---------------------------------------------------------------------------

describe("sidebar tree", () => {
  it("setSidebarTree normalizes nodes", () => {
    const store = useGalleryStore();
    store.setSidebarTree([
      { type: "folder", path: "/a", name: "A", children: [{ type: "folder", path: "/a/b", name: "B" }] },
    ] as any);
    expect(store.sidebarTree[0].children).toBeUndefined();
    expect(store.sidebarTree.length).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// Browse navigation
// ---------------------------------------------------------------------------

describe("browse navigation", () => {
  it("selectFolder with string", () => {
    const store = useGalleryStore();
    store.selectFolder("/path");
    expect(store.currentBrowsePath).toBe("/path");
    expect(store.hasEverLoaded).toBe(true);
    expect(store.history).toContain("/path");
  });

  it("selectFolder with FileNode", () => {
    const store = useGalleryStore();
    store.selectFolder({ path: "/node", name: "x", type: "folder" } as any);
    expect(store.currentBrowsePath).toBe("/node");
  });

  it("pushHistory skips duplicate at current index", () => {
    const store = useGalleryStore();
    store.pushHistory("/a");
    store.pushHistory("/a");
    expect(store.history.filter((p) => p === "/a").length).toBe(1);
  });

  it("pushHistory no-ops on empty path", () => {
    const store = useGalleryStore();
    store.pushHistory("");
    expect(store.history).toEqual([]);
  });

  it("goBack and goForward navigate", () => {
    const store = useGalleryStore();
    store.pushHistory("/a");
    store.pushHistory("/b");
    store.pushHistory("/c");
    expect(store.currentBrowsePath).toBe("");
    expect(store.historyIndex).toBe(2);
    store.goBack();
    expect(store.currentBrowsePath).toBe("/b");
    store.goBack();
    expect(store.currentBrowsePath).toBe("/a");
    store.goForward();
    expect(store.currentBrowsePath).toBe("/b");
  });

  it("goBack at boundary does nothing", () => {
    const store = useGalleryStore();
    store.goBack();
    expect(store.historyIndex).toBe(-1);
  });

  it("goForward at boundary does nothing", () => {
    const store = useGalleryStore();
    store.goForward();
    expect(store.historyIndex).toBe(-1);
  });
});

// ---------------------------------------------------------------------------
// resetBrowseState
// ---------------------------------------------------------------------------

describe("resetBrowseState", () => {
  it("resets to empty", () => {
    const store = useGalleryStore();
    store.selectFolder("/old");
    store.resetBrowseState();
    expect(store.currentBrowsePath).toBe("");
    expect(store.history).toEqual([]);
    expect(store.historyIndex).toBe(-1);
    expect(store.hasEverLoaded).toBe(false);
    expect(store.isLoading).toBe(false);
    expect(store.searchQuery).toBe("");
  });

  it("resets to a specific root", () => {
    const store = useGalleryStore();
    store.resetBrowseState("/root");
    expect(store.currentBrowsePath).toBe("/root");
    expect(store.history).toEqual(["/root"]);
    expect(store.historyIndex).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Library selection with localStorage
// ---------------------------------------------------------------------------

describe("hydrateActiveLibrary", () => {
  it("selects persisted library and import path", () => {
    const lib = makeLib(1, [{ id: 10, path: "/photos", position: 0 }]);
    localStorage.setItem("gallery-active-library-id", "1");
    localStorage.setItem("gallery-active-import-path-id", "10");

    const store = useGalleryStore();
    store.hydrateActiveLibrary([lib]);
    expect(store.activeLibraryId).toBe(1);
    expect(store.activeImportPathId).toBe(10);
    expect(store.activeLibraryHydrated).toBe(true);
    expect(store.currentBrowsePath).toBe(lib.import_paths[0].path);
  });

  it("falls back to legacy root path when no persisted library", () => {
    const lib = makeLib(1, [{ id: 10, path: "/photos", position: 0 }]);
    localStorage.setItem("gallery-root-path", "/photos/album");

    const store = useGalleryStore();
    store.hydrateActiveLibrary([lib]);
    expect(store.activeLibraryId).toBe(1);
    expect(store.activeImportPathId).toBe(10);
    expect(store.currentBrowsePath).toBe("/photos/album");
    expect(localStorage.getItem("gallery-root-path")).toBeNull();
  });

  it("auto-selects single library when nothing persisted", () => {
    const lib = makeLib(1, [{ id: 10, path: "/photos", position: 0 }]);
    const store = useGalleryStore();
    store.hydrateActiveLibrary([lib]);
    expect(store.activeLibraryId).toBe(1);
    expect(store.activeLibraryHydrated).toBe(true);
  });

  it("clears and sets hydrated when no libraries", () => {
    const store = useGalleryStore();
    store.hydrateActiveLibrary([]);
    expect(store.activeLibraryId).toBeNull();
    expect(store.activeLibraryHydrated).toBe(true);
  });

  it("ignores stale persisted id with no matching library", () => {
    localStorage.setItem("gallery-active-library-id", "999");
    const lib = makeLib(1, [{ id: 10, path: "/p", position: 0 }]);
    const store = useGalleryStore();
    store.hydrateActiveLibrary([lib]);
    expect(store.activeLibraryId).toBe(1);
  });

  it("removes invalid persisted ids", () => {
    localStorage.setItem("gallery-active-library-id", "abc");
    const store = useGalleryStore();
    store.hydrateActiveLibrary([]);
    expect(store.activeLibraryHydrated).toBe(true);
  });
});

describe("setActiveLibrary", () => {
  it("sets library and import path", () => {
    const lib = makeLib(1, [{ id: 10, path: "/p", position: 0 }]);
    const store = useGalleryStore();
    const ok = store.setActiveLibrary(lib);
    expect(ok).toBe(true);
    expect(store.activeLibraryId).toBe(1);
    expect(store.activeImportPathId).toBe(10);
  });

  it("returns false when import path not in library", () => {
    const lib = makeLib(1, [{ id: 10, path: "/p", position: 0 }]);
    const store = useGalleryStore();
    const ok = store.setActiveLibrary(lib, {
      id: 99,
      library_id: 1,
      path: "/x",
      position: 0,
      created_at: 1,
      updated_at: 1,
    });
    expect(ok).toBe(false);
  });
});

describe("setActiveImportPath", () => {
  const ip = (id: number, path: string, library_id = 1) => ({
    id,
    library_id,
    path,
    position: 0,
    created_at: 1,
    updated_at: 1,
  });

  it("returns false on mismatched library id", () => {
    const store = useGalleryStore();
    store.activeLibraryId = 1;
    const ok = store.setActiveImportPath(ip(10, "/a", 2), makeLib(2, [{ id: 10, path: "/a", position: 0 }]));
    expect(ok).toBe(false);
  });

  it("returns false on mismatched import path library_id", () => {
    const store = useGalleryStore();
    store.activeLibraryId = 1;
    const ok = store.setActiveImportPath(ip(10, "/a", 2), makeLib(1, [{ id: 10, path: "/a", position: 0 }]));
    expect(ok).toBe(false);
  });

  it("updates when valid", () => {
    const lib = makeLib(1, [
      { id: 10, path: "/p", position: 0 },
      { id: 11, path: "/q", position: 1 },
    ]);
    const store = useGalleryStore();
    store.setActiveLibrary(lib);
    const ok = store.setActiveImportPath(ip(11, "/q", 1), lib);
    expect(ok).toBe(true);
    expect(store.activeImportPathId).toBe(11);
  });
});

describe("clearActiveLibrary", () => {
  it("clears library and browse state", () => {
    const lib = makeLib(1, [{ id: 10, path: "/p", position: 0 }]);
    const store = useGalleryStore();
    store.setActiveLibrary(lib);
    store.selectFolder("/sub");
    store.clearActiveLibrary();
    expect(store.activeLibraryId).toBeNull();
    expect(store.activeImportPathId).toBeNull();
    expect(store.currentBrowsePath).toBe("");
  });
});

// ---------------------------------------------------------------------------
// applyActiveSelection
// ---------------------------------------------------------------------------

describe("applyActiveSelection", () => {
  it("sets library, import path, localStorage, and browse state", () => {
    const lib = makeLib(1, [{ id: 10, path: "/p", position: 0 }]);
    const store = useGalleryStore();
    store.applyActiveSelection(lib, lib.import_paths[0]);
    expect(store.activeLibraryId).toBe(1);
    expect(store.activeImportPathId).toBe(10);
    expect(localStorage.getItem("gallery-active-library-id")).toBe("1");
  });
});

// ---------------------------------------------------------------------------
// findImportPathForPath
// ---------------------------------------------------------------------------

describe("findImportPathForPath", () => {
  const libraries = [
    makeLib(1, [
      { id: 10, path: "/photos", position: 0 },
      { id: 11, path: "/photos/vacation", position: 1 },
    ]),
  ];

  it("finds exact match", () => {
    const result = findImportPathForPath(libraries, "/photos");
    expect(result?.importPath.path).toBe("/photos");
  });

  it("finds nested path", () => {
    const result = findImportPathForPath(libraries, "/photos/vacation/beach.jpg");
    expect(result?.importPath.path).toBe("/photos/vacation");
  });

  it("returns null for non-matching path", () => {
    expect(findImportPathForPath(libraries, "/other")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// resolveActiveImportPath
// ---------------------------------------------------------------------------

describe("resolveActiveImportPath", () => {
  const libraries = [
    makeLib(1, [
      { id: 10, path: "/a", position: 0 },
      { id: 11, path: "/b", position: 1 },
    ]),
  ];

  it("resolves by library and path ids", () => {
    const result = resolveActiveImportPath(libraries, 1, 10);
    expect(result?.path).toBe("/a");
  });

  it("returns null when library not found", () => {
    expect(resolveActiveImportPath(libraries, 999, 10)).toBeNull();
  });

  it("returns null when import path not found", () => {
    expect(resolveActiveImportPath(libraries, 1, 999)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// openInExplorer
// ---------------------------------------------------------------------------

describe("openInExplorer", () => {
  it("no-ops when no path set", async () => {
    const store = useGalleryStore();
    const before = store.errorMessage;
    await store.openInExplorer();
    expect(store.errorMessage).toBe(before);
  });

  it("calls openFolder and clears errors on success", async () => {
    const store = useGalleryStore();
    store.selectFolder("/test");
    await store.openInExplorer();
    expect(store.errorMessage).toBeNull();
  });
});
