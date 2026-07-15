import { useQuery } from "@tanstack/vue-query";
import { computed, toValue, type MaybeRefOrGetter } from "vue";
import { refDebounced } from "@vueuse/core";
import { queryKeys } from "../query/keys";
import { searchCountV2 } from "../services/api";
import type { PersistableSearchRequestV1, SearchQueryRequestV1 } from "@/types";
import { GALLERY_SEARCH_DEBOUNCE_MS } from "../constants";

export type SearchMatchPreviewStatus = "idle" | "loading" | "error" | "done";

export interface SearchMatchPreviewState {
  status: SearchMatchPreviewStatus;
  total: number;
  hasMore: boolean;
}

export interface UseSearchMatchPreviewOptions {
  enabled?: MaybeRefOrGetter<boolean>;
  debounceMs?: number;
}

const IDLE_STATE: SearchMatchPreviewState = {
  status: "idle",
  total: 0,
  hasMore: false,
};

export function useSearchMatchPreview(
  request: MaybeRefOrGetter<PersistableSearchRequestV1 | null>,
  options: UseSearchMatchPreviewOptions = {},
) {
  const { enabled = true, debounceMs = GALLERY_SEARCH_DEBOUNCE_MS } = options;

  const latestRequest = computed(() => toValue(request));
  const debouncedRequest = refDebounced(latestRequest, debounceMs);
  const effectiveRequest = computed<PersistableSearchRequestV1 | null>(() =>
    latestRequest.value ? debouncedRequest.value : null,
  );

  const fullRequest = computed<SearchQueryRequestV1 | null>(() => {
    const persistable = effectiveRequest.value;
    if (!persistable) return null;
    return { ...persistable, cursor: null, limit: 1 };
  });

  const countQuery = useQuery({
    queryKey: computed(() =>
      fullRequest.value ? queryKeys.searchCount(fullRequest.value) : ["search-count", "disabled"],
    ),
    queryFn: ({ signal }) => searchCountV2(fullRequest.value as SearchQueryRequestV1, signal),
    enabled: computed(() => toValue(enabled) && fullRequest.value !== null),
    staleTime: 30_000,
    gcTime: 60_000,
  });

  const state = computed<SearchMatchPreviewState>(() => {
    if (!effectiveRequest.value) return IDLE_STATE;
    if (countQuery.isError.value) {
      return { status: "error", total: 0, hasMore: false };
    }
    const data = countQuery.data.value;
    if (!data) return { status: "loading", total: 0, hasMore: false };
    return {
      status: "done",
      total: data.total,
      hasMore: data.has_more,
    };
  });

  return {
    state,
    isFetching: computed(() => countQuery.isFetching.value),
  };
}
