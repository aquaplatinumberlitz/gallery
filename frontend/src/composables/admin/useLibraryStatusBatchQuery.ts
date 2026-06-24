import { useQuery } from "@tanstack/vue-query";
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useEventListener } from "@vueuse/core";
import { queryKeys } from "@/query/keys";
import { fetchLibraryStatusBatch } from "@/services/api";
import { assertLibraryStatusBatch, isStatusContractError } from "@/lib/catalog/contractGuard";
import { ACTIVE_POLL_INTERVAL, STABLE_POLL_INTERVAL, isUnifiedStatusActive } from "@/lib/catalog/polling";
import type { UnifiedStatus } from "@/lib/catalog/status";

function batchHasActiveStatus(items: { status: UnifiedStatus }[] | undefined): boolean {
  if (!items) return false;
  return items.some(({ status }) => isUnifiedStatusActive(status));
}

export function useLibraryStatusBatchQuery() {
  const isDocumentHidden = ref(false);
  const queryEnabled = computed(() => !isDocumentHidden.value);

  const query = useQuery({
    queryKey: queryKeys.statusBatch(),
    queryFn: () =>
      fetchLibraryStatusBatch().then((value) => {
        assertLibraryStatusBatch(value);
        return value;
      }),
    enabled: queryEnabled,
    staleTime: 5_000,
    retry: (failureCount, error) => {
      if (isStatusContractError(error)) return false;
      return failureCount < 1;
    },
    refetchInterval: (q) => {
      if (!queryEnabled.value) return false;
      return batchHasActiveStatus(q.state.data?.items) ? ACTIVE_POLL_INTERVAL : STABLE_POLL_INTERVAL;
    },
    refetchOnWindowFocus: () => typeof document === "undefined" || document.visibilityState !== "hidden",
  });

  const statusByLibrary = computed(() => {
    const items = query.data.value?.items ?? [];
    return new Map<number, UnifiedStatus>(items.map((item) => [item.library_id, item.status]));
  });

  const contractError = computed(() => (isStatusContractError(query.error.value) ? query.error.value : null));

  let focusTimer: number | undefined;

  function updateDocumentHidden() {
    isDocumentHidden.value = typeof document !== "undefined" && document.visibilityState === "hidden";
  }

  function debouncedFocusRefetch() {
    if (isDocumentHidden.value || typeof window === "undefined") return;
    window.clearTimeout(focusTimer);
    focusTimer = window.setTimeout(() => {
      void query.refetch();
    }, 300);
  }

  function onVisibilityChange() {
    updateDocumentHidden();
    if (!isDocumentHidden.value) debouncedFocusRefetch();
  }

  useEventListener(document, "visibilitychange", onVisibilityChange);
  useEventListener(window, "focus", debouncedFocusRefetch);

  onMounted(() => {
    updateDocumentHidden();
  });

  onUnmounted(() => {
    window.clearTimeout(focusTimer);
  });

  return { ...query, statusByLibrary, contractError };
}
