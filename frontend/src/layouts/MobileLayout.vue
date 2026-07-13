<script setup lang="ts">
import GallerySidebarContent from "../components/GallerySidebarContent.vue";
import MobileHeader from "../components/MobileHeader.vue";
import { RouterView } from "vue-router";
import MobileFloatingBottomBar from "../components/MobileFloatingBottomBar.vue";
import { SidebarProvider, Sidebar, SidebarInset } from "@/components/ui/sidebar";
import type { FolderTreeNode, SearchScope } from "@/types";

defineProps<{
  theme: "light" | "dark";
  isSidebarOpen: boolean;
  tree: FolderTreeNode[];
  isLoading: boolean;
  hasActiveLibrary: boolean;
  currentPath: string;
  searchQuery: string;
  searchScope: SearchScope;
  searchLoading: boolean;
  barsVisible: boolean;
  canBack: boolean;
  canForward: boolean;
  showBackToGallery: boolean;
}>();

const emit = defineEmits<{
  (e: "update:searchQuery", value: string): void;
  (e: "scope-change", value: SearchScope): void;
  (e: "update:sidebarOpen", value: boolean): void;
  (e: "toggleSidebar"): void;
  (e: "toggleTheme"): void;
  (e: "back"): void;
  (e: "forward"): void;
  (e: "openFolder"): void;
  (e: "openAdvancedSearch"): void;
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

    <SidebarInset id="main-content" class="content" :class="{ 'bars-hidden': !barsVisible }">
      <MobileHeader
        :is-dark="theme === 'dark'"
        :search-query="searchQuery"
        :search-scope="searchScope"
        :search-loading="searchLoading"
        :current-path="currentPath"
        :bars-visible="showBackToGallery || barsVisible"
        :show-back-to-gallery="showBackToGallery"
        @update:search-query="emit('update:searchQuery', $event)"
        @scope-change="emit('scope-change', $event)"
        @toggle-sidebar="emit('toggleSidebar')"
        @toggle-theme="emit('toggleTheme')"
        @open-advanced-search="emit('openAdvancedSearch')"
      />

      <div class="content-body">
        <RouterView />
      </div>

      <MobileFloatingBottomBar
        v-if="!showBackToGallery"
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
  padding: calc(68px + env(safe-area-inset-top)) 8px calc(80px + env(safe-area-inset-bottom)) 8px;
  display: flex;
  flex-direction: column;
  gap: 0;
  height: 100dvh;
  overflow: hidden;
}

.content.bars-hidden {
  padding-top: max(8px, env(safe-area-inset-top));
  padding-bottom: 12px;
}

.content-body {
  background: transparent;
  border-radius: 0;
  box-shadow: none;
  padding: 0;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Compact: <480px */
@media (max-width: 480px) {
  .content {
    padding: calc(64px + env(safe-area-inset-top)) 4px calc(76px + env(safe-area-inset-bottom)) 4px;
    gap: 0;
    overflow: hidden;
  }

  .content.bars-hidden {
    padding-bottom: 8px;
  }

  .content-body {
    padding: 0;
    border-radius: 0;
    background: transparent;
    box-shadow: none;
  }
}
</style>
