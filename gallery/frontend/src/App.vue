<script setup lang="ts">
import { computed, ref, watchEffect, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from "vue";
import { useGalleryStore } from "./stores/gallery";
import SidebarHeader from "./components/SidebarHeader.vue";
import FolderTreeItem from "./components/FolderTreeItem.vue";
import GalleryGrid from "./components/GalleryGrid.vue";
import BottomNavigationBar from "./components/BottomNavigationBar.vue";
import ToastContainer from "./components/ToastContainer.vue";
import SettingsModal from "./components/SettingsModal.vue";
import IntroScreen from "./components/IntroScreen.vue";
import {
  Loader, ChevronLeft, ChevronRight, Settings, Landmark,
  Search, X, Menu
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

// ------------------------

const galleryStore = useGalleryStore();

const theme = ref<"light" | "dark">("light");
const THEME_STORAGE_KEY = "gallery-theme";
let themeMediaQuery: MediaQueryList | null = null;

const handleMediaChange = (e: MediaQueryListEvent) => {
  // Only auto-switch if user hasn't manually selected a theme
  if (!localStorage.getItem(THEME_STORAGE_KEY)) {
    theme.value = e.matches ? "dark" : "light";
  }
};
const isSidebarOpen = ref(true);
const isMobile = ref(false);
const isTablet = ref(false);
const tree = computed(() => galleryStore.sidebarTree);
const isLoading = computed(() => galleryStore.isLoading);
const currentPath = computed(() => galleryStore.currentPath);

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

const handleResize = () => {
  const width = window.innerWidth;
  isMobile.value = width < 640;
  isTablet.value = width >= 640 && width < 1024;
  if (!isMobile.value) {
    isSidebarOpen.value = true;
  } else {
    isSidebarOpen.value = false;
  }
};

// Bottom navigation state
const activeBottomTab = ref('photos')

function handleBottomNav(tabId: string) {
  activeBottomTab.value = tabId
  if (tabId === 'more') {
    isSettingsOpen.value = true
  }
}

// Handle Escape key to close sidebar on mobile
const handleGlobalKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && isMobile.value && isSidebarOpen.value) {
    closeSidebar();
  }
};

onMounted(() => {
  // Restore theme from storage or system preference
  if (typeof window !== "undefined") {
    const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
    if (savedTheme === "dark" || savedTheme === "light") {
      theme.value = savedTheme;
    } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      theme.value = "dark";
    }
  }

  // Listen for system theme changes
  themeMediaQuery = typeof window !== "undefined"
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;
  themeMediaQuery?.addEventListener("change", handleMediaChange);

  handleResize();
  window.addEventListener("resize", handleResize);
  window.addEventListener('keydown', handleGlobalKeydown);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  window.removeEventListener('keydown', handleGlobalKeydown);
  themeMediaQuery?.removeEventListener("change", handleMediaChange);
});

watchEffect(() => {
  document.documentElement.setAttribute("data-theme", theme.value);
});

