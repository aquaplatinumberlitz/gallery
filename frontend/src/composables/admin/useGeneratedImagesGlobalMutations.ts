import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { useToast } from "@/composables/useToast";
import { queryKeys } from "@/query/keys";
import { clearImportedData, GalleryAPIError, rebuildImportedData } from "@/services/api";

function maintenanceMutationErrorMessage(error: unknown): string {
  if (error instanceof GalleryAPIError) {
    return error.suggestion || error.userMessage;
  }
  return error instanceof Error ? error.message : String(error);
}

export function useGeneratedImagesGlobalMutations() {
  const queryClient = useQueryClient();
  const toast = useToast();

  function invalidate(clear = false) {
    const keys: Array<{ queryKey: readonly unknown[] }> = [
      { queryKey: queryKeys.generatedImagesRoot() },
      { queryKey: queryKeys.librariesRoot() },
      { queryKey: queryKeys.galleryStats() },
      { queryKey: queryKeys.jobsRoot() },
      { queryKey: queryKeys.statusRoot() },
      { queryKey: queryKeys.maintenanceRoot() },
    ];
    if (clear) {
      keys.push({ queryKey: queryKeys.browseAllRoot() }, { queryKey: queryKeys.browseInfiniteAllRoot() });
    }
    void Promise.all(keys.map((k) => queryClient.invalidateQueries(k)));
  }

  const rebuildMutation = useMutation({
    mutationFn: rebuildImportedData,
    onSuccess: (data) => {
      toast.success(`Imported data rebuild queued for ${data.count} libraries`);
      invalidate(true);
    },
    onError: (error) => toast.error("Could not rebuild imported data", maintenanceMutationErrorMessage(error)),
  });

  const clearMutation = useMutation({
    mutationFn: clearImportedData,
    onSuccess: () => {
      toast.success("Imported data cleared. Libraries and source files are not affected.");
      invalidate(true);
    },
    onError: (error) => toast.error("Could not clear imported data", maintenanceMutationErrorMessage(error)),
  });

  return { rebuildMutation, clearMutation };
}
