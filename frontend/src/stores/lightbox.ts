import { defineStore } from "pinia";
import type { FileNode, MetadataResponse } from "../types";
import { fetchMetadata, getThumbnailUrl } from "../services/api";

const preloadImage = (path: string) => {
  if (typeof Image === "undefined") return;
  const img = new Image();
  img.src = getThumbnailUrl(path, 800);
};

export const useLightboxStore = defineStore("lightbox", {
  state: () => ({
    isOpen: false,
    isLoading: false,
    itemPath: "",
    itemName: "",
    width: null as number | null,
    height: null as number | null,
    metadata: null as MetadataResponse | null,
    metadataRequestId: 0,
    // Navigation state
    galleryItems: [] as FileNode[],
    currentIndex: -1,
  }),
  actions: {
    async open(node: FileNode | { path: string; name?: string }, items: FileNode[] = []) {
      const path = "path" in node ? node.path : "";
      const name = "name" in node ? node.name || "" : "";
      
      this.itemPath = path;
      this.itemName = name;
      this.isOpen = true;
      this.isLoading = true;
      this.metadata = null;
      
      // Setup navigation
      this.galleryItems = items.filter(i => i.type === 'image');
      this.currentIndex = this.galleryItems.findIndex(i => i.path === path);

      this.preloadNeighbors();
      await this.loadMetadata(path);
    },

    async loadMetadata(path: string) {
      const requestId = ++this.metadataRequestId;
      this.isLoading = true;
      this.metadata = null;
      try {
        const data = await fetchMetadata(path);
        if (requestId !== this.metadataRequestId || path !== this.itemPath) return;
        this.metadata = data;
        this.width = data.width;
        this.height = data.height;
        this.itemName = data.name || this.itemName;
      } catch (error: unknown) {
        if (requestId !== this.metadataRequestId) return;
        console.error("Failed to load metadata", error);
        this.metadata = null;
      } finally {
        if (requestId === this.metadataRequestId) {
          this.isLoading = false;
        }
      }
    },

    async next() {
      if (this.currentIndex < this.galleryItems.length - 1) {
        this.currentIndex++;
        const nextItem = this.galleryItems[this.currentIndex];
        this.itemPath = nextItem.path;
        this.itemName = nextItem.name;
        this.preloadNeighbors();
        await this.loadMetadata(nextItem.path);
      }
    },

    async prev() {
      if (this.currentIndex > 0) {
        this.currentIndex--;
        const prevItem = this.galleryItems[this.currentIndex];
        this.itemPath = prevItem.path;
        this.itemName = prevItem.name;
        this.preloadNeighbors();
        await this.loadMetadata(prevItem.path);
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
      // Invalidate any in-flight metadata request so stale responses can't overwrite state.
      this.metadataRequestId += 1;
      this.isOpen = false;
      this.metadata = null;
      this.itemPath = "";
      this.itemName = "";
      this.width = null;
      this.height = null;
      this.isLoading = false;
      this.galleryItems = [];
      this.currentIndex = -1;
    },
  },
});
