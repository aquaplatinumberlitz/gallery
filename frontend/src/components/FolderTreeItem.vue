<script setup lang="ts">
import { computed, ref } from "vue";
import { useGalleryStore } from "../stores/gallery";
import type { FileNode } from "../types";
import { ChevronDown, ChevronRight, Folder, FolderOpen, Loader } from "lucide-vue-next";

defineOptions({ name: "FolderTreeItem" });

const props = withDefaults(defineProps<{
  node: FileNode;
  activePath?: string;
  level?: number;
}>(), {
  level: 1,
});

const galleryStore = useGalleryStore();
const itemRef = ref<HTMLElement | null>(null);

const isActive = computed(() => props.activePath === props.node.path);
const isLoading = computed(() => !!galleryStore.loadingMap[props.node.path]);

const folderIcon = computed(() =>
  props.node.isOpen
    ? FolderOpen
    : Folder
);

const arrowIcon = computed(() =>
  props.node.isOpen ? ChevronDown : ChevronRight
);

const onToggle = () => {
  if (!props.node.has_children) return;
  galleryStore.toggleFolder(props.node);
};

const onSelect = () => {
  galleryStore.selectFolder(props.node);
};

// Keyboard navigation following WAI-ARIA TreeView pattern
const handleKeydown = (e: KeyboardEvent) => {
  switch (e.key) {
    case 'Enter':
    case ' ':
      e.preventDefault();
      onSelect();
      break;
    case 'ArrowRight':
      e.preventDefault();
      if (props.node.has_children) {
        if (!props.node.isOpen) {
          onToggle();
        }
      }
      break;
    case 'ArrowLeft':
      e.preventDefault();
      if (props.node.isOpen) {
        onToggle();
      }
      break;
  }
};
</script>

<template>
  <div 
    class="tree-item"
  >
    <div 
      ref="itemRef"
      class="tree-row" 
      :class="{ active: isActive }" 
      @click="onSelect"
      @keydown="handleKeydown"
    >
      <button
        class="toggle-btn"
        type="button"
        :disabled="!node.has_children"
        @click.stop="onToggle"
      >
        <component :is="arrowIcon" :size="12" />
      </button>
      <component :is="folderIcon" :size="16" class="folder-icon" />
      <span class="name">{{ node.name }}</span>
      <Loader v-if="isLoading" :size="14" class="lucide-spin spinner" />
    </div>

    <div 
      v-if="node.isOpen && node.children?.length" 
      class="children"
    >
      <FolderTreeItem
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        :active-path="activePath"
        :level="level + 1"
      />
    </div>

    <div
      v-else-if="node.isOpen && !isLoading && (!node.children || !node.children.length)"
      class="empty-children"
    >
      (Empty)
    </div>
  </div>
</template>

<style scoped>
.tree-item {
  display: block;
}

.tree-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 6px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--text-color);
  font-size: 13px;
  transition: background-color 120ms ease, color 120ms ease;
}

.tree-row:hover {
  background: var(--gallery-surface-hover, rgba(0, 0, 0, 0.03));
}

.tree-row.active {
  background: color-mix(in srgb, var(--primary-color) 16%, transparent);
  color: var(--primary-color);
  position: relative;
}

.tree-row.active .folder-icon,
.tree-row:hover .folder-icon {
  color: var(--folder-color);
}

.tree-row.active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 4px;
  bottom: 4px;
  width: 1.5px;
  border-radius: 999px;
  background: var(--primary-color);
}

.toggle-btn {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid var(--gallery-border-subtle, rgba(0, 0, 0, 0.08));
  background: transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: inherit;
  cursor: pointer;
  transition: border-color 120ms ease, background-color 120ms ease;
}

.toggle-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.toggle-btn:not(:disabled):hover {
  border-color: var(--primary-color);
  background: var(--gallery-surface-hover, rgba(0, 0, 0, 0.04));
}

.folder-icon {
  color: var(--folder-color);
  transition: color 120ms ease;
}

.name {
  flex: 1;
  min-width: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
  overflow: hidden;
}

.children {
  margin-left: 18px;
  border-left: 1px dashed var(--gallery-border-subtle, rgba(0, 0, 0, 0.06));
  padding-left: 10px;
}

.empty-children {
  margin-left: 36px;
  color: var(--muted-text);
  font-size: 12px;
  padding: 4px 0 8px;
}

/* Focus styles for keyboard navigation */
.tree-row:focus {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

.tree-row:focus:not(:focus-visible) {
  outline: none;
}

.tree-row:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}
</style>
