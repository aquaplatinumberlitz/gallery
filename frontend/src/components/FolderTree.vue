<script setup lang="ts">
import { computed, inject, reactive, watch } from "vue";
import { useGalleryStore } from "@/stores/gallery";
import type { FolderTreeNode } from "@/types";
import { normalizeQueryPath } from "@/query/keys";
import { closeSidebarKey } from "@/injectionKeys";
import { useDevice } from "@/composables/useDevice";
import { Tree, TreeItem } from "@/components/ui/tree";
import FolderTreeRow, { type FolderTreeDisplayItem } from "@/components/FolderTreeRow.vue";
import Button from "@/components/ui/Button.vue";
import { ListCollapse, ListTree } from "lucide-vue-next";

defineOptions({ name: "FolderTree" });

const props = defineProps<{
  tree: FolderTreeNode[];
  activePath: string;
}>();

const galleryStore = useGalleryStore();
const { isMobile, isTablet } = useDevice();
const closeSidebar = inject(closeSidebarKey, () => {});

const loadedChildren = reactive<Record<string, FolderTreeNode[]>>({});
const loadedPaths = reactive<Record<string, boolean>>({});
const loadStates = reactive<Record<string, { isLoading: boolean; errorMessage?: string }>>({});

const normalizeFolderPath = (path: string) => normalizeQueryPath(path) || path;
const treeSignature = computed(() => props.tree.map((node) => normalizeFolderPath(node.path)).join("\u001f"));

watch(treeSignature, () => {
  for (const path of Object.keys(loadedChildren)) delete loadedChildren[path];
  for (const path of Object.keys(loadedPaths)) delete loadedPaths[path];
  for (const path of Object.keys(loadStates)) delete loadStates[path];
});

const makePlaceholder = (
  parentPath: string,
  kind: "loading" | "empty" | "error",
  message?: string,
): FolderTreeDisplayItem => ({
  kind,
  id: `${parentPath}::__${kind}`,
  parentPath,
  name: message ?? (kind === "empty" ? "(Empty)" : kind === "error" ? "Unable to load folder." : "Loading"),
});

const makeDisplayNode = (node: FolderTreeNode): FolderTreeDisplayItem => {
  const path = normalizeFolderPath(node.path);
  const hasInlineChildren = node.children !== undefined;
  const hasLoadedChildren = hasInlineChildren || !!loadedPaths[path];
  const knownChildren = hasInlineChildren ? (node.children ?? []) : (loadedChildren[path] ?? []);

  let children: FolderTreeDisplayItem[] | undefined;
  if (knownChildren.length) {
    children = knownChildren.map(makeDisplayNode);
  } else if (node.has_children) {
    if (hasLoadedChildren) {
      children = [makePlaceholder(path, "empty")];
    } else {
      const state = loadStates[path];
      children = [
        state?.errorMessage ? makePlaceholder(path, "error", state.errorMessage) : makePlaceholder(path, "loading"),
      ];
    }
  }

  return {
    kind: "folder",
    id: path,
    path,
    name: node.name,
    node,
    hasChildren: !!node.has_children,
    childrenLoaded: hasLoadedChildren,
    children,
  };
};

const items = computed<FolderTreeDisplayItem[]>(() => props.tree.map(makeDisplayNode));

const expandedItems = computed<string[]>({
  get: () =>
    Object.entries(galleryStore.expandedFolderPaths)
      .filter(([, expanded]) => expanded)
      .map(([path]) => path),
  set: (paths) => {
    const next = new Set(paths.map(normalizeFolderPath));
    const current = new Set(expandedItems.value.map(normalizeFolderPath));

    for (const path of current) {
      if (!next.has(path)) galleryStore.setFolderExpanded(path, false);
    }
    for (const path of next) {
      if (!current.has(path)) galleryStore.setFolderExpanded(path, true);
    }
  },
});

const findItemByPath = (nodes: FolderTreeDisplayItem[], path: string): FolderTreeDisplayItem | undefined => {
  for (const item of nodes) {
    if (item.kind === "folder" && item.path === path) return item;
    const child = item.kind === "folder" && item.children ? findItemByPath(item.children, path) : undefined;
    if (child) return child;
  }
};

