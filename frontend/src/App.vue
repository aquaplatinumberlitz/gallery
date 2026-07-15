<script setup lang="ts">
import { computed, ref, shallowRef, defineAsyncComponent, provide, watch } from "vue";
import { useEventListener, useStorage } from "@vueuse/core";
import { useGalleryStore } from "./stores/gallery";
import GalleryToaster from "./components/GalleryToaster.vue";
import IntroScreen from "./components/IntroScreen.vue";
import { useScrollVisibility } from "./composables/useScrollVisibility";
import { useDevice } from "./composables/useDevice";
import { useGalleryTheme } from "./composables/useGalleryTheme";
import { galleryScrollContainerRefKey } from "./injectionKeys";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useRouter } from "vue-router";
import { useLibrariesQuery } from "./composables/admin/useLibrariesQuery";
import { useRouteChrome } from "@/composables/useRouteChrome";
import { useSidebarTreeQuery } from "./composables/useSidebarTreeQuery";
import { MotionConfig } from "motion-v";
import { useFieldedSearch } from "./composables/useFieldedSearch";
import { useSearchUrlSync } from "./composables/useSearchUrlSync";
import type { FieldFilter, PersistableSearchRequestV1 } from "./types";

const Lightbox = defineAsyncComponent(() => import("./components/Lightbox.vue"));
const RelatedAssetsPanel = defineAsyncComponent(() => import("./components/RelatedAssetsPanel.vue"));
const DesktopLayout = defineAsyncComponent(() => import("./layouts/DesktopLayout.vue"));
const TabletLayout = defineAsyncComponent(() => import("./layouts/TabletLayout.vue"));
const MobileLayout = defineAsyncComponent(() => import("./layouts/MobileLayout.vue"));
const SettingsModal = defineAsyncComponent(() => import("./components/SettingsModal.vue"));
const AdvancedSearchDrawer = defineAsyncComponent(() => import("./components/search/AdvancedSearchDrawer.vue"));
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
const rawSearchQuery = computed(() => galleryStore.searchQuery);
const fieldedSearch = useFieldedSearch(rawSearchQuery);
const isAdvancedSearchOpen = shallowRef(false);
const advancedSearchInitialFilters = shallowRef<FieldFilter[]>([]);

watch(
  () => galleryStore.searchFieldErrors,
  (errors) => {
    if (Object.keys(errors).length) isAdvancedSearchOpen.value = true;
  },
  { deep: true },
);

function handleSearchQueryUpdate(value: string) {
  galleryStore.updateLexicalSearchText(value);
}

function openAdvancedSearch() {
  advancedSearchInitialFilters.value = [...fieldedSearch.fieldedFilters.value];
  isAdvancedSearchOpen.value = true;
}

function handleAdvancedSearchApply(filters: FieldFilter[]) {
  galleryStore.updateLexicalSearchText(fieldedSearch.applyFilters(filters));
  galleryStore.submitSearch();
}

function handleCanonicalSearchApply(request: PersistableSearchRequestV1) {
  const libraries = librariesQuery.data.value ?? [];
  const scope = request.scope;
  if (scope.kind !== "all") {
    const library = libraries.find((item) => item.id === scope.library_id);
    if (!library) return;
    const importPath =
      scope.kind === "folder"
        ? library.import_paths.find((item) => item.id === scope.import_path_id)
        : library.import_paths[0];
    if (!importPath || !galleryStore.setActiveLibrary(library, importPath)) return;
    if (scope.kind === "folder" && scope.relative_path) {
      const root = importPath.path.replace(/[\\/]+$/, "");
      galleryStore.selectFolder(`${root}/${scope.relative_path}`);
    }
  }
  galleryStore.setSearchQuery(request.text);
  galleryStore.setSearchMode(request.mode, false);
  galleryStore.setSearchFilters(request.filters, false);
  galleryStore.setSearchScope(scope.kind === "folder" ? "current" : scope.kind, false);
  galleryStore.submitSearch();
}

