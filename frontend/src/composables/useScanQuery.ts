import { useQuery } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { IMAGE_PAGE_SIZE } from "../constants";
import { scanDirectory } from "../services/api";
import type { ScanResponse } from "../types";
import { queryClient } from "../query";

function normalizeQueryPath(path: string): string {
  return path.trim().replace(/\\/g, "/").replace(/\/+/g, "/").replace(/\/$/, "");
}

export function getScanQueryKey(path: string) {
  return ["scan", normalizeQueryPath(path), IMAGE_PAGE_SIZE] as const;
}

export function useScanQuery(path: Ref<string>) {
  const normalizedPath = computed(() => normalizeQueryPath(path.value || ""));

  const queryKey = computed(() =>
    normalizedPath.value
      ? getScanQueryKey(normalizedPath.value)
      : []
  );

  return useQuery({
    queryKey,
    queryFn: async () => {
      const result = await scanDirectory(normalizedPath.value, {
        imageLimit: IMAGE_PAGE_SIZE,
        imageCursor: 0,
      });
      return result;
    },
    enabled: computed(() => normalizedPath.value.length > 0),
    placeholderData: (previousData) => previousData,
  });
}

/**
 * Pre-fetch a scan query into cache for instant navigation.
 * Called on album hover/focus.
 */
export function prefetchScan(path: string) {
  const normalized = normalizeQueryPath(path);
  if (!normalized) return;
  queryClient.prefetchQuery({
    queryKey: getScanQueryKey(normalized),
    queryFn: () => scanDirectory(normalized, { imageLimit: IMAGE_PAGE_SIZE, imageCursor: 0 }),
    staleTime: 60_000,
  });
}

/**
 * Get cached scan data without fetching.
 * Used by the store to check if data exists before deciding skeleton vs instant render.
 */
export function getCachedScan(path: string): ScanResponse | undefined {
  const normalized = normalizeQueryPath(path);
  if (!normalized) return undefined;
  return queryClient.getQueryData<ScanResponse>(getScanQueryKey(normalized));
}

/**
 * Fetch scan data respecting staleTime.
 * - If cached data is fresh (within staleTime=60s): returns cached, no network.
 * - If cached data is stale: fetches fresh data.
 * - If no cached data: fetches.
 */
export async function fetchScan(path: string): Promise<ScanResponse | undefined> {
  const normalized = normalizeQueryPath(path);
  if (!normalized) return undefined;
  try {
    return await queryClient.fetchQuery({
      queryKey: getScanQueryKey(normalized),
      queryFn: () => scanDirectory(normalized, { imageLimit: IMAGE_PAGE_SIZE, imageCursor: 0 }),
      staleTime: 60_000,
    });
  } catch {
    return undefined;
  }
}

/**
 * Check if cached scan data for a path is still fresh (within staleTime).
 */
export function isScanFresh(path: string): boolean {
  const normalized = normalizeQueryPath(path);
  if (!normalized) return false;
  const state = queryClient.getQueryState(getScanQueryKey(normalized));
  if (!state || !state.data) return false;
  const staleAt = (state.dataUpdatedAt || 0) + 60_000;
  return Date.now() < staleAt;
}

/**
 * Store scan data after manual fetches.
 * Used by Pinia actions that keep existing UI-state behavior.
 */
export function setCachedScan(path: string, data: ScanResponse) {
  const normalized = normalizeQueryPath(path);
  if (!normalized) return;
  queryClient.setQueryData(getScanQueryKey(normalized), data);
}

/**
 * Invalidate scan cache for a path.
 * Called after folder operations.
 */
export function invalidateScan(path: string) {
  const normalized = normalizeQueryPath(path);
  if (!normalized) return;
  queryClient.invalidateQueries({ queryKey: ["scan", normalized] });
}
