import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { useToast } from "@/composables/useToast";
import { queryKeys } from "@/query/keys";
import { generateMissingImages } from "@/services/api";
import type { GeneratedImageKind } from "@/types";

export function useGeneratedImagesMutations(libraryId: MaybeRefOrGetter<number | null | undefined>) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const resolvedId = computed(() => toValue(libraryId) ?? 0);

  const baseWarmMutation = useMutation({
    mutationFn: (kind: GeneratedImageKind | undefined) => generateMissingImages(resolvedId.value, kind),
    onSuccess: () => {
      toast.success("Image cache preparation queued");
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.generatedImages(resolvedId.value) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.statusLibrary(resolvedId.value) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryJobs(resolvedId.value) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() }),
      ]);
    },
    onError: (error) => toast.error("Could not queue image cache preparation", String(error)),
  });
  const warmMutation = {
    ...baseWarmMutation,
    mutate: (kind?: GeneratedImageKind) => baseWarmMutation.mutate(kind),
    mutateAsync: (kind?: GeneratedImageKind) => baseWarmMutation.mutateAsync(kind),
  };

  return { warmMutation };
}
