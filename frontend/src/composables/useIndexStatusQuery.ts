import { useQuery } from "@tanstack/vue-query";
import { computed, onMounted, onUnmounted, ref, type MaybeRefOrGetter, toValue } from "vue";
import { normalizeQueryPath, queryKeys } from "../query/keys";
import { fetchIndexStatus } from "../services/api";
import { getIndexStatusRefetchInterval } from "../utils/indexStatus";

export function useIndexStatusQuery(
  path: MaybeRefOrGetter<string | null | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const isDocumentHidden = ref(false);
  const normalizedPath = computed(() => normalizeQueryPath(toValue(path) || ""));
  const queryEnabled = computed(() => toValue(enabled) && normalizedPath.value.length > 0);

  const query = useQuery({
    queryKey: computed(() => (normalizedPath.value ? queryKeys.indexStatus(normalizedPath.value) : [])),
    queryFn: ({ queryKey }) => {
      const [, requestPath] = queryKey as ReturnType<typeof queryKeys.indexStatus>;
      return fetchIndexStatus(requestPath);
    },
    refetchInterval: (query) => {
      if (!queryEnabled.value || isDocumentHidden.value) return false;
      return getIndexStatusRefetchInterval(query.state.data, query.state.status === "error");
    },
    staleTime: 15_000,
    retry: 0,
    refetchOnWindowFocus: false,
    enabled: queryEnabled,
  });

  let focusTimer: number | undefined;

  function updateDocumentHidden() {
    isDocumentHidden.value = typeof document !== "undefined" && document.visibilityState === "hidden";
  }

  function debouncedFocusRefetch() {
    if (!queryEnabled.value || isDocumentHidden.value || typeof window === "undefined") return;
    window.clearTimeout(focusTimer);
    focusTimer = window.setTimeout(() => {
      void query.refetch();
    }, 300);
  }

  function onVisibilityChange() {
    updateDocumentHidden();
    if (!isDocumentHidden.value) {
      debouncedFocusRefetch();
    }
  }

  onMounted(() => {
    updateDocumentHidden();
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("focus", debouncedFocusRefetch);
  });

  onUnmounted(() => {
    document.removeEventListener("visibilitychange", onVisibilityChange);
    window.removeEventListener("focus", debouncedFocusRefetch);
    window.clearTimeout(focusTimer);
  });

  return query;
}
