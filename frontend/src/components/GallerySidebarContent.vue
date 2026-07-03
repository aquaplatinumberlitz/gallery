<script setup lang="ts">
import { computed } from "vue";
import LibrarySidebarHeader from "@/components/LibrarySidebarHeader.vue";
import FolderTree from "@/components/FolderTree.vue";
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
  hasActiveLibrary: boolean;
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

  <SidebarContent class="border-t border-sidebar-border/55 pt-2">
    <SidebarGroup class="min-h-0 px-3 pb-3 pt-1 group-data-[collapsible=icon]:px-2">
      <SidebarGroupLabel as="div" class="sidebar-title" id="folder-tree-label">
        <span>Folder Tree</span>
        <span v-if="isLoading" class="loading-pill"> <Loader class="gallery-icon-md lucide-spin" /> Loading </span>
      </SidebarGroupLabel>

      <SidebarGroupContent>
        <div class="tree-container">
          <p v-if="!hasActiveLibrary" class="empty-state group-data-[collapsible=icon]:hidden">
            Select a registered library to start browsing.
          </p>
          <p v-else-if="!isLoading && !tree.length" class="empty-state group-data-[collapsible=icon]:hidden">
            No folders available for this library.
          </p>
          <FolderTree :tree="tree" :active-path="currentPath" />
        </div>
      </SidebarGroupContent>
    </SidebarGroup>
  </SidebarContent>

  <SidebarFooter
    class="overflow-hidden border-t border-sidebar-border/55 p-2 group-data-[collapsible=icon]:items-center group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:p-1"
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
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  padding-right: 4px;
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
