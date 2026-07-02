import { useQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { queryKeys } from "@/query/keys";
import { fetchJob } from "@/services/api";

export function useJobQuery(id: MaybeRefOrGetter<number | null | undefined>) {
  return useQuery({
    queryKey: computed(() => queryKeys.job(toValue(id) || 0)),
    queryFn: ({ queryKey }) => {
      const [, requestJobId] = queryKey as ReturnType<typeof queryKeys.job>;
      return fetchJob(requestJobId);
    },
    enabled: computed(() => Boolean(toValue(id))),
  });
}
