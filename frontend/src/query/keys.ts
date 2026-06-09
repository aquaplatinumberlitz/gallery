const normalizePath = (path: string | null | undefined) =>
  (path ?? "").trim().replace(/\\/g, "/").replace(/\/+/g, "/").replace(/\/$/, "");

export const queryKeys = {
  landingPages: () => ["landing-pages"] as const,

  scan: (path: string, imageLimit: number) =>
    ["scan", normalizePath(path), imageLimit] as const,

  scanInfinite: (path: string, imageLimit: number) =>
    ["scan-infinite", normalizePath(path), imageLimit] as const,

  search: (query: string, scope: string, path: string) =>
    ["search", query.trim(), scope, normalizePath(path)] as const,

  metadata: (path: string) =>
    ["metadata", normalizePath(path)] as const,
};
