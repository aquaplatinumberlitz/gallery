import { useQuery } from "@tanstack/vue-query";
import { computed } from "vue";
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
  const query = useQuery({
    queryKey: queryKeys.statusBatch(),
    queryFn: () =>
      fetchLibraryStatusBatch().then((value) => {
        assertLibraryStatusBatch(value);
        return value;
      }),
    staleTime: 5_000,
    retry: (failureCount, error) => {
      if (isStatusContractError(error)) return false;
      return failureCount < 1;
    },
    refetchInterval: (q) => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return false;
      return hasActiveStatus(q.state.data?.items) ? ACTIVE_POLL_INTERVAL : STABLE_POLL_INTERVAL;
    },
    refetchOnWindowFocus: () => typeof document === "undefined" || document.visibilityState !== "hidden",
  });

  const statusByLibrary = computed(() => {
    const items = query.data.value?.items ?? [];
    return new Map<number, UnifiedStatus>(items.map((item) => [item.library_id, item.status]));
  });

  const contractError = computed(() => (isStatusContractError(query.error.value) ? query.error.value : null));

  return { ...query, statusByLibrary, contractError };
}
