import { defineStore } from "pinia";
import type {
  FileNode,
  FolderTreeNode,
  LibraryImportPath,
  RegisteredLibrary,
  SearchScope,
  SortField,
  SortOrder,
  SortValue,
} from "../types";
import { openFolder, GalleryAPIError } from "../services/api";
import { useToastStore } from "./toast";
import { normalizeQueryPath } from "../query/keys";

export const ACTIVE_LIBRARY_STORAGE_KEY = "gallery-active-library-id";
export const ACTIVE_IMPORT_PATH_STORAGE_KEY = "gallery-active-import-path-id";
export const LEGACY_ROOT_PATH_STORAGE_KEY = "gallery-root-path";
export const SORT_STORAGE_KEY = "gallery-sort-preference";
export const EXPANDED_FOLDER_PATHS_STORAGE_KEY = "gallery-expanded-folder-paths";

const readStoredPositiveId = (key: string): number | null => {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(key);
  if (!raw || !/^[1-9]\d*$/.test(raw)) {
    if (raw !== null) localStorage.removeItem(key);
    return null;
  }
  const id = Number(raw);
  if (!Number.isSafeInteger(id)) {
    localStorage.removeItem(key);
    return null;
  }
  return id;
};

const orderedImportPaths = (library: RegisteredLibrary): LibraryImportPath[] =>
  [...library.import_paths].sort((a, b) => a.position - b.position || a.id - b.id);

