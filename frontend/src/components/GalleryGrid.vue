<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, ref, watch, type ComponentPublicInstance } from "vue";
import { RecycleScroller } from "vue-virtual-scroller";
import { useGalleryStore } from "../stores/gallery";
import { useLightboxStore } from "../stores/lightbox";
import type { FileNode, MetadataSearchResult, SortField } from "../types";
import AlbumScroller from "./AlbumScroller.vue";
import GallerySectionHeader from "./GallerySectionHeader.vue";
import GlowContainer from "./GlowContainer.vue";
import PhotoCard from "./PhotoCard.vue";
import SkeletonLoader from "./SkeletonLoader.vue";
import Breadcrumb from "./Breadcrumb.vue";
import EmptyState from "./EmptyState.vue";
import TabletGalleryToolbar from "./TabletGalleryToolbar.vue";
import { compareNatural } from "../composables/useNaturalSort";
import { useColumnResize, PHOTO_GRID_LEVELS, GRID_COLUMN_MAP } from "../composables/useColumnResize";
import { useDevice } from "../composables/useDevice";
import { usePullToRefresh } from "../composables/usePullToRefresh";
import { galleryScrollContainerRefKey } from "../injectionKeys";
import { fuzzySearchFileNodes } from "../utils/fuzzySearch";
import { 
  ArrowLeft, ArrowRight, ArrowUpRight, ArrowUpDown, ChevronDown, 
  ArrowUp, ArrowDown, LayoutGrid, Loader, TriangleAlert, X, 
  ArrowDownToLine, Check,
  Type, Clock, Images 
} from "lucide-vue-next";

const _icons: Record<string, any> = { Type, Clock }

const galleryStore = useGalleryStore();
const lightboxStore = useLightboxStore();

const {
  pullDistance,
  isRefreshing,
  showPullIndicator,
  pullProgress,
  pullTransform,
  pullOpacity,
  onTouchStart,
  onTouchMove,
  onTouchEnd,
} = usePullToRefresh({
  onRefresh: () => galleryStore.scanFolder(),
});

interface Props {
  isMobile: boolean
  barsVisible?: boolean
  showToolbarBreadcrumb?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  barsVisible: true,
  showToolbarBreadcrumb: true,
})
const injectedScrollContainerRef = inject(galleryScrollContainerRefKey, null)

const setScrollContainerRef = (target: Element | ComponentPublicInstance | null) => {
  if (!injectedScrollContainerRef) return;

  if (!target) {
    injectedScrollContainerRef.value = null;
    return;
  }

  const el = target instanceof HTMLElement
    ? target
    : "$el" in target && target.$el instanceof HTMLElement
      ? target.$el
      : null;

  injectedScrollContainerRef.value = el;
};

const searchQuery = computed(() => galleryStore.searchQuery);
const trimmedSearchQuery = computed(() => searchQuery.value.trim());
const hasSearchQuery = computed(() => trimmedSearchQuery.value.length > 0);
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
  showDensityMenu.value = false;
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
  document.addEventListener("click", closeDensityMenu);
});

onBeforeUnmount(() => {
  document.removeEventListener("click", closeSortMenu);
  document.removeEventListener("click", closeDensityMenu);
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
    fuzzySearchFileNodes(galleryStore.galleryFolders, searchQuery.value)
  )
);

// Fuse search is client-side and only covers images currently loaded into galleryImages.
const filenameImages = computed(() =>
  sortItems(
    fuzzySearchFileNodes(galleryStore.galleryImages, searchQuery.value)
  )
);

const metadataResultToFileNode = (result: MetadataSearchResult): FileNode => ({
  name: result.name,
  path: result.path,
  type: "image",
  has_children: false,
  cover_images: [],
  mtime: result.mtime,
  width: result.width ?? undefined,
  height: result.height ?? undefined,
});

const metadataImages = computed(() => {
  const seenPaths = new Set(filenameImages.value.map((image) => image.path));
  return galleryStore.metadataSearchResults.reduce<FileNode[]>((matches, result) => {
    if (seenPaths.has(result.path)) return matches;
    seenPaths.add(result.path);
    matches.push(metadataResultToFileNode(result));
    return matches;
  }, []);
});

