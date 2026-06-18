import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useLightboxStore } from "../lightbox";
import type { FileNode } from "@/types";

const getThumbnailUrlMock = vi.fn<(path: string, edge?: number) => string>();
const getPreviewUrlMock = vi.fn<(path: string, edge?: number) => string>();

vi.mock("@/services/api", () => ({
  GalleryAPIError: class GalleryAPIError extends Error {},
  getThumbnailUrl: (...args: unknown[]) => getThumbnailUrlMock(...(args as [string, number | undefined])),
  getPreviewUrl: (...args: unknown[]) => getPreviewUrlMock(...(args as [string, number | undefined])),
}));

function makeImage(overrides: Partial<FileNode> = {}): FileNode {
  return { name: "img.png", path: "/album/img.png", type: "image", ...overrides };
}

function makeFolder(overrides: Partial<FileNode> = {}): FileNode {
  return { name: "folder", path: "/album/folder", type: "folder", ...overrides };
}

describe("useLightboxStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    getThumbnailUrlMock.mockReset();
    getPreviewUrlMock.mockReset();
    getThumbnailUrlMock.mockImplementation((path) => `/thumb?path=${encodeURIComponent(path)}`);
    getPreviewUrlMock.mockImplementation((path) => `/preview?path=${encodeURIComponent(path)}`);
  });

  describe("initial state", () => {
    it("starts closed with no items", () => {
      const store = useLightboxStore();
      expect(store.isOpen).toBe(false);
      expect(store.itemPath).toBe("");
      expect(store.itemName).toBe("");
      expect(store.galleryItems).toEqual([]);
      expect(store.currentIndex).toBe(-1);
      expect(store.dimensionsByPath).toEqual({});
    });
  });

  describe("open", () => {
    it("opens with the given node and sets currentIndex based on the items list", () => {
      const store = useLightboxStore();
      const items = [makeImage({ path: "/a.png" }), makeImage({ path: "/b.png" }), makeImage({ path: "/c.png" })];

      store.open({ path: "/b.png", name: "b.png" }, items);

      expect(store.isOpen).toBe(true);
      expect(store.itemPath).toBe("/b.png");
      expect(store.itemName).toBe("b.png");
      expect(store.galleryItems).toHaveLength(3);
      expect(store.currentIndex).toBe(1);
    });

    it("filters out non-image items from the navigation list", () => {
      const store = useLightboxStore();
      const items = [
        makeImage({ path: "/a.png" }),
        makeFolder({ path: "/folder", type: "folder" }),
        makeImage({ path: "/b.png" }),
      ];

      store.open({ path: "/b.png", name: "b.png" }, items);

      expect(store.galleryItems).toHaveLength(2);
      expect(store.currentIndex).toBe(1);
    });

    it("uses preferredIndex when its item path matches the requested path", () => {
      const store = useLightboxStore();
      const items = [makeImage({ path: "/a.png" }), makeImage({ path: "/b.png" })];

      store.open({ path: "/b.png", name: "b.png" }, items, 1);

      expect(store.currentIndex).toBe(1);
    });

    it("falls back to findIndex when preferredIndex does not match the requested path", () => {
      const store = useLightboxStore();
      const items = [makeImage({ path: "/a.png" }), makeImage({ path: "/b.png" })];

      // preferredIndex=0 points to /a.png but the requested path is /b.png
      store.open({ path: "/b.png", name: "b.png" }, items, 0);

      expect(store.currentIndex).toBe(1);
    });

    it("sets currentIndex to -1 when the requested path is not in the items list", () => {
      const store = useLightboxStore();
      const items = [makeImage({ path: "/a.png" })];

      store.open({ path: "/missing.png", name: "missing.png" }, items);

      expect(store.currentIndex).toBe(-1);
    });

    it("accepts a FileNode and uses its path and name", () => {
      const store = useLightboxStore();
      const node = makeImage({ path: "/x.png", name: "x.png" });
      store.open(node, [node]);
      expect(store.itemPath).toBe("/x.png");
      expect(store.itemName).toBe("x.png");
    });

    it("handles nodes without a name field", () => {
      const store = useLightboxStore();
      const items = [makeImage({ path: "/a.png" })];
      store.open({ path: "/a.png" }, items);
      expect(store.itemName).toBe("");
    });

    it("preloads neighbor images on open", () => {
      const store = useLightboxStore();
      const items = [makeImage({ path: "/a.png" }), makeImage({ path: "/b.png" }), makeImage({ path: "/c.png" })];

      store.open({ path: "/b.png", name: "b.png" }, items);

      // neighbors of index 1 are /a.png and /c.png
      expect(getThumbnailUrlMock).toHaveBeenCalledWith("/a.png", expect.any(Number));
      expect(getThumbnailUrlMock).toHaveBeenCalledWith("/c.png", expect.any(Number));
      expect(getPreviewUrlMock).toHaveBeenCalledWith("/a.png", expect.any(Number));
      expect(getPreviewUrlMock).toHaveBeenCalledWith("/c.png", expect.any(Number));
    });
  });

  describe("rememberDimensions / getRememberedDimensions", () => {
    it("stores dimensions by path and returns them via getRememberedDimensions", () => {
      const store = useLightboxStore();
      store.rememberDimensions("/x.png", { width: 800, height: 600, source: "metadata" });
      expect(store.getRememberedDimensions("/x.png")).toEqual({ width: 800, height: 600, source: "metadata" });
    });

    it("returns undefined for an unknown path", () => {
      const store = useLightboxStore();
      expect(store.getRememberedDimensions("/unknown.png")).toBeUndefined();
    });

    it("ignores empty paths", () => {
      const store = useLightboxStore();
      store.rememberDimensions("", { width: 800, height: 600, source: "metadata" });
      expect(store.dimensionsByPath).toEqual({});
    });

    it("ignores invalid dimensions (zero or negative width/height)", () => {
      const store = useLightboxStore();
      store.rememberDimensions("/a.png", { width: 0, height: 600, source: "metadata" });
      store.rememberDimensions("/b.png", { width: 800, height: -1, source: "metadata" });
      expect(store.dimensionsByPath).toEqual({});
    });

    it("ignores thumbnail-source dimensions (already lower quality)", () => {
      const store = useLightboxStore();
      store.rememberDimensions("/a.png", { width: 100, height: 100, source: "thumbnail" });
      expect(store.dimensionsByPath).toEqual({});
    });

    it("updates the matching galleryItem's width and height", () => {
      const store = useLightboxStore();
      const items = [makeImage({ path: "/a.png", width: null, height: null })];
      store.open({ path: "/a.png", name: "a.png" }, items);

      store.rememberDimensions("/a.png", { width: 1024, height: 768, source: "metadata" });

      expect(store.galleryItems[0]!.width).toBe(1024);
      expect(store.galleryItems[0]!.height).toBe(768);
    });
  });

  describe("next / prev", () => {
    it("next advances the index and updates itemPath/itemName", () => {
      const store = useLightboxStore();
      const items = [makeImage({ path: "/a.png", name: "a.png" }), makeImage({ path: "/b.png", name: "b.png" })];
      store.open({ path: "/a.png", name: "a.png" }, items);

      store.next();

      expect(store.currentIndex).toBe(1);
      expect(store.itemPath).toBe("/b.png");
      expect(store.itemName).toBe("b.png");
    });

    it("next does nothing at the end of the list", () => {
      const store = useLightboxStore();
      const items = [makeImage({ path: "/a.png", name: "a.png" })];
      store.open({ path: "/a.png", name: "a.png" }, items);

      store.next();

      expect(store.currentIndex).toBe(0);
    });

    it("prev moves to the previous index and updates itemPath/itemName", () => {
      const store = useLightboxStore();
      const items = [makeImage({ path: "/a.png", name: "a.png" }), makeImage({ path: "/b.png", name: "b.png" })];
      store.open({ path: "/b.png", name: "b.png" }, items);

      store.prev();

      expect(store.currentIndex).toBe(0);
      expect(store.itemPath).toBe("/a.png");
      expect(store.itemName).toBe("a.png");
    });

    it("prev does nothing at the start of the list", () => {
      const store = useLightboxStore();
      const items = [makeImage({ path: "/a.png", name: "a.png" }), makeImage({ path: "/b.png", name: "b.png" })];
      store.open({ path: "/a.png", name: "a.png" }, items);

      store.prev();

      expect(store.currentIndex).toBe(0);
    });

    it("next preloads the new neighbor", () => {
      const store = useLightboxStore();
      const items = [
        makeImage({ path: "/a.png", name: "a.png" }),
        makeImage({ path: "/b.png", name: "b.png" }),
        makeImage({ path: "/c.png", name: "c.png" }),
      ];
      store.open({ path: "/a.png", name: "a.png" }, items);

      getThumbnailUrlMock.mockClear();
      getPreviewUrlMock.mockClear();

      store.next(); // now at index 1, neighbors are /a.png and /c.png

      expect(getThumbnailUrlMock).toHaveBeenCalledWith("/a.png", expect.any(Number));
      expect(getThumbnailUrlMock).toHaveBeenCalledWith("/c.png", expect.any(Number));
    });
  });

  describe("close", () => {
    it("resets open state, item info, items list, and index", () => {
      const store = useLightboxStore();
      const items = [makeImage({ path: "/a.png", name: "a.png" })];
      store.open({ path: "/a.png", name: "a.png" }, items);

      store.close();

      expect(store.isOpen).toBe(false);
      expect(store.itemPath).toBe("");
      expect(store.itemName).toBe("");
      expect(store.galleryItems).toEqual([]);
      expect(store.currentIndex).toBe(-1);
    });

    it("is a no-op when already closed and empty", () => {
      const store = useLightboxStore();
      // Should not throw when called on the initial state.
      store.close();
      expect(store.isOpen).toBe(false);
    });
  });

  describe("preloadNeighbors", () => {
    it("does not preload anything when there are no neighbors", () => {
      const store = useLightboxStore();
      const items = [makeImage({ path: "/a.png", name: "a.png" })];
      store.open({ path: "/a.png", name: "a.png" }, items);

      getThumbnailUrlMock.mockClear();
      getPreviewUrlMock.mockClear();

      store.preloadNeighbors();

      expect(getThumbnailUrlMock).not.toHaveBeenCalled();
      expect(getPreviewUrlMock).not.toHaveBeenCalled();
    });
  });
});
