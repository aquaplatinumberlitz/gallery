<script setup lang="ts">
import { computed, inject } from "vue";
import { useGalleryStore } from "../stores/gallery";
import type { FileNode } from "../types";
import { ChevronDown, ChevronRight, Folder, FolderOpen, Loader } from "lucide-vue-next";
import { useDevice } from "../composables/useDevice";
import { useFolderChildrenQuery } from "../composables/useFolderChildrenQuery";
import { closeSidebarKey } from "../injectionKeys";
import Button from "@/components/ui/Button.vue";
import { cn } from "@/lib/utils";

defineOptions({ name: "FolderTreeItem" });

const props = withDefaults(
  defineProps<{
    node: FileNode;
    activePath?: string;
    level?: number;
  }>(),
  {
    level: 1,
  },
);

const galleryStore = useGalleryStore();
const { isMobile, isTablet } = useDevice();
const closeSidebar = inject(closeSidebarKey, () => {});

const isActive = computed(() => props.activePath === props.node.path);
const isOpen = computed(() => galleryStore.isFolderExpanded(props.node.path));
const childrenQueryEnabled = computed(() => isOpen.value && !!props.node.has_children);
const folderChildrenQuery = useFolderChildrenQuery(
  computed(() => props.node.path),
  childrenQueryEnabled,
);
const visibleChildren = computed(() => {
  if (!isOpen.value || !props.node.has_children) return [];
  if (folderChildrenQuery.isFetched.value && !folderChildrenQuery.isError.value) {
    return folderChildrenQuery.folders.value;
  }
  return props.node.children ?? [];
});
const isLoading = computed(
  () =>
    isOpen.value &&
    !!props.node.has_children &&
    !visibleChildren.value.length &&
    (folderChildrenQuery.isLoading.value || folderChildrenQuery.isFetching.value),
);
const hasLoadError = computed(() => folderChildrenQuery.isError.value);
const loadErrorMessage = computed(() => {
  const error = folderChildrenQuery.error.value;
  const userMessage = (error as { userMessage?: string } | null)?.userMessage;
  return userMessage || "Unable to load folder.";
});

const folderIcon = computed(() => (isOpen.value ? FolderOpen : Folder));

const arrowIcon = computed(() => (isOpen.value ? ChevronDown : ChevronRight));

const onToggle = () => {
  if (!props.node.has_children) return;
  galleryStore.toggleFolderExpanded(props.node.path);
};

const onSelect = () => {
  galleryStore.selectFolder(props.node);
  if (isMobile.value || isTablet.value) {
    closeSidebar();
  }
};

// Keyboard navigation following WAI-ARIA TreeView pattern
const handleKeydown = (e: KeyboardEvent) => {
  switch (e.key) {
    case "Enter":
    case " ":
      e.preventDefault();
      onSelect();
      break;
    case "ArrowRight":
      e.preventDefault();
      if (props.node.has_children) {
        if (!isOpen.value) {
          onToggle();
        }
      }
      break;
    case "ArrowLeft":
      e.preventDefault();
      if (isOpen.value) {
        onToggle();
      }
      break;
  }
};
</script>

<template>
  <div role="tree" class="tree-item block group-data-[collapsible=icon]:hidden">
    <div class="tree-row-shell flex items-center gap-1.5">
      <Button
        variant="ghost"
        size="icon"
        class="toggle-btn size-7 shrink-0"
        type="button"
        :disabled="!node.has_children"
        @click.stop="onToggle"
        :aria-label="isOpen ? 'Collapse folder' : 'Expand folder'"
      >
        <component :is="arrowIcon" class="gallery-icon-xs" />
      </Button>

      <Button
        variant="ghost"
        size="sm"
        type="button"
        role="treeitem"
        :aria-expanded="node.has_children ? isOpen : undefined"
        :aria-selected="isActive ? true : undefined"
        :class="
          cn(
            'tree-row min-w-0 flex-1 justify-start gap-1.5 px-1.5 py-[3px] text-[13px]',
            isActive && 'bg-accent text-accent-foreground',
          )
        "
        @click="onSelect"
        @keydown="handleKeydown"
      >
        <component :is="folderIcon" class="folder-icon gallery-icon-md" />
        <span class="name flex-1 min-w-0 truncate text-left">{{ node.name }}</span>
        <Loader v-if="isLoading" class="gallery-icon-sm lucide-spin spinner" />
      </Button>
    </div>

    <div
      v-if="isOpen && visibleChildren.length"
      class="children ml-[18px] border-l border-dashed border-border-subtle pl-2.5"
    >
      <FolderTreeItem
        v-for="child in visibleChildren"
        :key="child.path"
        :node="child"
        :active-path="activePath"
        :level="level + 1"
      />
    </div>

    <div v-else-if="isOpen && hasLoadError" class="empty-children ml-9 text-muted-foreground text-xs py-1 pb-2">
      {{ loadErrorMessage }}
    </div>

    <div
      v-else-if="isOpen && !isLoading && !visibleChildren.length"
      class="empty-children ml-9 text-muted-foreground text-xs py-1 pb-2"
    >
      (Empty)
    </div>
  </div>
</template>

<style scoped>
/* tree-item, children, empty-children layout handled by Tailwind utilities */
/* Keep only icon sizing and folder color */

.tree-item {
  /* Class preserved for scoped style encapsulation */
}

.tree-row {
  /* Layout handled by Tailwind utilities; visual states via shadcn Button */
}

.tree-row-shell {
  /* Layout handled by Tailwind utilities */
}

.toggle-btn {
  /* Layout handled by Tailwind utilities; visual states via shadcn Button */
}

.folder-icon {
  color: var(--primary);
  transition: color 120ms ease;
}

/* .name layout handled by Tailwind utilities */

.children {
  /* Layout handled by Tailwind utilities */
}

.empty-children {
  /* Layout handled by Tailwind utilities */
}

/* Icon sizes using design tokens */
.gallery-icon-md {
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}
.gallery-icon-sm {
  width: var(--gallery-icon-sm);
  height: var(--gallery-icon-sm);
}
.gallery-icon-xs {
  width: var(--gallery-icon-xs);
  height: var(--gallery-icon-xs);
}
</style>
