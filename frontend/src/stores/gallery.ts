import { defineStore } from "pinia";
import type { FileNode, SortField, SortOrder } from "../types";
import { openFolder, scanDirectory, GalleryAPIError } from "../services/api";
import { useToastStore } from "./toast";
import { IMAGE_PAGE_SIZE } from "../constants";

type LoadingMap = Record<string, boolean>;
const STORAGE_KEY = "gallery-root-path";
const SORT_STORAGE_KEY = "gallery-sort-preference";

const getStoredRoot = () => {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(STORAGE_KEY) || "";
};

const getStoredSort = (): { field: SortField; order: SortOrder } => {
  if (typeof window === "undefined") return { field: "name", order: "asc" };
  try {
    const stored = localStorage.getItem(SORT_STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      if (parsed.field && parsed.order) return parsed;
    }
  } catch {
    // ignore
  }
  return { field: "name", order: "asc" };
};

const saveSort = (field: SortField, order: SortOrder) => {
  if (typeof window === "undefined") return;
  localStorage.setItem(SORT_STORAGE_KEY, JSON.stringify({ field, order }));
};

const normalizeNodes = (nodes: FileNode[]): FileNode[] =>
  nodes
    .filter((n) => n.type === "folder")
    .map((n) => ({
      ...n,
      isOpen: false,
      children: undefined,
    }));

/**
 * Private helper that wraps an async operation with consistent error handling.
 * On success, clears errorMessage and returns the result.
 * On error, checks for GalleryAPIError, sets errorMessage, shows toast, and returns undefined.
 */
async function _withError<T>(
  store: any,
  fn: () => Promise<T>,
  fallbackMsg: string,
  retry?: () => void,
  options?: { noFallbackRetry?: boolean }
): Promise<T | undefined> {
  const toast = useToastStore();
  try {
    store.errorMessage = null;
    return await fn();
  } catch (error: unknown) {
    console.error(fallbackMsg, error);
    if (error instanceof GalleryAPIError) {
      store.errorMessage = error.suggestion;
      toast.error(
        error.userMessage,
        error.suggestion,
        error.canRetry && retry
          ? { action: { label: 'Retry', onClick: retry } }
          : undefined
      );
    } else {
      store.errorMessage = fallbackMsg;
      toast.error(
        'Error',
        fallbackMsg,
        !options?.noFallbackRetry && retry
          ? { action: { label: 'Retry', onClick: retry } }
          : undefined
      );
    }
    return undefined;
  }
}

