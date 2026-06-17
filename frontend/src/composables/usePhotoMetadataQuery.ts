import { useQuery } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { queryKeys } from "../query/keys";
import { fetchMetadata } from "../services/api";

export function usePhotoMetadataQuery(isOpen: Ref<boolean>, path: Ref<string>) {
  const metadataPath = computed(() => path.value.trim());

  return useQuery({
    queryKey: computed(() => (metadataPath.value ? queryKeys.metadata(metadataPath.value) : [])),
    queryFn: () => fetchMetadata(metadataPath.value),
    enabled: computed(() => isOpen.value && metadataPath.value.length > 0),
    staleTime: 10 * 60_000,
    gcTime: 30 * 60_000,
  });
}
