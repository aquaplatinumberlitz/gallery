<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RecycleScroller } from "vue-virtual-scroller";
import { useGalleryStore } from "../stores/gallery";
import { useLightboxStore } from "../stores/lightbox";
import type { SortField } from "../types";
import AlbumScroller from "./AlbumScroller.vue";
import GlowContainer from "./GlowContainer.vue";
import PhotoCard from "./PhotoCard.vue";
import SkeletonLoader from "./SkeletonLoader.vue";
import Breadcrumb from "./Breadcrumb.vue";
import EmptyState from "./EmptyState.vue";
import { compareNatural } from "../composables/useNaturalSort";
import { useColumnResize } from "../composables/useColumnResize";
import { 
  ArrowLeft, ArrowRight, ArrowUpRight, ArrowUpDown, ChevronDown, 
  ArrowUp, ArrowDown, LayoutGrid, Loader, TriangleAlert, X, 
  Type, Clock, Images 
} from "lucide-vue-next";

const _icons: Record<string, any> = { ArrowUp, ArrowDown, Type, Clock }

const galleryStore = useGalleryStore();
const lightboxStore = useLightboxStore();

const searchQuery = computed(() => galleryStore.searchQuery);
const sortField = computed(() => galleryStore.sortField);
const sortOrder = computed(() => galleryStore.sortOrder);

// Sort dropdown state
const showSortMenu = ref(false);
const sortMenuRef = ref<HTMLElement | null>(null);

const sortOptions: { field: SortField; label: string; icon: string }[] = [
  { field: "name", label: "Name", icon: "Type" },
  { field: "date", label: "Date modified", icon: "Clock" },
];

const currentSortLabel = computed(() => {
  const option = sortOptions.find(o => o.field === sortField.value);
  return option?.label || "Name";
});

const toggleSortMenu = () => {
  showSortMenu.value = !showSortMenu.value;
};

const selectSort = (field: SortField) => {
  if (sortField.value === field) {
    galleryStore.toggleSortOrder();
  } else {
    galleryStore.setSortField(field);
    galleryStore.setSortOrder(field === "date" ? "desc" : "asc");
  }
  showSortMenu.value = false;
};

const closeSortMenu = (e: MouseEvent) => {
  const target = e.target as HTMLElement;
  if (!target.closest(".sort-dropdown")) {
    showSortMenu.value = false;
  }
};

// Handle keyboard navigation in sort menu
const handleSortMenuKeydown = (e: KeyboardEvent) => {
  if (!showSortMenu.value) return;
  
  if (e.key === 'Escape') {
    showSortMenu.value = false;
  } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    const buttons = sortMenuRef.value?.querySelectorAll('button');
    if (buttons) {
      const currentIndex = Array.from(buttons).findIndex(b => b === document.activeElement);
      const nextIndex = e.key === 'ArrowDown' 
        ? (currentIndex + 1) % buttons.length 
        : (currentIndex - 1 + buttons.length) % buttons.length;
      (buttons[nextIndex] as HTMLElement).focus();
    }
  }
};

onMounted(() => {
  document.addEventListener("click", closeSortMenu);
});

onBeforeUnmount(() => {
  document.removeEventListener("click", closeSortMenu);
});

const sortItems = <T extends { name: string; mtime?: number }>(items: T[]): T[] => {
  const sorted = [...items];
  const field = sortField.value;
  const order = sortOrder.value;
  
  sorted.sort((a, b) => {
    let cmp = 0;
    if (field === "name") {
      cmp = compareNatural(a.name, b.name);
    } else if (field === "date") {
      cmp = (a.mtime || 0) - (b.mtime || 0);
    }
    return order === "asc" ? cmp : -cmp;
  });
  
  return sorted;
};

const folders = computed(() =>
  sortItems(
    galleryStore.galleryFolders.filter((item) =>
      !searchQuery.value ||
      item.name.toLowerCase().includes(searchQuery.value.toLowerCase())
    )
  )
);

const images = computed(() =>
  sortItems(
    galleryStore.galleryImages.filter((item) =>
      !searchQuery.value ||
      item.name.toLowerCase().includes(searchQuery.value.toLowerCase())
    )
  )
);

