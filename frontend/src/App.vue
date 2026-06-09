<script setup lang="ts">
import { computed, ref, watchEffect, watch, onMounted, onBeforeUnmount, defineAsyncComponent, provide } from "vue";
import { useGalleryStore } from "./stores/gallery";
import ToastContainer from "./components/ToastContainer.vue";
import SettingsModal from "./components/SettingsModal.vue";
import IntroScreen from "./components/IntroScreen.vue";
import DesktopLayout from "./layouts/DesktopLayout.vue";
import TabletLayout from "./layouts/TabletLayout.vue";
import MobileLayout from "./layouts/MobileLayout.vue";
import { useScrollVisibility } from "./composables/useScrollVisibility";
import { useDevice } from "./composables/useDevice";
import { galleryScrollContainerRefKey } from "./injectionKeys";
import { closeSidebarKey } from "./injectionKeys";

const Lightbox = defineAsyncComponent(() => import("./components/Lightbox.vue"));
const isDev = import.meta.env.DEV;
const VueQueryDevtools = isDev
  ? defineAsyncComponent(() =>
      import("@tanstack/vue-query-devtools").then((m) => m.VueQueryDevtools)
    )
  : null;

const { isMobile, isTablet } = useDevice();

// --- INTRO PAGE LOGIC ---
const showIntro = ref(!isMobile.value && !isTablet.value);
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

const scrollerRef = ref<HTMLElement | null>(null);
provide(galleryScrollContainerRefKey, scrollerRef);

const { barsVisible } = useScrollVisibility(scrollerRef);

const toggleTheme = () => {
  theme.value = theme.value === "light" ? "dark" : "light";
};

const toggleSidebar = () => {
  isSidebarOpen.value = !isSidebarOpen.value;
};

const closeSidebar = () => {
  if (isMobile.value || isTablet.value) {
    isSidebarOpen.value = false;
  }
};
provide(closeSidebarKey, closeSidebar);

// Handle Escape key to close sidebar on mobile
const handleGlobalKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && (isMobile.value || isTablet.value) && isSidebarOpen.value) {
    closeSidebar();
  }
};

onMounted(() => {
  // Auto-load persisted root path on app start
  if (galleryStore.rootPath && !galleryStore.hasEverLoaded) {
    galleryStore.setRootPath(galleryStore.rootPath);
  }

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

const canBack = computed(() => galleryStore.historyIndex > 0);
const canForward = computed(() => galleryStore.historyIndex < galleryStore.history.length - 1);
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
  <MobileLayout
    v-else-if="isMobile"
    :theme="theme"
    :is-sidebar-open="isSidebarOpen"
    :tree="tree"
    :is-loading="isLoading"
    :current-path="currentPath"
    :search-query="galleryStore.searchQuery"
    :search-scope="galleryStore.searchScope"
    :bars-visible="barsVisible"
    :can-back="canBack"
    :can-forward="canForward"
    @update:search-query="galleryStore.setSearchQuery($event)"
    @scope-change="galleryStore.setSearchScope($event)"
    @toggle-sidebar="toggleSidebar"
    @toggle-theme="toggleTheme"
    @back="galleryStore.goBack()"
    @forward="galleryStore.goForward()"
    @open-folder="galleryStore.openInExplorer()"
  />

  <TabletLayout
    v-else-if="isTablet"
    :theme="theme"
    :is-sidebar-open="isSidebarOpen"
    :tree="tree"
    :is-loading="isLoading"
    :current-path="currentPath"
    :search-query="galleryStore.searchQuery"
    :search-scope="galleryStore.searchScope"
    @update:search-query="galleryStore.setSearchQuery($event)"
    @scope-change="galleryStore.setSearchScope($event)"
    @toggle-sidebar="toggleSidebar"
    @toggle-theme="toggleTheme"
    @open-settings="isSettingsOpen = true"
  />

  <DesktopLayout
    v-else
    :theme="theme"
    :is-sidebar-open="isSidebarOpen"
    :tree="tree"
    :is-loading="isLoading"
    :current-path="currentPath"
    :search-query="galleryStore.searchQuery"
    :search-scope="galleryStore.searchScope"
    @update:search-query="galleryStore.setSearchQuery($event)"
    @scope-change="galleryStore.setSearchScope($event)"
    @toggle-sidebar="toggleSidebar"
    @toggle-theme="toggleTheme"
    @open-settings="isSettingsOpen = true"
  />

  <Lightbox />
  <ToastContainer v-if="!isMobile" />
  <SettingsModal 
    :is-open="isSettingsOpen" 
    @close="isSettingsOpen = false"
    @preview="handlePreviewIntro"
  />
  <component
    :is="VueQueryDevtools"
    v-if="isDev && VueQueryDevtools"
    button-position="bottom-right"
    position="bottom"
  />
</template>

<style scoped>
/* Layout styles moved to layout-specific components (DesktopLayout, TabletLayout, MobileLayout) */
</style>
