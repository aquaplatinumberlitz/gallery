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

/** How long a browse page stays fresh; a page prefetched before mount (see `utils/homeBrowsePrefetch`) is reused within it. */
export const BROWSE_STALE_TIME_MS = 60_000;

/** The infinite browse query key. Shared with the pre-mount prefetch so the mounted query reuses its result. */
export const browseInfiniteQueryKey = (libraryId: number, path: string | null | undefined, includeOffline = false) =>
  queryKeys.browseInfinite(libraryId, normalizeBrowsePath(path), IMAGE_PAGE_SIZE, includeOffline);

/** The infinite browse query function (one page per `pageParam` cursor), shared with the pre-mount prefetch. */
export async function fetchBrowsePage({ queryKey, pageParam }: { queryKey: readonly unknown[]; pageParam: number }) {
  const requestLibraryId = queryKey[1] as number;
  const requestPath = queryKey[2] as string | null;
  const requestIncludeOffline = queryKey[4] as boolean;
  const result = await browseDirectory(requestLibraryId, requestPath, {
    limit: IMAGE_PAGE_SIZE,
    cursor: pageParam,
    includeOffline: requestIncludeOffline,
  });
  return withBrowseRequestPath(result, requestPath);
}

export const getNextBrowsePageParam = (lastPage: BrowseResponse) =>
  lastPage.next_media_cursor ?? lastPage.next_cursor ?? undefined;

export interface InfiniteBrowseQueryOptions {
  /**
   * Called from the query function with each freshly fetched first page, before the data reaches Vue.
   * Album open uses it to start the first viewport's thumbnails ahead of the render that mounts the grid.
   * A returned promise is awaited, so the callback can end its task and let the render start in the next one.
   * Errors thrown here never fail the query.
   */
  onFirstPageFetched?: (page: BrowseResponse) => void | Promise<void>;
}

export function useInfiniteBrowseQuery(
  libraryId: Ref<number | null | undefined>,
  path: Ref<string | null | undefined>,
  includeOffline?: Ref<boolean>,
  options: InfiniteBrowseQueryOptions = {},
) {
  const normalizedPath = computed(() => normalizeBrowsePath(path.value));
  const activeLibraryId = computed(() => libraryId.value ?? null);
  const activeIncludeOffline = computed(() => includeOffline?.value ?? false);

  const queryKey = computed(() =>
    activeLibraryId.value
      ? browseInfiniteQueryKey(activeLibraryId.value, normalizedPath.value, activeIncludeOffline.value)
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
    staleTime: BROWSE_STALE_TIME_MS,
    queryFn: async (context) => {
      const page = await fetchBrowsePage(context);
      if (context.pageParam === 0 && options.onFirstPageFetched) {
        try {
          await options.onFirstPageFetched(page);
        } catch {
          // A warm-up hint must never fail the browse request.
        }
      }
      return page;
    },
    getNextPageParam: getNextBrowsePageParam,
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