export const useGalleryStore = defineStore("gallery", {
  state: () => {
    const storedSort = getStoredSort();
    return {
      rootPath: getStoredRoot(),
      sidebarTree: [] as FileNode[],
      currentPath: "",
      isLoading: false,
      galleryFolders: [] as FileNode[],
      galleryImages: [] as FileNode[],
      nextImageCursor: null as number | null,
      totalImages: 0,
      loadingMoreImages: false,
      galleryLoading: false,
      loadingMap: {} as LoadingMap,
      history: [] as string[],
      historyIndex: -1,
      errorMessage: "" as string | null,
      searchQuery: "",
      sortField: storedSort.field as SortField,
      sortOrder: storedSort.order as SortOrder,
    };
  },

  actions: {
    clearError() {
      this.errorMessage = null;
    },

    setSearchQuery(query: string) {
      this.searchQuery = query;
    },

    clearSearch() {
      this.searchQuery = "";
    },

    setSortField(field: SortField) {
      this.sortField = field;
      saveSort(this.sortField, this.sortOrder);
    },

    setSortOrder(order: SortOrder) {
      this.sortOrder = order;
      saveSort(this.sortField, this.sortOrder);
    },

    toggleSortOrder() {
      this.sortOrder = this.sortOrder === "asc" ? "desc" : "asc";
      saveSort(this.sortField, this.sortOrder);
    },

    async setRootPath(path: string) {
      if (!path) {
        this.resetRootPath();
        return;
      }
      this.isLoading = true;
      this.galleryLoading = true;
      this.loadingMoreImages = false;
      this.rootPath = path;

      const data = await _withError(
        this,
        () => scanDirectory(path, { imageLimit: IMAGE_PAGE_SIZE, imageCursor: 0 }),
        "Unable to load the root folder. Check the path or backend connection.",
        () => this.setRootPath(path)
      );

      if (!data) {
        this.sidebarTree = [];
        this.galleryFolders = [];
        this.galleryImages = [];
        this.nextImageCursor = null;
        this.totalImages = 0;
        this.currentPath = "";
        this.isLoading = false;
        this.galleryLoading = false;
        return;
      }

      this.sidebarTree = normalizeNodes(data.folders);
      this.galleryFolders = data.folders;
      this.galleryImages = data.images;
      this.nextImageCursor = data.next_cursor;
      this.totalImages = data.total_images;
      this.currentPath = path;
      if (typeof window !== "undefined") {
        localStorage.setItem(STORAGE_KEY, path);
      }
      this.pushHistory(path);

      // Show summary toast on first load (when entering root path)
      const imageCount = this.totalImages || this.galleryImages.length;
      const albumCount = this.galleryFolders.length;
      const toast = useToastStore();
      toast.success(
        'Gallery loaded',
        `<span class="toast-stat toast-stat--album">${albumCount} albums</span> • <span class="toast-stat toast-stat--image">${imageCount} images</span>`,
        { html: true }
      );

      this.isLoading = false;
      this.galleryLoading = false;
    },

    async toggleFolder(node: FileNode) {
      node.isOpen = !node.isOpen;

      const shouldLoadChildren =
        node.isOpen && node.children === undefined && node.has_children;

      if (!shouldLoadChildren) {
        return;
      }

      this.loadingMap = { ...this.loadingMap, [node.path]: true };

      const children = await _withError(
        this,
        () => scanDirectory(node.path),
        "Unable to load folder contents. Please try again.",
        () => {
          node.isOpen = false;
          node.children = undefined;
          this.toggleFolder(node);
        },
        { noFallbackRetry: true }
      );

      if (!children) {
        node.children = [];
      } else {
        node.children = normalizeNodes(children.folders);
      }

      const { [node.path]: _, ...rest } = this.loadingMap;
      this.loadingMap = rest;
    },

    async selectFolder(nodeOrPath: FileNode | string) {
      const path = typeof nodeOrPath === "string" ? nodeOrPath : nodeOrPath.path;
      this.currentPath = path;
      this.pushHistory(path);
      await this.scanFolder(path);
    },

    async scanFolder(path?: string) {
      const target = path || this.currentPath || this.rootPath;
      if (!target) {
        this.galleryFolders = [];
        this.galleryImages = [];
        this.nextImageCursor = null;
        this.totalImages = 0;
        return;
      }
      this.galleryLoading = true;

      const data = await _withError(
        this,
        () => scanDirectory(target, { imageLimit: IMAGE_PAGE_SIZE, imageCursor: 0 }),
        "Unable to scan the folder. Check the backend connection.",
        () => this.scanFolder(target)
      );

      if (!data) {
        this.galleryFolders = [];
        this.galleryImages = [];
        this.nextImageCursor = null;
        this.totalImages = 0;
        this.galleryLoading = false;
        return;
      }

      this.galleryFolders = data.folders;
      this.galleryImages = data.images;
      this.nextImageCursor = data.next_cursor;
      this.totalImages = data.total_images;
      this.currentPath = target;
      this.galleryLoading = false;
    },

    async loadMoreImages() {
      if (this.loadingMoreImages || this.nextImageCursor === null) return;
      const target = this.currentPath || this.rootPath;
      if (!target) return;
      this.loadingMoreImages = true;

      const data = await _withError(
        this,
        () => scanDirectory(target, { imageLimit: IMAGE_PAGE_SIZE, imageCursor: this.nextImageCursor! }),
        "Unable to fetch more images"
      );

      if (data) {
        this.galleryImages = [...this.galleryImages, ...data.images];
        this.nextImageCursor = data.next_cursor;
        this.totalImages = data.total_images;
      }

      this.loadingMoreImages = false;
    },

    async openInExplorer() {
      if (!this.currentPath) return;
      await _withError(
        this,
        () => openFolder(this.currentPath),
        "Unable to open the folder in your operating system."
      );
      // No success toast - Explorer window opening is feedback enough
    },

    resetRootPath() {
      this.rootPath = "";
      this.currentPath = "";
      this.sidebarTree = [];
      this.galleryFolders = [];
      this.galleryImages = [];
      if (typeof window !== "undefined") {
        localStorage.removeItem(STORAGE_KEY);
      }
    },

    pushHistory(path: string) {
      if (!path) return;
      if (this.historyIndex >= 0 && this.history[this.historyIndex] === path) return;
      this.history = this.history.slice(0, this.historyIndex + 1);
      this.history.push(path);
      this.historyIndex = this.history.length - 1;
    },

    goBack() {
      if (this.historyIndex > 0) {
        this.historyIndex -= 1;
        const path = this.history[this.historyIndex];
        this.currentPath = path;
        this.scanFolder(path);
      }
    },

    goForward() {
      if (this.historyIndex < this.history.length - 1) {
        this.historyIndex += 1;
        const path = this.history[this.historyIndex];
        this.currentPath = path;
        this.scanFolder(path);
      }
    },
  },
});
