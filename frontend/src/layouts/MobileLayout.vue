<script setup lang="ts">
import SidebarHeader from "../components/SidebarHeader.vue";
import FolderTreeItem from "../components/FolderTreeItem.vue";
import MobileHeader from "../components/MobileHeader.vue";
import GalleryGrid from "../components/GalleryGrid.vue";
import MobileFloatingBottomBar from "../components/MobileFloatingBottomBar.vue";
import { Loader } from "lucide-vue-next";

defineProps<{
  theme: "light" | "dark";
  isSidebarOpen: boolean;
  tree: any[];
  isLoading: boolean;
  currentPath: string;
  searchQuery: string;
  searchScope: "current" | "all";
  barsVisible: boolean;
  canBack: boolean;
  canForward: boolean;
}>();

const emit = defineEmits<{
  (e: "update:searchQuery", value: string): void;
  (e: "scope-change", value: "current" | "all"): void;
  (e: "toggleSidebar"): void;
  (e: "toggleTheme"): void;
  (e: "back"): void;
  (e: "forward"): void;
  (e: "openFolder"): void;
}>();
</script>

<template>
  <div class="layout">
    <aside
      id="sidebar"
      class="sidebar mobile"
      :class="{ open: isSidebarOpen, closed: !isSidebarOpen }"
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

    <div
      v-if="isSidebarOpen"
      class="sidebar-backdrop"
      @click="emit('toggleSidebar')"
    ></div>

    <section class="content" :class="{ 'bars-hidden': !barsVisible }" id="main-content" tabindex="-1">
      <MobileHeader
        :is-dark="theme === 'dark'"
        :search-query="searchQuery"
        :search-scope="searchScope"
        :bars-visible="barsVisible"
        @update:search-query="emit('update:searchQuery', $event)"
        @scope-change="emit('scope-change', $event)"
        @toggle-sidebar="emit('toggleSidebar')"
        @toggle-theme="emit('toggleTheme')"
      />

      <div class="content-body">
        <GalleryGrid
          :is-mobile="true"
          :bars-visible="barsVisible"
        />
      </div>

      <MobileFloatingBottomBar
        :can-back="canBack"
        :can-forward="canForward"
        :current-path="currentPath"
        :bars-visible="barsVisible"
        @back="emit('back')"
        @forward="emit('forward')"
        @open-folder="emit('openFolder')"
      />
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
  overflow: visible;
  display: flex;
  flex-direction: column;
}

.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  width: 240px;
  height: 100dvh;
  height: 100vh; /* fallback */
  z-index: 100;
  transform: translateX(-100%);
  box-shadow: var(--gallery-shadow-xl, 0 10px 30px rgba(0, 0, 0, 0.25));
  background: linear-gradient(180deg, rgba(0, 0, 0, 0.02), rgba(0, 0, 0, 0.04)), var(--surface-color);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.sidebar.mobile.open {
  transform: translateX(0);
}

.sidebar.closed {
  transform: translateX(-100%);
}

.sidebar-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 90;
  backdrop-filter: blur(2px);
}

/* Compact: <480px — compact layout */
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

  .sidebar {
    width: 100%;
    max-width: 300px;
  }
}
</style>
