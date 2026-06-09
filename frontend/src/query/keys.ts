export const normalizeQueryPath = (path: string | null | undefined) =>
  (path ?? "").trim().replace(/\\/g, "/").replace(/\/+/g, "/").replace(/\/$/, "");

export const queryKeys = {
  landingPages: () => ["landing-pages"] as const,

  scanPath: (path: string) =>
    ["scan", normalizeQueryPath(path)] as const,

  scan: (path: string, imageLimit: number) =>
    ["scan", normalizeQueryPath(path), imageLimit] as const,

  scanInfinite: (path: string, imageLimit: number) =>
    ["scan-infinite", normalizeQueryPath(path), imageLimit] as const,

  search: (query: string, scope: string, path: string) =>
    ["search", query.trim(), scope, normalizeQueryPath(path)] as const,

  metadata: (path: string) =>
    ["metadata", normalizeQueryPath(path)] as const,
};
