import { useQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { queryKeys } from "@/query/keys";
import { fetchGeneratedImagesStatus } from "@/services/api";

export function useGeneratedImagesStatusQuery(libraryId: MaybeRefOrGetter<number | null | undefined>) {
  return useQuery({
    queryKey: computed(() => queryKeys.generatedImages(toValue(libraryId) || 0)),
    queryFn: ({ queryKey }) => {
      const [, , requestLibraryId] = queryKey as ReturnType<typeof queryKeys.generatedImages>;
      return fetchGeneratedImagesStatus(requestLibraryId);
    },
    enabled: computed(() => Boolean(toValue(libraryId))),
    staleTime: 10_000,
  });
}
