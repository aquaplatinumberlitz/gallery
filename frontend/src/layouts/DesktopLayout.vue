<script setup lang="ts">
import GallerySidebarContent from "../components/GallerySidebarContent.vue";
import AppHeader from "../components/AppHeader.vue";
import { RouterView } from "vue-router";
import {
  SidebarProvider,
  Sidebar,
  SidebarInset,
  SidebarRail,
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
    <Sidebar side="left" variant="sidebar" collapsible="icon">
      <div class="flex h-full w-full flex-col group-data-[collapsible=icon]:items-center">
        <GallerySidebarContent
          :tree="tree"
          :is-loading="isLoading"
          :current-path="currentPath"
          index-status-variant="card"
        />
      </div>
      <SidebarRail />
    </Sidebar>

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
        <RouterView />
      </div>
    </SidebarInset>
  </SidebarProvider>
</template>

<style scoped lang="scss">

.content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100svh;
  min-height: 0;
  overflow: hidden;
  padding: 16px 16px 24px 16px;
  transition: padding-top 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.content-body {
  background: transparent;
  padding: 0;
  box-shadow: none;
  border-radius: 0;
  flex: 1;
  min-height: 0;
  overflow: hidden;
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