const isLoading = computed(() => galleryStore.galleryLoading);
const currentPath = computed(() => galleryStore.currentPath);
const canBack = computed(() => galleryStore.historyIndex > 0);
const canForward = computed(
  () => galleryStore.historyIndex < galleryStore.history.length - 1
);
const hasMoreImages = computed(() => galleryStore.nextImageCursor !== null);
const hasAnyItems = computed(() => galleryStore.galleryFolders.length + galleryStore.galleryImages.length > 0);
const hasNoPath = computed(() => !galleryStore.currentPath && !galleryStore.rootPath);
const noSearchResults = computed(
  () =>
    !!searchQuery.value &&
    folders.value.length === 0 &&
    images.value.length === 0 &&
    hasAnyItems.value
);
const errorMessage = computed(() => galleryStore.errorMessage);

const handleOpenFolder = (path: string) => {
  galleryStore.selectFolder(path);
};

const handleOpenImage = (path: string, name: string) => {
  // Pass the full list of images to the lightbox for navigation
  lightboxStore.open({ path, name }, images.value);
};

const goBack = () => galleryStore.goBack();
const goForward = () => galleryStore.goForward();
const openFolder = () => galleryStore.openInExplorer();
const isLoadingMore = computed(() => galleryStore.loadingMoreImages);

// --- Virtual scroller state ---
const { columnCount, rowHeight, setGridRef, MIN_COLS, MAX_COLS } = useColumnResize();

const imageRows = computed(() => {
  const rows: { id: string; items: typeof images.value }[] = [];
  for (let i = 0; i < images.value.length; i += columnCount.value) {
    rows.push({
      id: `row-${columnCount.value}-${i}`,
      items: images.value.slice(i, i + columnCount.value)
    });
  }
  return rows;
});

const skeletonItems = computed(() => Array.from({ length: 12 }, (_, i) => i));

// Infinite load sentinel
const loadMoreSentinel = ref<HTMLElement | null>(null);
let loadObserver: IntersectionObserver | null = null;

const setupLoadObserver = () => {
  if (loadObserver) {
    loadObserver.disconnect();
    loadObserver = null;
  }
  if (!loadMoreSentinel.value) return;
  loadObserver = new IntersectionObserver(
    (entries) => {
      if (!hasMoreImages.value || isLoadingMore.value) return;
      if (entries.some((e) => e.isIntersecting)) {
        galleryStore.loadMoreImages();
      }
    },
    {
      root: null,
      rootMargin: "400px",
      threshold: 0,
    }
  );
  loadObserver.observe(loadMoreSentinel.value);
};

onMounted(() => {
  setupLoadObserver();
});

watch(loadMoreSentinel, () => setupLoadObserver());

onBeforeUnmount(() => {
  if (loadObserver) {
    loadObserver.disconnect();
    loadObserver = null;
  }
});

// ── Album Horizontal Scroll (handled by AlbumScroller component) ──
</script>

