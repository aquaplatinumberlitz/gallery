import { useInfiniteQuery, type InfiniteData } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { IMAGE_PAGE_SIZE } from "../constants";
import { queryClient } from "../query";
import { normalizeQueryPath, queryKeys } from "../query/keys";
import { scanDirectory } from "../services/api";
import type { ScanResponse } from "../types";

const withScanRequestPath = (data: ScanResponse, requestPath: string): ScanResponse => ({
  ...data,
  request_path: requestPath,
});

const getCachedFirstPage = (requestPath: string): InfiniteData<ScanResponse, number> | undefined => {
  const cached = queryClient.getQueryData<ScanResponse>(
    queryKeys.scan(requestPath, IMAGE_PAGE_SIZE)
  );
  if (!cached) return undefined;

  return {
    pages: [withScanRequestPath(cached, requestPath)],
    pageParams: [0],
  };
};

const getCachedFirstPageUpdatedAt = (requestPath: string) =>
  queryClient.getQueryState(queryKeys.scan(requestPath, IMAGE_PAGE_SIZE))?.dataUpdatedAt;

export function useInfiniteScanQuery(path: Ref<string>) {
  const normalizedPath = computed(() => normalizeQueryPath(path.value || ""));

  const queryKey = computed(() =>
    normalizedPath.value
      ? queryKeys.scanInfinite(normalizedPath.value, IMAGE_PAGE_SIZE)
      : []
  );

  const scanQuery = useInfiniteQuery({
    queryKey,
    enabled: computed(() => normalizedPath.value.length > 0),
    initialPageParam: 0,
    initialData: () => {
      if (!normalizedPath.value) return undefined;
      return getCachedFirstPage(normalizedPath.value);
    },
    initialDataUpdatedAt: () => {
      if (!normalizedPath.value) return undefined;
      return getCachedFirstPageUpdatedAt(normalizedPath.value);
    },
    queryFn: async ({ queryKey, pageParam }) => {
      const requestPath = queryKey[1] as string;
      const result = await scanDirectory(requestPath, {
        imageLimit: IMAGE_PAGE_SIZE,
        imageCursor: pageParam,
      });
      return withScanRequestPath(result, requestPath);
    },
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const pages = computed(() => scanQuery.data.value?.pages ?? []);
  const firstPage = computed(() => pages.value[0]);
  const folders = computed(() => firstPage.value?.folders ?? []);
  const images = computed(() => pages.value.flatMap((page) => page.images));
  const totalImages = computed(() => firstPage.value?.total_images ?? 0);
  const nextCursor = computed(() => {
    if (!pages.value.length) return null;
    return pages.value[pages.value.length - 1]?.next_cursor ?? null;
  });
  const activeFolderPath = computed(() => firstPage.value?.request_path || normalizedPath.value);

  return {
    ...scanQuery,
    scanPath: normalizedPath,
    activeFolderPath,
    folders,
    images,
    totalImages,
    nextCursor,
  };
}
