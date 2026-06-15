import type { QueryClient } from "@tanstack/vue-query";
import { queryKeys } from "@/query/keys";

declare global {
  interface Window {
    __GALLERY_DEBUG_INDEX_REBUILD?: boolean;
  }
}

export function isIndexRebuildDebugEnabled() {
  if (typeof window === "undefined") return false;
  return (
    window.__GALLERY_DEBUG_INDEX_REBUILD === true ||
    window.localStorage.getItem("debug-index-rebuild") === "true"
  );
}

export function logIndexRebuildDebug(event: string, payload: Record<string, unknown>) {
  if (!isIndexRebuildDebugEnabled()) return;
  console.info(
    "[index-rebuild-debug]",
    JSON.stringify({
      event,
      ...payload,
    })
  );
}

export function getLibraryInspectorQueryDebug(queryClient: QueryClient) {
  return queryClient
    .getQueryCache()
    .findAll({ queryKey: queryKeys.libraryInspectorRoot() })
    .map((query) => ({
      queryKey: query.queryKey,
      isActive: query.isActive(),
      isStale: query.isStale(),
      fetchStatus: query.state.fetchStatus,
      status: query.state.status,
      dataUpdatedAt: query.state.dataUpdatedAt,
    }));
}
