import { useInfiniteQuery } from "@tanstack/vue-query";
import { computed, watch, type Ref } from "vue";
import { IMAGE_PAGE_SIZE } from "../constants";
import { normalizeBrowsePath, queryKeys } from "../query/keys";
import { browseDirectory } from "../services/api";
import { useGalleryStore } from "../stores/gallery";
import type { BrowseResponse, FolderTreeNode } from "../types";

const withBrowseRequestPath = (data: BrowseResponse, requestPath: string | null): BrowseResponse => ({
  ...data,
  request_path: requestPath,
});

const getImportRootName = (path: string) => {
  const normalizedPath = normalizeBrowsePath(path) ?? "";
  if (!normalizedPath || normalizedPath === "/") return normalizedPath || "Library root";
  const parts = normalizedPath.split("/").filter(Boolean);
  return parts[parts.length - 1] || normalizedPath;
};

const makeImportRootNode = (path: string, folders: FolderTreeNode[], isLoaded: boolean): FolderTreeNode | null => {
  const normalizedPath = normalizeBrowsePath(path);
  if (!normalizedPath) return null;
  return {
    name: getImportRootName(normalizedPath),
    display_label: normalizedPath,
    path: normalizedPath,
    type: "folder",
    entry_kind: "import_root",
    has_children: isLoaded ? folders.length > 0 : false,
    children: isLoaded ? folders : undefined,
  };
};

export function useSidebarTreeQuery(
  libraryId: Ref<number | null | undefined>,
  rootPath: Ref<string | null | undefined>,
) {
  const galleryStore = useGalleryStore();
  const activeLibraryId = computed(() => libraryId.value ?? null);
  const normalizedRootPath = computed(() => normalizeBrowsePath(rootPath.value));

  const query = useInfiniteQuery({
    queryKey: computed(() =>
      activeLibraryId.value && normalizedRootPath.value
        ? queryKeys.browseInfinite(activeLibraryId.value, normalizedRootPath.value, IMAGE_PAGE_SIZE, false)
        : [],
    ),
    enabled: computed(() => Boolean(activeLibraryId.value && normalizedRootPath.value)),
    initialPageParam: 0,
    staleTime: 60_000,
    queryFn: async ({ queryKey, pageParam }) => {
      const requestLibraryId = queryKey[1] as number;
      const requestPath = queryKey[2] as string | null;
      const result = await browseDirectory(requestLibraryId, requestPath, {
        limit: IMAGE_PAGE_SIZE,
        cursor: pageParam,
      });
      return withBrowseRequestPath(result, requestPath);
    },
    getNextPageParam: (lastPage) => lastPage.next_media_cursor ?? lastPage.next_cursor ?? undefined,
  });

  const folders = computed(() => (activeLibraryId.value ? (query.data.value?.pages[0]?.folders ?? []) : []));
  const tree = computed(() => {
    if (!activeLibraryId.value || !normalizedRootPath.value) return [];
    const rootNode = makeImportRootNode(normalizedRootPath.value, folders.value, query.isSuccess.value);
    return rootNode ? [rootNode] : [];
  });

  watch(
    tree,
    (nodes) => {
      galleryStore.setSidebarTree(nodes, { preserveChildren: true });
    },
    { immediate: true },
  );

  watch(
    [
      () => activeLibraryId.value,
      () => normalizedRootPath.value,
      () => query.isLoading.value,
      () => query.isFetching.value,
    ],
    ([id, root, loading, fetching]) => {
      galleryStore.isLoading = Boolean(id && root) && (loading || fetching);
    },
    { immediate: true },
  );

  return {
    ...query,
    browsePath: normalizedRootPath,
    folders,
    tree,
  };
}
