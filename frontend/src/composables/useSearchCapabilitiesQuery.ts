import { useQuery } from "@tanstack/vue-query";
import { queryKeys } from "@/query/keys";
import { fetchSearchCapabilities } from "@/services/api";

export function useSearchCapabilitiesQuery() {
  return useQuery({
    queryKey: queryKeys.searchCapabilities(),
    queryFn: ({ signal }) => fetchSearchCapabilities(signal),
    staleTime: 10 * 60_000,
  });
}
