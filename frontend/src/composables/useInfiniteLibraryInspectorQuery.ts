import { useInfiniteQuery } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { refDebounced } from "@vueuse/core";
import { normalizeQueryPath, queryKeys } from "@/query/keys";
import { fetchLibraryInspector } from "@/services/api";
import type { LibraryInspectorResponse, PromptPresenceFilter, SearchScope, SortValue } from "@/types";

const EMPTY_RESPONSE: LibraryInspectorResponse = {
  root: "",
  scope: "current",
  query: "",
  limit: 200,
  generated_at: 0,
  total_indexed: 0,
  returned: 0,
  truncated: false,
  next_cursor: null,
  has_more: false,
  sort: "date_desc",
  rows: [],
};

interface UseInfiniteLibraryInspectorQueryOptions {
  query: Ref<string>;
  scope: Ref<SearchScope>;
  path: Ref<string>;
  limit: Ref<number>;
  sort: Ref<SortValue>;
  model: Ref<string>;
  prompt: Ref<PromptPresenceFilter>;
}

export function useInfiniteLibraryInspectorQuery({
  query,
  scope,
  path,
  limit,
  sort,
  model,
  prompt,
}: UseInfiniteLibraryInspectorQueryOptions) {
  const trimmedQuery = computed(() => query.value.trim());
  const debouncedQuery = refDebounced(trimmedQuery, 250);

  const requestPath = computed(() => (scope.value === "current" ? normalizeQueryPath(path.value || "") : ""));
  const requestLimit = computed(() => Math.max(1, limit.value));
  const enabled = computed(() => Boolean(requestPath.value) || scope.value === "all");

  const queryResult = useInfiniteQuery<
    LibraryInspectorResponse,
    Error,
    { pages: LibraryInspectorResponse[]; pageParams: (string | undefined)[] },
    ReturnType<typeof queryKeys.libraryInspector>,
    string | undefined
  >({
    queryKey: computed(() =>
      queryKeys.libraryInspector(
        debouncedQuery.value,
        scope.value,
        requestPath.value,
        requestLimit.value,
        sort.value,
        model.value,
        prompt.value,
      ),
    ),
    queryFn: ({ queryKey, pageParam }) => {
      const [, requestQuery, requestScope, pathForRequest, requestLimit, requestSort, requestModel, requestPrompt] =
        queryKey as ReturnType<typeof queryKeys.libraryInspector>;
      return fetchLibraryInspector({
        q: requestQuery,
        scope: requestScope as SearchScope,
        path: pathForRequest,
        limit: Math.max(1, requestLimit),
        sort: requestSort,
        cursor: pageParam,
        model: requestModel,
        prompt: requestPrompt,
      });
    },
    initialPageParam: undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled,
    staleTime: 30_000,
    gcTime: 5 * 60_000,
  });

  const allRows = computed(() => queryResult.data.value?.pages.flatMap((page) => page.rows) ?? []);

  const data = computed<LibraryInspectorResponse>(() => {
    const firstPage = queryResult.data.value?.pages[0];
    if (!firstPage) return EMPTY_RESPONSE;
    const lastPage = queryResult.data.value?.pages.at(-1) ?? firstPage;
    return {
      ...firstPage,
      generated_at: lastPage.generated_at,
      returned: allRows.value.length,
      truncated: lastPage.truncated,
      next_cursor: lastPage.next_cursor ?? null,
      has_more: lastPage.has_more ?? Boolean(lastPage.next_cursor),
      rows: allRows.value,
    };
  });

  const totalIndexed = computed(() => data.value.total_indexed);

  return {
    ...queryResult,
    data,
    rows: allRows,
    allRows,
    totalIndexed,
    debouncedQuery,
  };
}
