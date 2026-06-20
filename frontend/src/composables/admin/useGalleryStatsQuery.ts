import { useQuery } from "@tanstack/vue-query";
import { queryKeys } from "@/query/keys";
import { fetchGalleryStats } from "@/services/api";

export function useGalleryStatsQuery() {
  return useQuery({
    queryKey: queryKeys.galleryStats(),
    queryFn: fetchGalleryStats,
  });
}
