import { useQuery } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { queryKeys, normalizeQueryPath } from "../query/keys";
import { listFolderChildren } from "../services/api";
import type { FileNode } from "../types";

const normalizeFolderChildren = (nodes: FileNode[]): FileNode[] =>
  nodes.filter((node) => node.type === "folder");

export function useFolderChildrenQuery(path: Ref<string>, enabled: Ref<boolean>) {
  const normalizedPath = computed(() => normalizeQueryPath(path.value || ""));

  const queryKey = computed(() =>
    normalizedPath.value
      ? queryKeys.folderChildren(normalizedPath.value)
      : []
  );

  const query = useQuery({
    queryKey,
    queryFn: async ({ queryKey }) => {
      const requestPath = queryKey[1] as string;
      return listFolderChildren(requestPath);
    },
    enabled: computed(() => enabled.value && normalizedPath.value.length > 0),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
  });

  const folders = computed(() => normalizeFolderChildren(query.data.value ?? []));

  return {
    folders,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    isFetched: query.isFetched,
    error: query.error,
    refetch: query.refetch,
  };
}
