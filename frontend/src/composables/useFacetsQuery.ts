import { useQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { normalizeQueryPath, queryKeys } from "../query/keys";
import { fetchFacets } from "../services/api";
import type { FacetRequestContext } from "../types";

export function useFacetsQuery(
  context: MaybeRefOrGetter<FacetRequestContext>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const requestContext = computed(() => {
    const value = toValue(context);
    return {
      scope: value.scope,
      libraryId: value.libraryId ?? null,
      path: value.scope === "folder" ? normalizeQueryPath(value.path) : "",
    } satisfies FacetRequestContext;
  });
  const hasScope = computed(
    () =>
      requestContext.value.scope === "all" ||
      (requestContext.value.libraryId !== null &&
        (requestContext.value.scope === "library" || requestContext.value.path.length > 0)),
  );

  return useQuery({
    queryKey: computed(() =>
      hasScope.value
        ? queryKeys.facets(requestContext.value.scope, requestContext.value.libraryId, requestContext.value.path)
        : [],
    ),
    queryFn: ({ signal }) => {
      return fetchFacets(requestContext.value, signal);
    },
    enabled: computed(() => toValue(enabled) && hasScope.value),
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
  });
}
