import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useGalleryStore } from "../gallery";
import { GalleryAPIError } from "@/services/api";
import type { FileNode, FolderTreeNode, ScanResponse } from "@/types";
const fetchScanOrThrowMock = vi.fn<(path: string) => Promise<ScanResponse>>();
const openFolderMock = vi.fn<(path: string) => Promise<void>>();

vi.mock("@/query/scan", () => ({
  fetchScanOrThrow: (...args: unknown[]) => fetchScanOrThrowMock(...(args as [string])),
}));

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return {
    ...actual,
    openFolder: (...args: unknown[]) => openFolderMock(...(args as [string])),
  };
});

function makeScanResponse(folders: FolderTreeNode[] = [], images: FileNode[] = []): ScanResponse {
  return {
    folders,
    images,
    next_cursor: null,
    total_images: images.length,
  };
}

function makeNode(overrides: Partial<FileNode> = {}): FileNode {
  return { name: "node", path: "/node", type: "image", ...overrides };
}

function makeFolderNode(overrides: Partial<FolderTreeNode> = {}): FolderTreeNode {
  return { name: "folder", path: "/folder", type: "folder", ...overrides };
}

describe("useGalleryStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    fetchScanOrThrowMock.mockReset();
    openFolderMock.mockReset();
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("initial state", () => {
    it("exposes empty defaults when localStorage is empty", () => {
      const store = useGalleryStore();
      expect(store.rootPath).toBe("");
      expect(store.sidebarTree).toEqual([]);
      expect(store.expandedFolderPaths).toEqual({});
      expect(store.currentPath).toBe("");
      expect(store.isLoading).toBe(false);
      expect(store.history).toEqual([]);
      expect(store.historyIndex).toBe(-1);
      expect(store.hasEverLoaded).toBe(false);
      expect(store.errorMessage).toBe("");
      expect(store.searchQuery).toBe("");
      expect(store.searchScope).toBe("current");
      expect(store.sortField).toBe("name");
      expect(store.sortOrder).toBe("asc");
      expect(store.metadataInspector).toEqual({
        query: "",
        scope: "current",
        sort: "date_desc",
        modelFilter: "all",
        promptFilter: "all",
        selectedPath: "",
        scrollTop: 0,
        scrollPath: "",
      });
    });

    it("reads the stored root path from localStorage", () => {
      window.localStorage.setItem("gallery-root-path", "/stored/root");
      const store = useGalleryStore();
      expect(store.rootPath).toBe("/stored/root");
    });

    it("reads the stored sort preference from localStorage", () => {
      window.localStorage.setItem("gallery-sort-preference", JSON.stringify({ field: "date", order: "desc" }));
      const store = useGalleryStore();
      expect(store.sortField).toBe("date");
      expect(store.sortOrder).toBe("desc");
    });

    it("falls back to name/asc when the stored sort preference is invalid JSON", () => {
      window.localStorage.setItem("gallery-sort-preference", "not-json");
      const store = useGalleryStore();
      expect(store.sortField).toBe("name");
      expect(store.sortOrder).toBe("asc");
    });

    it("falls back to name/asc when the stored sort preference is missing fields", () => {
      window.localStorage.setItem("gallery-sort-preference", JSON.stringify({ field: "date" }));
      const store = useGalleryStore();
      expect(store.sortField).toBe("name");
      expect(store.sortOrder).toBe("asc");
    });
  });

  describe("clearError", () => {
    it("clears the current error message", () => {
      const store = useGalleryStore();
      store.errorMessage = "boom";
      store.clearError();
      expect(store.errorMessage).toBeNull();
    });
  });

  describe("setSearchQuery / clearSearch", () => {
    it("updates the search query", () => {
      const store = useGalleryStore();
      store.setSearchQuery("kittens");
      expect(store.searchQuery).toBe("kittens");
    });

    it("clears the search query", () => {
      const store = useGalleryStore();
      store.setSearchQuery("kittens");
      store.clearSearch();
      expect(store.searchQuery).toBe("");
    });
  });

  describe("setSearchScope", () => {
    it("updates the search scope", () => {
      const store = useGalleryStore();
      store.setSearchScope("all");
      expect(store.searchScope).toBe("all");
    });
  });

  describe("setSortField / setSortOrder / toggleSortOrder", () => {
    it("setSortField updates the field and persists the preference", () => {
      const store = useGalleryStore();
      store.setSortField("date");
      expect(store.sortField).toBe("date");
      expect(window.localStorage.getItem("gallery-sort-preference")).toBe(
        JSON.stringify({ field: "date", order: "asc" }),
      );
    });

    it("setSortOrder updates the order and persists the preference", () => {
      const store = useGalleryStore();
      store.setSortOrder("desc");
      expect(store.sortOrder).toBe("desc");
      expect(window.localStorage.getItem("gallery-sort-preference")).toBe(
        JSON.stringify({ field: "name", order: "desc" }),
      );
    });

    it("toggleSortOrder flips asc <-> desc and persists", () => {
      const store = useGalleryStore();
      expect(store.sortOrder).toBe("asc");
      store.toggleSortOrder();
      expect(store.sortOrder).toBe("desc");
      expect(window.localStorage.getItem("gallery-sort-preference")).toBe(
        JSON.stringify({ field: "name", order: "desc" }),
      );
      store.toggleSortOrder();
      expect(store.sortOrder).toBe("asc");
      expect(window.localStorage.getItem("gallery-sort-preference")).toBe(
        JSON.stringify({ field: "name", order: "asc" }),
      );
    });
  });

  describe("isFolderExpanded / toggleFolderExpanded / setFolderExpanded / toggleFolder", () => {
    it("isFolderExpanded normalizes the path and returns false by default", () => {
      const store = useGalleryStore();
      expect(store.isFolderExpanded("/root/album/")).toBe(false);
    });

    it("toggleFolderExpanded flips the expansion state for a normalized path", () => {
      const store = useGalleryStore();
      store.toggleFolderExpanded("/root/album/");
      expect(store.isFolderExpanded("/root/album")).toBe(true);
      expect(store.isFolderExpanded("/root/album/")).toBe(true);
      store.toggleFolderExpanded("/root/album");
      expect(store.isFolderExpanded("/root/album")).toBe(false);
    });

    it("toggleFolderExpanded ignores empty paths", () => {
      const store = useGalleryStore();
      store.toggleFolderExpanded("");
      expect(store.expandedFolderPaths).toEqual({});
    });

    it("setFolderExpanded sets the explicit expansion state", () => {
      const store = useGalleryStore();
      store.setFolderExpanded("/root/album", true);
      expect(store.isFolderExpanded("/root/album")).toBe(true);
      store.setFolderExpanded("/root/album", false);
      expect(store.isFolderExpanded("/root/album")).toBe(false);
    });

    it("setFolderExpanded ignores empty paths", () => {
      const store = useGalleryStore();
      store.setFolderExpanded("", true);
      expect(store.expandedFolderPaths).toEqual({});
    });

    it("toggleFolder toggles expansion via a FileNode", () => {
      const store = useGalleryStore();
      const node = makeNode({ path: "/root/album", type: "folder" });
      store.toggleFolder(node);
      expect(store.isFolderExpanded("/root/album")).toBe(true);
      store.toggleFolder(node);
      expect(store.isFolderExpanded("/root/album")).toBe(false);
    });
  });

  describe("selectFolder", () => {
    it("sets currentPath, pushes history, and marks hasEverLoaded when given a string", () => {
      const store = useGalleryStore();
      store.selectFolder("/root/album");
      expect(store.currentPath).toBe("/root/album");
      expect(store.history).toEqual(["/root/album"]);
      expect(store.historyIndex).toBe(0);
      expect(store.hasEverLoaded).toBe(true);
    });

    it("accepts a FileNode and uses its path", () => {
      const store = useGalleryStore();
      store.selectFolder(makeNode({ path: "/root/album", type: "folder" }));
      expect(store.currentPath).toBe("/root/album");
      expect(store.history).toContain("/root/album");
    });
  });

  describe("pushHistory", () => {
    it("does nothing for an empty path", () => {
      const store = useGalleryStore();
      store.pushHistory("");
      expect(store.history).toEqual([]);
      expect(store.historyIndex).toBe(-1);
    });

    it("appends a new path and advances the index", () => {
      const store = useGalleryStore();
      store.pushHistory("/a");
      store.pushHistory("/b");
      expect(store.history).toEqual(["/a", "/b"]);
      expect(store.historyIndex).toBe(1);
    });

    it("skips duplicate entries at the current index", () => {
      const store = useGalleryStore();
      store.pushHistory("/a");
      store.pushHistory("/a");
      expect(store.history).toEqual(["/a"]);
      expect(store.historyIndex).toBe(0);
    });

    it("truncates forward history when pushing after going back", () => {
      const store = useGalleryStore();
      store.pushHistory("/a");
      store.pushHistory("/b");
      store.pushHistory("/c");
      store.goBack(); // index 1 (/b)
      store.goBack(); // index 0 (/a)
      store.pushHistory("/d");
      expect(store.history).toEqual(["/a", "/d"]);
      expect(store.historyIndex).toBe(1);
    });
  });

  describe("goBack / goForward", () => {
    it("goBack moves to the previous history entry and updates currentPath", () => {
      const store = useGalleryStore();
      store.pushHistory("/a");
      store.pushHistory("/b");
      store.goBack();
      expect(store.historyIndex).toBe(0);
      expect(store.currentPath).toBe("/a");
      expect(store.hasEverLoaded).toBe(true);
    });

    it("goBack does nothing at the start of history", () => {
      const store = useGalleryStore();
      store.pushHistory("/a");
      store.goBack();
      expect(store.historyIndex).toBe(0);
      expect(store.currentPath).toBe("");
    });

    it("goForward moves to the next history entry and updates currentPath", () => {
      const store = useGalleryStore();
      store.pushHistory("/a");
      store.pushHistory("/b");
      store.goBack();
      store.goForward();
      expect(store.historyIndex).toBe(1);
      expect(store.currentPath).toBe("/b");
    });

    it("goForward does nothing at the end of history", () => {
      const store = useGalleryStore();
      store.pushHistory("/a");
      store.goForward();
      expect(store.historyIndex).toBe(0);
    });
  });

  describe("resetRootPath", () => {
    it("clears root-related state and removes the localStorage key", () => {
      const store = useGalleryStore();
      store.rootPath = "/root";
      store.currentPath = "/root/album";
      store.sidebarTree = [makeFolderNode()];
      store.expandedFolderPaths = { "/root": true };
      store.hasEverLoaded = true;
      window.localStorage.setItem("gallery-root-path", "/root");

      store.resetRootPath();

      expect(store.rootPath).toBe("");
      expect(store.currentPath).toBe("");
      expect(store.sidebarTree).toEqual([]);
      expect(store.expandedFolderPaths).toEqual({});
      expect(store.hasEverLoaded).toBe(false);
      expect(window.localStorage.getItem("gallery-root-path")).toBeNull();
    });
  });

  describe("setRootPath", () => {
    it("returns false and resets root state when called with an empty path", async () => {
      const store = useGalleryStore();
      const result = await store.setRootPath("");
      expect(result).toBe(false);
      expect(store.rootPath).toBe("");
      expect(store.currentPath).toBe("");
      expect(fetchScanOrThrowMock).not.toHaveBeenCalled();
    });

    it("loads sidebar tree, persists root, and pushes history on success", async () => {
      const folders: FolderTreeNode[] = [{ name: "album", path: "/root/album", type: "folder", children: [] }];
      fetchScanOrThrowMock.mockResolvedValue(makeScanResponse(folders, [makeNode()]));
      const store = useGalleryStore();

      const result = await store.setRootPath("/root");

      expect(result).toBe(true);
      expect(store.rootPath).toBe("/root");
      expect(store.currentPath).toBe("/root");
      // children are stripped via normalizeNodes
      expect(store.sidebarTree).toEqual([{ name: "album", path: "/root/album", type: "folder", children: undefined }]);
      expect(store.isLoading).toBe(false);
      expect(store.hasEverLoaded).toBe(true);
      expect(store.history).toEqual(["/root"]);
      expect(window.localStorage.getItem("gallery-root-path")).toBe("/root");
      expect(store.errorMessage).toBeNull();
    });

    it("filters out non-folder entries from the sidebar tree", async () => {
      const folders: FolderTreeNode[] = [
        { name: "album", path: "/root/album", type: "folder" },
        { name: "photo.png", path: "/root/photo.png", type: "image" } as unknown as FolderTreeNode,
      ];
      fetchScanOrThrowMock.mockResolvedValue(makeScanResponse(folders, []));
      const store = useGalleryStore();

      await store.setRootPath("/root");

      expect(store.sidebarTree).toHaveLength(1);
      expect(store.sidebarTree[0].name).toBe("album");
    });

    it("sets errorMessage and shows an error toast when fetchScanOrThrow throws a GalleryAPIError", async () => {
      const apiError = new GalleryAPIError("not_found", "Folder not found", "It may have moved.", false);
      fetchScanOrThrowMock.mockRejectedValue(apiError);
      const store = useGalleryStore();

      const result = await store.setRootPath("/missing");

      expect(result).toBe(false);
      expect(store.isLoading).toBe(false);
      expect(store.rootPath).toBe("/missing");
      expect(store.currentPath).toBe("");
      expect(store.sidebarTree).toEqual([]);
      expect(store.errorMessage).toBe("It may have moved.");
    });

    it("sets errorMessage to the fallback message for non-API errors", async () => {
      fetchScanOrThrowMock.mockRejectedValue(new Error("network"));
      const store = useGalleryStore();

      const result = await store.setRootPath("/missing");

      expect(result).toBe(false);
      expect(store.errorMessage).toBe("Unable to load the root folder. Check the path or backend connection.");
    });

    it("clears the previous errorMessage on a successful retry", async () => {
      fetchScanOrThrowMock.mockRejectedValueOnce(new Error("network")).mockResolvedValueOnce(makeScanResponse());
      const store = useGalleryStore();

      await store.setRootPath("/root");
      expect(store.errorMessage).toBeTruthy();

      await store.setRootPath("/root");
      expect(store.errorMessage).toBeNull();
    });
  });

  describe("openInExplorer", () => {
    it("does nothing when currentPath is empty", async () => {
      const store = useGalleryStore();
      await store.openInExplorer();
      expect(openFolderMock).not.toHaveBeenCalled();
    });

    it("calls openFolder with the current path on success", async () => {
      openFolderMock.mockResolvedValue(undefined);
      const store = useGalleryStore();
      store.currentPath = "/root/album";

      await store.openInExplorer();

      expect(openFolderMock).toHaveBeenCalledWith("/root/album");
      expect(store.errorMessage).toBeNull();
    });

    it("sets errorMessage when openFolder throws a GalleryAPIError", async () => {
      openFolderMock.mockRejectedValue(
        new GalleryAPIError("permission", "Access denied", "Check folder permissions.", false),
      );
      const store = useGalleryStore();
      store.currentPath = "/root/album";

      await store.openInExplorer();

      expect(store.errorMessage).toBe("Check folder permissions.");
    });

    it("sets the fallback errorMessage for non-API errors", async () => {
      openFolderMock.mockRejectedValue(new Error("os"));
      const store = useGalleryStore();
      store.currentPath = "/root/album";

      await store.openInExplorer();

      expect(store.errorMessage).toBe("Unable to open the folder in your operating system.");
    });
  });
});