const selectedItem = computed(() => findItemByPath(items.value, normalizeFolderPath(props.activePath)));

const getItemKey = (item: FolderTreeDisplayItem) => item.id;
const getItemChildren = (item: FolderTreeDisplayItem) => (item.kind === "folder" ? item.children : undefined);

const collectExpandablePaths = (nodes: FolderTreeDisplayItem[]): string[] =>
  nodes.flatMap((item) => {
    if (item.kind !== "folder") return [];
    const childPaths = item.children ? collectExpandablePaths(item.children) : [];
    return item.hasChildren ? [item.path, ...childPaths] : childPaths;
  });

const expandablePaths = computed(() => collectExpandablePaths(items.value));
const hasExpandableItems = computed(() => expandablePaths.value.length > 0);

const expandAll = () => {
  for (const path of expandablePaths.value) {
    galleryStore.setFolderExpanded(path, true);
  }
};

const collapseAll = () => {
  for (const path of expandedItems.value) {
    galleryStore.setFolderExpanded(path, false);
  }
};

const onChildrenLoaded = (path: string, children: FolderTreeNode[]) => {
  const normalizedPath = normalizeFolderPath(path);
  loadedChildren[normalizedPath] = children;
  loadedPaths[normalizedPath] = true;
  loadStates[normalizedPath] = { isLoading: false };
};

const onLoadState = (path: string, state: { isLoading: boolean; errorMessage?: string }) => {
  loadStates[normalizeFolderPath(path)] = state;
};

const onItemSelect = (event: CustomEvent<{ value?: FolderTreeDisplayItem }>) => {
  const item = event.detail.value;
  if (!item || item.kind !== "folder") {
    event.preventDefault();
    return;
  }

  galleryStore.selectFolder(item.node);
  if (isMobile.value || isTablet.value) {
    closeSidebar();
  }
};
</script>

<template>
  <div class="flex min-h-0 flex-col gap-2 group-data-[collapsible=icon]:hidden">
    <div class="tree-actions-bar flex items-center gap-1.5 px-1">
      <Button
        size="sm"
        variant="outline"
        type="button"
        class="tree-action-btn"
        :disabled="!hasExpandableItems"
        @click="expandAll"
      >
        <ListTree data-icon="inline-start" class="opacity-70" aria-hidden="true" />
        Expand all
      </Button>
      <Button
        size="sm"
        variant="outline"
        type="button"
        class="tree-action-btn"
        :disabled="!expandedItems.length"
        @click="collapseAll"
      >
        <ListCollapse data-icon="inline-start" class="opacity-70" aria-hidden="true" />
        Collapse all
      </Button>
    </div>

    <Tree
      :items="items"
      :indent="14"
      :indent-max="84"
      :get-key="getItemKey"
      :get-children="getItemChildren"
      :model-value="selectedItem"
      :expanded="expandedItems"
      @update:expanded="expandedItems = $event"
      v-slot="{ flattenItems }"
    >
      <TreeItem
        v-for="item in flattenItems"
        :key="item._id"
        v-bind="item.bind"
        :has-children="item.value.kind === 'folder' && item.value.hasChildren"
        @select="onItemSelect"
        v-slot="{ isExpanded }"
      >
        <FolderTreeRow
          :item="item.value"
          :is-expanded="isExpanded"
          @children-loaded="onChildrenLoaded"
          @load-state="onLoadState"
        />
      </TreeItem>
    </Tree>
  </div>
</template>

<style scoped>
.tree-action-btn {
  height: 28px;
  gap: 5px;
  padding-inline: 10px;
  border-radius: 999px;
  border-color: color-mix(in srgb, var(--sidebar-border) 60%, transparent);
  background: var(--sidebar);
  font-size: 11px;
  font-weight: 500;
  color: var(--sidebar-foreground);
  transition: background 150ms ease, border-color 150ms ease;
}

.tree-action-btn:hover {
  background: color-mix(in srgb, var(--sidebar-accent) 70%, transparent);
}

.tree-action-btn:disabled {
  opacity: 0.35;
}

@media (max-width: 1023px) {
  .tree-action-btn {
    height: 34px;
    padding-inline: 12px;
    font-size: 12px;
  }
}
</style>
