<script setup lang="ts">
import { computed, ref, defineAsyncComponent, provide, watch } from "vue";
import { useEventListener, useStorage } from "@vueuse/core";
import { useGalleryStore } from "./stores/gallery";
import GalleryToaster from "./components/GalleryToaster.vue";
import SettingsModal from "./components/SettingsModal.vue";
import IntroScreen from "./components/IntroScreen.vue";
import DesktopLayout from "./layouts/DesktopLayout.vue";
import TabletLayout from "./layouts/TabletLayout.vue";
import MobileLayout from "./layouts/MobileLayout.vue";
import { useScrollVisibility } from "./composables/useScrollVisibility";
import { useDevice } from "./composables/useDevice";
import { useGalleryTheme } from "./composables/useGalleryTheme";
import { galleryScrollContainerRefKey } from "./injectionKeys";
import { closeSidebarKey } from "./injectionKeys";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useRouter } from "vue-router";
import { useLibrariesQuery } from "./composables/admin/useLibrariesQuery";
import { useRouteChrome } from "@/composables/useRouteChrome";
import { useSidebarTreeQuery } from "./composables/useSidebarTreeQuery";

const Lightbox = defineAsyncComponent(() => import("./components/Lightbox.vue"));
const showDevtools = import.meta.env.DEV || import.meta.env.VITE_DEVTOOLS === "true";
const VueQueryDevtools = showDevtools
  ? defineAsyncComponent(() => import("@tanstack/vue-query-devtools").then((m) => m.VueQueryDevtools))
  : null;

const { isMobile, isTablet } = useDevice();
const router = useRouter();
const { isMetadataRoute, isAdminRoute, isGalleryRoute, showBackToGallery } = useRouteChrome();

// --- INTRO PAGE LOGIC ---
const showIntro = ref(!isMobile.value && !isTablet.value && isGalleryRoute.value);
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

watch(
  () => showBackToGallery.value,
  (shouldShowBackToGallery) => {
    if (shouldShowBackToGallery) {
      showIntro.value = false;
      introPreviewUrl.value = null;
    }
  },
);

watch(
  () => isMetadataRoute.value && (isMobile.value || isTablet.value),
  (shouldRedirect) => {
    if (shouldRedirect) {
      router.replace("/");
    }
  },
  { immediate: true },
);

const galleryStore = useGalleryStore();
const librariesQuery = useLibrariesQuery();

watch(
  () => librariesQuery.isSuccess.value,
  (isSuccess) => {
    if (isSuccess && !galleryStore.activeLibraryHydrated) {
      galleryStore.hydrateActiveLibrary(librariesQuery.data.value ?? []);
    }
  },
  { immediate: true },
);

const { resolvedTheme, toggleTheme } = useGalleryTheme();

const SIDEBAR_STATE_KEY = "gallery-sidebar-open";

const isSidebarOpen = useStorage(SIDEBAR_STATE_KEY, true);

watch(
  [isAdminRoute, isMobile, isTablet],
  ([isAdminRoute, mobile, tablet]) => {
    if (isAdminRoute && (mobile || tablet)) {
      isSidebarOpen.value = false;
    }
  },
  { immediate: true },
);

const tree = computed(() => galleryStore.sidebarTree);
const isLoading = computed(() => galleryStore.isLoading);
const currentPath = computed(() => galleryStore.currentBrowsePath);
const activeLibraryId = computed(() => galleryStore.activeLibraryId);
useSidebarTreeQuery(activeLibraryId, currentPath);

const scrollerRef = ref<HTMLElement | null>(null);
provide(galleryScrollContainerRefKey, scrollerRef);

const { barsVisible } = useScrollVisibility(scrollerRef);

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
  if (e.key === "Escape" && (isMobile.value || isTablet.value) && isSidebarOpen.value) {
    closeSidebar();
  }
};

useEventListener(window, "keydown", handleGlobalKeydown);

const canBack = computed(() => galleryStore.historyIndex > 0);
const canForward = computed(() => galleryStore.historyIndex < galleryStore.history.length - 1);
</script>

<template>
  <TooltipProvider :delay-duration="300" :skip-delay-duration="100">
    <!-- Intro Screen -->
    <IntroScreen v-if="showIntro" v-model:visible="showIntro" :force-url="introPreviewUrl" @enter="handleIntroEnter" />

    <!-- Main App Layout -->
    <MobileLayout
      v-else-if="isMobile"
      :theme="resolvedTheme"
      :is-sidebar-open="isSidebarOpen"
      :tree="tree"
      :is-loading="isLoading"
      :current-path="currentPath"
      :search-query="galleryStore.searchQuery"
      :search-scope="galleryStore.searchScope"
      :bars-visible="barsVisible"
      :can-back="canBack"
      :can-forward="canForward"
      :show-back-to-gallery="showBackToGallery"
      @update:search-query="galleryStore.setSearchQuery($event)"
      @scope-change="galleryStore.setSearchScope($event)"
      @update:sidebar-open="isSidebarOpen = $event"
      @toggle-sidebar="toggleSidebar"
      @toggle-theme="toggleTheme"
      @back="galleryStore.goBack()"
      @forward="galleryStore.goForward()"
      @open-folder="galleryStore.openInExplorer()"
    />

    <TabletLayout
      v-else-if="isTablet"
      :theme="resolvedTheme"
      :is-sidebar-open="isSidebarOpen"
      :tree="tree"
      :is-loading="isLoading"
      :current-path="currentPath"
      :search-query="galleryStore.searchQuery"
      :search-scope="galleryStore.searchScope"
      @update:search-query="galleryStore.setSearchQuery($event)"
      @scope-change="galleryStore.setSearchScope($event)"
      @update:sidebar-open="isSidebarOpen = $event"
      @toggle-sidebar="toggleSidebar"
      @toggle-theme="toggleTheme"
      @open-settings="isSettingsOpen = true"
    />

    <DesktopLayout
      v-else
      :theme="resolvedTheme"
      :is-sidebar-open="isSidebarOpen"
      :tree="tree"
      :is-loading="isLoading"
      :current-path="currentPath"
      :search-query="galleryStore.searchQuery"
      :search-scope="galleryStore.searchScope"
      @update:search-query="galleryStore.setSearchQuery($event)"
      @scope-change="galleryStore.setSearchScope($event)"
      @update:sidebar-open="isSidebarOpen = $event"
      @toggle-sidebar="toggleSidebar"
      @toggle-theme="toggleTheme"
      @open-settings="isSettingsOpen = true"
    />

    <Lightbox />
    <GalleryToaster v-if="!isMobile" />
    <SettingsModal :is-open="isSettingsOpen" @close="isSettingsOpen = false" @preview="handlePreviewIntro" />
    <component
      :is="VueQueryDevtools"
      v-if="showDevtools && VueQueryDevtools"
      button-position="bottom-right"
      position="bottom"
    />
  </TooltipProvider>
</template>

<style scoped>
/* Layout styles moved to layout-specific components (DesktopLayout, TabletLayout, MobileLayout) */
</style>
