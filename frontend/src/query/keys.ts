import type { SortValue } from "@/types";

export const normalizeQueryPath = (path: string | null | undefined) => {
  const normalized = (path ?? "").trim().replace(/\\/g, "/").replace(/\/+/g, "/");
  // Preserve the filesystem root path; trim trailing slashes only for non-root paths.
  return normalized === "/" ? normalized : normalized.replace(/\/$/, "");
};

export const normalizeBrowsePath = (path: string | null | undefined) => {
  const normalized = normalizeQueryPath(path);
  return normalized || null;
};

export const queryKeys = {
  landingPages: () => ["landing-pages"] as const,

  librariesRoot: () => ["libraries"] as const,

  libraries: () => ["libraries", "list"] as const,

  library: (id: number) => ["libraries", "detail", id] as const,

  // cleanup: remove after migration to unified status. Still consumed by
  // useLibraryStatsQuery / LibraryDetailPage for storage usage stats.
  libraryStats: (id: number) => ["libraries", "stats", id] as const,

  libraryJobs: (id: number) => ["libraries", "jobs", id] as const,

  galleryStats: () => ["stats", "gallery"] as const,

  jobsRoot: () => ["jobs"] as const,

  jobs: () => ["jobs", "list"] as const,

  job: (id: number) => ["jobs", id] as const,

  browseRoot: (libraryId: number) => ["browse", libraryId] as const,

  browse: (libraryId: number, path: string | null | undefined, limit: number, includeOffline = false) =>
    ["browse", libraryId, normalizeBrowsePath(path), limit, includeOffline] as const,

  folderChildren: (path: string) => ["folder-children", normalizeQueryPath(path)] as const,

  browseInfiniteRoot: (libraryId: number) => ["browse-infinite", libraryId] as const,

  browseInfinite: (libraryId: number, path: string | null | undefined, limit: number, includeOffline = false) =>
    ["browse-infinite", libraryId, normalizeBrowsePath(path), limit, includeOffline] as const,

  search: (query: string, scope: string, path: string) =>
    ["search", query.trim(), scope, normalizeQueryPath(path)] as const,

  metadata: (path: string) => ["metadata", normalizeQueryPath(path)] as const,

  statusRoot: () => ["status"] as const,

  statusBatch: () => ["status", "libraries", "batch"] as const,

  statusLibrary: (libraryId: number) => ["status", "library", libraryId] as const,

  statusPathRoot: (libraryId: number) => ["status", "path", libraryId] as const,

  statusPath: (libraryId: number, path: string | null | undefined) =>
    ["status", "path", libraryId, normalizeBrowsePath(path)] as const,

  libraryInspectorRoot: () => ["library-inspector"] as const,

  facets: (path: string) => ["facets", normalizeQueryPath(path)] as const,

  libraryInspector: (query: string, scope: string, path: string, limit: number, sort: SortValue) =>
    ["library-inspector", query.trim(), scope, normalizeQueryPath(path), limit, sort] as const,

  libraryInspectorMetadata: (path: string) => ["library-inspector-metadata", normalizeQueryPath(path)] as const,
};
