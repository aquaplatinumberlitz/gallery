<script setup lang="ts">
import GallerySidebarContent from "../components/GallerySidebarContent.vue";
import GallerySidebarEdgeTrigger from "../components/GallerySidebarEdgeTrigger.vue";
import AppHeader from "../components/AppHeader.vue";
import GalleryGrid from "../components/GalleryGrid.vue";
import {
  SidebarProvider,
  Sidebar,
  SidebarInset,
} from "@/components/ui/sidebar";

defineProps<{
  theme: "light" | "dark";
  isSidebarOpen: boolean;
  tree: any[];
  isLoading: boolean;
  currentPath: string;
  searchQuery: string;
  searchScope: "current" | "all";
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
  <SidebarProvider
    :open="isSidebarOpen"
    @update:open="emit('update:sidebarOpen', $event)"
  >
    <Sidebar side="left" variant="sidebar" collapsible="offcanvas">
      <div class="gallery-sidebar-surface flex h-full w-full flex-col">
        <GallerySidebarContent
          :tree="tree"
          :is-loading="isLoading"
          :current-path="currentPath"
        />
      </div>
    </Sidebar>

    <GallerySidebarEdgeTrigger @toggle="emit('toggleSidebar')" />

    <SidebarInset id="main-content" tabindex="-1" class="content">
      <AppHeader
        :is-mobile="false"
        :is-sidebar-open="isSidebarOpen"
        :is-dark="theme === 'dark'"
        :search-query="searchQuery"
        :search-scope="searchScope"
        @update:search-query="emit('update:searchQuery', $event)"
        @scope-change="emit('scope-change', $event)"
        @toggle-sidebar="emit('toggleSidebar')"
        @toggle-theme="emit('toggleTheme')"
        @open-settings="emit('openSettings')"
      />

      <div class="content-body">
        <GalleryGrid
          :is-mobile="false"
        />
      </div>
    </SidebarInset>
  </SidebarProvider>
</template>

<style scoped lang="scss">
.gallery-sidebar-surface {
  background: linear-gradient(180deg, rgba(0, 0, 0, 0.02), rgba(0, 0, 0, 0.04)), var(--surface-color);
}

.content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  overflow: hidden;
  padding: 16px 16px 24px 16px;
  transition: padding-top 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.content-body {
  background: var(--surface-color);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.04);
  flex: 1;
  min-height: 0;
  overflow: visible;
  display: flex;
  flex-direction: column;
}

/* Import breakpoint mixins */
@import "../styles/breakpoints";

/* Tablet & below: 1199px */
@media (max-width: 1199px) {
  .content {
    padding: 16px 12px 20px 12px;
  }
}
</style>