<template>
  <div class="gallery-grid">
    <div class="grid-header">
      <div class="nav-group">
        <button 
          class="nav-btn ghost" 
          :disabled="!canBack" 
          @click="goBack" 
          title="Back"
        >
          <ArrowLeft :size="18" />
        </button>
        <button 
          class="nav-btn ghost" 
          :disabled="!canForward" 
          @click="goForward" 
          title="Forward"
        >
          <ArrowRight :size="18" />
        </button>
      </div>
      <Breadcrumb class="breadcrumb-wrap" :path="currentPath" @navigate="handleOpenFolder" />

      <button 
        class="nav-btn open-folder" 
        @click="openFolder" 
        title="Open current folder in file explorer"
      >
        <ArrowUpRight :size="18" />
      </button>

      <!-- Sort Dropdown (Google Photos style) -->
      <div class="sort-dropdown" :class="{ open: showSortMenu }">
        <button 
          class="sort-trigger" 
          @click.stop="toggleSortMenu" 
          title="Sort by"
        >
          <ArrowUpDown :size="16" />
          <span class="sort-label">{{ currentSortLabel }}</span>
          <ChevronDown :size="12" class="sort-chevron" />
        </button>
        <Transition name="dropdown">
          <div 
            v-if="showSortMenu" 
            ref="sortMenuRef"
            class="sort-menu"
            @keydown="handleSortMenuKeydown"
          >
            <button
              v-for="option in sortOptions"
              :key="option.field"
              class="sort-option"
              :class="{ active: sortField === option.field }"
              @click="selectSort(option.field)"
            >
              <component :is="_icons[option.icon]" :size="14" />
              <span>{{ option.label }}</span>
              <component 
                v-if="sortField === option.field" 
                :is="sortOrder === 'asc' ? ArrowUp : ArrowDown" 
                class="sort-direction"
                :size="12"
              />
            </button>
          </div>
        </Transition>
      </div>

      <div class="grid-slider" title="Columns per Row">
        <LayoutGrid :size="16" class="slider-icon" />
        <span class="slider-count-badge">{{ columnCount }}</span>
        <div class="slider-track-wrapper">
          <input
            id="grid-size"
            v-model.number="columnCount"
            type="range"
            :min="MIN_COLS"
            :max="MAX_COLS"
          />
          <div class="slider-progress" :style="{ width: ((columnCount - MIN_COLS) / (MAX_COLS - MIN_COLS)) * 100 + '%' }"></div>
          <div class="slider-tooltip" :style="{ left: ((columnCount - MIN_COLS) / (MAX_COLS - MIN_COLS)) * 100 + '%' }">{{ columnCount }}</div>
        </div>
      </div>

      <div v-if="isLoading" class="loading-badge">
        <Loader :size="16" class="lucide-spin" /> 
        <span>Loading</span>
      </div>
    </div>

    <div v-if="errorMessage" class="error-banner">
      <div class="error-text">
        <TriangleAlert :size="16" />
        <span>{{ errorMessage }}</span>
      </div>
      <button 
        class="error-close" 
        type="button" 
        @click="galleryStore.clearError()"
      >
        <X :size="14" />
      </button>
    </div>

    <div v-if="isLoading" class="skeleton-container">
      <div class="skeleton-grid" :style="{ gridTemplateColumns: `repeat(${columnCount}, 1fr)` }">
        <SkeletonLoader
          v-for="i in skeletonItems"
          :key="i"
          type="photo"
        />
      </div>
    </div>

    <!-- Has content: images or folders -->
    <template v-else-if="images.length > 0 || folders.length > 0">
      <!-- Album scroller: outside scroller-container để glow khong bi clip boi content-body overflow:hidden -->
      <GlowContainer v-if="folders.length" :bleed="50">
        <AlbumScroller
          :folders="folders"
          @open-folder="handleOpenFolder"
        />
      </GlowContainer>
      <div class="scroller-container" :ref="setGridRef">

      <RecycleScroller
        v-if="imageRows.length > 0 && rowHeight > 0"
        :key="`${columnCount}-${imageRows.length}`"
        class="scroller fade-slide"
        :items="imageRows"
        :item-size="rowHeight"
        key-field="id"
        :buffer="200"
      >
        <template #before>
          <div class="scroller-header">
            <div v-if="images.length" class="section-title photos-title">
              <h3>Photos</h3>
              <span class="photo-count-badge">
                <Images :size="13" />
                {{ images.length }}
              </span>
            </div>
          </div>
        </template>

        <template #default="{ item: row }">
          <div 
            class="virtual-row" 
            :style="{ gridTemplateColumns: `repeat(${columnCount}, 1fr)` }"
          >
            <PhotoCard
              v-for="img in row.items"
              :key="img.path"
              :src="img.path"
              :name="img.name"
              @click="handleOpenImage(img.path, img.name)"
              @keydown.enter="handleOpenImage(img.path, img.name)"
              @keydown.space.prevent="handleOpenImage(img.path, img.name)"
            />
          </div>
        </template>

        <template #after>
          <div class="scroller-footer">
            <div ref="loadMoreSentinel" class="load-more-sentinel"></div>
            <div v-if="isLoadingMore" class="loading-more">
              <Loader :size="16" class="lucide-spin" />
              <span>Loading more photos...</span>
            </div>

            <!-- No Search Results (only state possible inside RecycleScroller) -->
            <EmptyState
              v-if="noSearchResults"
              type="no-results"
              :title="`No results for '${searchQuery}'`"
              description="Try a different search term or clear the search"
              action-label="Clear search"
              action-icon="xmark"
              compact
              @action="galleryStore.clearSearch()"
            />
          </div>
        </template>
      </RecycleScroller>

      <!-- Fallback: Only folders, no images (when RecycleScroller is not rendered) -->
      <!-- AlbumScroller is rendered above (outside scroller-container), so no duplicate here -->
      <div v-else-if="folders.length > 0" class="folders-only-container">
        <!-- Has only folders, no images -->
        <EmptyState
          v-if="!images.length && !isLoading"
          type="no-images"
          title="No images in this folder"
          description="This folder only contains subfolders. Browse the albums above."
          compact
        />
      </div>
    </div>
    </template>

    <!-- Empty States (when scroller-container is not rendered) -->
    <div v-else class="empty-state-container">
      <!-- Error State -->
      <EmptyState
        v-if="errorMessage && !hasAnyItems"
        type="error"
        title="Unable to load folder"
        :description="errorMessage"
        action-label="Clear"
        action-icon="xmark"
        @action="galleryStore.clearError()"
      />

      <!-- No Search Results -->
      <EmptyState
        v-else-if="noSearchResults"
        type="no-results"
        :title="`No results for '${searchQuery}'`"
        description="Try a different search term or clear the search"
        action-label="Clear search"
        action-icon="xmark"
        @action="galleryStore.clearSearch()"
      />
      
      <!-- No Path Selected -->
      <EmptyState
        v-else-if="hasNoPath"
        type="no-path"
        title="Welcome to Gallery"
        description="Enter a folder path in the sidebar to start browsing your images"
      />
      
      <!-- Empty Folder -->
      <EmptyState
        v-else-if="!folders.length && !images.length"
        type="empty-folder"
        title="This folder is empty"
        description="No images or subfolders found in this location"
        action-label="Go Back"
        action-icon="arrow-left"
        @action="goBack"
      />
    </div>
  </div>
