import { defineStore } from "pinia";
import type { FileNode } from "../types";
import { getPreviewUrl, getThumbnailUrl } from "../services/api";
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

      this.preloadNeighbors();
    },

    rememberDimensions(path: string, dimensions: LightboxDimensions) {
      if (!path || dimensions.width <= 0 || dimensions.height <= 0) return;

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
        this.currentIndex++;
        const nextItem = this.galleryItems[this.currentIndex];
        this.itemPath = nextItem.path;
        this.itemName = nextItem.name;
        this.preloadNeighbors();
      }
    },

    prev() {
      if (this.currentIndex > 0) {
        this.currentIndex--;
        const prevItem = this.galleryItems[this.currentIndex];
        this.itemPath = prevItem.path;
        this.itemName = prevItem.name;
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
      this.isOpen = false;
      this.itemPath = "";
      this.itemName = "";
      this.galleryItems = [];
      this.currentIndex = -1;
    },
  },
});
