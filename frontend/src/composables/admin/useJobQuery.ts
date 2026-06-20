import { useQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { queryKeys } from "@/query/keys";
import { fetchJob } from "@/services/api";

export function useJobQuery(id: MaybeRefOrGetter<number | null | undefined>) {
  return useQuery({
    queryKey: computed(() => queryKeys.job(toValue(id) || 0)),
    queryFn: () => fetchJob(toValue(id) || 0),
    enabled: computed(() => Boolean(toValue(id))),
  });
}