</template>

<style scoped>
.gallery-grid {
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: 100%;
  min-height: 0; /* override flex default min-height:auto — content-body overflow:visible means parent is NOT a scroll container, so flex children's min-height:auto resolves to content size, breaking the height constraint chain */
}

.grid-header {
  display: grid;
  grid-template-columns: auto 1fr auto auto auto auto;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.error-banner {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--primary-color) 40%, transparent);
  color: var(--title-color);
  padding: 10px 12px;
  border-radius: 10px;
}

.error-text {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.error-close {
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;

  &:hover {
    background: rgba(0, 0, 0, 0.05);
  }
}

.scroller-container {
  flex: 1;
  min-height: 0; /* Important for flex child scrolling */
}

.scroller {
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 14px;
  padding-left: 10px;
  scrollbar-width: thin; /* Slim size for Firefox */
  outline: none;
}

.scroller:focus,
.scroller:focus-visible {
  outline: none;
  box-shadow: none;
}

/* Allow card hover to extend beyond each row height in virtual scroller */
:deep(.vue-recycle-scroller__item-wrapper) {
  overflow: visible;
}

/* Ensure before/after slot content is not clipped by glow/box-shadow */
:deep(.vue-recycle-scroller__slot) {
  overflow: visible;
}

.fade-slide {
  animation: fadeSlideIn 260ms ease;
}

@keyframes fadeSlideIn {
  0% {
    opacity: 0;
    transform: translateY(8px);
  }
  100% {
    opacity: 1;
    transform: translateY(0);
  }
}

.scroller::-webkit-scrollbar {
  width: 6px;
}

.scroller::-webkit-scrollbar-track {
  background: transparent;
}

.scroller::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 6px;
}

.scroller::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.25);
}

.scroller-header {
  /* Glow bleed is now handled by overflow chain fix (Item 1) */
}

.folders-only-container {
  padding-left: 10px;
  padding-right: 14px;
  overflow-y: auto;
  overflow-x: hidden;
  height: 100%;
}

