<script setup lang="ts">
import { computed, ref, watchEffect, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from "vue";
import { useGalleryStore } from "./stores/gallery";
import SidebarHeader from "./components/SidebarHeader.vue";
import FolderTreeItem from "./components/FolderTreeItem.vue";
import GalleryGrid from "./components/GalleryGrid.vue";
import ToastContainer from "./components/ToastContainer.vue";
import SettingsModal from "./components/SettingsModal.vue";
import IntroScreen from "./components/IntroScreen.vue";
import AppHeader from "./components/AppHeader.vue";
import MobileHeader from "./components/MobileHeader.vue";
import MobileFloatingBottomBar from "./components/MobileFloatingBottomBar.vue";
import { useScrollVisibility } from "./composables/useScrollVisibility";
import { useDevice } from "./composables/useDevice";
import {
  Loader, ChevronLeft, ChevronRight
} from "lucide-vue-next";

const Lightbox = defineAsyncComponent(() => import("./components/Lightbox.vue"));

// --- INTRO PAGE LOGIC ---
const showIntro = ref(true);
const introPreviewUrl = ref<string | null>(null);
const isSettingsOpen = ref(false);
const handleIntroEnter = () => {
  showIntro.value = false;
  introPreviewUrl.value = null;
};

const handlePreviewIntro = (url: string) => {
  introPreviewUrl.value = url;
  showIntro.value = true;
  isSettingsOpen.value = false;
};
// ------------------------

const galleryStore = useGalleryStore();

const theme = ref<"light" | "dark">(
  (() => {
    // Initialize from system preference during setup to avoid initial flash
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem('gallery-theme');
        if (saved === "dark" || saved === "light") return saved;
      } catch (e) {
        // Safari Private Browsing — localStorage throws
      }
      if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
        return "dark";
      }
    }
    return "light";
  })()
);
const THEME_STORAGE_KEY = "gallery-theme";
let themeMediaQuery: MediaQueryList | null = null;

const handleMediaChange = (e: MediaQueryListEvent) => {
  // Only auto-switch if user hasn't manually selected a theme
  if (!localStorage.getItem(THEME_STORAGE_KEY)) {
    theme.value = e.matches ? "dark" : "light";
  }
};
const isSidebarOpen = ref(true);
const tree = computed(() => galleryStore.sidebarTree);
const isLoading = computed(() => galleryStore.isLoading);
const currentPath = computed(() => galleryStore.currentPath);

const { barsVisible } = useScrollVisibility();
const { isMobile } = useDevice();

const toggleTheme = () => {
  theme.value = theme.value === "light" ? "dark" : "light";
};

const toggleSidebar = () => {
  isSidebarOpen.value = !isSidebarOpen.value;
};

const closeSidebar = () => {
  if (isMobile.value) {
    isSidebarOpen.value = false;
  }
};

// Handle Escape key to close sidebar on mobile
const handleGlobalKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && isMobile.value && isSidebarOpen.value) {
    closeSidebar();
  }
};

onMounted(() => {
  // Restore theme from storage or system preference
  if (typeof window !== "undefined") {
    try {
      const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
      if (savedTheme === "dark" || savedTheme === "light") {
        theme.value = savedTheme;
      } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
        theme.value = "dark";
      }
    } catch (e) {
      // Safari Private Browsing — localStorage throws; use system preference
      if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
        theme.value = "dark";
      }
    }
  }

  // Listen for system theme changes
  themeMediaQuery = typeof window !== "undefined"
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;
  themeMediaQuery?.addEventListener("change", handleMediaChange);

  window.addEventListener('keydown', handleGlobalKeydown);
});

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleGlobalKeydown);
  themeMediaQuery?.removeEventListener("change", handleMediaChange);
});

watchEffect(() => {
  document.documentElement.setAttribute("data-theme", theme.value);
});

watch(theme, (val) => {
  if (typeof window !== "undefined") {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, val);
    } catch (e) {
      // Safari Private Browsing — localStorage throws; silently ignore
    }
  }
});
</script>

