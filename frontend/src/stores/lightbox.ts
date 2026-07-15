import { defineStore } from "pinia";
import type { FileNode } from "../types";
import {
  isLightboxNavDebugEnabled,
  lightboxItemAt,
  logLightboxNavDebug,
  summarizeLightboxItems,
} from "../debug/lightboxNavDebug";
import { type LightboxDimensions } from "../utils/lightbox";

export const useLightboxStore = defineStore("lightbox", {
  state: () => ({
    isOpen: false,
    itemPath: "",
    itemName: "",
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

      // Query-owned FileNodes are treated as immutable. Dimensions discovered
      // by the lightbox live in dimensionsByPath instead of mutating/cloning
      // every item on the interaction hot path.
      this.galleryItems = items.filter((item) => item.type === "image");
      const candidateIndex = typeof preferredIndex === "number" && preferredIndex >= 0 ? preferredIndex : -1;
      const preferredItem = candidateIndex >= 0 ? this.galleryItems[candidateIndex] : undefined;
      this.currentIndex =
        preferredItem?.path === path ? candidateIndex : this.galleryItems.findIndex((item) => item.path === path);

      if (isLightboxNavDebugEnabled()) {
        logLightboxNavDebug("store-open", {
          requested: { path, name },
          preferredIndex,
          candidateIndex,
          resolvedIndex: this.currentIndex,
          resolvedItem: lightboxItemAt(this.galleryItems, this.currentIndex),
          previous,
          items: summarizeLightboxItems(this.galleryItems, this.currentIndex),
        });
      }
    },

    rememberDimensions(path: string, dimensions: LightboxDimensions) {
      if (!path || dimensions.width <= 0 || dimensions.height <= 0) return;
      if (dimensions.source === "thumbnail") return;
      this.dimensionsByPath[path] = dimensions;
    },

    getRememberedDimensions(path: string): LightboxDimensions | undefined {
      return this.dimensionsByPath[path];
    },

    next() {
      if (this.currentIndex >= this.galleryItems.length - 1) return;
      const beforeIndex = this.currentIndex;
      const beforeItem = isLightboxNavDebugEnabled() ? lightboxItemAt(this.galleryItems, beforeIndex) : null;
      this.currentIndex++;
      const nextItem = this.galleryItems[this.currentIndex];
      this.itemPath = nextItem.path;
      this.itemName = nextItem.name;
      if (isLightboxNavDebugEnabled()) {
        logLightboxNavDebug("store-next", {
          beforeIndex,
          beforeItem,
          afterIndex: this.currentIndex,
          afterItem: lightboxItemAt(this.galleryItems, this.currentIndex),
        });
      }
    },

    prev() {
      if (this.currentIndex <= 0) return;
      const beforeIndex = this.currentIndex;
      const beforeItem = isLightboxNavDebugEnabled() ? lightboxItemAt(this.galleryItems, beforeIndex) : null;
      this.currentIndex--;
      const prevItem = this.galleryItems[this.currentIndex];
      this.itemPath = prevItem.path;
      this.itemName = prevItem.name;
      if (isLightboxNavDebugEnabled()) {
        logLightboxNavDebug("store-prev", {
          beforeIndex,
          beforeItem,
          afterIndex: this.currentIndex,
          afterItem: lightboxItemAt(this.galleryItems, this.currentIndex),
        });
      }
    },

    close() {
      if (!this.isOpen && this.currentIndex === -1 && !this.itemPath && this.galleryItems.length === 0) return;
      if (isLightboxNavDebugEnabled()) {
        logLightboxNavDebug("store-close", {
          currentIndex: this.currentIndex,
          currentItem: lightboxItemAt(this.galleryItems, this.currentIndex),
          galleryItems: this.galleryItems.length,
        });
      }
      this.isOpen = false;
      this.itemPath = "";
      this.itemName = "";
      this.galleryItems = [];
      this.currentIndex = -1;
    },
  },
});
