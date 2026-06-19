import { defineStore } from "pinia";
import type { FileNode } from "../types";
import { fetchMetadata, getPreviewUrl, getThumbnailUrl } from "../services/api";
import { lightboxItemAt, logLightboxNavDebug, summarizeLightboxItems } from "../debug/lightboxNavDebug";
import {
  hasValidDimensions,
  LIGHTBOX_PREVIEW_EDGE,
  LIGHTBOX_THUMBNAIL_EDGE,
  type LightboxDimensions,
} from "../utils/lightbox";

type PreloadedImage = { width: number; height: number };
type NeighborPreload = { controller: AbortController };

const neighborPreloadsByState = new WeakMap<object, Map<string, NeighborPreload>>();

const getActiveNeighborPreloads = (state: object): Map<string, NeighborPreload> => {
  const existing = neighborPreloadsByState.get(state);
  if (existing) return existing;
  const created = new Map<string, NeighborPreload>();
  neighborPreloadsByState.set(state, created);
  return created;
};

const abortError = () => new DOMException("Neighbor preload cancelled", "AbortError");

const preloadImage = (src: string, signal: AbortSignal): Promise<PreloadedImage> =>
  new Promise((resolve, reject) => {
    if (typeof Image === "undefined") {
      reject(new Error("Image API unavailable"));
      return;
    }

    const image = new Image();
    const cleanup = () => signal.removeEventListener("abort", handleAbort);
    const handleAbort = () => {
      image.onload = null;
      image.onerror = null;
      image.src = "";
      cleanup();
      reject(abortError());
    };
    image.onload = () => {
      cleanup();
      resolve({ width: image.naturalWidth, height: image.naturalHeight });
    };
    image.onerror = () => {
      cleanup();
      reject(new Error(`Image preload failed: ${src}`));
    };
    signal.addEventListener("abort", handleAbort, { once: true });
    if (signal.aborted) {
      handleAbort();
      return;
    }
    image.decoding = "async";
    image.src = src;
  });

