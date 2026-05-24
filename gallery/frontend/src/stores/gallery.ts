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
      const toast = useToastStore();
      if (!path) {
        this.resetRootPath();
        return;
      }
      this.isLoading = true;
      this.galleryLoading = true;
      this.loadingMoreImages = false;
      this.rootPath = path;
      try {
        const data = await scanDirectory(path, { imageLimit: IMAGE_PAGE_SIZE, imageCursor: 0 });
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
        this.errorMessage = null;
        
        // Show summary toast on first load (when entering root path)
        const imageCount = this.totalImages || this.galleryImages.length;
        const albumCount = this.galleryFolders.length;
        
        toast.success(
          'Gallery loaded',
          `<span class="toast-stat toast-stat--album">${albumCount} albums</span> • <span class="toast-stat toast-stat--image">${imageCount} images</span>`,
          { html: true }
        );
      } catch (error: unknown) {
        console.error("Failed to load root path", error);
        
        if (error instanceof GalleryAPIError) {
          this.errorMessage = error.suggestion;
          toast.error(error.userMessage, error.suggestion, 
            error.canRetry ? {
              action: {
                label: 'Retry',
                onClick: () => this.setRootPath(path)
              }
            } : undefined
          );
        } else {
          this.errorMessage = "Unable to load the root folder. Check the path or backend connection.";
          toast.error('Failed to load folder', 'Check the path or backend connection', {
            action: {
              label: 'Retry',
              onClick: () => this.setRootPath(path)
            }
          });
        }
        this.sidebarTree = [];
        this.galleryFolders = [];
        this.galleryImages = [];
        this.nextImageCursor = null;
        this.totalImages = 0;
        this.currentPath = "";
      } finally {
        this.isLoading = false;
        this.galleryLoading = false;
      }
    },

    async toggleFolder(node: FileNode) {
      const toast = useToastStore();
      node.isOpen = !node.isOpen;

      const shouldLoadChildren =
        node.isOpen && node.children === undefined && node.has_children;

      if (!shouldLoadChildren) {
        return;
      }

      this.loadingMap = { ...this.loadingMap, [node.path]: true };
      try {
        const children = await scanDirectory(node.path);
        node.children = normalizeNodes(children.folders);
        this.errorMessage = null;
      } catch (error: unknown) {
        console.error("Failed to load children for", node.path, error);
        
        if (error instanceof GalleryAPIError) {
          this.errorMessage = error.suggestion;
          toast.error(error.userMessage, error.suggestion,
            error.canRetry ? {
              action: {
                label: 'Retry',
                onClick: () => {
                  node.isOpen = false; // Reset to closed
                  node.children = undefined; // Clear children to retry
                  this.toggleFolder(node);
                }
              }
            } : undefined
          );
        } else {
          this.errorMessage = "Unable to load folder contents. Please try again.";
          toast.error('Failed to load folder', node.name || 'Unable to load folder contents');
        }
        node.children = [];
      } finally {
        const { [node.path]: _, ...rest } = this.loadingMap;
        this.loadingMap = rest;
      }
    },

    async selectFolder(nodeOrPath: FileNode | string) {
      const path = typeof nodeOrPath === "string" ? nodeOrPath : nodeOrPath.path;
      this.currentPath = path;
      this.pushHistory(path);
      await this.scanFolder(path);
    },

    async scanFolder(path?: string) {
      const toast = useToastStore();
      const target = path || this.currentPath || this.rootPath;
      if (!target) {
        this.galleryFolders = [];
        this.galleryImages = [];
        this.nextImageCursor = null;
        this.totalImages = 0;
        return;
      }
      this.galleryLoading = true;
      try {
        const data = await scanDirectory(target, { imageLimit: IMAGE_PAGE_SIZE, imageCursor: 0 });
        this.galleryFolders = data.folders;
        this.galleryImages = data.images;
        this.nextImageCursor = data.next_cursor;
        this.totalImages = data.total_images;
        this.currentPath = target;
        this.errorMessage = null;
      } catch (error: unknown) {
        console.error("Failed to scan folder", target, error);
        
        if (error instanceof GalleryAPIError) {
          this.errorMessage = error.suggestion;
          toast.error(error.userMessage, error.suggestion,
            error.canRetry ? {
              action: {
                label: 'Retry',
                onClick: () => this.scanFolder(target)
              }
            } : undefined
          );
        } else {
          this.errorMessage = "Unable to scan the folder. Check the backend connection.";
          toast.error('Failed to scan folder', 'Check backend connection', {
            action: {
              label: 'Retry',
              onClick: () => this.scanFolder(target)
            }
          });
        }
        this.galleryFolders = [];
        this.galleryImages = [];
        this.nextImageCursor = null;
        this.totalImages = 0;
      } finally {
        this.galleryLoading = false;
      }
    },

    async loadMoreImages() {
      if (this.loadingMoreImages || this.nextImageCursor === null) return;
      const toast = useToastStore();
      const target = this.currentPath || this.rootPath;
      if (!target) return;
      this.loadingMoreImages = true;
      try {
        const data = await scanDirectory(target, { imageLimit: IMAGE_PAGE_SIZE, imageCursor: this.nextImageCursor });
        this.galleryImages = [...this.galleryImages, ...data.images];
        this.nextImageCursor = data.next_cursor;
        this.totalImages = data.total_images;
      } catch (error: unknown) {
        console.error("Failed to load more images", error);
        if (error instanceof GalleryAPIError) {
          this.errorMessage = error.suggestion;
          toast.error(error.userMessage, error.suggestion);
        } else {
          toast.error('Failed to load more', 'Unable to fetch more images');
        }
      } finally {
        this.loadingMoreImages = false;
      }
    },

    async openInExplorer() {
      const toast = useToastStore();
      if (!this.currentPath) return;
      try {
        await openFolder(this.currentPath);
        this.errorMessage = null;
        // No success toast - Explorer window opening is feedback enough
      } catch (error: unknown) {
        console.error("Failed to open folder", error);
        
        if (error instanceof GalleryAPIError) {
          this.errorMessage = error.suggestion;
          toast.error(error.userMessage, error.suggestion);
        } else {
          this.errorMessage = "Unable to open the folder in your operating system.";
          toast.error('Failed to open folder', 'Unable to open in file explorer');
        }
      }
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
