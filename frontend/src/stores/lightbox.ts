import { defineStore } from "pinia";
import type { FileNode } from "../types";
import { getPreviewUrl, getThumbnailUrl } from "../services/api";
import { lightboxItemAt, logLightboxNavDebug, summarizeLightboxItems } from "../debug/lightboxNavDebug";
import {
  LIGHTBOX_PREVIEW_EDGE,
  LIGHTBOX_THUMBNAIL_EDGE,
  type LightboxDimensions,
} from "../utils/lightbox";

const preloadImage = (path: string) => {
  if (typeof Image === "undefined") return;
  [getThumbnailUrl(path, LIGHTBOX_THUMBNAIL_EDGE), getPreviewUrl(path, LIGHTBOX_PREVIEW_EDGE)].forEach((src) => {
    const img = new Image();
    img.src = src;
  });
};

export const useLightboxStore = defineStore("lightbox", {
  state: () => ({
    isOpen: false,
    itemPath: "",
    itemName: "",
    // Navigation state
    galleryItems: [] as FileNode[],
    currentIndex: -1,
    dimensionsByPath: {} as Record<string, LightboxDimensions>,
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
      this.galleryItems = items.filter(i => i.type === 'image');
      const candidateIndex = typeof preferredIndex === "number" && preferredIndex >= 0 ? preferredIndex : -1;
      const preferredItem = candidateIndex >= 0 ? this.galleryItems[candidateIndex] : undefined;
      this.currentIndex = preferredItem?.path === path
        ? candidateIndex
        : this.galleryItems.findIndex(i => i.path === path);

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
      const neighbors = [
        this.galleryItems[this.currentIndex - 1],
        this.galleryItems[this.currentIndex + 1],
      ].filter(Boolean) as FileNode[];

      neighbors.forEach((item) => preloadImage(item.path));
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
    },
  },
});
