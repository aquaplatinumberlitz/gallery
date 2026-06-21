import type { SortValue } from "@/types";

export const normalizeQueryPath = (path: string | null | undefined) => {
  const normalized = (path ?? "").trim().replace(/\\/g, "/").replace(/\/+/g, "/");
  // Preserve the filesystem root path; trim trailing slashes only for non-root paths.
  return normalized === "/" ? normalized : normalized.replace(/\/$/, "");
};

export const queryKeys = {
  landingPages: () => ["landing-pages"] as const,

  librariesRoot: () => ["libraries"] as const,

  libraries: () => ["libraries", "list"] as const,

  library: (id: number) => ["libraries", "detail", id] as const,

  libraryProgress: (id: number) => ["libraries", "progress", id] as const,

  libraryStats: (id: number) => ["libraries", "stats", id] as const,

  libraryJobs: (id: number) => ["libraries", "jobs", id] as const,

  galleryStats: () => ["stats", "gallery"] as const,

  jobsRoot: () => ["jobs"] as const,

  jobs: () => ["jobs", "list"] as const,

  job: (id: number) => ["jobs", id] as const,

  scan: (path: string, limit: number) => ["scan", normalizeQueryPath(path), limit] as const,

  folderChildren: (path: string) => ["folder-children", normalizeQueryPath(path)] as const,

  scanInfinite: (path: string, limit: number) => ["scan-infinite", normalizeQueryPath(path), limit] as const,

  search: (query: string, scope: string, path: string) =>
    ["search", query.trim(), scope, normalizeQueryPath(path)] as const,

  metadata: (path: string) => ["metadata", normalizeQueryPath(path)] as const,

  indexStatus: (path: string) => ["index-status", normalizeQueryPath(path)] as const,

  libraryInspectorRoot: () => ["library-inspector"] as const,

  facets: (path: string) => ["facets", normalizeQueryPath(path)] as const,

  libraryInspector: (query: string, scope: string, path: string, limit: number, sort: SortValue) =>
    ["library-inspector", query.trim(), scope, normalizeQueryPath(path), limit, sort] as const,

  libraryInspectorMetadataRoot: () => ["library-inspector-metadata"] as const,

  libraryInspectorMetadata: (path: string) => ["library-inspector-metadata", normalizeQueryPath(path)] as const,
};
