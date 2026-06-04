<script setup lang="ts">
import SidebarHeader from "../components/SidebarHeader.vue";
import FolderTreeItem from "../components/FolderTreeItem.vue";
import TabletHeader from "../components/TabletHeader.vue";
import GalleryGrid from "../components/GalleryGrid.vue";
import { Loader } from "lucide-vue-next";

defineProps<{
  theme: "light" | "dark";
  isSidebarOpen: boolean;
  tree: any[];
  isLoading: boolean;
  currentPath: string;
  searchQuery: string;
}>();

const emit = defineEmits<{
  (e: "update:searchQuery", value: string): void;
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
    >
      <SidebarHeader />
      <div class="sidebar-body">
        <div class="sidebar-title" id="folder-tree-label">
          <span>Folder Tree</span>
          <span v-if="isLoading" class="loading-pill">
            <Loader :size="16" class="lucide-spin" /> Loading
          </span>
        </div>
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
      </div>
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
        :current-path="currentPath"
        @update:search-query="emit('update:searchQuery', $event)"
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

.sidebar-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  overflow: hidden;
}

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

.sidebar ::-webkit-scrollbar,
.tree-container ::-webkit-scrollbar {
  width: 6px;
}

.sidebar ::-webkit-scrollbar-thumb,
.tree-container ::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.12);
  border-radius: 6px;
}

.sidebar ::-webkit-scrollbar-track,
.tree-container ::-webkit-scrollbar-track {
  background: transparent;
}

.empty-state {
  margin: 0;
  color: var(--muted-text);
  font-size: 14px;
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
