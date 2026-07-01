import { useQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { queryKeys } from "@/query/keys";
import { fetchJobs } from "@/services/api";

export function useJobsQuery(limit?: MaybeRefOrGetter<number | undefined>) {
  return useQuery({
    queryKey: computed(() => queryKeys.jobs(toValue(limit))),
    queryFn: () => fetchJobs(toValue(limit)),
  });
}
