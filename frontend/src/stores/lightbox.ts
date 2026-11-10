import { defineStore } from "pinia";
import { effectScope, watch, type EffectScope } from "vue";
import type { FileNode } from "../types";
import {
  isLightboxNavDebugEnabled,
  lightboxItemAt,
  logLightboxNavDebug,
  summarizeLightboxItems,
} from "../debug/lightboxNavDebug";
import { type LightboxDimensions } from "../utils/lightbox";

/**
 * What the lightbox needs from the owner of a paged list (a folder, search results, the Library Inspector) to keep
 * navigating past the pages that were loaded when it opened. The getters read the owner's reactive state, so the
 * store re-reads them when a page lands.
 */
export interface LightboxPager {
  /** The owner's current list; image nodes not yet shown are appended to the lightbox. */
  items: () => FileNode[];
  /** Whether the owner has another page to load. */
  hasMore: () => boolean;
  /** Loads the next page. A rejection is treated as a failed load and leaves the lightbox on the loaded items. */
  loadMore: () => Promise<unknown>;
}

/** The next page is requested once this many items or fewer remain after the current one. */
export const LIGHTBOX_LOAD_MORE_THRESHOLD = 5;

// The pager and its watchers are not Pinia state: they hold the owner's reactive getters, which must not be wrapped
// or serialised with the store. One lightbox is open at a time.
let activePager: LightboxPager | null = null;
let pagerScope: EffectScope | null = null;
let loadMorePending = false;
let loadMoreRecheck = false;
let pagerGeneration = 0;

function detachPager() {
  pagerScope?.stop();
  pagerScope = null;
  activePager = null;
  loadMorePending = false;
  loadMoreRecheck = false;
  pagerGeneration += 1;
}

export const useLightboxStore = defineStore("lightbox", {
  state: () => ({
    isOpen: false,
    itemPath: "",
    itemName: "",
    galleryItems: [] as FileNode[],
    currentIndex: -1,
    dimensionsByPath: {} as Record<string, LightboxDimensions>,
    /** True while the owner has pages the lightbox has not received; PhotoSwipe must not wrap around then. */
    hasMoreItems: false,
  }),
  getters: {
    /** Same rule as PhotoSwipe's `canLoop()`: wrap only with more than two items and no page still to come. */
    canWrap: (state) => !state.hasMoreItems && state.galleryItems.length > 2,
  },
  actions: {
    open(
      node: FileNode | { path: string; name?: string },
      items: FileNode[] = [],
      preferredIndex?: number,
      pager?: LightboxPager,
    ) {
      detachPager();
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

      if (pager) this.attachPager(pager);
      else this.hasMoreItems = false;

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

    attachPager(pager: LightboxPager) {
      activePager = pager;
      pagerScope = effectScope(true);
      pagerScope.run(() => {
        // A page landing (or the owner running out of pages) changes what the getters read.
        watch(
          () => [pager.items(), pager.hasMore()],
          () => this.syncFromPager(),
        );
        // Moving towards the end, by any route (PhotoSwipe, arrows, keyboard fallback), asks for the next page.
        watch(
          () => this.currentIndex,
          () => this.requestMoreIfNearEnd(),
        );
      });
      this.hasMoreItems = pager.hasMore();
      this.requestMoreIfNearEnd();
    },

    /**
     * Appends the owner's image items that are not shown yet. The shown prefix is never reordered or replaced, so the
     * current slide and its index stay where they are.
     */
    syncFromPager() {
      const pager = activePager;
      if (!pager || !this.isOpen) return;
      const known = new Set<string>();
      for (const item of this.galleryItems) known.add(item.path);
      for (const node of pager.items()) {
        if (node.type !== "image" || known.has(node.path)) continue;
        known.add(node.path);
        this.galleryItems.push(node);
      }
      this.hasMoreItems = pager.hasMore();
      this.requestMoreIfNearEnd();
    },

    /** Asks the owner for its next page when the current item is within the threshold of the loaded end. */
    requestMoreIfNearEnd() {
      const pager = activePager;
      if (!pager || !this.isOpen || !pager.hasMore()) return;
      if (this.galleryItems.length - 1 - this.currentIndex > LIGHTBOX_LOAD_MORE_THRESHOLD) return;
      if (loadMorePending) {
        // The page in flight may still leave the end close: look again when it settles.
        loadMoreRecheck = true;
        return;
      }

      const generation = pagerGeneration;
      loadMorePending = true;
      let request: Promise<unknown>;
      try {
        request = Promise.resolve(pager.loadMore());
      } catch (error) {
        request = Promise.reject(error);
      }
      void request
        // A failed page leaves the lightbox on the loaded items; reaching the end again retries.
        .catch(() => undefined)
        .finally(() => {
          if (generation !== pagerGeneration) return;
          loadMorePending = false;
          if (loadMoreRecheck) {
            loadMoreRecheck = false;
            this.syncFromPager();
          }
        });
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
      const atEnd = this.currentIndex >= this.galleryItems.length - 1;
      if (atEnd && !this.canWrap) {
        // No wrap while pages are still to come; this retries a page that failed or has not been asked for yet.
        this.requestMoreIfNearEnd();
        return;
      }
      const beforeIndex = this.currentIndex;
      const beforeItem = isLightboxNavDebugEnabled() ? lightboxItemAt(this.galleryItems, beforeIndex) : null;
      this.currentIndex = atEnd ? 0 : this.currentIndex + 1;
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
      const atStart = this.currentIndex <= 0;
      if (atStart && !this.canWrap) return;
      const beforeIndex = this.currentIndex;
      const beforeItem = isLightboxNavDebugEnabled() ? lightboxItemAt(this.galleryItems, beforeIndex) : null;
      this.currentIndex = atStart ? this.galleryItems.length - 1 : this.currentIndex - 1;
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
      detachPager();
      this.hasMoreItems = false;
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
