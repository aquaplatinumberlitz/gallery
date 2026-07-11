import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { useToast } from "@/composables/useToast";
import { queryKeys } from "@/query/keys";
import { fetchOfflineLibraryAssets, forgetOfflineLibraryAssets, GalleryAPIError } from "@/services/api";

export function useOfflineLibraryAssets(
  libraryId: MaybeRefOrGetter<number | null | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const id = computed(() => toValue(libraryId) || 0);

  const query = useQuery({
    queryKey: computed(() => queryKeys.offlineLibraryAssets(id.value)),
    queryFn: () => fetchOfflineLibraryAssets(id.value),
    enabled: computed(() => Boolean(id.value) && toValue(enabled)),
  });

  const forgetMutation = useMutation({
    mutationFn: () => forgetOfflineLibraryAssets(id.value),
    onSuccess: async (response) => {
      toast.success(
        response.forgotten === 1 ? "Unavailable file forgotten" : `${response.forgotten} unavailable files forgotten`,
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.offlineLibraryAssets(id.value) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryStats(id.value) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.library(id.value) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraries() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.galleryStats() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.generatedImages(id.value) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.statusLibrary(id.value) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.statusPathRoot(id.value) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.statusBatch() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.browseRoot(id.value) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.browseInfiniteRoot(id.value) }),
      ]);
    },
    onError: (error) => {
      const detail = error instanceof GalleryAPIError ? error.userMessage : "An unexpected error occurred.";
      toast.error("Could not forget unavailable files", detail);
    },
  });

  return { query, forgetMutation };
}
