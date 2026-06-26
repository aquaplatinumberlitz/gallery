import { useQuery, useMutation, useQueryClient } from "@tanstack/vue-query";
import { queryKeys } from "@/query/keys";
import { fetchFileHealth, runFileHealthCheck } from "@/services/api";
import { useToast } from "@/composables/useToast";

export function useFileHealthQuery() {
  return useQuery({
    queryKey: queryKeys.maintenanceFileHealth(),
    queryFn: fetchFileHealth,
    staleTime: 60_000,
  });
}

export function useFileHealthMutation() {
  const queryClient = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: runFileHealthCheck,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.maintenanceFileHealth() });
    },
    onError: (error) => toast.error("Could not run file health check", String(error)),
  });
}
