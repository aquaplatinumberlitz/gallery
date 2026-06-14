<script setup lang="ts">
import RootPathSidebarHeader from "@/components/SidebarHeader.vue";
import FolderTreeItem from "@/components/FolderTreeItem.vue";
import { Loader } from "lucide-vue-next";
import {
  SidebarHeader as ShadSidebarHeader,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
} from "@/components/ui/sidebar";

defineProps<{
  tree: any[];
  isLoading: boolean;
  currentPath: string;
}>();
</script>

<template>
  <ShadSidebarHeader class="p-0">
    <RootPathSidebarHeader />
  </ShadSidebarHeader>

  <SidebarContent>
    <SidebarGroup>
      <div class="sidebar-title" id="folder-tree-label">
        <span>Folder Tree</span>
        <span v-if="isLoading" class="loading-pill">
          <Loader class="gallery-icon-md lucide-spin" /> Loading
        </span>
      </div>

      <SidebarGroupContent>
        <div class="tree-container">
          <p v-if="!isLoading && !tree.length" class="empty-state">
            Enter a root path and click Load to start.
          </p>
          <FolderTreeItem
            v-for="node in tree"
            :key="node.path"
            :node="node"
            :active-path="currentPath"
            :level="1"
          />
        </div>
      </SidebarGroupContent>
    </SidebarGroup>
  </SidebarContent>
</template>

<style scoped>
.sidebar-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  color: var(--title-color);
  flex-shrink: 0;
}

.loading-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.04);
  font-size: 12px;
}

.tree-container {
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
}

.tree-container::-webkit-scrollbar {
  width: 6px;
}

.tree-container::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.12);
  border-radius: 6px;
}

.tree-container::-webkit-scrollbar-track {
  background: transparent;
}

.empty-state {
  margin: 0;
  color: var(--muted-text);
  font-size: 14px;
}

.gallery-icon-md {
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}
</style>
