import { useQuery } from "@tanstack/vue-query";
import { computed, onMounted, onUnmounted, ref } from "vue";
import { queryKeys } from "@/query/keys";
import { fetchLibraryStatusBatch } from "@/services/api";
import { assertLibraryStatusBatch, isStatusContractError } from "@/lib/catalog/contractGuard";
import type { UnifiedStatus } from "@/lib/catalog/status";

const ACTIVE_POLL_INTERVAL = 2_500;
const STABLE_POLL_INTERVAL = 60_000;

function hasActiveStatus(items: { status: UnifiedStatus }[] | undefined): boolean {
  if (!items) return false;
  return items.some(({ status }) => {
    if (status.scan.state === "queued" || status.scan.state === "scanning") return true;
    if (status.metadata.state === "queued" || status.metadata.state === "indexing") return true;
    return false;
  });
}

export function useLibraryStatusBatchQuery() {
  const isDocumentHidden = ref(false);

  const query = useQuery({
    queryKey: queryKeys.statusBatch(),
    queryFn: () =>
      fetchLibraryStatusBatch().then((value) => {
        assertLibraryStatusBatch(value);
        return value;
      }),
    enabled: !isDocumentHidden.value,
    staleTime: 5_000,
    retry: (failureCount, error) => {
      if (isStatusContractError(error)) return false;
      return failureCount < 1;
    },
    refetchInterval: (q) => {
      if (isDocumentHidden.value) return false;
      return hasActiveStatus(q.state.data?.items) ? ACTIVE_POLL_INTERVAL : STABLE_POLL_INTERVAL;
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

  return { ...query, statusByLibrary, contractError };
}
