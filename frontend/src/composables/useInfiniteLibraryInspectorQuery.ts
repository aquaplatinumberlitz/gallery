import { useInfiniteQuery } from "@tanstack/vue-query";
import { computed, onBeforeUnmount, ref, watch, type Ref } from "vue";
import { normalizeQueryPath, queryKeys } from "@/query/keys";
import { fetchLibraryInspector } from "@/services/api";
import type { LibraryInspectorResponse, SearchScope, SortValue } from "@/types";

const EMPTY_RESPONSE: LibraryInspectorResponse = {
  root: "",
  scope: "current",
  query: "",
  limit: 200,
  offset: 0,
  generated_at: 0,
  total_indexed: 0,
  returned: 0,
  truncated: false,
  sort: "date_desc",
  rows: [],
};

export function useInfiniteLibraryInspectorQuery(
  query: Ref<string>,
  scope: Ref<SearchScope>,
  path: Ref<string>,
  limit: Ref<number>,
  sort: Ref<SortValue>
) {
  const debouncedQuery = ref(query.value.trim());
  let searchTimer: number | undefined;

  watch(
    [query, scope, path, sort],
    () => {
      if (searchTimer) {
        window.clearTimeout(searchTimer);
        searchTimer = undefined;
      }
      searchTimer = window.setTimeout(() => {
        debouncedQuery.value = query.value.trim();
      }, 250);
    },
    { flush: "sync" }
  );

  onBeforeUnmount(() => {
    if (searchTimer) {
      window.clearTimeout(searchTimer);
    }
  });

  const requestPath = computed(() =>
    scope.value === "current" ? normalizeQueryPath(path.value || "") : ""
  );
  const requestLimit = computed(() => Math.max(1, limit.value));
  const enabled = computed(() => Boolean(requestPath.value) || scope.value === "all");

  const queryResult = useInfiniteQuery<LibraryInspectorResponse, Error, { pages: LibraryInspectorResponse[]; pageParams: number[] }, ReturnType<typeof queryKeys.libraryInspector>, number>({
    queryKey: computed(() =>
      queryKeys.libraryInspector(debouncedQuery.value, scope.value, requestPath.value, limit.value, sort.value)
    ),
    queryFn: ({ pageParam = 0 }) =>
      fetchLibraryInspector({
        q: debouncedQuery.value,
        scope: scope.value,
        path: requestPath.value,
        limit: requestLimit.value,
        sort: sort.value,
        offset: pageParam,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      if (lastPage.truncated) {
        return allPages.length * requestLimit.value;
      }
      return undefined;
    },
    enabled,
    staleTime: 30_000,
    gcTime: 5 * 60_000,
  });

  const allRows = computed(() =>
    queryResult.data.value?.pages.flatMap((page) => page.rows) ?? []
  );

  const data = computed<LibraryInspectorResponse>(() => {
    const firstPage = queryResult.data.value?.pages[0];
    if (!firstPage) return EMPTY_RESPONSE;
    const lastPage = queryResult.data.value?.pages.at(-1) ?? firstPage;
    return {
      ...firstPage,
      generated_at: lastPage.generated_at,
      returned: allRows.value.length,
      truncated: lastPage.truncated,
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
