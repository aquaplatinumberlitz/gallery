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
): InfiniteData<BrowseResponse, number> | undefined => {
  const cached = queryClient.getQueryData<BrowseResponse>(queryKeys.browse(libraryId, requestPath, IMAGE_PAGE_SIZE));
  if (!cached) return undefined;

  return {
    pages: [withBrowseRequestPath(cached, requestPath)],
    pageParams: [0],
  };
};

const getCachedFirstPageUpdatedAt = (libraryId: number, requestPath: string | null) =>
  queryClient.getQueryState(queryKeys.browse(libraryId, requestPath, IMAGE_PAGE_SIZE))?.dataUpdatedAt;

export function useInfiniteBrowseQuery(
  libraryId: Ref<number | null | undefined>,
  path: Ref<string | null | undefined>,
) {
  const normalizedPath = computed(() => normalizeBrowsePath(path.value));
  const activeLibraryId = computed(() => libraryId.value ?? null);

  const queryKey = computed(() =>
    activeLibraryId.value ? queryKeys.browseInfinite(activeLibraryId.value, normalizedPath.value, IMAGE_PAGE_SIZE) : [],
  );

  const browseQuery = useInfiniteQuery({
    queryKey,
    enabled: computed(() => Boolean(activeLibraryId.value)),
    initialPageParam: 0,
    initialData: () => {
      if (!activeLibraryId.value) return undefined;
      return getCachedFirstPage(activeLibraryId.value, normalizedPath.value);
    },
    initialDataUpdatedAt: () => {
      if (!activeLibraryId.value) return undefined;
      return getCachedFirstPageUpdatedAt(activeLibraryId.value, normalizedPath.value);
    },
    staleTime: 60_000,
    queryFn: async ({ queryKey, pageParam }) => {
      const requestLibraryId = queryKey[1] as number;
      const requestPath = queryKey[2] as string | null;
      const result = await browseDirectory(requestLibraryId, requestPath, {
        limit: IMAGE_PAGE_SIZE,
        cursor: pageParam,
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
    nextMediaCursor,
  };
}
