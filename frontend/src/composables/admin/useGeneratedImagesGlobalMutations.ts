import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { useToast } from "@/composables/useToast";
import { queryKeys } from "@/query/keys";
import { clearImportedData, rebuildImportedData } from "@/services/api";

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
      { queryKey: queryKeys.searchIndexesRoot() },
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
    onError: (error) => toast.error("Could not rebuild imported data", String(error)),
  });

  const clearMutation = useMutation({
    mutationFn: clearImportedData,
    onSuccess: () => {
      toast.success("Imported data cleared. Libraries and source files are not affected.");
      invalidate(true);
    },
    onError: (error) => toast.error("Could not clear imported data", String(error)),
  });

  return { rebuildMutation, clearMutation };
}