watch(theme, (val) => {
  if (typeof window !== "undefined") {
    localStorage.setItem(THEME_STORAGE_KEY, val);
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

    <section class="content" id="main-content" tabindex="-1">
      <header class="content-header">
        <div class="header-left">
          <button 
            v-if="!isMobile"
            class="hamburger-btn"
            @click="toggleSidebar"
            title="Toggle sidebar"
          >
            <Menu :size="18" />
          </button>
          <button 
            class="settings-btn" 
            @click="isSettingsOpen = true"
            title="Change Intro Page"
          >
            <Settings :size="18" />
          </button>
        </div>
        <div class="brand-hero">
          <div class="brand-icon flicker-effect">
            <Landmark :size="40" />
          </div>
          <div class="brand-text">
            <p class="eyebrow">Local collections</p>
            <h1 class="brand-title">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="18" height="18" class="title-sparkle"><path fill="currentColor" d="M480 96L512 24L544 96L616 128L544 160L512 232L480 160L408 128L480 96zM160 256L224 112L288 256L432 320L288 384L224 528L160 384L16 320L160 256zM480 408L512 480L584 512L512 544L480 616L448 544L376 512L448 480L480 408z"/></svg>
              Museum Art Gallery
            </h1>
          </div>
        </div>
        <div class="header-actions">
          <button 
            class="theme-toggle" 
            type="button" 
            @click="toggleTheme" 
            :title="theme === 'dark' ? 'Switch to Light mode' : 'Switch to Dark mode'" 
            :class="{ 'is-dark': theme === 'dark' }"
          >
            <span class="toggle-track">
              <span class="toggle-thumb">
                <svg v-if="theme === 'dark'" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="18" height="18"><path fill="currentColor" d="M423.7 85.9C336.6 107.5 272 186.2 272 280C272 390.4 361.5 480 472 480C490.5 480 508.4 477.5 525.4 472.8C478.8 535.4 404.1 576 320 576C178.6 576 64 461.4 64 320C64 178.6 178.6 64 320 64C356.9 64 392 71.8 423.7 85.9z"/></svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="18" height="18"><path fill="currentColor" d="M340.8 43.6L396.3 136.2C477.1 115.9 525 104 539.9 100.2C536.2 115.1 524.2 163 503.9 243.8C575.4 286.6 617.7 312 630.9 319.9C617.7 327.8 575.4 353.2 503.9 396C524.2 476.8 536.2 524.7 539.9 539.6C525 535.9 477.1 523.9 396.3 503.6C353.5 575.1 328.1 617.4 320.2 630.6C312.3 617.4 286.9 575.1 244.1 503.6C163.3 523.9 115.5 535.9 100.5 539.6C104.2 524.7 116.2 476.8 136.5 396C65 353.2 22.7 327.8 9.5 319.9C22.7 312 65 286.6 136.5 243.8C116.2 163 104.3 115.2 100.5 100.2C115.4 103.9 163.3 115.9 244.1 136.2C286.9 64.7 312.3 22.4 320.2 9.2L340.8 43.5zM320.2 176C240.7 175.9 176.1 240.3 176 319.8C175.9 399.3 240.3 463.9 319.8 464C399.3 464.1 463.9 399.7 464 320.2C464.1 240.7 399.7 176.1 320.2 176zM319.8 416C266.8 415.9 223.9 372.8 224 319.8C224.1 266.8 267.2 223.9 320.2 224C373.2 224.1 416.1 267.2 416 320.2C415.9 373.2 372.8 416.1 319.8 416z"/></svg>
              </span>
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="16" height="16" class="icon-left"><path fill="currentColor" d="M340.8 43.6L396.3 136.2C477.1 115.9 525 104 539.9 100.2C536.2 115.1 524.2 163 503.9 243.8C575.4 286.6 617.7 312 630.9 319.9C617.7 327.8 575.4 353.2 503.9 396C524.2 476.8 536.2 524.7 539.9 539.6C525 535.9 477.1 523.9 396.3 503.6C353.5 575.1 328.1 617.4 320.2 630.6C312.3 617.4 286.9 575.1 244.1 503.6C163.3 523.9 115.5 535.9 100.5 539.6C104.2 524.7 116.2 476.8 136.5 396C65 353.2 22.7 327.8 9.5 319.9C22.7 312 65 286.6 136.5 243.8C116.2 163 104.3 115.2 100.5 100.2C115.4 103.9 163.3 115.9 244.1 136.2C286.9 64.7 312.3 22.4 320.2 9.2L340.8 43.5zM320.2 176C240.7 175.9 176.1 240.3 176 319.8C175.9 399.3 240.3 463.9 319.8 464C399.3 464.1 463.9 399.7 464 320.2C464.1 240.7 399.7 176.1 320.2 176zM319.8 416C266.8 415.9 223.9 372.8 224 319.8C224.1 266.8 267.2 223.9 320.2 224C373.2 224.1 416.1 267.2 416 320.2C415.9 373.2 372.8 416.1 319.8 416z"/></svg>
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="16" height="16" class="icon-right"><path fill="currentColor" d="M423.7 85.9C336.6 107.5 272 186.2 272 280C272 390.4 361.5 480 472 480C490.5 480 508.4 477.5 525.4 472.8C478.8 535.4 404.1 576 320 576C178.6 576 64 461.4 64 320C64 178.6 178.6 64 320 64C356.9 64 392 71.8 423.7 85.9z"/></svg>
            </span>
          </button>
          <div class="search-box">
            <Search :size="18" class="search-icon" />
            <input
              id="gallery-search"
              v-model="galleryStore.searchQuery"
              type="search"
              placeholder="Search images..."
              autocomplete="off"
            />
            <button 
              v-if="galleryStore.searchQuery" 
              class="clear-btn" 
              @click="galleryStore.clearSearch()"
              type="button"
            >
              <X :size="12" />
            </button>
          </div>
        </div>
      </header>

      <div class="content-body">
        <GalleryGrid />
      </div>
    </section>
  </div>

  <!-- Bottom nav - only on mobile/tablet -->
  <BottomNavigationBar 
    v-if="isMobile"
    active-tab="photos"
    @navigate="handleBottomNav"
  />

  <Lightbox />
  <ToastContainer />
  <SettingsModal 
    :is-open="isSettingsOpen" 
    @close="isSettingsOpen = false"
    @preview="handlePreviewIntro"
  />
</template>

<style scoped>
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.settings-btn {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: var(--surface-color);
  color: var(--text-color);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 120ms ease, box-shadow 150ms ease, border-color 120ms ease;
  font-size: 16px;
}

.settings-btn:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px rgba(214, 161, 93, 0.25);
  transform: translateY(-1px);
  color: var(--primary-color);
}

.hamburger-btn {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: var(--surface-color);
  color: var(--text-color);
  cursor: pointer;
  display: none;
  align-items: center;
  justify-content: center;
  transition: transform 120ms ease, box-shadow 150ms ease, border-color 120ms ease;
  font-size: 16px;
}

.hamburger-btn:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px rgba(214, 161, 93, 0.25);
  transform: translateY(-1px);
  color: var(--primary-color);
}

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
  padding: 24px 12px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  overflow: hidden;
}

