import { useQuery } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { IMAGE_PAGE_SIZE } from "../constants";
import { queryKeys, normalizeQueryPath } from "../query/keys";
import { scanDirectory } from "../services/api";
import type { FileNode, ScanResponse } from "../types";

const normalizeFolderChildren = (nodes: FileNode[]): FileNode[] =>
  nodes
    .filter((node) => node.type === "folder")
    .map((node) => ({
      ...node,
      isOpen: false,
      children: undefined,
    }));

const withScanRequestPath = (data: ScanResponse, requestPath: string): ScanResponse => ({
  ...data,
  request_path: requestPath,
});

export function useFolderChildrenQuery(path: Ref<string>, enabled: Ref<boolean>) {
  const normalizedPath = computed(() => normalizeQueryPath(path.value || ""));

  const queryKey = computed(() =>
    normalizedPath.value
      ? queryKeys.scan(normalizedPath.value, IMAGE_PAGE_SIZE)
      : []
  );

  const query = useQuery({
    queryKey,
    queryFn: async ({ queryKey }) => {
      const requestPath = queryKey[1] as string;
      return withScanRequestPath(
        await scanDirectory(requestPath, {
          imageLimit: IMAGE_PAGE_SIZE,
          imageCursor: 0,
        }),
        requestPath
      );
    },
    enabled: computed(() => enabled.value && normalizedPath.value.length > 0),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
  });

  const folders = computed(() => normalizeFolderChildren(query.data.value?.folders ?? []));

  return {
    ...query,
    folders,
    scanPath: normalizedPath,
  };
}
