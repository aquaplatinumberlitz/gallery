import { useQuery } from "@tanstack/vue-query";
import { queryKeys } from "@/query/keys";
import { fetchLibraries } from "@/services/api";

export function useLibrariesQuery() {
  return useQuery({
    queryKey: queryKeys.libraries(),
    queryFn: fetchLibraries,
  });
}
