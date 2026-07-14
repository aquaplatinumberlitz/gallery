import { computed, toValue, type MaybeRefOrGetter } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { queryKeys } from "@/query/keys";
import { fetchRelatedAssets, GalleryAPIError } from "@/services/api";
import type { RelatedSearchRequestV1 } from "@/types";

export function useRelatedAssetsQuery(request: MaybeRefOrGetter<RelatedSearchRequestV1 | null>) {
  const resolvedRequest = computed(() => toValue(request));

  return useQuery({
    queryKey: computed(() =>
      resolvedRequest.value ? queryKeys.relatedAssets(resolvedRequest.value) : (["related-assets", "idle"] as const),
    ),
    queryFn: ({ signal }) => {
      const value = resolvedRequest.value;
      if (!value) throw new Error("Related Assets request is unavailable");
      return fetchRelatedAssets(value, signal);
    },
    enabled: computed(() => resolvedRequest.value !== null),
    staleTime: 30_000,
    gcTime: 10 * 60_000,
    retry: (failureCount, error) => error instanceof GalleryAPIError && error.canRetry && failureCount < 2,
  });
}
