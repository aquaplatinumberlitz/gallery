import { useInfiniteQuery, type InfiniteData } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { IMAGE_PAGE_SIZE } from "../constants";
import { queryClient } from "../query";
import { normalizeBrowsePath, queryKeys } from "../query/keys";
import { browseDirectory } from "../services/api";
import type { BrowseResponse } from "../types";

const withBrowseRequestPath = (data: BrowseResponse, requestPath: string | null): BrowseResponse => ({
  ...data,
  request_path: requestPath,
});

const getCachedFirstPage = (
  libraryId: number,
  requestPath: string | null,
  includeOffline: boolean,
): InfiniteData<BrowseResponse, number> | undefined => {
  const cached = queryClient.getQueryData<BrowseResponse>(
    queryKeys.browse(libraryId, requestPath, IMAGE_PAGE_SIZE, includeOffline),
  );
  if (!cached) return undefined;

  return {
    pages: [withBrowseRequestPath(cached, requestPath)],
    pageParams: [0],
  };
};

const getCachedFirstPageUpdatedAt = (libraryId: number, requestPath: string | null, includeOffline: boolean) =>
  queryClient.getQueryState(queryKeys.browse(libraryId, requestPath, IMAGE_PAGE_SIZE, includeOffline))?.dataUpdatedAt;

export function useInfiniteBrowseQuery(
  libraryId: Ref<number | null | undefined>,
  path: Ref<string | null | undefined>,
  includeOffline?: Ref<boolean>,
) {
  const normalizedPath = computed(() => normalizeBrowsePath(path.value));
  const activeLibraryId = computed(() => libraryId.value ?? null);
  const activeIncludeOffline = computed(() => includeOffline?.value ?? false);

  const queryKey = computed(() =>
    activeLibraryId.value
      ? queryKeys.browseInfinite(
          activeLibraryId.value,
          normalizedPath.value,
          IMAGE_PAGE_SIZE,
          activeIncludeOffline.value,
        )
      : [],
  );

  const browseQuery = useInfiniteQuery({
    queryKey,
    enabled: computed(() => Boolean(activeLibraryId.value)),
    initialPageParam: 0,
    initialData: () => {
      if (!activeLibraryId.value) return undefined;
      return getCachedFirstPage(activeLibraryId.value, normalizedPath.value, activeIncludeOffline.value);
    },
    initialDataUpdatedAt: () => {
      if (!activeLibraryId.value) return undefined;
      return getCachedFirstPageUpdatedAt(activeLibraryId.value, normalizedPath.value, activeIncludeOffline.value);
    },
    staleTime: 60_000,
    queryFn: async ({ queryKey, pageParam }) => {
      const requestLibraryId = queryKey[1] as number;
      const requestPath = queryKey[2] as string | null;
      const requestIncludeOffline = queryKey[4] as boolean;
      const result = await browseDirectory(requestLibraryId, requestPath, {
        limit: IMAGE_PAGE_SIZE,
        cursor: pageParam,
        includeOffline: requestIncludeOffline,
      });
      return withBrowseRequestPath(result, requestPath);
    },
    getNextPageParam: (lastPage) => lastPage.next_media_cursor ?? lastPage.next_cursor ?? undefined,
  });

  const pages = computed(() => browseQuery.data.value?.pages ?? []);
  const firstPage = computed(() => pages.value[0]);
  const folders = computed(() => firstPage.value?.folders ?? []);
  const media = computed(() => pages.value.flatMap((page) => page.media));
  const totalImages = computed(() => firstPage.value?.total_images ?? 0);
  const totalVideos = computed(() => firstPage.value?.total_videos ?? 0);
  const totalAssets = computed(() => firstPage.value?.total_assets ?? 0);
  const hasActivePage = computed(() => {
    const page = firstPage.value;
    if (!page || !activeLibraryId.value) return false;
    return (
      page.library_id === activeLibraryId.value &&
      normalizeBrowsePath(page.request_path ?? page.path) === normalizedPath.value
    );
  });
  const nextMediaCursor = computed(() => {
    if (!pages.value.length) return null;
    return pages.value[pages.value.length - 1].next_media_cursor;
  });
  const activeFolderPath = computed(() => firstPage.value?.request_path ?? normalizedPath.value ?? "");

  return {
    ...browseQuery,
    browsePath: normalizedPath,
    activeFolderPath,
    folders,
    media,
    totalImages,
    totalVideos,
    totalAssets,
    hasActivePage,
    nextMediaCursor,
  };
}
