import { useInfiniteQuery } from "@tanstack/vue-query";
import { computed, watch, type Ref } from "vue";
import { IMAGE_PAGE_SIZE } from "../constants";
import { normalizeBrowsePath, queryKeys } from "../query/keys";
import { browseDirectory } from "../services/api";
import { useGalleryStore } from "../stores/gallery";
import type { BrowseResponse } from "../types";

const withBrowseRequestPath = (data: BrowseResponse, requestPath: string | null): BrowseResponse => ({
  ...data,
  request_path: requestPath,
});

export function useSidebarTreeQuery(libraryId: Ref<number | null | undefined>, path: Ref<string | null | undefined>) {
  const galleryStore = useGalleryStore();
  const activeLibraryId = computed(() => libraryId.value ?? null);
  const normalizedPath = computed(() => normalizeBrowsePath(path.value));

  const query = useInfiniteQuery({
    queryKey: computed(() =>
      activeLibraryId.value
        ? queryKeys.browseInfinite(activeLibraryId.value, normalizedPath.value, IMAGE_PAGE_SIZE, false)
        : [],
    ),
    enabled: computed(() => Boolean(activeLibraryId.value)),
    initialPageParam: 0,
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

  const folders = computed(() => (activeLibraryId.value ? (query.data.value?.pages[0]?.folders ?? []) : []));

  watch(
    folders,
    (nodes) => {
      galleryStore.setSidebarTree(nodes);
    },
    { immediate: true },
  );

  watch(
    [() => activeLibraryId.value, () => query.isLoading.value, () => query.isFetching.value],
    ([id, loading, fetching]) => {
      galleryStore.isLoading = Boolean(id) && (loading || fetching);
    },
    { immediate: true },
  );

  return {
    ...query,
    browsePath: normalizedPath,
    folders,
  };
}
