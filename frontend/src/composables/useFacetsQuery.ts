import { useQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { normalizeQueryPath, queryKeys } from "../query/keys";
import { fetchFacets } from "../services/api";

export function useFacetsQuery(
  path: MaybeRefOrGetter<string | null | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
  allowGlobal = false,
) {
  const rawPath = computed(() => toValue(path));
  const normalizedPath = computed(() => normalizeQueryPath(rawPath.value || ""));
  const hasScope = computed(() => normalizedPath.value.length > 0 || (allowGlobal && rawPath.value === null));

  return useQuery({
    queryKey: computed(() => (hasScope.value ? queryKeys.facets(normalizedPath.value) : [])),
    queryFn: ({ queryKey }) => {
      const [, requestPath] = queryKey as ReturnType<typeof queryKeys.facets>;
      return fetchFacets(requestPath || undefined);
    },
    enabled: computed(() => toValue(enabled) && hasScope.value),
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
  });
}