watch(
  () => librariesQuery.isSuccess.value,
  (isSuccess) => {
    if (isSuccess && !galleryStore.activeLibraryHydrated) {
      galleryStore.hydrateActiveLibrary(librariesQuery.data.value ?? []);
    }
  },
  { immediate: true },
);

useSearchUrlSync(
  () => librariesQuery.data.value ?? [],
  () => librariesQuery.isSuccess.value && galleryStore.activeLibraryHydrated,
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

const isLoading = computed(() => galleryStore.isLoading);
const currentPath = computed(() => galleryStore.currentBrowsePath);
const activeLibraryId = computed(() => galleryStore.activeLibraryId);
const activeImportRootPath = computed(() => galleryStore.activeImportRootPath || null);
const hasActiveLibrary = computed(() => galleryStore.activeLibraryId !== null);
const sidebarTreeQuery = useSidebarTreeQuery(activeLibraryId, activeImportRootPath);
const tree = computed(() => sidebarTreeQuery.tree.value);

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
  <MotionConfig reduced-motion="user">
    <TooltipProvider :delay-duration="300" :skip-delay-duration="100">
      <a v-if="!showIntro" href="#main-content" class="skip-link">Skip to main content</a>

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
        :theme="resolvedTheme"
        :is-sidebar-open="isSidebarOpen"
        :tree="tree"
        :is-loading="isLoading"
        :has-active-library="hasActiveLibrary"
        :current-path="currentPath"
        :search-query="galleryStore.searchQuery"
        :search-scope="galleryStore.searchScope"
        :search-loading="galleryStore.searchLoading"
        :bars-visible="barsVisible"
        :can-back="canBack"
        :can-forward="canForward"
        :show-back-to-gallery="showBackToGallery"
        @update:search-query="handleSearchQueryUpdate"
        @scope-change="galleryStore.setSearchScope($event)"
        @open-advanced-search="openAdvancedSearch"
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
        :has-active-library="hasActiveLibrary"
        :current-path="currentPath"
        :search-query="galleryStore.searchQuery"
        :search-scope="galleryStore.searchScope"
        :search-loading="galleryStore.searchLoading"
        @update:search-query="handleSearchQueryUpdate"
        @scope-change="galleryStore.setSearchScope($event)"
        @open-advanced-search="openAdvancedSearch"
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
        :has-active-library="hasActiveLibrary"
        :current-path="currentPath"
        :search-query="galleryStore.searchQuery"
        :search-scope="galleryStore.searchScope"
        :search-loading="galleryStore.searchLoading"
        @update:search-query="handleSearchQueryUpdate"
        @scope-change="galleryStore.setSearchScope($event)"
        @open-advanced-search="openAdvancedSearch"
        @update:sidebar-open="isSidebarOpen = $event"
        @toggle-sidebar="toggleSidebar"
        @toggle-theme="toggleTheme"
        @open-settings="isSettingsOpen = true"
      />

      <Lightbox />
      <RelatedAssetsPanel />
      <AdvancedSearchDrawer
        v-if="isAdvancedSearchOpen"
        :is-open="isAdvancedSearchOpen"
        :initial-filters="advancedSearchInitialFilters"
        @close="isAdvancedSearchOpen = false"
        @apply="handleAdvancedSearchApply"
        @apply-request="handleCanonicalSearchApply"
      />
      <GalleryToaster v-if="!isMobile" />
      <SettingsModal
        v-if="isSettingsOpen"
        :is-open="isSettingsOpen"
        @close="isSettingsOpen = false"
        @preview="handlePreviewIntro"
      />
      <component
        :is="VueQueryDevtools"
        v-if="showDevtools && VueQueryDevtools"
        button-position="bottom-right"
        position="bottom"
      />
    </TooltipProvider>
  </MotionConfig>
</template>

<style scoped>
/* Layout styles moved to layout-specific components (DesktopLayout, TabletLayout, MobileLayout) */
</style>
