import { useQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { queryKeys } from "@/query/keys";
import { fetchLibrary } from "@/services/api";

export function useLibraryQuery(id: MaybeRefOrGetter<number | null | undefined>) {
  return useQuery({
    queryKey: computed(() => queryKeys.library(toValue(id) || 0)),
    queryFn: () => fetchLibrary(toValue(id) || 0),
    enabled: computed(() => Boolean(toValue(id))),
  });
}
