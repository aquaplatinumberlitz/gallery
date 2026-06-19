import { defineStore } from "pinia";
import type { FileNode, FolderTreeNode, SearchScope, SortField, SortOrder, SortValue } from "../types";
import { openFolder, GalleryAPIError } from "../services/api";
import { useToastStore } from "./toast";
import { fetchScanOrThrow } from "../query/scan";
import { normalizeQueryPath } from "../query/keys";

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

const normalizeNodes = (nodes: FolderTreeNode[]): FolderTreeNode[] =>
  nodes
    .filter((n) => n.type === "folder")
    .map((n) => ({
      ...n,
      children: undefined,
    }));

interface ErrorMessageStore {
  errorMessage: string | null;
  errorType: string | null;
}

/**
 * Private helper that wraps an async operation with consistent error handling.
 * On success, clears errorMessage and returns the result.
 * On error, checks for GalleryAPIError, sets errorMessage, shows toast, and returns undefined.
 */
async function _withError<T>(
  store: ErrorMessageStore,
  fn: () => Promise<T>,
  fallbackMsg: string,
  retry?: () => void,
  options?: { noFallbackRetry?: boolean },
): Promise<T | undefined> {
  const toast = useToastStore();
  try {
    store.errorMessage = null;
    store.errorType = null;
    return await fn();
  } catch (error: unknown) {
    console.error(fallbackMsg, error);
    if (error instanceof GalleryAPIError) {
      store.errorMessage = error.suggestion;
      store.errorType = error.type;
      toast.error(
        error.userMessage,
        error.suggestion,
        error.canRetry && retry ? { action: { label: "Retry", onClick: retry } } : undefined,
      );
    } else {
      store.errorMessage = fallbackMsg;
      store.errorType = null;
      toast.error(
        "Error",
        fallbackMsg,
        !options?.noFallbackRetry && retry ? { action: { label: "Retry", onClick: retry } } : undefined,
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
      sidebarTree: [] as FolderTreeNode[],
      expandedFolderPaths: {} as Record<string, boolean>,
      currentPath: "",
      isLoading: false,
      history: [] as string[],
      historyIndex: -1,
      hasEverLoaded: false,
      errorMessage: "" as string | null,
      errorType: null as string | null,
      searchQuery: "",
      searchScope: "current" as SearchScope,
      sortField: storedSort.field as SortField,
      sortOrder: storedSort.order as SortOrder,
      metadataInspector: {
        query: "",
        scope: "current" as SearchScope,
        sort: "date_desc" as SortValue,
        modelFilter: "all",
        promptFilter: "all" as "all" | "has_prompt" | "no_prompt",
        selectedPath: "",
        scrollTop: 0,
        scrollPath: "",
      },
    };
  },

  actions: {
    clearError() {
      this.errorMessage = null;
      this.errorType = null;
    },

    setSearchQuery(query: string) {
      this.searchQuery = query;
    },

    clearSearch() {
      this.searchQuery = "";
    },

    setSearchScope(scope: SearchScope) {
      this.searchScope = scope;
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

    async setRootPath(path: string): Promise<boolean> {
      if (!path) {
        this.resetRootPath();
        return false;
      }
      this.isLoading = true;
      this.rootPath = path;

      const data = await _withError(
        this,
        () => fetchScanOrThrow(path),
        "Unable to load the root folder. Check the path or backend connection.",
        () => this.setRootPath(path),
      );

      if (!data) {
        this.sidebarTree = [];
        this.currentPath = "";
        this.isLoading = false;
        return false;
      }

      this.sidebarTree = normalizeNodes(data.folders);
      this.currentPath = path;
      this.errorType = null;
      if (typeof window !== "undefined") {
        localStorage.setItem(STORAGE_KEY, path);
      }
      this.pushHistory(path);
      this.hasEverLoaded = true;

      this.isLoading = false;
      return true;
    },

    isFolderExpanded(path: string): boolean {
      const normalizedPath = normalizeQueryPath(path);
      return !!this.expandedFolderPaths[normalizedPath];
    },

    toggleFolderExpanded(path: string) {
      const normalizedPath = normalizeQueryPath(path);
      if (!normalizedPath) return;
      this.expandedFolderPaths[normalizedPath] = !this.expandedFolderPaths[normalizedPath];
    },

    setFolderExpanded(path: string, expanded: boolean) {
      const normalizedPath = normalizeQueryPath(path);
      if (!normalizedPath) return;
      this.expandedFolderPaths[normalizedPath] = expanded;
    },

    toggleFolder(node: FileNode) {
      this.toggleFolderExpanded(node.path);
    },

    selectFolder(nodeOrPath: FileNode | string) {
      const path = typeof nodeOrPath === "string" ? nodeOrPath : nodeOrPath.path;
      this.currentPath = path;
      this.pushHistory(path);
      this.hasEverLoaded = true;
    },

    async openInExplorer() {
      if (!this.currentPath) return;
      await _withError(this, () => openFolder(this.currentPath), "Unable to open the folder in your operating system.");
      // No success toast - Explorer window opening is feedback enough
    },

    resetRootPath() {
      this.rootPath = "";
      this.currentPath = "";
      this.sidebarTree = [];
      this.expandedFolderPaths = {};
      this.hasEverLoaded = false;
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
        this.hasEverLoaded = true;
      }
    },

    goForward() {
      if (this.historyIndex < this.history.length - 1) {
        this.historyIndex += 1;
        const path = this.history[this.historyIndex];
        this.currentPath = path;
        this.hasEverLoaded = true;
      }
    },
  },
});