.content-header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: start;
  gap: 12px;
  flex-shrink: 0;
}

.header-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
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
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
}

.sidebar-edge-toggle:hover {
  color: var(--primary-color);
  background: var(--surface-color);
  box-shadow: 2px 0 12px rgba(214, 161, 93, 0.3);
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
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.eyebrow {
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 12px;
  color: var(--muted-text);
}

h1 {
  margin: 4px 0 0 0;
  font-size: clamp(22px, 3vw, 30px);
  color: var(--title-color);
}

.theme-toggle {
  position: relative;
  width: 72px;
  height: 36px;
  border: none;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 0;
  border-radius: 50px;
  cursor: pointer;
  transition: all 0.4s cubic-bezier(0.68, -0.15, 0.265, 1.35);
  box-shadow: 
    inset 0 2px 4px rgba(0, 0, 0, 0.2),
    0 4px 12px rgba(102, 126, 234, 0.3);
}

.theme-toggle.is-dark {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  box-shadow: 
    inset 0 2px 4px rgba(0, 0, 0, 0.4),
    0 4px 12px rgba(0, 0, 0, 0.4);
}

.toggle-track {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  height: 100%;
  padding: 0 10px;
}

.toggle-thumb {
  position: absolute;
  left: 4px;
  top: 50%;
  transform: translateY(-50%);
  width: 28px;
  height: 28px;
  background: linear-gradient(180deg, #fff 0%, #f0f0f0 100%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.4s cubic-bezier(0.68, -0.15, 0.265, 1.35);
  box-shadow: 
    0 2px 8px rgba(0, 0, 0, 0.2),
    0 1px 2px rgba(0, 0, 0, 0.1);
  z-index: 2;
}

.theme-toggle.is-dark .toggle-thumb {
  left: calc(100% - 32px);
  background: linear-gradient(180deg, #ffd54f 0%, #ffb300 100%);
  box-shadow: 
    0 2px 8px rgba(255, 213, 79, 0.4),
    0 0 20px rgba(255, 213, 79, 0.3);
}

.toggle-thumb svg {
  width: 18px;
  height: 18px;
  color: #764ba2;
  transition: all 0.3s ease;
}

.theme-toggle.is-dark .toggle-thumb svg {
  color: #1a1a2e;
}

.icon-left,
.icon-right {
  width: 16px;
  height: 16px;
  opacity: 0.6;
  transition: all 0.3s ease;
  z-index: 1;
}

.icon-left {
  color: #ffd54f;
}

.icon-right {
  color: #fff;
}

.theme-toggle:hover {
  transform: scale(1.05);
}

.theme-toggle:hover .toggle-thumb {
  box-shadow: 
    0 4px 12px rgba(0, 0, 0, 0.25),
    0 2px 4px rgba(0, 0, 0, 0.15);
}

.theme-toggle.is-dark:hover .toggle-thumb {
  box-shadow: 
    0 4px 16px rgba(255, 213, 79, 0.5),
    0 0 30px rgba(255, 213, 79, 0.4);
}

.theme-toggle:active {
  transform: scale(0.98);
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
  background: var(--surface-color);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 10px;
  padding: 0 12px;
  min-width: 220px;
  height: 40px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.search-box:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px rgba(214, 161, 93, 0.25);
}

.search-box:focus-within {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px rgba(214, 161, 93, 0.25);
}

.search-box input {
  flex: 1;
  border: none;
  background: transparent;
  padding: 0 8px;
  font-size: 14px;
  color: var(--text-color);
  outline: none;
  min-width: 0;
}

.search-box input::placeholder {
  color: var(--muted-text);
}

.search-box .clear-btn {
  background: transparent;
  border: none;
  color: var(--muted-text);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

.search-box .clear-btn:hover {
  background: rgba(0, 0, 0, 0.05);
  color: var(--text-color);
}

.brand-hero {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
}

/* === Trong file frontend/src/App.vue === */

.brand-icon {
  /* --- 1. CẤU TRÚC CHUNG (Giữ nguyên kích thước cho cả 2 theme) --- */
  width: 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 15px;
  border-radius: 50%;
  margin-top: 12px; /* Push icon down to align with main title line */
  
  /* Transition để hiệu ứng chuyển màu mượt mà */
  transition: all 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);

  /* --- 2. LIGHT MODE (Mặc định: Đơn sắc, Không viền, Không Glow) --- */
  color: var(--title-color);     /* Dùng màu Navy đậm của tiêu đề cho đồng bộ */
  border: 2px solid transparent; /* Viền trong suốt (giữ chỗ) */
  box-shadow: none;              /* Không bóng */
  filter: none;                  /* Không phát sáng */
}

/* Dark mode styles được chuyển xuống <style> block riêng (không scoped) ở cuối file */

.brand-text {
  text-align: left;
}

/* Keyframes for hover effects only - main animation in main.scss */
@keyframes underline-grow {
  0% { transform: scaleX(0); }
  100% { transform: scaleX(1); }
}

@keyframes subtle-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-2px); }
}