const comparablePath = (path: string): string => {
  const normalized = path
    .trim()
    .replace(/\\/g, "/")
    .replace(/\/{2,}/g, "/");
  if (/^[A-Za-z]:\//.test(normalized)) return normalized.replace(/\/$/, "").toLowerCase();
  return normalized === "/" ? normalized : normalized.replace(/\/$/, "");
};

export const pathContains = (root: string, candidate: string): boolean => {
  const normalizedRoot = comparablePath(root);
  const normalizedCandidate = comparablePath(candidate);
  return (
    normalizedCandidate === normalizedRoot ||
    (normalizedRoot === "/"
      ? normalizedCandidate.startsWith("/")
      : normalizedCandidate.startsWith(`${normalizedRoot}/`))
  );
};

export function findImportPathForPath(
  libraries: RegisteredLibrary[],
  candidatePath: string,
): { library: RegisteredLibrary; importPath: LibraryImportPath } | null {
  const matches = libraries.flatMap((library) =>
    orderedImportPaths(library)
      .filter((importPath) => pathContains(importPath.path, candidatePath))
      .map((importPath) => ({ library, importPath })),
  );
  matches.sort(
    (a, b) =>
      comparablePath(b.importPath.path).length - comparablePath(a.importPath.path).length ||
      a.library.id - b.library.id ||
      a.importPath.position - b.importPath.position ||
      a.importPath.id - b.importPath.id,
  );
  return matches[0] ?? null;
}

export function resolveActiveImportPath(
  libraries: RegisteredLibrary[],
  libraryId: number | null,
  importPathId: number | null,
): LibraryImportPath | null {
  const library = libraries.find((item) => item.id === libraryId);
  return library?.import_paths.find((item) => item.id === importPathId) ?? null;
}

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

const normalizeTreeNodes = (nodes: FolderTreeNode[], preserveChildren = false): FolderTreeNode[] =>
  nodes
    .filter((node) => node.type === "folder")
    .map((node) => ({
      ...node,
      children: preserveChildren && node.children ? normalizeTreeNodes(node.children) : undefined,
    }));

const getExpansionScopeKey = (libraryId: number | null, importPathId: number | null): string | null => {
  if (!libraryId) return null;
  return `${libraryId}:${importPathId ?? "all"}`;
};

const readExpandedFolderPathScopes = (): Record<string, string[]> => {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(EXPANDED_FOLDER_PATHS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.entries(parsed).reduce<Record<string, string[]>>((acc, [key, value]) => {
      if (Array.isArray(value)) {
        acc[key] = value.filter(
          (path): path is string => typeof path === "string" && Boolean(normalizeQueryPath(path)),
        );
      }
      return acc;
    }, {});
  } catch {
    localStorage.removeItem(EXPANDED_FOLDER_PATHS_STORAGE_KEY);
    return {};
  }
};

const writeExpandedFolderPathScope = (
  libraryId: number | null,
  importPathId: number | null,
  expandedFolderPaths: Record<string, boolean>,
) => {
  const scopeKey = getExpansionScopeKey(libraryId, importPathId);
  if (typeof window === "undefined" || !scopeKey) return;
  const scopes = readExpandedFolderPathScopes();
  scopes[scopeKey] = Object.entries(expandedFolderPaths)
    .filter(([, expanded]) => expanded)
    .map(([path]) => path)
    .sort();
  localStorage.setItem(EXPANDED_FOLDER_PATHS_STORAGE_KEY, JSON.stringify(scopes));
};

const readExpandedFolderPathScope = (
  libraryId: number | null,
  importPathId: number | null,
): Record<string, boolean> => {
  const scopeKey = getExpansionScopeKey(libraryId, importPathId);
  if (!scopeKey) return {};
  return (readExpandedFolderPathScopes()[scopeKey] ?? []).reduce<Record<string, boolean>>((acc, path) => {
    const normalizedPath = normalizeQueryPath(path);
    if (normalizedPath) acc[normalizedPath] = true;
    return acc;
  }, {});
};

const getPathAncestorChain = (root: string, path: string): string[] => {
  const normalizedRoot = normalizeQueryPath(root);
  const normalizedPath = normalizeQueryPath(path);
  if (!normalizedRoot || !normalizedPath || !pathContains(normalizedRoot, normalizedPath)) return [];
  if (normalizedRoot === normalizedPath) return [normalizedRoot];

  if (normalizedRoot === "/") {
    const segments = normalizedPath
      .split("/")
      .map((segment) => segment.trim())
      .filter(Boolean);
    return segments.reduce<string[]>(
      (paths, segment) => {
        const previous = paths[paths.length - 1] ?? "";
        paths.push(`${previous}/${segment}`.replace(/\/{2,}/g, "/"));
        return paths;
      },
      ["/"],
    );
  }

  const relativeSegments = normalizedPath
    .slice(normalizedRoot.length + 1)
    .split("/")
    .filter(Boolean);
  return relativeSegments.reduce<string[]>(
    (paths, segment) => {
      paths.push(`${paths[paths.length - 1]}/${segment}`.replace(/\/{2,}/g, "/"));
      return paths;
    },
    [normalizedRoot],
  );
};

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
      activeLibraryId: null as number | null,
      activeImportPathId: null as number | null,
      activeImportRootPath: "",
      activeLibraryHydrated: false,
      sidebarTree: [] as FolderTreeNode[],
      expandedFolderPaths: {} as Record<string, boolean>,
      currentBrowsePath: "",
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

    hydrateActiveLibrary(libraries: RegisteredLibrary[]) {
      const persistedLibraryId = readStoredPositiveId(ACTIVE_LIBRARY_STORAGE_KEY);
      const persistedImportPathId = readStoredPositiveId(ACTIVE_IMPORT_PATH_STORAGE_KEY);
      const persistedLibrary = libraries.find((library) => library.id === persistedLibraryId);
      const persistedPaths = persistedLibrary ? orderedImportPaths(persistedLibrary) : [];

      if (persistedLibrary && persistedPaths.length) {
        const importPath = persistedPaths.find((item) => item.id === persistedImportPathId) ?? persistedPaths[0];
        this.applyActiveSelection(persistedLibrary, importPath);
        if (typeof window !== "undefined") localStorage.removeItem(LEGACY_ROOT_PATH_STORAGE_KEY);
        this.activeLibraryHydrated = true;
        return;
      }

      this.clearActiveLibrary();
      const legacyPath =
        typeof window === "undefined" ? "" : (localStorage.getItem(LEGACY_ROOT_PATH_STORAGE_KEY) ?? "").trim();
      const legacyMatch = legacyPath ? findImportPathForPath(libraries, legacyPath) : null;
      if (legacyMatch) {
        this.applyActiveSelection(legacyMatch.library, legacyMatch.importPath, legacyPath);
        if (typeof window !== "undefined") localStorage.removeItem(LEGACY_ROOT_PATH_STORAGE_KEY);
        this.activeLibraryHydrated = true;
        return;
      }

      if (typeof window !== "undefined") localStorage.removeItem(LEGACY_ROOT_PATH_STORAGE_KEY);
      const eligible = libraries.filter((library) => library.import_paths.length > 0);
      if (eligible.length === 1) {
        this.applyActiveSelection(eligible[0], orderedImportPaths(eligible[0])[0]);
      }
      this.activeLibraryHydrated = true;
    },

    applyActiveSelection(library: RegisteredLibrary, importPath: LibraryImportPath, browsePath = importPath.path) {
      this.activeLibraryId = library.id;
      this.activeImportPathId = importPath.id;
      this.activeImportRootPath = importPath.path;
      if (typeof window !== "undefined") {
        localStorage.setItem(ACTIVE_LIBRARY_STORAGE_KEY, String(library.id));
        localStorage.setItem(ACTIVE_IMPORT_PATH_STORAGE_KEY, String(importPath.id));
        localStorage.removeItem(LEGACY_ROOT_PATH_STORAGE_KEY);
      }
      this.resetBrowseState(browsePath);
    },

    setActiveLibrary(library: RegisteredLibrary, importPath?: LibraryImportPath): boolean {
      const selected = importPath ?? orderedImportPaths(library)[0];
      if (
        !selected ||
        selected.library_id !== library.id ||
        !library.import_paths.some((item) => item.id === selected.id)
      ) {
        return false;
      }
      this.applyActiveSelection(library, selected);
      return true;
    },

    setActiveImportPath(importPath: LibraryImportPath, library: RegisteredLibrary): boolean {
      if (library.id !== this.activeLibraryId || importPath.library_id !== library.id) return false;
      return this.setActiveLibrary(library, importPath);
    },

    clearActiveLibrary() {
      this.activeLibraryId = null;
      this.activeImportPathId = null;
      this.activeImportRootPath = "";
      if (typeof window !== "undefined") {
        localStorage.removeItem(ACTIVE_LIBRARY_STORAGE_KEY);
        localStorage.removeItem(ACTIVE_IMPORT_PATH_STORAGE_KEY);
      }
      this.resetBrowseState();
    },

    resetBrowseState(rootPath = "") {
      const safeRootPath = this.clampToActiveImportRoot(rootPath);
      this.currentBrowsePath = safeRootPath;
      this.sidebarTree = [];
      this.expandedFolderPaths = readExpandedFolderPathScope(this.activeLibraryId, this.activeImportPathId);
      this.expandPathAncestors(safeRootPath || this.activeImportRootPath);
      this.history = safeRootPath ? [safeRootPath] : [];
      this.historyIndex = safeRootPath ? 0 : -1;
      this.hasEverLoaded = false;
      this.isLoading = false;
      this.clearSearch();
      this.clearError();
    },

    isPathInActiveImportRoot(path: string): boolean {
      return !this.activeImportRootPath || pathContains(this.activeImportRootPath, path);
    },

    clampToActiveImportRoot(path: string): string {
      if (!path) return "";
      return this.isPathInActiveImportRoot(path) ? path : this.activeImportRootPath;
    },

    sanitizeBrowseHistory() {
      if (!this.activeImportRootPath || !this.history.length) return;
      const currentHistoryPath = this.historyIndex >= 0 ? this.history[this.historyIndex] : "";
      const currentSafePath = this.clampToActiveImportRoot(currentHistoryPath);
      const safeHistory = this.history
        .map((path) => this.clampToActiveImportRoot(path))
        .filter((path): path is string => Boolean(path))
        .filter((path, index, paths) => index === 0 || path !== paths[index - 1]);

      this.history = safeHistory;
      this.historyIndex = currentSafePath ? safeHistory.lastIndexOf(currentSafePath) : -1;
      if (this.historyIndex < 0 && safeHistory.length) {
        this.historyIndex = 0;
      }
    },

    setSidebarTree(nodes: FolderTreeNode[], options?: { preserveChildren?: boolean }) {
      this.sidebarTree = options?.preserveChildren ? normalizeTreeNodes(nodes, true) : normalizeNodes(nodes);
    },

    isFolderExpanded(path: string): boolean {
      const normalizedPath = normalizeQueryPath(path);
      return !!this.expandedFolderPaths[normalizedPath];
    },

    toggleFolderExpanded(path: string) {
      const normalizedPath = normalizeQueryPath(path);
      if (!normalizedPath) return;
      this.expandedFolderPaths[normalizedPath] = !this.expandedFolderPaths[normalizedPath];
      writeExpandedFolderPathScope(this.activeLibraryId, this.activeImportPathId, this.expandedFolderPaths);
    },

    setFolderExpanded(path: string, expanded: boolean) {
      const normalizedPath = normalizeQueryPath(path);
      if (!normalizedPath) return;
      this.expandedFolderPaths[normalizedPath] = expanded;
      writeExpandedFolderPathScope(this.activeLibraryId, this.activeImportPathId, this.expandedFolderPaths);
    },

    loadPersistedExpandedFolders() {
      this.expandedFolderPaths = readExpandedFolderPathScope(this.activeLibraryId, this.activeImportPathId);
      this.expandPathAncestors(this.currentBrowsePath || this.activeImportRootPath);
    },

    expandPathAncestors(path: string) {
      const chain = getPathAncestorChain(this.activeImportRootPath, path);
      for (const ancestorPath of chain) {
        this.expandedFolderPaths[ancestorPath] = true;
      }
      writeExpandedFolderPathScope(this.activeLibraryId, this.activeImportPathId, this.expandedFolderPaths);
    },

    toggleFolder(node: FileNode) {
      this.toggleFolderExpanded(node.path);
    },

    selectFolder(nodeOrPath: FileNode | string) {
      const path = typeof nodeOrPath === "string" ? nodeOrPath : nodeOrPath.path;
      const safePath = this.clampToActiveImportRoot(path);
      this.currentBrowsePath = safePath;
      this.expandPathAncestors(safePath);
      this.pushHistory(safePath);
      this.hasEverLoaded = true;
    },

    async openInExplorer() {
      if (!this.currentBrowsePath) return;
      await _withError(
        this,
        () => openFolder(this.currentBrowsePath),
        "Unable to open the folder in your operating system.",
      );
      // No success toast - Explorer window opening is feedback enough
    },

    pushHistory(path: string) {
      const safePath = this.clampToActiveImportRoot(path);
      if (!safePath) return;
      this.sanitizeBrowseHistory();
      if (this.historyIndex >= 0 && this.history[this.historyIndex] === safePath) return;
      this.history = this.history.slice(0, this.historyIndex + 1);
      this.history.push(safePath);
      this.historyIndex = this.history.length - 1;
    },

    goBack() {
      this.sanitizeBrowseHistory();
      if (this.historyIndex > 0) {
        this.historyIndex -= 1;
        const path = this.history[this.historyIndex];
        this.currentBrowsePath = path;
        this.expandPathAncestors(path);
        this.hasEverLoaded = true;
      }
    },

    goForward() {
      this.sanitizeBrowseHistory();
      if (this.historyIndex < this.history.length - 1) {
        this.historyIndex += 1;
        const path = this.history[this.historyIndex];
        this.currentBrowsePath = path;
        this.expandPathAncestors(path);
        this.hasEverLoaded = true;
      }
    },
  },
});
