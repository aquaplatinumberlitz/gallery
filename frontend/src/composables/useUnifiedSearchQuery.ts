import { useQuery } from "@tanstack/vue-query";
import { computed, onBeforeUnmount, ref, watch, type Ref } from "vue";
import { normalizeQueryPath, queryKeys } from "../query/keys";
import { unifiedSearch } from "../services/api";
import type { SearchScope, UnifiedSearchResults } from "../types";

const EMPTY_SEARCH_RESULTS: UnifiedSearchResults = {
  albums: [],
  photos: [],
  prompt: [],
};

export function useUnifiedSearchQuery(query: Ref<string>, scope: Ref<SearchScope>, path: Ref<string>) {
  const debouncedQuery = ref("");
  let searchTimer: number | undefined;

  const trimmedQuery = computed(() => query.value.trim());
  const normalizedPath = computed(() => normalizeQueryPath(path.value || ""));
  const requestPath = computed(() => (scope.value === "current" ? normalizedPath.value : ""));

  watch(
    trimmedQuery,
    (nextQuery) => {
      if (searchTimer) {
        window.clearTimeout(searchTimer);
        searchTimer = undefined;
      }

      if (!nextQuery) {
        debouncedQuery.value = "";
        return;
      }

      searchTimer = window.setTimeout(() => {
        debouncedQuery.value = nextQuery;
      }, 300);
    },
    { immediate: true },
  );

  onBeforeUnmount(() => {
    if (searchTimer) {
      window.clearTimeout(searchTimer);
    }
  });

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
    prompt: computed(() => results.value.prompt),
  };
}
