import { useQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { queryKeys } from "@/query/keys";
import { fetchLibrary } from "@/services/api";

export function useLibraryQuery(id: MaybeRefOrGetter<number | null | undefined>) {
  return useQuery({
    queryKey: computed(() => queryKeys.library(toValue(id) || 0)),
    queryFn: ({ queryKey }) => {
      const [, , requestLibraryId] = queryKey as ReturnType<typeof queryKeys.library>;
      return fetchLibrary(requestLibraryId);
    },
    enabled: computed(() => Boolean(toValue(id))),
  });
}
