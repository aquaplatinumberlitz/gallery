import { useQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { normalizeQueryPath, queryKeys } from "../query/keys";
import { fetchFacets } from "../services/api";

export function useFacetsQuery(
  path: MaybeRefOrGetter<string | null | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true
) {
  const normalizedPath = computed(() => normalizeQueryPath(toValue(path) || ""));

  return useQuery({
    queryKey: computed(() =>
      normalizedPath.value ? queryKeys.facets(normalizedPath.value) : []
    ),
    queryFn: ({ queryKey }) => {
      const [, requestPath] = queryKey as ReturnType<typeof queryKeys.facets>;
      return fetchFacets(requestPath);
    },
    enabled: computed(() => toValue(enabled) && normalizedPath.value.length > 0),
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
  });
}
