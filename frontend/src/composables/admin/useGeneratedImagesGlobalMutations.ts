import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { useToast } from "@/composables/useToast";
import { queryKeys } from "@/query/keys";
import { clearGeneratedImages, refreshStaleGeneratedImages } from "@/services/api";

export function useGeneratedImagesGlobalMutations() {
  const queryClient = useQueryClient();
  const toast = useToast();

  function invalidate() {
    void Promise.all([
      queryClient.invalidateQueries({ queryKey: ["generated-images"] }),
      queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.statusRoot() }),
    ]);
  }

  const rebuildMutation = useMutation({
    mutationFn: refreshStaleGeneratedImages,
    onSuccess: (data) => {
      toast.success(`Refresh queued for ${data.stale_derivatives} stale items across all libraries`);
      invalidate();
    },
    onError: (error) => toast.error("Could not refresh generated images", String(error)),
  });

  const clearMutation = useMutation({
    mutationFn: clearGeneratedImages,
    onSuccess: () => {
      toast.success("Generated files cleared across all libraries. Source images are not affected.");
      invalidate();
    },
    onError: (error) => toast.error("Could not clear generated images", String(error)),
  });

  return { rebuildMutation, clearMutation };
}
