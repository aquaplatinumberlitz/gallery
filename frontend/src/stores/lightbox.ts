import { defineStore } from "pinia";
import type { FileNode } from "../types";
import { getThumbnailUrl } from "../services/api";
import type { LightboxDimensions } from "../utils/lightbox";

const preloadImage = (path: string) => {
  if (typeof Image === "undefined") return;
  const img = new Image();
  img.src = getThumbnailUrl(path, 800);
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
    open(node: FileNode | { path: string; name?: string }, items: FileNode[] = []) {
      const path = "path" in node ? node.path : "";
      const name = "name" in node ? node.name || "" : "";
      
      this.itemPath = path;
      this.itemName = name;
      this.isOpen = true;
      
      // Setup navigation
      this.galleryItems = items.filter(i => i.type === 'image');
      this.currentIndex = this.galleryItems.findIndex(i => i.path === path);

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
