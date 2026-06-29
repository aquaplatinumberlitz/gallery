import { useQuery } from "@tanstack/vue-query";
import { computed, watch, type Ref } from "vue";
import { IMAGE_PAGE_SIZE } from "../constants";
import { normalizeBrowsePath, queryKeys } from "../query/keys";
import { browseDirectory } from "../services/api";
import { useGalleryStore } from "../stores/gallery";

export function useSidebarTreeQuery(libraryId: Ref<number | null | undefined>, path: Ref<string | null | undefined>) {
  const galleryStore = useGalleryStore();
  const activeLibraryId = computed(() => libraryId.value ?? null);
  const normalizedPath = computed(() => normalizeBrowsePath(path.value));

  const query = useQuery({
    queryKey: computed(() =>
      activeLibraryId.value
        ? queryKeys.browse(activeLibraryId.value, normalizedPath.value, IMAGE_PAGE_SIZE, false)
        : [],
    ),
    enabled: computed(() => Boolean(activeLibraryId.value)),
    staleTime: 60_000,
    queryFn: async ({ queryKey }) => {
      const requestLibraryId = queryKey[1] as number;
      const requestPath = queryKey[2] as string | null;
      return browseDirectory(requestLibraryId, requestPath, { limit: IMAGE_PAGE_SIZE });
    },
  });

  const folders = computed(() => (activeLibraryId.value ? (query.data.value?.folders ?? []) : []));

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