.empty-state-container {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

.albums-section {
  margin-bottom: 8px;
}

.photos-title {
  margin-bottom: 12px;
}

.photo-count-badge {
  display: inline-flex !important;
  align-items: center;
  gap: 4px;
  padding: 3px 10px 3px 8px !important;
}

.scroller-footer {
  padding-top: 20px;
  padding-bottom: 40px;
}

.load-more-sentinel {
  width: 100%;
  height: 1px;
}

.loading-more {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.04);
  color: var(--text-color);
  border-radius: 10px;
}

/* ...existing code... */

.nav-group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.nav-btn {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: transparent;
  color: var(--text-color);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 120ms ease, box-shadow 150ms ease, border-color 120ms ease, background-color 120ms ease;
}

.nav-btn.ghost {
  background: transparent;
}

.nav-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.nav-btn:not(:disabled):hover {
  border-color: var(--primary-color);
  background: rgba(0, 0, 0, 0.04);
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
}

/* Open Folder Button - Tinted Pill Style */
.nav-btn.open-folder {
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--primary-color) 20%, transparent);
  color: var(--primary-color);
  box-shadow: none;
}

.nav-btn.open-folder:hover {
  background: color-mix(in srgb, var(--primary-color) 16%, transparent);
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary-color) 12%, transparent);
  transform: translateY(-1px);
}

.nav-btn.open-folder:active {
  transform: translateY(0) scale(0.98);
  box-shadow: none;
}

.breadcrumb-wrap {
  min-width: 0;
}

/* Sort Dropdown - Google Photos Style */
.sort-dropdown {
  position: relative;
}

.sort-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--surface-color);
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));
  border-radius: 10px;
  color: var(--text-color);
  font-size: 13px;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all 0.2s ease;
}

.sort-trigger:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary-color) 25%, transparent);
}

.sort-dropdown.open .sort-trigger {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary-color) 25%, transparent);
}

.sort-label {
  font-weight: 500;
}

.sort-chevron {
  opacity: 0.6;
  transition: transform 0.2s ease;
}

.sort-dropdown.open .sort-chevron {
  transform: rotate(180deg);
}

.sort-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 180px;
  background: var(--surface-color);
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
  padding: 6px;
  z-index: 100;
  overflow: hidden;
}

.sort-option {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  background: transparent;
  border: none;
  border-radius: 8px;
  color: var(--text-color);
  font-size: 13px;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
}

.sort-option:hover {
  background: rgba(0, 0, 0, 0.05);
}

.sort-option.active {
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  color: var(--primary-color);
  font-weight: 500;
}

.sort-direction {
  margin-left: auto;
}

/* Dropdown animation */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.2s ease;
  transform-origin: top right;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: scale(0.95) translateY(-4px);
}

.grid-slider {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  background: var(--surface-color);
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));
  padding: 8px 14px;
  border-radius: 12px;
  transition: all 0.2s ease;
}

.grid-slider:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary-color) 25%, transparent);
}

/* Focus style when slider input is focused */
.grid-slider:has(input:focus-visible) {
  border-color: var(--border-color, rgba(0, 0, 0, 0.1));
  box-shadow: none;
}

/* Fallback for browsers that don't support :has() */
.grid-slider:focus-within {
  border-color: var(--border-color, rgba(0, 0, 0, 0.1));
  box-shadow: none;
}

.slider-icon {
  color: var(--primary-color);
}

.slider-count-badge {
  min-width: 28px;
  padding: 2px 10px;
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 600;
  font-family: var(--font-code);
  border-radius: 999px;
  text-align: center;
  box-shadow: none;
}

.slider-track-wrapper {
  position: relative;
  width: 100px;
  height: 6px;
  background: rgba(0, 0, 0, 0.1);
  border-radius: 3px;
  overflow: hidden;
}

.slider-progress {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: linear-gradient(90deg, var(--primary-color), #e8c07a);
  border-radius: 3px;
  pointer-events: none;
  transition: width 0.15s ease;
}

.grid-slider input[type="range"] {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  margin: 0;
  opacity: 0;
  cursor: pointer;
  z-index: 2;
}

/* Custom thumb for webkit browsers */
.grid-slider input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 28px;
  height: 28px;
  background: var(--primary-color);
  border: 3px solid #fff;
  border-radius: 50%;
  cursor: pointer;
  box-shadow: 0 2px 6px color-mix(in srgb, var(--primary-color) 40%, transparent);
}

