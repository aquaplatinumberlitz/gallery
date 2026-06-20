import { useQuery } from "@tanstack/vue-query";
import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { queryKeys } from "@/query/keys";
import { fetchLibraryProgress } from "@/services/api";
import { isLibraryBusy } from "@/utils/libraryStatus";

const ACTIVE_POLL_INTERVAL = 2_500;

export function useLibraryProgressQuery(id: MaybeRefOrGetter<number | null | undefined>) {
  const enabled = computed(() => Boolean(toValue(id)));

  return useQuery({
    queryKey: computed(() => queryKeys.libraryProgress(toValue(id) || 0)),
    queryFn: () => fetchLibraryProgress(toValue(id) || 0),
    enabled,
    refetchInterval: (query) => {
      if (!enabled.value) return false;
      const progress = query.state.data;
      if (!progress) return ACTIVE_POLL_INTERVAL;
      return progress.active_job_id || isLibraryBusy(progress.library_state) || !progress.discovery_complete
        ? ACTIVE_POLL_INTERVAL
        : false;
    },
    refetchOnWindowFocus: () => typeof document === "undefined" || document.visibilityState !== "hidden",
  });
}
