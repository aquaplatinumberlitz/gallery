import { useQuery } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { refDebounced } from "@vueuse/core";
import { normalizeQueryPath, queryKeys } from "../query/keys";
import { unifiedSearch } from "../services/api";
import type { SearchScope, UnifiedSearchResults } from "../types";
import { parseFieldedQuery } from "../utils/serializeAdvancedSearchToQuery";

export const MIN_PLAIN_SEARCH_QUERY_LENGTH = 2;

export function isExecutableSearchQuery(query: string): boolean {
  const trimmed = query.trim();
  if (!trimmed) return false;
  if (parseFieldedQuery(trimmed).length > 0) return true;
  return trimmed.length >= MIN_PLAIN_SEARCH_QUERY_LENGTH;
}

const EMPTY_SEARCH_RESULTS: UnifiedSearchResults = {
  albums: [],
  photos: [],
  videos: [],
  prompt: [],
};

export function useUnifiedSearchQuery(query: Ref<string>, scope: Ref<SearchScope>, path: Ref<string>) {
  const trimmedQuery = computed(() => query.value.trim());
  const trimmedDebounced = refDebounced(trimmedQuery, 300);
  const debouncedQuery = computed(() =>
    isExecutableSearchQuery(trimmedDebounced.value) ? trimmedDebounced.value : "",
  );

  const normalizedPath = computed(() => normalizeQueryPath(path.value || ""));
  const requestPath = computed(() => (scope.value === "current" ? normalizedPath.value : ""));

  const searchQuery = useQuery({
    queryKey: computed(() => {
      const requestQuery = debouncedQuery.value;
      const requestScope = scope.value;
      const pathForRequest = requestPath.value;
      return requestQuery ? queryKeys.search(requestQuery, requestScope, pathForRequest) : [];
    }),
    queryFn: ({ queryKey }) => {
      const [, requestQuery, requestScope, pathForRequest] = queryKey as ReturnType<typeof queryKeys.search>;
      return unifiedSearch(requestQuery, {
        scope: requestScope as SearchScope,
        path: pathForRequest,
        limit: 100,
      });
    },
    enabled: computed(() => debouncedQuery.value.length > 0),
    placeholderData: (previousData) => previousData,
  });

  const results = computed<UnifiedSearchResults>(() =>
    debouncedQuery.value ? (searchQuery.data.value ?? EMPTY_SEARCH_RESULTS) : EMPTY_SEARCH_RESULTS,
  );

  return {
    ...searchQuery,
    debouncedQuery,
    results,
    albums: computed(() => results.value.albums),
    photos: computed(() => results.value.photos),
    videos: computed(() => results.value.videos ?? []),
    prompt: computed(() => results.value.prompt),
  };
}
