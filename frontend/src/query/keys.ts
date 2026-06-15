export const normalizeQueryPath = (path: string | null | undefined) => {
  const normalized = (path ?? "").trim().replace(/\\/g, "/").replace(/\/+/g, "/");
  // Preserve the filesystem root path; trim trailing slashes only for non-root paths.
  return normalized === "/" ? normalized : normalized.replace(/\/$/, "");
};

export const queryKeys = {
  landingPages: () => ["landing-pages"] as const,

  scan: (path: string, imageLimit: number) =>
    ["scan", normalizeQueryPath(path), imageLimit] as const,

  folderChildren: (path: string) =>
    ["folder-children", normalizeQueryPath(path)] as const,

  scanInfinite: (path: string, imageLimit: number) =>
    ["scan-infinite", normalizeQueryPath(path), imageLimit] as const,

  search: (query: string, scope: string, path: string) =>
    ["search", query.trim(), scope, normalizeQueryPath(path)] as const,

  metadata: (path: string) =>
    ["metadata", normalizeQueryPath(path)] as const,

  indexStatus: (path: string) =>
    ["index-status", normalizeQueryPath(path)] as const,

  facets: (path: string) =>
    ["facets", normalizeQueryPath(path)] as const,

  libraryInspector: (query: string, scope: string, path: string, limit: number) =>
    ["library-inspector", query.trim(), scope, normalizeQueryPath(path), limit] as const,

  libraryInspectorMetadata: (path: string) =>
    ["library-inspector-metadata", normalizeQueryPath(path)] as const,
};
