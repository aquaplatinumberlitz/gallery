<script setup lang="ts">
import GallerySidebarContent from "../components/GallerySidebarContent.vue";
import MobileHeader from "../components/MobileHeader.vue";
import { RouterView } from "vue-router";
import MobileFloatingBottomBar from "../components/MobileFloatingBottomBar.vue";
import { SidebarProvider, Sidebar, SidebarInset } from "@/components/ui/sidebar";
import type { FolderTreeNode } from "@/types";

defineProps<{
  theme: "light" | "dark";
  isSidebarOpen: boolean;
  tree: FolderTreeNode[];
  isLoading: boolean;
  currentPath: string;
  searchQuery: string;
  searchScope: "current" | "all";
  barsVisible: boolean;
  canBack: boolean;
  canForward: boolean;
  isAdminRoute: boolean;
}>();

const emit = defineEmits<{
  (e: "update:searchQuery", value: string): void;
  (e: "scope-change", value: "current" | "all"): void;
  (e: "update:sidebarOpen", value: boolean): void;
  (e: "toggleSidebar"): void;
  (e: "toggleTheme"): void;
  (e: "back"): void;
  (e: "forward"): void;
  (e: "openFolder"): void;
}>();
</script>

<template>
  <SidebarProvider :open="true" :open-mobile="isSidebarOpen" @update:open-mobile="emit('update:sidebarOpen', $event)">
    <Sidebar side="left" variant="sidebar" collapsible="offcanvas">
      <div class="gallery-sidebar-surface flex h-full w-full flex-col">
        <GallerySidebarContent :tree="tree" :is-loading="isLoading" :current-path="currentPath" />
      </div>
    </Sidebar>

    <SidebarInset id="main-content" tabindex="-1" class="content" :class="{ 'bars-hidden': !barsVisible }">
      <MobileHeader
        :is-dark="theme === 'dark'"
        :search-query="searchQuery"
        :search-scope="searchScope"
        :bars-visible="isAdminRoute || barsVisible"
        :is-admin-route="isAdminRoute"
        @update:search-query="emit('update:searchQuery', $event)"
        @scope-change="emit('scope-change', $event)"
        @toggle-sidebar="emit('toggleSidebar')"
        @toggle-theme="emit('toggleTheme')"
      />

      <div class="content-body">
        <RouterView />
      </div>

      <MobileFloatingBottomBar
        v-if="!isAdminRoute"
        :can-back="canBack"
        :can-forward="canForward"
        :current-path="currentPath"
        :bars-visible="barsVisible"
        @back="emit('back')"
        @forward="emit('forward')"
        @open-folder="emit('openFolder')"
      />
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
  padding: 60px 16px 72px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  overflow: hidden;
  transition: padding-top 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.content.bars-hidden {
  padding-top: max(8px, env(safe-area-inset-top));
  padding-bottom: 12px;
}

.content-body {
  background: transparent;
  border-radius: 0;
  box-shadow: none;
  padding: 4px 4px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Compact: <480px */
@media (max-width: 480px) {
  .content {
    padding: 56px 12px 72px 12px;
    gap: 6px;
    overflow: hidden;
  }

  .content.bars-hidden {
    padding-bottom: 8px;
  }

  .content-body {
    padding: 4px 4px;
    border-radius: 0;
    background: transparent;
    box-shadow: none;
  }
}
</style>
