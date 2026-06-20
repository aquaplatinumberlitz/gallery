import { useQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { queryKeys } from "@/query/keys";
import { fetchLibraryStats } from "@/services/api";

export function useLibraryStatsQuery(id: MaybeRefOrGetter<number | null | undefined>) {
  return useQuery({
    queryKey: computed(() => queryKeys.libraryStats(toValue(id) || 0)),
    queryFn: () => fetchLibraryStats(toValue(id) || 0),
    enabled: computed(() => Boolean(toValue(id))),
  });
}