<template>
  <!-- Intro Screen -->
  <IntroScreen
    v-if="showIntro"
    v-model:visible="showIntro"
    :force-url="introPreviewUrl"
    @enter="handleIntroEnter"
  />

  <!-- Main App Layout -->
  <div v-else class="layout" :class="{ collapsed: !isSidebarOpen && !isMobile }">
    <aside
      id="sidebar"
      class="sidebar"
      :class="{ open: isSidebarOpen, mobile: isMobile, closed: !isSidebarOpen && !isMobile }"
    >
      <SidebarHeader />
      <div class="sidebar-body">
        <div class="sidebar-title" id="folder-tree-label">
          <span>Folder Tree</span>
          <span v-if="isLoading" class="loading-pill">
            <Loader :size="16" class="lucide-spin" /> Loading
          </span>
        </div>
        <div 
          class="tree-container"
        >
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
    
    <!-- Sidebar Edge Toggle Button -->
    <button
      class="sidebar-edge-toggle"
      :class="{ 'sidebar-open': isSidebarOpen }"
      type="button"
      @click="toggleSidebar"
      :title="isSidebarOpen ? 'Hide Sidebar' : 'Show Sidebar'"
    >
      <ChevronLeft v-if="isSidebarOpen" :size="14" />
      <ChevronRight v-else :size="14" />
    </button>
    
    <div
      v-if="isSidebarOpen && isMobile"
      class="sidebar-backdrop"
      @click="closeSidebar"
    ></div>

    <section class="content" :class="{ 'bars-hidden': isMobile && !barsVisible }" id="main-content" tabindex="-1">
      <MobileHeader
        v-if="isMobile"
        :is-dark="theme === 'dark'"
        :search-query="galleryStore.searchQuery"
        :bars-visible="barsVisible"
        @update:search-query="galleryStore.searchQuery = $event"
        @toggle-sidebar="toggleSidebar"
        @toggle-theme="toggleTheme"
        @open-settings="isSettingsOpen = true"
      />

      <AppHeader
        v-if="!isMobile"
        :is-mobile="isMobile"
        :is-sidebar-open="isSidebarOpen"
        :is-dark="theme === 'dark'"
        :search-query="galleryStore.searchQuery"
        @update:search-query="galleryStore.searchQuery = $event"
        @toggle-sidebar="toggleSidebar"
        @toggle-theme="toggleTheme"
        @open-settings="isSettingsOpen = true"
      />

      <div class="content-body">
        <GalleryGrid
          :is-mobile="isMobile"
        />
      </div>

      <MobileFloatingBottomBar
        v-if="isMobile"
        :can-back="galleryStore.historyIndex > 0"
        :can-forward="galleryStore.historyIndex < galleryStore.history.length - 1"
        :current-path="galleryStore.currentPath"
        :bars-visible="barsVisible"
        @back="galleryStore.goBack()"
        @forward="galleryStore.goForward()"
        @open-folder="galleryStore.openInExplorer()"
      />
    </section>
  </div>

  <Lightbox />
  <ToastContainer v-if="!isMobile" />
  <SettingsModal 
    :is-open="isSettingsOpen" 
    @close="isSettingsOpen = false"
    @preview="handlePreviewIntro"
  />
</template>

<style scoped>
.layout {
  height: 100vh;
  background: var(--bg-color);
  color: var(--text-color);
  display: grid;
  grid-template-columns: 280px 1fr;
  overflow-x: visible;
  overflow-y: hidden;
}

.layout.collapsed {
  grid-template-columns: 0 1fr;
}

.sidebar {
  background: linear-gradient(180deg, rgba(0, 0, 0, 0.02), rgba(0, 0, 0, 0.04)), var(--surface-color);
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.sidebar.closed {
  transform: translateX(-100%);
  box-shadow: none;
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
  padding: 16px 16px 24px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  overflow: hidden;
  transition: padding-top 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.content.bars-hidden {
  padding-top: max(8px, env(safe-area-inset-top));
}

/* Sidebar Edge Toggle Button */
.sidebar-edge-toggle {
  position: fixed;
  left: 260px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 101;
  width: 24px;
  height: 48px;
  border: none;
  border-radius: 0 8px 8px 0;
  background: var(--surface-color);
  color: var(--muted-text);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--gallery-shadow-sm, 2px 0 8px rgba(0, 0, 0, 0.1));
  transition: all 0.3s ease;
}

.sidebar-edge-toggle:hover {
  color: var(--primary-color);
  background: var(--surface-color);
  box-shadow: var(--gallery-shadow-md, 2px 0 12px rgba(214, 161, 93, 0.3));
}

.sidebar-edge-toggle:not(.sidebar-open) {
  left: 0;
  border-radius: 0 8px 8px 0;
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

/* =============================================
   RESPONSIVE BREAKPOINTS
   ============================================= */

/* Tablet: 768px - 1024px */
@media (max-width: 1024px) {
  .layout {
    grid-template-columns: 240px 1fr;
  }

  .layout.collapsed {
    grid-template-columns: 0 1fr;
  }

  .content {
    padding: 16px 12px 20px 12px;
  }

  .sidebar-edge-toggle {
    left: 220px;
  }

  .sidebar-edge-toggle:not(.sidebar-open) {
    left: 0;
  }
}

/* NEW: Tablet range (768-1024px) — sidebar 240px persistent + hamburger always visible, edge-toggle hidden */
@media (min-width: 768px) and (max-width: 1024px) {
  .sidebar-edge-toggle {
    display: none !important;
  }

  .sidebar {
    width: 240px;
  }

  .sidebar.closed {
    transform: translateX(0);
    width: 240px;
  }

  .sidebar-backdrop {
    display: none;
  }
}

/* Phone: <768px — sidebar becomes overlay, hamburger appears */
@media (max-width: 767px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .sidebar-edge-toggle {
    display: none !important;
  }

  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    width: 240px;
    height: 100vh;
    z-index: 100;
    transform: translateX(-100%);
    box-shadow: var(--gallery-shadow-xl, 0 10px 30px rgba(0, 0, 0, 0.25));
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

  .content {
    padding: 60px 16px 72px 16px;
    gap: 8px;
    overflow: hidden;
  }

  .content-body {
    background: transparent;
    border-radius: 0;
    box-shadow: none;
    padding: 4px 4px;
  }

  .tab-empty-placeholder {
    display: none;
  }
}

/* Small phone: <480px — compact layout */
@media (max-width: 480px) {
  .content {
    padding: 56px 12px 72px 12px;
    gap: 6px;
    overflow: hidden;
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
