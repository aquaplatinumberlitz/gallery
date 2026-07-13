import { useInfiniteQuery } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { refDebounced } from "@vueuse/core";
import { normalizeQueryPath, queryKeys } from "../query/keys";
import { unifiedSearch } from "../services/api";
import type { SearchScope, UnifiedSearchResponse, UnifiedSearchResult, UnifiedSearchResults } from "../types";
import { GALLERY_SEARCH_DEBOUNCE_MS } from "../constants";

export const SEARCH_PAGE_SIZE = 60;

const EMPTY_SEARCH_RESULTS: UnifiedSearchResults = {
  albums: [],
  photos: [],
  videos: [],
  prompt: [],
  media: [],
};

const canonicalResultKey = (result: UnifiedSearchResult) =>
  typeof result.library_id === "number" && typeof result.asset_id === "number"
    ? `asset:${result.library_id}:${result.asset_id}`
    : `path:${result.path.trim()}`;

const dedupeCanonicalResults = (results: UnifiedSearchResult[]) => {
  const seen = new Set<string>();
  return results.filter((result) => {
    const key = canonicalResultKey(result);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
};

export function useUnifiedSearchQuery(query: Ref<string>, scope: Ref<SearchScope>, path: Ref<string>) {
  const trimmedQuery = computed(() => query.value.trim());
  const trimmedDebounced = refDebounced(trimmedQuery, GALLERY_SEARCH_DEBOUNCE_MS);
  const debouncedQuery = computed(() => (trimmedQuery.value ? trimmedDebounced.value : ""));

  const normalizedPath = computed(() => normalizeQueryPath(path.value || ""));
  const requestPath = computed(() => (scope.value === "current" ? normalizedPath.value : ""));

  const searchQuery = useInfiniteQuery({
    queryKey: computed(() => {
      const requestQuery = debouncedQuery.value;
      const requestScope = scope.value;
      const pathForRequest = requestPath.value;
      return queryKeys.search(requestQuery, requestScope, pathForRequest, SEARCH_PAGE_SIZE);
    }),
    queryFn: ({ queryKey, pageParam, signal }) => {
      const [, requestQuery, requestScope, pathForRequest, limit] = queryKey as ReturnType<typeof queryKeys.search>;
      return unifiedSearch(
        requestQuery,
        {
          scope: requestScope as SearchScope,
          path: pathForRequest,
          limit,
          cursor: pageParam ?? undefined,
        },
        signal,
      );
    },
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage: UnifiedSearchResponse) => lastPage.next_cursor ?? undefined,
    enabled: computed(() => debouncedQuery.value.length > 0),
  });

  const pages = computed(() => searchQuery.data.value?.pages ?? []);
  const results = computed<UnifiedSearchResults>(() => {
    if (!debouncedQuery.value || trimmedQuery.value !== debouncedQuery.value || !pages.value.length) {
      return EMPTY_SEARCH_RESULTS;
    }
    const [firstPage] = pages.value;
    const pageMedia = (page: UnifiedSearchResponse) =>
      page.media !== undefined ? page.media : [...page.photos, ...(page.videos ?? []), ...page.prompt];
    const media = dedupeCanonicalResults(pages.value.flatMap(pageMedia));
    return {
      albums: firstPage?.albums ?? [],
      photos: dedupeCanonicalResults(pages.value.flatMap((page) => page.photos ?? [])),
      videos: dedupeCanonicalResults(pages.value.flatMap((page) => page.videos ?? [])),
      prompt: dedupeCanonicalResults(pages.value.flatMap((page) => page.prompt ?? [])),
      media,
    };
  });

  return {
    ...searchQuery,
    debouncedQuery,
    results,
    albums: computed(() => results.value.albums),
    media: computed(() => results.value.media ?? []),
    photos: computed(() => results.value.photos),
    videos: computed(() => results.value.videos ?? []),
    prompt: computed(() => results.value.prompt),
  };
}