const images = computed(() =>
  hasSearchQuery.value
    ? [...filenameImages.value, ...metadataImages.value]
    : filenameImages.value
);

const isLoading = computed(() => galleryStore.galleryLoading);
const isMetadataLoading = computed(() => galleryStore.metadataSearchLoading);
const currentPath = computed(() => galleryStore.currentPath);
const canBack = computed(() => galleryStore.historyIndex > 0);
const canForward = computed(
  () => galleryStore.historyIndex < galleryStore.history.length - 1
);
const hasMoreImages = computed(() => !hasSearchQuery.value && galleryStore.nextImageCursor !== null);
const hasAnyItems = computed(() => galleryStore.galleryFolders.length + galleryStore.galleryImages.length > 0);
const hasNoPath = computed(() => !galleryStore.currentPath && !galleryStore.rootPath);
const hasNotLoaded = computed(() => !galleryStore.hasEverLoaded && (!!galleryStore.currentPath || !!galleryStore.rootPath));
const noSearchResults = computed(
  () =>
    hasSearchQuery.value &&
    !isMetadataLoading.value &&
    folders.value.length === 0 &&
    filenameImages.value.length === 0 &&
    metadataImages.value.length === 0 &&
    hasAnyItems.value
);
const errorMessage = computed(() => galleryStore.errorMessage);

let metadataSearchTimer: number | undefined;

watch(trimmedSearchQuery, (query) => {
  if (metadataSearchTimer) {
    window.clearTimeout(metadataSearchTimer);
    metadataSearchTimer = undefined;
  }
  if (query.length < 2) {
    galleryStore.metadataSearchResults = [];
    galleryStore.metadataSearchTotal = 0;
    galleryStore.metadataSearchLoading = false;
    return;
  }
  metadataSearchTimer = window.setTimeout(() => {
    galleryStore.searchMetadata(query);
  }, 300);
}, { immediate: true });

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
const { isTablet } = useDevice()
const deviceCategory = computed(() => props.isMobile ? 'mobile' : isTablet.value ? 'tablet' : 'desktop')
const { columnCount, sliderLevel, rowHeight, setGridRef } = useColumnResize(deviceCategory);

// Density dropdown state
const showDensityMenu = ref(false);
const densityMenuRef = ref<HTMLElement | null>(null);

const densityOptions = computed(() => {
  if (deviceCategory.value !== 'tablet') return PHOTO_GRID_LEVELS
  const map = GRID_COLUMN_MAP.tablet
  const seen = new Set<number>()
  const result: Array<{ level: number; label: string; columns: number }> = []
  for (let i = 0; i < PHOTO_GRID_LEVELS.length; i++) {
    const cols = map[i]
    if (!seen.has(cols)) {
      seen.add(cols)
      result.push({ ...PHOTO_GRID_LEVELS[i], columns: cols })
    }
  }
  return result
})

const toggleDensityMenu = () => {
  showSortMenu.value = false;
  showDensityMenu.value = !showDensityMenu.value;
};

const selectDensity = (level: number) => {
  sliderLevel.value = level;
  showDensityMenu.value = false;
};

const closeDensityMenu = (e: MouseEvent) => {
  const target = e.target as HTMLElement;
  if (!target.closest('.density-dropdown')) {
    showDensityMenu.value = false;
  }
};

const handleDensityMenuKeydown = (e: KeyboardEvent) => {
  if (!showDensityMenu.value) return;
  
  if (e.key === 'Escape') {
    showDensityMenu.value = false;
  } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    const buttons = densityMenuRef.value?.querySelectorAll('button');
    if (buttons) {
      const currentIndex = Array.from(buttons).findIndex(b => b === document.activeElement);
      const nextIndex = e.key === 'ArrowDown' 
        ? (currentIndex + 1) % buttons.length 
        : (currentIndex - 1 + buttons.length) % buttons.length;
      (buttons[nextIndex] as HTMLElement).focus();
    }
  }
};

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

const filenameImageRows = computed(() => {
  const rows: { id: string; items: typeof filenameImages.value }[] = [];
  for (let i = 0; i < filenameImages.value.length; i += columnCount.value) {
    rows.push({
      id: `filename-row-${columnCount.value}-${i}`,
      items: filenameImages.value.slice(i, i + columnCount.value)
    });
  }
  return rows;
});