.brand-title {
  margin: 0;
  font-family: "Cinzel", serif;
  font-size: clamp(28px, 5vw, 42px);
  font-weight: 600;
  letter-spacing: 0.08em;
  position: relative;
  display: inline-block;
  
  /* Clean solid color - elegant & readable */
  color: var(--title-color);
  
  /* Smooth transitions for hover effects */
  transition: 
    letter-spacing 0.6s cubic-bezier(0.23, 1, 0.32, 1),
    color 0.4s ease;
}

/* Decorative underline with sweep animation */
.brand-title::after {
  content: "";
  position: absolute;
  bottom: -6px;
  left: 0;
  width: 100%;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    #c9a962 10%,
    #d4af37 50%,
    #c9a962 90%,
    transparent 100%
  );
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.8s cubic-bezier(0.23, 1, 0.32, 1);
  opacity: 0.85;
}

/* Decorative sparkle icon - styles in main.scss for theme support */

/* Hover effects - elegant reveal */
.brand-hero:hover .brand-title {
  letter-spacing: 0.12em;
}

.brand-hero:hover .brand-title::after {
  transform: scaleX(1);
  transform-origin: left;
}

/* .brand-hero:hover .title-sparkle - styles in main.scss */

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
    padding: 20px 10px;
  }

  .brand-icon {
    width: 48px;
    height: 48px;
    margin-right: 10px;
  }

  .brand-title {
    font-size: clamp(22px, 4vw, 32px) !important;
  }

  .sidebar-edge-toggle {
    left: 220px;
  }

  .sidebar-edge-toggle:not(.sidebar-open) {
    left: 0;
  }

  .search-box {
    min-width: 180px;
  }
}

