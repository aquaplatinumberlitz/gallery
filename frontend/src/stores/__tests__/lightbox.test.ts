import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { nextTick, ref, toRaw } from "vue";
import { useLightboxStore } from "../lightbox";
import type { FileNode } from "@/types";

function makeImage(overrides: Partial<FileNode> = {}): FileNode {
  return { name: "img.png", path: "/album/img.png", type: "image", ...overrides };
}

function makeFolder(overrides: Partial<FileNode> = {}): FileNode {
  return { name: "folder", path: "/album/folder", type: "folder", ...overrides };
}

describe("useLightboxStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
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

    it("keeps query-owned items immutable while storing discovered dimensions separately", () => {
      const store = useLightboxStore();
      const source = Object.freeze(makeImage({ path: "/a.png", width: null, height: null }));

      store.open(source, [source]);
      store.rememberDimensions("/a.png", { width: 1024, height: 768, source: "metadata" });

      expect(toRaw(store.galleryItems[0])).toBe(source);
      expect(store.getRememberedDimensions("/a.png")).toEqual({ width: 1024, height: 768, source: "metadata" });
      expect(source.width).toBeNull();
      expect(source.height).toBeNull();
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

    it("does not mutate the matching gallery item", () => {
      const store = useLightboxStore();
      const items = [makeImage({ path: "/a.png", width: null, height: null })];
      store.open({ path: "/a.png", name: "a.png" }, items);

      store.rememberDimensions("/a.png", { width: 1024, height: 768, source: "metadata" });

      expect(store.galleryItems[0]!.width).toBeNull();
      expect(store.galleryItems[0]!.height).toBeNull();
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
  });

  describe("wrapping", () => {
    const three = () => ["/a.png", "/b.png", "/c.png"].map((path) => makeImage({ path, name: path.slice(1) }));

    it("wraps next and prev with more than two items and no pager", () => {
      const store = useLightboxStore();
      store.open({ path: "/c.png", name: "c.png" }, three());

      store.next();
      expect(store.itemPath).toBe("/a.png");
      store.prev();
      expect(store.itemPath).toBe("/c.png");
      expect(store.currentIndex).toBe(2);
    });

    it("does not wrap while the pager has more pages", () => {
      const store = useLightboxStore();
      const loadMore = vi.fn(() => new Promise<void>(() => undefined));
      store.open({ path: "/c.png", name: "c.png" }, three(), 2, { items: three, hasMore: () => true, loadMore });

      store.next();
      expect(store.currentIndex).toBe(2);
      store.open({ path: "/a.png", name: "a.png" }, three(), 0, { items: three, hasMore: () => true, loadMore });
      store.prev();
      expect(store.currentIndex).toBe(0);
    });
  });

  describe("pager", () => {
    const img = (n: number) => makeImage({ path: `/p/${n}.png`, name: `${n}.png` });
    const range = (from: number, to: number) => Array.from({ length: to - from }, (_, i) => img(from + i));

    function makePager(initial: FileNode[], pages: FileNode[][]) {
      const list = ref<FileNode[]>(initial);
      const remaining = ref(pages.length);
      const resolvers: Array<() => void> = [];
      const loadMore = vi.fn(
        () =>
          new Promise<void>((resolve, reject) => {
            resolvers.push(() => {
              const page = pages.shift();
              if (!page) return reject(new Error("failed"));
              list.value = [...list.value, ...page];
              remaining.value = pages.length;
              resolve();
            });
          }),
      );
      return {
        list,
        loadMore,
        resolvers,
        pager: { items: () => list.value, hasMore: () => remaining.value > 0, loadMore },
      };
    }

    it("does not ask for a page while the current item is far from the end", async () => {
      const store = useLightboxStore();
      const { pager, loadMore } = makePager(range(0, 20), [range(20, 40)]);

      store.open({ path: "/p/0.png", name: "0.png" }, range(0, 20), 0, pager);

      expect(loadMore).not.toHaveBeenCalled();
      expect(store.hasMoreItems).toBe(true);
    });

    it("asks once when the index comes within the threshold, not again while pending", async () => {
      const store = useLightboxStore();
      const { pager, loadMore } = makePager(range(0, 20), [range(20, 40)]);
      store.open({ path: "/p/0.png", name: "0.png" }, range(0, 20), 0, pager);

      store.currentIndex = 14;
      await nextTick();
      expect(loadMore).toHaveBeenCalledTimes(1);

      store.currentIndex = 17;
      store.next();
      await nextTick();
      expect(loadMore).toHaveBeenCalledTimes(1);
    });

    it("asks at open when the opening item is already near the end", () => {
      const store = useLightboxStore();
      const { pager, loadMore } = makePager(range(0, 20), [range(20, 40)]);

      store.open({ path: "/p/17.png", name: "17.png" }, range(0, 20), 17, pager);

      expect(loadMore).toHaveBeenCalledTimes(1);
    });

    it("appends only new images, keeping the shown prefix, index and item", async () => {
      const store = useLightboxStore();
      const first = range(0, 8);
      const { pager, resolvers, list } = makePager(first, [[img(7), makeFolder({ path: "/p/dir" }), ...range(8, 12)]]);
      store.open({ path: "/p/7.png", name: "7.png" }, first, 7, pager);
      const prefix = [...store.galleryItems];

      resolvers[0]();
      await vi.waitFor(() => expect(store.galleryItems).toHaveLength(12));

      expect(store.galleryItems.slice(0, 8).map((i) => i.path)).toEqual(prefix.map((i) => i.path));
      expect(store.galleryItems.map((i) => i.path)).toEqual(range(0, 12).map((i) => i.path));
      expect(store.currentIndex).toBe(7);
      expect(store.itemPath).toBe("/p/7.png");
      expect(list.value.length).toBeGreaterThan(12);
      expect(store.hasMoreItems).toBe(false);
    });

    it("does not reorder the shown items when the owner's list is reordered", async () => {
      const store = useLightboxStore();
      const { pager, list } = makePager(range(0, 8), [range(8, 10)]);
      store.open({ path: "/p/7.png", name: "7.png" }, range(0, 8), 7, pager);

      list.value = [...range(8, 10), ...range(0, 8).reverse()];
      await vi.waitFor(() => expect(store.galleryItems).toHaveLength(10));

      expect(store.galleryItems.slice(0, 8).map((i) => i.path)).toEqual(range(0, 8).map((i) => i.path));
      expect(store.currentIndex).toBe(7);
    });

    it("keeps the lightbox usable when a page fails, and retries when the end is reached again", async () => {
      const store = useLightboxStore();
      const rejections: unknown[] = [];
      const onRejection = (event: unknown) => rejections.push(event);
      process.on("unhandledRejection", onRejection);
      const { pager, resolvers, loadMore } = makePager(range(0, 8), []);
      const hasMore = vi.fn(() => true);
      store.open({ path: "/p/5.png", name: "5.png" }, range(0, 8), 5, { ...pager, hasMore });
      expect(loadMore).toHaveBeenCalledTimes(1);

      resolvers[0](); // no page left: rejects
      await new Promise((resolve) => setTimeout(resolve, 0));

      expect(store.isOpen).toBe(true);
      expect(store.galleryItems).toHaveLength(8);
      expect(store.currentIndex).toBe(5);

      store.next();
      store.next();
      store.next();
      store.next(); // at the end: retries
      await nextTick();
      expect(loadMore.mock.calls.length).toBeGreaterThanOrEqual(2);
      process.off("unhandledRejection", onRejection);
      expect(rejections).toEqual([]);
    });

    it("treats a loadMore that throws synchronously as a failed load", () => {
      const store = useLightboxStore();
      const loadMore = vi.fn(() => {
        throw new Error("boom");
      });

      expect(() =>
        store.open({ path: "/p/5.png", name: "5.png" }, range(0, 8), 5, {
          items: () => range(0, 8),
          hasMore: () => true,
          loadMore,
        }),
      ).not.toThrow();
      expect(store.isOpen).toBe(true);
    });

    it("clears the pager on close and on open without one", async () => {
      const store = useLightboxStore();
      const { pager, list, loadMore } = makePager(range(0, 8), [range(8, 12)]);
      store.open({ path: "/p/0.png", name: "0.png" }, range(0, 8), 0, pager);
      store.close();
      expect(store.hasMoreItems).toBe(false);

      store.open({ path: "/p/0.png", name: "0.png" }, range(0, 8), 0);
      list.value = [...list.value, ...range(8, 12)];
      await nextTick();
      store.currentIndex = 7;
      await nextTick();

      expect(store.galleryItems).toHaveLength(8);
      expect(store.hasMoreItems).toBe(false);
      expect(loadMore).not.toHaveBeenCalled();
    });

    it("keeps a page pending across the recheck: asks again only when still near the end", async () => {
      const store = useLightboxStore();
      // The first page holds only a duplicate: the end is still close, so the store asks for the next page.
      const { pager, resolvers, loadMore } = makePager(range(0, 8), [[img(7)], range(8, 30)]);
      store.open({ path: "/p/7.png", name: "7.png" }, range(0, 8), 7, pager);
      expect(loadMore).toHaveBeenCalledTimes(1);

      resolvers[0]();
      await vi.waitFor(() => expect(loadMore).toHaveBeenCalledTimes(2));
      resolvers[1]();
      await vi.waitFor(() => expect(store.galleryItems).toHaveLength(30));
      expect(loadMore).toHaveBeenCalledTimes(2);
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
});