.grid-slider input[type="range"]::-moz-range-thumb {
  width: 28px;
  height: 28px;
  background: var(--primary-color);
  border: 3px solid #fff;
  border-radius: 50%;
  cursor: pointer;
  box-shadow: 0 2px 6px color-mix(in srgb, var(--primary-color) 40%, transparent);
}

.slider-tooltip {
  display: none;
  position: absolute;
  top: -32px;
  left: 0;
  transform: translateX(-50%);
  padding: 4px 8px;
  background: linear-gradient(135deg, var(--primary-color), #e8c07a);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  font-family: var(--font-code);
  border-radius: 6px;
  text-align: center;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--primary-color) 30%, transparent);
  white-space: nowrap;
  pointer-events: none;
  transition: left 0.15s ease;
  z-index: 3;
}

.slider-tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: var(--primary-color);
}

.loading-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.05);
  font-size: 13px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;

  h3 {
    margin: 0;
    font-family: "Cinzel", serif;
    font-size: 16px;
    color: var(--primary-color);
    position: relative;
    display: inline-block;

    &::after {
      content: '';
      position: absolute;
      bottom: -4px;
      left: 0;
      width: 100%;
      height: 1.5px;
      background: linear-gradient(90deg, var(--primary-color, #d6a15d) 0%, transparent 100%);
      border-radius: 1px;
    }
  }

  span {
    padding: 2px 8px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--primary-color) 12%, transparent);
    font-size: 12px;
    font-family: var(--font-code);
    color: var(--primary-color);
  }
}

/* ── Album scroll styles are in AlbumScroller.vue ── */


.skeleton-container {
  flex: 1;
  min-height: 0;
}

.skeleton-grid {
  display: grid;
  gap: 20px;
}

.virtual-row {
  display: grid;
  gap: 20px;
  padding: 0 8px; /* Space for shadow on first and last column images */
}

@media (max-width: 1024px) {
  .grid-header {
    gap: 8px;
  }

  .breadcrumb-wrap {
    min-width: 0;
    max-width: min(300px, 50vw);
  }
}

@media (max-width: 640px) {
  .gallery-grid {
    gap: 6px;
  }

  .grid-header {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: nowrap;
    padding-top: 4px;
  }

  .loading-badge {
    display: none;
  }

  /* Hide open-folder button from mobile nav — icon moved to folder bar */
  .nav-btn.open-folder {
    display: none;
  }

  .nav-group {
    flex-shrink: 0;
  }

  .nav-btn {
    width: 32px;
    height: 32px;
  }

  .breadcrumb-wrap {
    display: none;
  }

  /* Sort: hidden on mobile */
  .sort-dropdown {
    display: none;
  }

  /* Grid slider: hidden on mobile */
  .grid-slider {
    display: none;
  }

  .albums-section {
    margin-bottom: 8px;
  }

  .section-title {
    margin-bottom: 6px;
  }

  .section-title h3 {
    font-size: 14px;
  }

  /* Reduce photo row gap and spacers on mobile */
  .virtual-row {
    gap: 6px;
    padding: 0 4px;
  }

  .scroller-header {
    padding-top: 40px;
    padding-bottom: 40px;
  }

  .scroller-footer {
    padding-top: 8px;
    padding-bottom: 20px;
  }
}

@media (max-width: 480px) {
  .grid-header {
    gap: 4px;
  }

  .nav-btn {
    width: 30px;
    height: 30px;
  }
}

/* Screen reader only - visually hidden but accessible */
/* Focus styles for keyboard navigation */
.nav-btn:focus-visible,
.sort-trigger:focus-visible,
.sort-option:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

/* Reduced motion support */
@media (prefers-reduced-motion: reduce) {
  .fade-slide {
    animation: none;
  }
  
  .dropdown-enter-active,
  .dropdown-leave-active {
    transition: none;
  }
}

</style>
