import { useQuery } from "@tanstack/vue-query";
import { computed, onBeforeUnmount, ref, watch, type Ref } from "vue";
import { normalizeQueryPath, queryKeys } from "@/query/keys";
import { fetchLibraryInspector } from "@/services/api";
import type { LibraryInspectorResponse, SearchScope, SortValue } from "@/types";

const EMPTY_RESPONSE: LibraryInspectorResponse = {
  root: "",
  scope: "current",
  query: "",
  limit: 200,
  generated_at: 0,
  total_indexed: 0,
  returned: 0,
  truncated: false,
  sort: "date_desc",
  rows: [],
};

export function useLibraryInspectorQuery(
  query: Ref<string>,
  scope: Ref<SearchScope>,
  path: Ref<string>,
  limit: Ref<number>,
  sort: Ref<SortValue>
) {
  const debouncedQuery = ref(query.value.trim());
  let searchTimer: number | undefined;

  watch(
    () => query.value.trim(),
    (nextQuery) => {
      if (searchTimer) {
        window.clearTimeout(searchTimer);
        searchTimer = undefined;
      }
      searchTimer = window.setTimeout(() => {
        debouncedQuery.value = nextQuery;
      }, 250);
    },
    { immediate: true }
  );

  onBeforeUnmount(() => {
    if (searchTimer) {
      window.clearTimeout(searchTimer);
    }
  });

  const requestPath = computed(() =>
    scope.value === "current" ? normalizeQueryPath(path.value || "") : ""
  );

  const inspectorQuery = useQuery({
    queryKey: computed(() =>
      queryKeys.libraryInspector(debouncedQuery.value, scope.value, requestPath.value, limit.value, sort.value)
    ),
    queryFn: ({ queryKey }) => {
      const [, requestQuery, requestScope, pathForRequest, requestLimit, requestSort] =
        queryKey as ReturnType<typeof queryKeys.libraryInspector>;
      return fetchLibraryInspector({
        q: requestQuery,
        scope: requestScope as SearchScope,
        path: pathForRequest,
        limit: requestLimit,
        sort: requestSort,
      });
    },
    placeholderData: (previousData) => previousData,
  });

  const data = computed(() => inspectorQuery.data.value ?? EMPTY_RESPONSE);
  const rows = computed(() => data.value.rows);

  return {
    ...inspectorQuery,
    data,
    rows,
    debouncedQuery,
  };
}