export const useLightboxStore = defineStore("lightbox", {
  state: () => ({
    isOpen: false,
    itemPath: "",
    itemName: "",
    // Navigation state
    galleryItems: [] as FileNode[],
    currentIndex: -1,
    dimensionsByPath: {} as Record<string, LightboxDimensions>,
    neighborReadyByPath: {} as Record<string, boolean>,
  }),
  actions: {
    open(node: FileNode | { path: string; name?: string }, items: FileNode[] = [], preferredIndex?: number) {
      const path = "path" in node ? node.path : "";
      const name = "name" in node ? node.name || "" : "";
      const previous = {
        isOpen: this.isOpen,
        currentIndex: this.currentIndex,
        itemPath: this.itemPath,
        itemName: this.itemName,
        galleryItems: this.galleryItems.length,
      };

      this.itemPath = path;
      this.itemName = name;
      this.isOpen = true;

      // Setup navigation
      this.galleryItems = items.filter((i) => i.type === "image");
      const candidateIndex = typeof preferredIndex === "number" && preferredIndex >= 0 ? preferredIndex : -1;
      const preferredItem = candidateIndex >= 0 ? this.galleryItems[candidateIndex] : undefined;
      this.currentIndex =
        preferredItem?.path === path ? candidateIndex : this.galleryItems.findIndex((i) => i.path === path);

      logLightboxNavDebug("store-open", {
        requested: { path, name },
        preferredIndex,
        candidateIndex,
        resolvedIndex: this.currentIndex,
        resolvedItem: lightboxItemAt(this.galleryItems, this.currentIndex),
        previous,
        items: summarizeLightboxItems(this.galleryItems, this.currentIndex),
      });

      this.preloadNeighbors();
    },

    rememberDimensions(path: string, dimensions: LightboxDimensions) {
      if (!path || dimensions.width <= 0 || dimensions.height <= 0) return;
      if (dimensions.source === "thumbnail") return;

      this.dimensionsByPath[path] = dimensions;

      const item = this.galleryItems.find((galleryItem) => galleryItem.path === path);
      if (item) {
        item.width = dimensions.width;
        item.height = dimensions.height;
      }
    },

    getRememberedDimensions(path: string): LightboxDimensions | undefined {
      return this.dimensionsByPath[path];
    },

    next() {
      if (this.currentIndex < this.galleryItems.length - 1) {
        const beforeIndex = this.currentIndex;
        const beforeItem = lightboxItemAt(this.galleryItems, beforeIndex);
        this.currentIndex++;
        const nextItem = this.galleryItems[this.currentIndex];
        this.itemPath = nextItem.path;
        this.itemName = nextItem.name;
        logLightboxNavDebug("store-next", {
          beforeIndex,
          beforeItem,
          afterIndex: this.currentIndex,
          afterItem: lightboxItemAt(this.galleryItems, this.currentIndex),
        });
        this.preloadNeighbors();
      }
    },

    prev() {
      if (this.currentIndex > 0) {
        const beforeIndex = this.currentIndex;
        const beforeItem = lightboxItemAt(this.galleryItems, beforeIndex);
        this.currentIndex--;
        const prevItem = this.galleryItems[this.currentIndex];
        this.itemPath = prevItem.path;
        this.itemName = prevItem.name;
        logLightboxNavDebug("store-prev", {
          beforeIndex,
          beforeItem,
          afterIndex: this.currentIndex,
          afterItem: lightboxItemAt(this.galleryItems, this.currentIndex),
        });
        this.preloadNeighbors();
      }
    },

    preloadNeighbors() {
      const activeNeighborPreloads = getActiveNeighborPreloads(this.$state);
      const neighbors = [this.galleryItems[this.currentIndex - 1], this.galleryItems[this.currentIndex + 1]].filter(
        Boolean,
      ) as FileNode[];
      const neighborPaths = new Set(neighbors.map((item) => item.path));

      for (const [path, preload] of activeNeighborPreloads) {
        if (!neighborPaths.has(path)) {
          preload.controller.abort();
          activeNeighborPreloads.delete(path);
        }
      }

      for (const item of neighbors) {
        if (this.neighborReadyByPath[item.path] || activeNeighborPreloads.has(item.path)) continue;

        this.neighborReadyByPath[item.path] = false;
        const controller = new AbortController();
        const { signal } = controller;

        // Neighbor promotion stops at preview. Originals remain on-demand for zoom,
        // fullscreen, explicit preference, animated content, or preview failure.
        const thumbnailUrl = getThumbnailUrl(item.path, LIGHTBOX_THUMBNAIL_EDGE);
        const previewUrl = getPreviewUrl(item.path, LIGHTBOX_PREVIEW_EDGE);
        const thumbnailPromise = preloadImage(thumbnailUrl, signal);
        const previewPromise = thumbnailPromise
          .catch(() => {
            if (signal.aborted) throw abortError();
            return { width: 0, height: 0 };
          })
          .then(() => preloadImage(previewUrl, signal));
        const dimensionsPromise = hasValidDimensions(item)
          ? Promise.resolve({ width: item.width, height: item.height })
          : previewPromise;
        const metadataPromise = fetchMetadata(item.path, signal);

        void Promise.all([previewPromise, dimensionsPromise, metadataPromise])
          .then(([, previewDimensions, metadata]) => {
            if (signal.aborted || !neighborPaths.has(item.path)) return;
            const dimensions = hasValidDimensions(metadata) ? metadata : previewDimensions;
            if (hasValidDimensions(dimensions)) {
              this.rememberDimensions(item.path, {
                width: dimensions.width,
                height: dimensions.height,
                source: hasValidDimensions(metadata) ? "metadata" : "preview",
              });
            }
            this.neighborReadyByPath[item.path] = true;
          })
          .catch(() => {
            if (!signal.aborted) this.neighborReadyByPath[item.path] = false;
          })
          .finally(() => {
            if (activeNeighborPreloads.get(item.path)?.controller === controller) {
              activeNeighborPreloads.delete(item.path);
            }
          });

        activeNeighborPreloads.set(item.path, { controller });
      }
    },

    close() {
      if (!this.isOpen && this.currentIndex === -1 && !this.itemPath && this.galleryItems.length === 0) {
        return;
      }
      logLightboxNavDebug("store-close", {
        currentIndex: this.currentIndex,
        currentItem: lightboxItemAt(this.galleryItems, this.currentIndex),
        galleryItems: this.galleryItems.length,
      });
      this.isOpen = false;
      this.itemPath = "";
      this.itemName = "";
      this.galleryItems = [];
      this.currentIndex = -1;
      const activeNeighborPreloads = getActiveNeighborPreloads(this.$state);
      for (const preload of activeNeighborPreloads.values()) preload.controller.abort();
      activeNeighborPreloads.clear();
      this.neighborReadyByPath = {};
    },
  },
});