const metadataImageRows = computed(() => {
  const rows: { id: string; items: typeof metadataImages.value }[] = [];
  for (let i = 0; i < metadataImages.value.length; i += columnCount.value) {
    rows.push({
      id: `metadata-row-${columnCount.value}-${i}`,
      items: metadataImages.value.slice(i, i + columnCount.value)
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
  if (metadataSearchTimer) {
    window.clearTimeout(metadataSearchTimer);
  }
  if (loadObserver) {
    loadObserver.disconnect();
    loadObserver = null;
  }
});

// ── Album Horizontal Scroll (handled by AlbumScroller component) ──
</script>

<template>
  <div 
    class="gallery-grid"
    @touchstart="onTouchStart"
    @touchmove="onTouchMove"
    @touchend="onTouchEnd"
  >
    <!-- Pull-to-refresh indicator -->
    <div
      v-if="showPullIndicator"
      class="pull-indicator"
      :data-pull-distance="Math.round(pullDistance)"
      :style="{ transform: pullTransform, opacity: pullOpacity }"
    >
      <div v-if="isRefreshing" class="pull-spinner">
        <Loader class="gallery-icon-toolbar lucide-spin" />
      </div>
      <div v-else class="pull-arrow" :style="{ transform: `rotate(${pullProgress * 180}deg)` }">
        <ArrowDownToLine class="gallery-icon-toolbar" />
      </div>
      <span class="pull-label">{{ isRefreshing ? 'Refreshing...' : 'Pull to refresh' }}</span>
    </div>

    <!-- ============================================================
         Desktop toolbar
         ============================================================ -->
    <div v-if="deviceCategory === 'desktop'" class="grid-header">
      <div class="nav-group">
        <button 
          class="nav-btn ghost" 
          :disabled="!canBack" 
          @click="goBack" 
          title="Back"
        >
          <ArrowLeft />
        </button>
        <button 
          class="nav-btn ghost" 
          :disabled="!canForward" 
          @click="goForward" 
          title="Forward"
        >
          <ArrowRight />
        </button>
      </div>
      <Breadcrumb v-if="showToolbarBreadcrumb" class="breadcrumb-wrap" :path="currentPath" @navigate="handleOpenFolder" />

      <button 
        class="nav-btn open-folder" 
        @click="openFolder" 
        title="Open current folder in file explorer"
      >
        <ArrowUpRight />
      </button>

      <!-- Sort Dropdown (Google Photos style) -->
      <div class="sort-dropdown" :class="{ open: showSortMenu }">
        <button 
          class="sort-trigger" 
          @click.stop="toggleSortMenu" 
          title="Sort by"
        >
          <ArrowUpDown />
          <span class="sort-label">{{ currentSortLabel }}</span>
          <ChevronDown class="sort-chevron" />
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
              <component :is="_icons[option.icon]" class="gallery-icon-sm" />
              <span>{{ option.label }}</span>
              <component 
                v-if="sortField === option.field" 
                :is="sortOrder === 'asc' ? ArrowUp : ArrowDown" 
                class="sort-direction gallery-icon-xs"
              />
            </button>
          </div>
        </Transition>
      </div>

      <!-- Density Dropdown -->
      <div 
        class="density-dropdown" 
        :class="{ open: showDensityMenu }"
      >
        <button 
          class="density-trigger" 
          @click.stop="toggleDensityMenu" 
          aria-haspopup="true"
          :aria-expanded="showDensityMenu"
          title="Thumbnail size"
        >
          <LayoutGrid />
          <span class="density-label">{{ columnCount }} cols</span>
          <ChevronDown class="density-chevron" />
        </button>
        <Transition name="dropdown">
          <div 
            v-if="showDensityMenu" 
            ref="densityMenuRef"
            class="density-menu"
            @keydown="handleDensityMenuKeydown"
          >
            <button
              v-for="option in densityOptions"
              :key="option.level"
              class="density-option"
              :class="{ active: sliderLevel === option.level }"
              @click="selectDensity(option.level)"
            >
              <LayoutGrid class="gallery-icon-sm" />
              <span>{{ option.label }}</span>
              <span class="density-cols">{{ option.columns }} cols</span>
              <Check 
                v-if="sliderLevel === option.level" 
                class="density-check gallery-icon-xs"
              />
            </button>
          </div>
        </Transition>
      </div>

      <div v-if="isLoading" class="loading-badge">
        <Loader class="gallery-icon-md lucide-spin" /> 
        <span>Loading</span>
      </div>
    </div>

    <!-- ============================================================
         Tablet toolbar (dedicated component)
         ============================================================ -->
    <TabletGalleryToolbar
      v-else-if="deviceCategory === 'tablet'"
      :can-go-back="canBack"
      :can-go-forward="canForward"
      :current-sort="sortField"
      :sort-options="sortOptions"
      :show-sort-menu="showSortMenu"
      :current-sort-label="currentSortLabel"
      :sort-order="sortOrder"
      :slider-level="sliderLevel"
      :column-count="columnCount"
      :density-options="densityOptions"
      :show-density-menu="showDensityMenu"
      @back="goBack"
      @forward="goForward"
      @toggle-sort-menu="toggleSortMenu"
      @select-sort="selectSort"
      @toggle-density-menu="toggleDensityMenu"
      @select-density="selectDensity"
    />

    <div v-if="errorMessage" class="error-banner">
      <div class="error-text">
        <TriangleAlert class="gallery-icon-md" />
        <span>{{ errorMessage }}</span>
      </div>
      <button 
        class="error-close" 
        type="button" 
        @click="galleryStore.clearError()"
      >
        <X class="gallery-icon-sm" />
      </button>
    </div>

    <div v-if="isLoading || (hasSearchQuery && isMetadataLoading && !folders.length && !filenameImages.length && !metadataImages.length)" class="skeleton-container">
      <div class="skeleton-grid" :style="{ gridTemplateColumns: `repeat(${columnCount}, 1fr)` }">
        <SkeletonLoader
          v-for="i in skeletonItems"
          :key="i"
          type="photo"
        />
      </div>
    </div>

    <!-- Search results: albums, current-view filename matches, and backend metadata matches -->
    <div
      v-else-if="hasSearchQuery"
      :ref="setScrollContainerRef"
      class="search-results-container"
    >
      <GlowContainer v-if="folders.length" :disabled="props.isMobile">
        <AlbumScroller
          :folders="folders"
          @open-folder="handleOpenFolder"
        />
      </GlowContainer>

      <section v-if="filenameImages.length" class="search-photo-section">
        <GallerySectionHeader
          title="Photos"
          :count="filenameImages.length"
          :badge-icon="Images"
        />

        <div
          v-for="row in filenameImageRows"
          :key="row.id"
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
      </section>

      <section v-if="metadataImages.length" class="search-photo-section">
        <GallerySectionHeader
          title="Metadata matches"
          :count="metadataImages.length"
          :badge-icon="Images"
        />

        <div
          v-for="row in metadataImageRows"
          :key="row.id"
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
      </section>

      <div v-if="noSearchResults" class="search-empty-wrap">
        <EmptyState
          type="no-results"
          title="No results"
          description="Try a filename, album name, or prompt."
          action-label="Clear search"
          action-icon="xmark"
          @action="galleryStore.clearSearch()"
        />
      </div>
    </div>

    <!-- Has content: images or folders -->
    <template v-else-if="images.length > 0 || folders.length > 0">
      <div class="scroller-container" :ref="setGridRef">

      <RecycleScroller
        v-if="!props.isMobile && imageRows.length > 0 && rowHeight > 0"
        :ref="setScrollContainerRef"
        :key="`${columnCount}-${imageRows.length}`"
        :class="['scroller', { 'fade-slide': !isMobile }]"
        :items="imageRows"
        :item-size="rowHeight"
        key-field="id"
        :buffer="600"
      >
        <template #before>
          <GlowContainer v-if="folders.length" :disabled="props.isMobile">
            <AlbumScroller
              :folders="folders"
              @open-folder="handleOpenFolder"
            />
          </GlowContainer>

        <GallerySectionHeader
          v-if="images.length"
            title="Photos"
            :count="images.length"
            :badge-icon="Images"
          />
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
          <div class="scroller-footer" :class="{ 'bars-hidden': !barsVisible }">
            <div ref="loadMoreSentinel" class="load-more-sentinel"></div>
            <div v-if="isLoadingMore" class="loading-more">
              <Loader class="gallery-icon-md lucide-spin" />
              <span>Loading more photos...</span>
            </div>

            <!-- No Search Results (only state possible inside RecycleScroller) -->
            <EmptyState
              v-if="noSearchResults"
              type="no-results"
              title="No results"
              description="Try a filename, album name, or prompt."
              action-label="Clear search"
              action-icon="xmark"
              compact
              @action="galleryStore.clearSearch()"
            />
          </div>
        </template>
      </RecycleScroller>

      <!-- Mobile: native scroll (no virtual scroller) -->
      <div
        v-else-if="props.isMobile && imageRows.length > 0"
        :ref="setScrollContainerRef"
        class="scroller mobile-scroller"
      >
        <GlowContainer v-if="folders.length" :disabled="true">
          <AlbumScroller
            :folders="folders"
            @open-folder="handleOpenFolder"
          />
        </GlowContainer>

        <GallerySectionHeader
          v-if="images.length"
          title="Photos"
          :count="images.length"
          :badge-icon="Images"
        />

        <div
          v-for="row in imageRows"
          :key="row.id"
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

        <div class="scroller-footer" :class="{ 'bars-hidden': !barsVisible }">
          <div ref="loadMoreSentinel" class="load-more-sentinel"></div>
          <div v-if="isLoadingMore" class="loading-more">
            <Loader class="gallery-icon-md lucide-spin" />
            <span>Loading more photos...</span>
          </div>

          <EmptyState
            v-if="noSearchResults"
            type="no-results"
            title="No results"
            description="Try a filename, album name, or prompt."
            action-label="Clear search"
            action-icon="xmark"
            compact
            @action="galleryStore.clearSearch()"
          />
        </div>
      </div>

      <!-- Fallback: Only folders, no images (when RecycleScroller is not rendered) -->
      <div v-else-if="folders.length > 0" :ref="setScrollContainerRef" class="folders-only-container">
        <GlowContainer :disabled="props.isMobile">
          <AlbumScroller
            :folders="folders"
            @open-folder="handleOpenFolder"
          />
        </GlowContainer>

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

      <!-- No Path Selected -->
      <EmptyState
        v-else-if="hasNoPath"
        type="no-path"
        title="Welcome to Gallery"
        description="Enter a folder path in the sidebar to start browsing your images"
      />
      
      <!-- Not Loaded Yet -->
      <EmptyState
        v-else-if="hasNotLoaded"
        type="not-loaded"
        title="Gallery not loaded"
        description="Click Load in the sidebar or press Enter to browse your images"
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

.search-results-container {
  flex: 1;
  min-height: 0;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 14px;
  padding-left: 10px;
  scrollbar-width: thin;
}

.search-photo-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}

.search-empty-wrap {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.scroller {
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior-y: contain;
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
  height: 100%;
}

.albums-section {
  margin-bottom: 8px;
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
  box-shadow: var(--gallery-shadow-sm, 0 8px 18px rgba(0, 0, 0, 0.08));
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

.sort-trigger:hover,
.density-trigger:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary-color) 25%, transparent);
}

.sort-dropdown.open .sort-trigger,
.density-dropdown.open .density-trigger {
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
  box-shadow: var(--gallery-shadow-lg, 0 10px 40px rgba(0, 0, 0, 0.15));
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

/* Density Dropdown */
.density-dropdown {
  position: relative;
}

.density-trigger {
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

.density-label {
  font-weight: 500;
}

.density-chevron {
  opacity: 0.6;
  transition: transform 0.2s ease;
}

.density-dropdown.open .density-chevron {
  transform: rotate(180deg);
}

.density-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 180px;
  background: var(--surface-color);
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));
  border-radius: 12px;
  box-shadow: var(--gallery-shadow-lg, 0 10px 40px rgba(0, 0, 0, 0.15));
  padding: 6px;
  z-index: 100;
  overflow: hidden;
}

