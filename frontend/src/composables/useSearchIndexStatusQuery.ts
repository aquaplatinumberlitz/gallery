import { useMutation, useQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { queryClient } from "@/query";
import { queryKeys } from "@/query/keys";
import { cancelSearchIndexJob, fetchSearchIndexes, rebuildSearchIndex } from "@/services/api";

export function useSearchIndexStatusQuery(
  libraryId: MaybeRefOrGetter<number | null>,
  panelOpen: MaybeRefOrGetter<boolean>,
) {
  const resolvedLibraryId = computed(() => toValue(libraryId));
  const statuses = useQuery({
    queryKey: computed(() => queryKeys.searchIndexes(resolvedLibraryId.value)),
    queryFn: ({ signal }) => fetchSearchIndexes(resolvedLibraryId.value, signal),
    enabled: computed(() => toValue(panelOpen)),
    refetchInterval: (query) => {
      const rows = query.state.data;
      return toValue(panelOpen) && rows?.some((row) => ["pending", "building"].includes(row.state)) ? 2_000 : false;
    },
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.searchIndexes(resolvedLibraryId.value) });
  const rebuild = useMutation({
    mutationFn: (request: { indexName: string; libraryId: number; mode?: "missing" | "full" }) =>
      rebuildSearchIndex(request.indexName, request.libraryId, request.mode),
    onSuccess: invalidate,
  });
  const cancel = useMutation({
    mutationFn: (jobId: number) => cancelSearchIndexJob(jobId),
    onSuccess: invalidate,
  });

  return { statuses, rebuild, cancel };
}
