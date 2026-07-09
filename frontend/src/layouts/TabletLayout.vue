<script setup lang="ts">
import GallerySidebarContent from "../components/GallerySidebarContent.vue";
import TabletHeader from "../components/TabletHeader.vue";
import { RouterView } from "vue-router";
import { SidebarProvider, Sidebar, SidebarInset } from "@/components/ui/sidebar";
import type { FolderTreeNode } from "@/types";

defineProps<{
  theme: "light" | "dark";
  isSidebarOpen: boolean;
  tree: FolderTreeNode[];
  isLoading: boolean;
  hasActiveLibrary: boolean;
  currentPath: string;
  searchQuery: string;
  searchScope: "current" | "all";
  searchLoading: boolean;
}>();

const emit = defineEmits<{
  (e: "update:searchQuery", value: string): void;
  (e: "scope-change", value: "current" | "all"): void;
  (e: "update:sidebarOpen", value: boolean): void;
  (e: "toggleSidebar"): void;
  (e: "toggleTheme"): void;
  (e: "openSettings"): void;
}>();
</script>

<template>
  <SidebarProvider :open="true" :open-mobile="isSidebarOpen" @update:open-mobile="emit('update:sidebarOpen', $event)">
    <Sidebar side="left" variant="sidebar" collapsible="offcanvas">
      <div class="gallery-sidebar-surface flex h-full w-full flex-col">
        <GallerySidebarContent
          :tree="tree"
          :is-loading="isLoading"
          :has-active-library="hasActiveLibrary"
          :current-path="currentPath"
        />
      </div>
    </Sidebar>

    <SidebarInset id="main-content" class="content">
      <TabletHeader
        :is-dark="theme === 'dark'"
        :search-query="searchQuery"
        :search-scope="searchScope"
        :search-loading="searchLoading"
        :current-path="currentPath"
        @update:search-query="emit('update:searchQuery', $event)"
        @scope-change="emit('scope-change', $event)"
        @toggle-sidebar="emit('toggleSidebar')"
        @toggle-theme="emit('toggleTheme')"
      />

      <div class="content-body">
        <RouterView />
      </div>
    </SidebarInset>
  </SidebarProvider>
</template>

<style scoped>
.gallery-sidebar-surface {
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--foreground) 2%, transparent),
      color-mix(in srgb, var(--foreground) 4%, transparent)
    ),
    var(--card);
}

.content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  overflow: hidden;
  padding: 16px 12px 20px 12px;
  transition: padding-top 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.content-body {
  background: var(--card);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.04);
  flex: 1;
  min-height: 0;
  overflow: visible;
  display: flex;
  flex-direction: column;
}
</style>
