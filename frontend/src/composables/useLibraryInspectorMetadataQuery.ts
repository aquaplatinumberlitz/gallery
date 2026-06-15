import { useQuery } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { queryKeys } from "@/query/keys";
import { fetchLibraryInspectorMetadata } from "@/services/api";

export function useLibraryInspectorMetadataQuery(path: Ref<string>, enabled: Ref<boolean>) {
  return useQuery({
    queryKey: computed(() => queryKeys.libraryInspectorMetadata(path.value)),
    queryFn: ({ queryKey }) => {
      const [, requestPath] = queryKey as ReturnType<typeof queryKeys.libraryInspectorMetadata>;
      return fetchLibraryInspectorMetadata(requestPath);
    },
    enabled: computed(() => enabled.value && path.value.length > 0),
  });
}
