import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { useToast } from "@/composables/useToast";
import { queryKeys } from "@/query/keys";
import {
  clearGeneratedImages,
  generateMissingImages,
  refreshStaleGeneratedImages,
} from "@/services/api";

export function useGeneratedImagesMutations(libraryId: MaybeRefOrGetter<number | null | undefined>) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const resolvedId = computed(() => toValue(libraryId) ?? 0);

  const warmMutation = useMutation({
    mutationFn: () => generateMissingImages(resolvedId.value),
    onSuccess: () => {
      toast.success("Generated images queued");
      invalidate();
    },
    onError: (error) => toast.error("Could not queue generation", String(error)),
  });

  const rebuildMutation = useMutation({
    mutationFn: refreshStaleGeneratedImages,
    onSuccess: (data) => {
      toast.success(`Refresh queued for ${data.stale_derivatives} stale items`);
      invalidate();
    },
    onError: (error) => toast.error("Could not refresh generated images", String(error)),
  });

  const clearMutation = useMutation({
    mutationFn: clearGeneratedImages,
    onSuccess: () => {
      toast.success("Generated files cleared. Source images are not affected.");
      invalidate();
    },
    onError: (error) => toast.error("Could not clear generated images", String(error)),
  });

  function invalidate() {
    const id = resolvedId.value;
    void Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.generatedImages(id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.statusLibrary(id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.libraryJobs(id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.browseRoot(id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.browseInfiniteRoot(id) }),
    ]);
  }

  return { warmMutation, rebuildMutation, clearMutation };
}
