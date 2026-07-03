import { useQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { queryKeys } from "@/query/keys";
import { fetchGeneratedImagesStatus } from "@/services/api";
import { ACTIVE_POLL_INTERVAL } from "@/lib/catalog/polling";
import type { GeneratedImagesStatus } from "@/types";

export function generatedImagesNeedActivePolling(data: GeneratedImagesStatus | undefined): boolean {
  if (!data || data.expected_derivatives <= 0) return false;
  return data.ready_derivatives < data.expected_derivatives;
}

export function useGeneratedImagesStatusQuery(libraryId: MaybeRefOrGetter<number | null | undefined>) {
  return useQuery({
    queryKey: computed(() => queryKeys.generatedImages(toValue(libraryId) || 0)),
    queryFn: ({ queryKey }) => {
      const [, , requestLibraryId] = queryKey as ReturnType<typeof queryKeys.generatedImages>;
      return fetchGeneratedImagesStatus(requestLibraryId);
    },
    enabled: computed(() => Boolean(toValue(libraryId))),
    staleTime: 10_000,
    refetchInterval: (q) => (generatedImagesNeedActivePolling(q.state.data) ? ACTIVE_POLL_INTERVAL : false),
  });
}