.density-option {
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
  position: relative;
}

.density-option:hover {
  background: rgba(0, 0, 0, 0.05);
}

.density-option.active {
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  color: var(--primary-color);
  font-weight: 500;
}

.density-cols {
  opacity: 0.6;
  font-weight: 400;
}

.density-option.active .density-cols {
  opacity: 0.8;
}

.density-check {
  margin-left: auto;
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

/* ── Album scroll styles are in AlbumScroller.vue ── */

/* ── SVG icon sizing via design tokens ── */
/* Nav button icons (ArrowLeft, ArrowRight, ArrowUpRight) */
.nav-btn svg {
  width: var(--gallery-icon-toolbar);
  height: var(--gallery-icon-toolbar);
}

/* Sort/density trigger main icons (ArrowUpDown, LayoutGrid) */
.sort-trigger > svg:not(.sort-chevron),
.density-trigger > svg:not(.density-chevron) {
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}

/* Chevron icons inside sort/density triggers */
.sort-trigger svg.sort-chevron,
.density-trigger svg.density-chevron {
  width: var(--gallery-icon-xs);
  height: var(--gallery-icon-xs);
}

/* Generic icon size classes */
.gallery-icon-toolbar {
  width: var(--gallery-icon-toolbar);
  height: var(--gallery-icon-toolbar);
}
.gallery-icon-md {
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}
.gallery-icon-sm {
  width: var(--gallery-icon-sm);
  height: var(--gallery-icon-sm);
}
.gallery-icon-xs {
  width: var(--gallery-icon-xs);
  height: var(--gallery-icon-xs);
}

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
  contain: layout style; /* Safer than content-visibility:auto — no Safari flicker bug */
}
/* content-visibility:auto removed - conflicts with RecycleScroller's own DOM recycling
   and causes flicker on mobile Safari */

