import { useQuery } from "@tanstack/vue-query";
import { queryKeys } from "@/query/keys";
import { fetchJobs } from "@/services/api";

export function useJobsQuery() {
  return useQuery({
    queryKey: queryKeys.jobs(),
    queryFn: fetchJobs,
  });
}
