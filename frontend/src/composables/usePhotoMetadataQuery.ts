import { useQuery } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { queryKeys } from "../query/keys";
import { fetchMetadata, isUnreadableImageError } from "../services/api";

export function usePhotoMetadataQuery(
  isOpen: Ref<boolean>,
  path: Ref<string>,
  contentVersion: Ref<string | null | undefined>,
) {
  const metadataPath = computed(() => path.value.trim());

  return useQuery({
    queryKey: computed(() => (metadataPath.value ? queryKeys.metadata(metadataPath.value, contentVersion.value) : [])),
    queryFn: ({ queryKey }) => {
      const [, requestPath] = queryKey as ReturnType<typeof queryKeys.metadata>;
      return fetchMetadata(requestPath);
    },
    enabled: computed(() => isOpen.value && metadataPath.value.length > 0),
    // image_unreadable is permanent: do not retry it, so the lightbox shows the error without a spinner delay.
    retry: (failureCount, error) => !isUnreadableImageError(error) && failureCount < 1,
    staleTime: 10 * 60_000,
    gcTime: 30 * 60_000,
  });
}
