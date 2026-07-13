import { useInfiniteQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { queryKeys } from "@/query/keys";
import { fetchPromptUsage } from "@/services/api";
import type { PromptUsageQueryRequestV1, PromptUsageResponseV1 } from "@/types";

export function usePromptUsageQuery(
  request: MaybeRefOrGetter<Omit<PromptUsageQueryRequestV1, "cursor"> | null>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const normalizedRequest = computed(() => toValue(request));
  const query = useInfiniteQuery({
    queryKey: computed(() =>
      normalizedRequest.value
        ? queryKeys.promptUsage(normalizedRequest.value)
        : (["prompt-usage", "disabled"] as const),
    ),
    queryFn: ({ pageParam, signal }) =>
      fetchPromptUsage({ ...normalizedRequest.value!, cursor: pageParam ?? null }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage: PromptUsageResponseV1) => lastPage.next_cursor ?? undefined,
    enabled: computed(() => Boolean(normalizedRequest.value) && toValue(enabled)),
    staleTime: 2 * 60_000,
  });

  return {
    ...query,
    items: computed(() => query.data.value?.pages.flatMap((page) => page.items) ?? []),
  };
}
