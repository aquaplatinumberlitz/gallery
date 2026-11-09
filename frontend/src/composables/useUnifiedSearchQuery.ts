import { keepPreviousData, useInfiniteQuery } from "@tanstack/vue-query";
import { computed, type Ref, watch } from "vue";
import { refDebounced } from "@vueuse/core";
import { queryKeys } from "../query/keys";
import { unifiedSearchV2 } from "../services/api";
import type { SearchQueryRequestV1, UnifiedSearchResponse, UnifiedSearchResult, UnifiedSearchResults } from "../types";
import { GALLERY_SEARCH_DEBOUNCE_MS } from "../constants";
import { recordRecentSearch } from "./useRecentSearches";

export const SEARCH_PAGE_SIZE = 60;

export interface UseUnifiedSearchQueryOptions {
  /** The text the user submitted with Enter (`galleryStore.submittedSearchQuery`). */
  submittedQuery?: Ref<string>;
}

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
    : `path:${result.path}`;

const dedupeCanonicalResults = (results: UnifiedSearchResult[]) => {
  const seen = new Set<string>();
  return results.filter((result) => {
    const key = canonicalResultKey(result);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
};

export function useUnifiedSearchQuery(
  request: Ref<SearchQueryRequestV1 | null>,
  options: UseUnifiedSearchQueryOptions = {},
) {
  const trimmedQuery = computed(() => request.value?.text.trim() ?? "");
  const trimmedDebounced = refDebounced(trimmedQuery, GALLERY_SEARCH_DEBOUNCE_MS);
  // SE-02: Enter submits the typed text, so that text settles at once instead of after the debounce.
  const submittedNow = computed(
    () => Boolean(trimmedQuery.value) && (options.submittedQuery?.value.trim() ?? "") === trimmedQuery.value,
  );
  const settledText = computed(() => (submittedNow.value ? trimmedQuery.value : trimmedDebounced.value));
  const debouncedQuery = computed(() => (trimmedQuery.value ? settledText.value : ""));
  // SE-01: while the newer text is still settling, the request (and so the shown results) stays on the last settled
  // text. Only a cleared request (null) has no results.
  const debouncedRequest = computed<SearchQueryRequestV1 | null>(() => {
    if (!request.value) return null;
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
    // SE-01: keep the previous settled pages while the next text's first page is pending. A cleared request keeps
    // nothing, so stale results cannot reappear when the user types again.
    placeholderData: (previousData) => (debouncedRequest.value ? keepPreviousData(previousData) : undefined),
  });

  watch(
    () => searchQuery.data.value?.pages[0],
    (firstPage) => {
      // Placeholder pages belong to the previous text, so they are not recorded for the current request.
      if (firstPage && firstPage.returned > 0 && debouncedRequest.value && !searchQuery.isPlaceholderData.value) {
        recordRecentSearch(debouncedRequest.value);
      }
    },
  );

  const pages = computed(() => searchQuery.data.value?.pages ?? []);
  const results = computed<UnifiedSearchResults>(() => {
    if (!debouncedRequest.value || !pages.value.length) {
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
