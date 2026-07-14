<script setup lang="ts">
import { computed, watch } from "vue";
import { Folder, FolderOpen, Loader } from "lucide-vue-next";
import type { FolderTreeNode } from "@/types";
import { useFolderChildrenQuery } from "@/composables/useFolderChildrenQuery";
import { TreeItemLabel } from "@/components/ui/tree";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export type FolderTreeDisplayItem =
  | {
      kind: "folder";
      id: string;
      path: string;
      name: string;
      node: FolderTreeNode;
      hasChildren: boolean;
      childrenLoaded: boolean;
      children?: FolderTreeDisplayItem[];
    }
  | {
      kind: "loading" | "empty" | "error";
      id: string;
      parentPath: string;
      name: string;
    };

const props = defineProps<{
  item: FolderTreeDisplayItem;
  isExpanded: boolean;
}>();

const emit = defineEmits<{
  (event: "children-loaded", path: string, children: FolderTreeNode[]): void;
  (event: "load-state", path: string, state: { isLoading: boolean; errorMessage?: string }): void;
}>();

const folderPath = computed(() => (props.item.kind === "folder" ? props.item.path : ""));
const shouldLoadChildren = computed(
  () => props.item.kind === "folder" && props.isExpanded && props.item.hasChildren && !props.item.childrenLoaded,
);

const folderChildrenQuery = useFolderChildrenQuery(folderPath, shouldLoadChildren);

const isLoading = computed(
  () =>
    props.item.kind === "folder" &&
    props.isExpanded &&
    props.item.hasChildren &&
    !props.item.childrenLoaded &&
    (folderChildrenQuery.isLoading.value || folderChildrenQuery.isFetching.value),
);

watch(
  () => [folderChildrenQuery.isFetched.value, folderChildrenQuery.isError.value, folderChildrenQuery.folders.value],
  ([isFetched, isError]) => {
    if (props.item.kind !== "folder" || !isFetched || isError) return;
    emit("children-loaded", props.item.path, folderChildrenQuery.folders.value);
  },
  { immediate: true },
);

watch(
  () => [
    folderChildrenQuery.isLoading.value,
    folderChildrenQuery.isFetching.value,
    folderChildrenQuery.isError.value,
    folderChildrenQuery.error.value,
  ],
  ([isLoadingValue, isFetchingValue, isErrorValue, errorValue]) => {
    if (props.item.kind !== "folder") return;
    const userMessage = (errorValue as { userMessage?: string } | null)?.userMessage;
    emit("load-state", props.item.path, {
      isLoading: Boolean(isLoadingValue || isFetchingValue),
      errorMessage: isErrorValue ? userMessage || "Unable to load folder." : undefined,
    });
  },
  { immediate: true },
);
</script>

<template>
  <TreeItemLabel
    v-if="item.kind === 'folder'"
    :has-children="item.hasChildren"
    class="folder-tree-label min-w-0 bg-transparent text-[13px] text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground in-data-[selected]:bg-sidebar-accent in-data-[selected]:text-sidebar-accent-foreground"
  >
    <span class="flex min-w-0 flex-1 items-center gap-1.5">
      <FolderOpen v-if="isExpanded" class="folder-icon gallery-icon-md" />
      <Folder v-else class="folder-icon gallery-icon-md" />
      <Tooltip :delay-duration="300">
        <TooltipTrigger as-child>
          <span class="min-w-0 flex-1 truncate text-left">{{ item.name }}</span>
        </TooltipTrigger>
        <TooltipContent side="right" align="start" class="max-w-[320px] break-all">
          {{ item.node.display_label || item.path }}
        </TooltipContent>
      </Tooltip>
      <Loader v-if="isLoading" class="gallery-icon-sm lucide-spin text-muted-foreground" />
    </span>
  </TreeItemLabel>

  <TreeItemLabel
    v-else
    :has-children="false"
    class="pointer-events-none bg-transparent py-1 text-xs text-sidebar-foreground/65"
  >
    <span class="flex min-w-0 flex-1 items-center gap-1.5">
      <Loader v-if="item.kind === 'loading'" class="gallery-icon-sm lucide-spin" />
      <Tooltip :delay-duration="300">
        <TooltipTrigger as-child>
          <span class="min-w-0 flex-1 truncate">{{ item.name }}</span>
        </TooltipTrigger>
        <TooltipContent side="right" align="start" class="max-w-[260px] break-words">
          {{ item.name }}
        </TooltipContent>
      </Tooltip>
    </span>
  </TreeItemLabel>
</template>

<style scoped>
@media (max-width: 1023px) {
  .folder-tree-label {
    min-height: 46px;
    border-radius: var(--gallery-radius-md);
    padding-inline: 8px;
    transition: background 150ms ease, transform 80ms ease;
    position: relative;
  }

  .folder-tree-label:active {
    transform: scale(0.98);
    background: color-mix(in srgb, var(--sidebar-accent) 80%, transparent);
  }

  /* Selected item accent indicator */
  :deep([data-selected]) .folder-tree-label {
    background: color-mix(in srgb, var(--primary) 8%, transparent);
    border-left: 3px solid var(--primary);
    padding-left: 6px;
  }
}

.folder-icon {
  color: var(--primary);
  transition: color 120ms ease, transform 120ms ease;
  flex-shrink: 0;
}

.gallery-icon-md {
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}

.gallery-icon-sm {
  width: var(--gallery-icon-sm);
  height: var(--gallery-icon-sm);
}
</style>
