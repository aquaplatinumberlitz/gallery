import { useQuery } from "@tanstack/vue-query";
import { queryKeys } from "../query/keys";
import { fetchIndexStatus } from "../services/api";
import { type MaybeRefOrGetter, toValue } from "vue";

export function useIndexStatusQuery(enabled: MaybeRefOrGetter<boolean> = true) {
  return useQuery({
    queryKey: queryKeys.indexStatus(),
    queryFn: fetchIndexStatus,
    refetchInterval: 30_000,
    staleTime: 15_000,
    retry: 0,
    enabled: () => toValue(enabled),
  });
}
