import { useQuery } from "@tanstack/vue-query";
import { queryKeys } from "@/query/keys";
import { fetchMaintenanceRuntime } from "@/services/api";

export function useMaintenanceRuntimeQuery() {
  return useQuery({
    queryKey: queryKeys.maintenanceRuntime(),
    queryFn: fetchMaintenanceRuntime,
    staleTime: 30_000,
  });
}
