import { useQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { queryKeys } from "@/query/keys";
import { fetchLibraryJobs } from "@/services/api";

export function useLibraryJobsQuery(
  id: MaybeRefOrGetter<number | null | undefined>,
  limit?: MaybeRefOrGetter<number | undefined>,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.libraryJobs(toValue(id) || 0, toValue(limit))),
    queryFn: () => fetchLibraryJobs(toValue(id) || 0, toValue(limit)),
    enabled: computed(() => Boolean(toValue(id))),
  });
}
