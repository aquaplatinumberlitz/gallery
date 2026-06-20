<script setup lang="ts">
import { computed } from "vue";
import LibrarySidebarHeader from "@/components/LibrarySidebarHeader.vue";
import FolderTreeItem from "@/components/FolderTreeItem.vue";
import { Loader } from "lucide-vue-next";
import {
  SidebarHeader as ShadSidebarHeader,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  useSidebar,
} from "@/components/ui/sidebar";
import IndexStatusPanel from "@/components/IndexStatusPanel.vue";
import type { FolderTreeNode } from "@/types";

defineProps<{
  tree: FolderTreeNode[];
  isLoading: boolean;
  currentPath: string;
}>();

const { isMobile, state } = useSidebar();
const isCollapsed = computed(() => state.value === "collapsed");
const indexStatusVariant = computed(() => (isMobile.value || isCollapsed.value ? "button" : "card"));
</script>

<template>
  <ShadSidebarHeader class="p-0">
    <LibrarySidebarHeader />
  </ShadSidebarHeader>

  <SidebarContent>
    <SidebarGroup>
      <SidebarGroupLabel as="div" class="sidebar-title" id="folder-tree-label">
        <span>Folder Tree</span>
        <span v-if="isLoading" class="loading-pill"> <Loader class="gallery-icon-md lucide-spin" /> Loading </span>
      </SidebarGroupLabel>

      <SidebarGroupContent>
        <div class="tree-container">
          <p v-if="!isLoading && !tree.length" class="empty-state group-data-[collapsible=icon]:hidden">
            Select a registered library to start browsing.
          </p>
          <FolderTreeItem v-for="node in tree" :key="node.path" :node="node" :active-path="currentPath" :level="1" />
        </div>
      </SidebarGroupContent>
    </SidebarGroup>
  </SidebarContent>

  <SidebarFooter
    class="border-t border-border p-2 overflow-hidden group-data-[collapsible=icon]:p-1 group-data-[collapsible=icon]:items-center group-data-[collapsible=icon]:justify-center"
  >
    <IndexStatusPanel :path="currentPath" :variant="indexStatusVariant" />
  </SidebarFooter>
</template>

<style scoped>
.sidebar-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  color: var(--foreground);
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
  color: var(--muted-foreground);
  font-size: 14px;
}

.gallery-icon-md {
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}
</style>
