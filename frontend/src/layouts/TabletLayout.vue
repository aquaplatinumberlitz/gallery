<script setup lang="ts">
import GallerySidebarContent from "../components/GallerySidebarContent.vue";
import TabletHeader from "../components/TabletHeader.vue";
import GalleryGrid from "../components/GalleryGrid.vue";

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
  (e: "toggleSidebar"): void;
  (e: "toggleTheme"): void;
}>();
</script>

<template>
  <div class="layout">
    <aside
      id="sidebar"
      class="sidebar tablet-overlay"
      :class="{ open: isSidebarOpen }"
      :inert="!isSidebarOpen"
    >
      <GallerySidebarContent
        :tree="tree"
        :is-loading="isLoading"
        :current-path="currentPath"
      />
    </aside>

    <Transition name="sidebar-backdrop">
      <div
        v-if="isSidebarOpen"
        class="sidebar-backdrop"
        @click="emit('toggleSidebar')"
      ></div>
    </Transition>

    <section class="content" id="main-content" tabindex="-1">
      <TabletHeader
        :is-dark="theme === 'dark'"
        :search-query="searchQuery"
        :search-scope="searchScope"
        :current-path="currentPath"
        @update:search-query="emit('update:searchQuery', $event)"
        @scope-change="emit('scope-change', $event)"
        @toggle-sidebar="emit('toggleSidebar')"
        @toggle-theme="emit('toggleTheme')"
      />

      <div class="content-body">
        <GalleryGrid
          :is-mobile="false"
          :show-toolbar-breadcrumb="false"
        />
      </div>
    </section>
  </div>
</template>

<style scoped>
.layout {
  height: 100dvh;
  height: 100vh; /* fallback */
  background: var(--bg-color);
  color: var(--text-color);
  display: grid;
  grid-template-columns: 1fr;
  overflow: hidden;
}

.content {
  padding: 16px 12px 20px 12px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  overflow: hidden;
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

/* Tablet overlay drawer */
.sidebar.tablet-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 280px;
  height: 100dvh;
  z-index: 100;
  pointer-events: none;
  transform: translateX(-100%);
  transition: transform 0.22s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: var(--gallery-shadow-xl);
  background: linear-gradient(180deg, rgba(0, 0, 0, 0.02), rgba(0, 0, 0, 0.04)), var(--surface-color);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  will-change: transform;
}

.sidebar.tablet-overlay.open {
  transform: translateX(0);
  pointer-events: auto;
}

.sidebar-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 90;
}

/* Backdrop transition */
.sidebar-backdrop-enter-active {
  transition: opacity 0.18s ease;
}
.sidebar-backdrop-leave-active {
  transition: opacity 0.18s ease;
  pointer-events: none;
}
.sidebar-backdrop-enter-from,
.sidebar-backdrop-leave-to {
  opacity: 0;
}
.sidebar-backdrop-enter-to,
.sidebar-backdrop-leave-from {
  opacity: 1;
}
</style>