@media (max-width: 1199px) {
  .grid-header {
    gap: 8px;
  }

  .breadcrumb-wrap {
    min-width: 0;
    max-width: min(300px, 50vw);
  }
}

/* ── Tablet (768px–1199px) spacing ── */
@media (min-width: 768px) and (max-width: 1199px) {
  .gallery-grid {
    gap: 12px;
  }

  .virtual-row {
    gap: 12px;
  }

  .skeleton-grid {
    gap: 12px;
  }

  .scroller {
    padding-left: 6px;
    padding-right: 10px;
  }

  .folders-only-container {
    padding-left: 6px;
    padding-right: 10px;
  }
}

@media (max-width: 767px) {
  .gallery-grid {
    gap: 6px;
  }

  .grid-header {
    display: none;
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
    width: 44px;
    height: 44px;
    min-width: 44px;
    min-height: 44px;
  }

  .breadcrumb-wrap {
    flex: 1;
    min-width: 0;
    overflow: hidden;
  }

  .nav-group {
    display: flex;
  }

  /* Sort: hidden on mobile */
  .sort-dropdown {
    display: none;
  }

  /* Density: hidden on mobile */
  .density-dropdown {
    display: none;
  }

  .albums-section {
    margin-bottom: 8px;
  }

  .scroller-container {
    padding-top: 8px;
  }

  /* Reduce photo row gap and spacers on mobile */
  .virtual-row {
    gap: 4px;
    padding: 0 4px;
  }

  .scroller-footer {
    padding-top: 8px;
    padding-bottom: 120px; /* Extra bottom padding for mobile nav bar */
  }

  .scroller-footer.bars-hidden {
    padding-bottom: 20px;
  }

  .scroller {
    padding-left: 4px;
    padding-right: 4px;
  }

  .folders-only-container {
    padding-left: 4px;
    padding-right: 4px;
  }

  .skeleton-grid {
    gap: 4px;
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
.sort-option:focus-visible,
.density-trigger:focus-visible,
.density-option:focus-visible {
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

/* ── Pull-to-refresh indicator ── */
.pull-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 0 8px;
  color: var(--primary-color);
  font-size: 13px;
  font-weight: 500;
  transition: transform 0.3s cubic-bezier(0.2, 0, 0, 1), opacity 0.2s ease;
  will-change: transform;
  flex-shrink: 0;
}

.pull-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s ease;
  color: var(--primary-color);
}

.pull-spinner {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary-color);
}

.pull-label {
  white-space: nowrap;
}

@media (prefers-reduced-motion: reduce) {
  .pull-indicator {
    transition: none;
  }
  .pull-arrow {
    transition: none;
  }
}

</style>
