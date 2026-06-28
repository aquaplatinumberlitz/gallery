import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { useToast } from "@/composables/useToast";
import { queryKeys } from "@/query/keys";
import { resetCatalogDatabase } from "@/services/api";

export function useCatalogResetMutation() {
  const queryClient = useQueryClient();
  const toast = useToast();

  return useMutation({
    mutationFn: (confirmPhrase: string) => resetCatalogDatabase(confirmPhrase),
    onSuccess: () => {
      toast.success("Catalog database reset. Library registrations and imported data were removed.");
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.generatedImagesRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.librariesRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.galleryStats() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.statusRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.maintenanceRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.browseAllRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.browseInfiniteAllRoot() }),
      ]);
    },
    onError: (error) => toast.error("Could not reset catalog database", String(error)),
  });
}
