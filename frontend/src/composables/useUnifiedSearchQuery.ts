import { useInfiniteQuery } from "@tanstack/vue-query";
import { computed, type Ref, watch } from "vue";
import { refDebounced } from "@vueuse/core";
import { queryKeys } from "../query/keys";
import { unifiedSearchV2 } from "../services/api";
import type { SearchQueryRequestV1, UnifiedSearchResponse, UnifiedSearchResult, UnifiedSearchResults } from "../types";
import { GALLERY_SEARCH_DEBOUNCE_MS } from "../constants";
import { recordRecentSearch } from "./useSavedSearches";

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

export function useUnifiedSearchQuery(request: Ref<SearchQueryRequestV1 | null>) {
  const trimmedQuery = computed(() => request.value?.text.trim() ?? "");
  const trimmedDebounced = refDebounced(trimmedQuery, GALLERY_SEARCH_DEBOUNCE_MS);
  const debouncedQuery = computed(() => (trimmedQuery.value ? trimmedDebounced.value : ""));
  const debouncedRequest = computed<SearchQueryRequestV1 | null>(() => {
    if (!request.value) return null;
    if (trimmedQuery.value && debouncedQuery.value !== trimmedQuery.value) return null;
    return { ...request.value, text: debouncedQuery.value };
  });

  const searchQuery = useInfiniteQuery({
    queryKey: computed(() =>
      queryKeys.search(
        debouncedRequest.value ?? {
          schema_version: 1,
          mode: "lexical",
          text: "",
          scope: { kind: "all" },
          filters: { prompt_groups: [], workflow_groups: [] },
          cursor: null,
          limit: SEARCH_PAGE_SIZE,
        },
      ),
    ),
    queryFn: ({ queryKey, pageParam, signal }) => {
      const [, persistable, limit] = queryKey as ReturnType<typeof queryKeys.search>;
      return unifiedSearchV2({ ...persistable, cursor: pageParam ?? null, limit }, signal);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage: UnifiedSearchResponse) => lastPage.next_cursor ?? undefined,
    enabled: computed(() => debouncedRequest.value !== null),
  });

  watch(
    () => searchQuery.data.value?.pages[0],
    (firstPage) => {
      if (firstPage && firstPage.returned > 0 && debouncedRequest.value) {
        recordRecentSearch(debouncedRequest.value);
      }
    },
  );

  const pages = computed(() => searchQuery.data.value?.pages ?? []);
  const results = computed<UnifiedSearchResults>(() => {
    if (
      !debouncedRequest.value ||
      (trimmedQuery.value && trimmedQuery.value !== debouncedQuery.value) ||
      !pages.value.length
    ) {
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
