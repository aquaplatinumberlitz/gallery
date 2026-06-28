import { useQuery } from "@tanstack/vue-query";
import { queryKeys } from "@/query/keys";
import { fetchMaintenanceRuntime } from "@/services/api";
import { ACTIVE_POLL_INTERVAL, STABLE_POLL_INTERVAL } from "@/lib/catalog/polling";
import type { MaintenanceRuntimeResponse } from "@/services/api";

export function runtimeHasActiveWork(data: MaintenanceRuntimeResponse | undefined): boolean {
  if (!data) return false;
  const gr = data.global_runtime;
  if (gr.catalog_active_jobs > 0 || gr.catalog_queue_depth > 0) return true;
  if (gr.metadata_active_jobs > 0 || gr.metadata_queue_depth > 0) return true;
  const lc = data.metadata_lifecycle;
  if (lc) {
    if (lc.queued_metadata_jobs > 0 || lc.running_metadata_jobs > 0) return true;
  }
  return false;
}

export function useMaintenanceRuntimeQuery() {
  return useQuery({
    queryKey: queryKeys.maintenanceRuntime(),
    queryFn: fetchMaintenanceRuntime,
    staleTime: 30_000,
    refetchInterval: (q) => (runtimeHasActiveWork(q.state.data) ? ACTIVE_POLL_INTERVAL : STABLE_POLL_INTERVAL),
  });
}