/* NEW: Tablet range (640-1024px) — sidebar 240px persistent + hamburger always visible, edge-toggle hidden */
@media (min-width: 641px) and (max-width: 1024px) {
  .hamburger-btn {
    display: inline-flex;
  }

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

  .brand-hero {
    transform: scale(0.8);
    transform-origin: left center;
  }
}

/* Phone: <640px — sidebar becomes overlay, hamburger appears */
@media (max-width: 640px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .hamburger-btn {
    display: inline-flex;
    flex-shrink: 0;
    width: 30px;
    height: 30px;
    min-width: 44px;
    min-height: 44px;
  }

  .hamburger-btn svg {
    width: 16px;
    height: 16px;
  }

  .sidebar-edge-toggle {
    display: none !important;
  }

  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    width: 260px;
    height: 100vh;
    z-index: 100;
    transform: translateX(-100%);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
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

  .content-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    min-height: 48px;
  }

  /* Explicit flex wrappers for header-left and header-actions (no display:contents) */
  .header-left,
  .header-actions {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .header-left {
    flex-shrink: 0;
  }

  .header-actions {
    flex: 1;
    margin-left: auto;
  }

  /* Mobile full-width search bar */
  .search-box {
    flex: 1;
    min-width: 0;
    height: 36px;
    padding: 0 10px;
    display: flex;
    align-items: center;
    gap: 6px;
    border-radius: 10px;
    border: 1px solid rgba(0, 0, 0, 0.12);
    background: var(--surface-color);
    transition: border-color 0.2s, box-shadow 0.2s;
  }

  .search-box:hover {
    border-color: var(--primary-color);
    box-shadow: 0 4px 12px rgba(214, 161, 93, 0.25);
  }

  .search-box:focus-within {
    border-color: var(--primary-color);
    box-shadow: 0 4px 12px rgba(214, 161, 93, 0.25);
  }

  .search-box input {
    flex: 1;
    border: none;
    background: transparent;
    padding: 0;
    font-size: 14px;
    color: var(--text-color);
    outline: none;
    min-width: 0;
  }

  .search-box input::placeholder {
    color: var(--muted-text);
  }

  .search-box .clear-btn {
    background: transparent;
    border: none;
    color: var(--muted-text);
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .search-box .clear-btn:hover {
    background: rgba(0, 0, 0, 0.05);
    color: var(--text-color);
  }

  .theme-toggle {
    display: none;
  }

  .settings-btn {
    display: none;
  }

  .brand-hero {
    display: none;
  }

  .content {
    padding: 8px 6px;
    padding-bottom: 0;
    gap: 8px;
  }

  .content-body {
    padding: 4px 0;
    border-radius: 8px;
  }

  .brand-icon {
    width: 44px;
    height: 44px;
    margin-right: 8px;
    margin-top: 8px;
  }

  .brand-title {
    font-size: clamp(18px, 4vw, 24px) !important;
  }
}

/* Small phone: <480px — compact layout */
@media (max-width: 480px) {
  .content-header {
    padding: 4px 12px;
    min-height: 44px;
    gap: 4px;
  }

  .search-box {
    width: 30px;
    height: 30px;
  }

  .hamburger-btn {
    width: 28px;
    height: 28px;
  }

  .settings-btn {
    width: 28px;
    height: 28px;
  }

  .settings-btn svg {
    width: 14px;
    height: 14px;
  }

  .search-box.expanded {
    height: 36px;
    top: 6px;
    left: 4px;
    right: 4px;
  }

  .content {
    padding: 6px 4px;
    padding-bottom: 0;
    gap: 6px;
  }

  .content-body {
    padding: 4px;
    border-radius: 6px;
  }

  .sidebar {
    width: 100%;
    max-width: 300px;
  }
}

/* Base state cho animation - chỉ để tắt trong light mode */
.brand-icon.flicker-effect {
  animation: none;
}

</style>
