<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, ref, watch, type ComponentPublicInstance } from "vue";
import { useVirtualizer } from "@tanstack/vue-virtual";
import { useGalleryStore } from "../stores/gallery";
import { useLightboxStore } from "../stores/lightbox";
import type { FileNode, SortField, UnifiedSearchResult } from "../types";
import AlbumCard from "./AlbumCard.vue";
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
import { useDelayedBoolean } from "../composables/useDelayedBoolean";
import { useInfiniteScanQuery } from "../composables/useInfiniteScanQuery";
import { useUnifiedSearchQuery } from "../composables/useUnifiedSearchQuery";
import { galleryScrollContainerRefKey } from "../injectionKeys";
import { fuzzySearchFileNodes } from "../utils/fuzzySearch";
import { 
  ArrowLeft, ArrowRight, ArrowUpRight, ArrowUpDown, ChevronDown, 
  ArrowUp, ArrowDown, LayoutGrid, Loader, TriangleAlert, X, 
  ArrowDownToLine, Check,
  Type, Clock, Images, Folder, FolderOpen
} from "lucide-vue-next";
import Button from "./ui/Button.vue";
import Badge from "./ui/Badge.vue";

const _icons: Record<string, any> = { Type, Clock }

const galleryStore = useGalleryStore();
const lightboxStore = useLightboxStore();
const activeScanPath = computed(() => galleryStore.currentPath);
const infiniteScanQuery = useInfiniteScanQuery(activeScanPath);

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
  onRefresh: async () => {
    await infiniteScanQuery.refetch();
  },
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
const scrollParentRef = ref<HTMLElement | null>(null)

const resolveTemplateRefElement = (target: Element | ComponentPublicInstance | null) => {
  if (!target) return null;
  return target instanceof HTMLElement
    ? target
    : "$el" in target && target.$el instanceof HTMLElement
      ? target.$el
      : null;
};

const setScrollContainerRef = (target: Element | ComponentPublicInstance | null) => {
  if (!injectedScrollContainerRef) return;

  if (!target) {
    injectedScrollContainerRef.value = null;
    return;
  }

  injectedScrollContainerRef.value = resolveTemplateRefElement(target);
};

const setVirtualScrollContainerRef = (target: Element | ComponentPublicInstance | null) => {
  const el = resolveTemplateRefElement(target);
  scrollParentRef.value = el;
  setScrollContainerRef(target);
};

const searchQuery = computed(() => galleryStore.searchQuery);
const trimmedSearchQuery = computed(() => searchQuery.value.trim());
const hasSearchQuery = computed(() => trimmedSearchQuery.value.length > 0);
const searchScope = computed(() => galleryStore.searchScope);
const searchContextPath = computed(() => infiniteScanQuery.activeFolderPath.value);
const unifiedSearchQuery = useUnifiedSearchQuery(searchQuery, searchScope, searchContextPath);
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

const scanFolders = computed(() => infiniteScanQuery.folders.value);
const scanImages = computed(() => infiniteScanQuery.images.value);

const folders = computed(() =>
  sortItems(
    hasSearchQuery.value ? scanFolders.value : fuzzySearchFileNodes(scanFolders.value, searchQuery.value)
  )
);

// Fuse search is client-side and only covers images currently loaded in the active scan view.
const filenameImages = computed(() =>
  sortItems(
    hasSearchQuery.value ? scanImages.value : fuzzySearchFileNodes(scanImages.value, searchQuery.value)
  )
);

const searchResultToFileNode = (result: UnifiedSearchResult): FileNode => ({
  name: result.name,
  path: result.path,
  type: result.type === "folder" ? "folder" : "image",
  has_children: false,
  cover_images: result.cover_images || [],
  image_count: result.image_count || 0,
  mtime: result.mtime,
  width: result.width ?? undefined,
  height: result.height ?? undefined,
});

const normalizeSearchPath = (path: string): string =>
  path.trim().replace(/\\/g, "/").replace(/\/+/g, "/").replace(/\/$/, "").toLowerCase();

const formatDisplayFilename = (name: string, maxLen = 28): string => {
  if (name.length <= maxLen) return name;

  const minSegmentLength = 3;
  const ellipsis = "…";
  const dotIndex = name.lastIndexOf(".");
  const hasExtension = dotIndex > 0 && dotIndex < name.length - 1;
  const baseName = hasExtension ? name.slice(0, dotIndex) : name;
  const extension = hasExtension ? name.slice(dotIndex) : "";
  const availableBaseLength = maxLen - extension.length - ellipsis.length;

  if (availableBaseLength < minSegmentLength * 2) {
    const fallbackBaseLength = Math.max(1, maxLen - extension.length - ellipsis.length);
    return `${baseName.slice(0, fallbackBaseLength)}${ellipsis}${extension}`;
  }

  const prefixLength = Math.ceil(availableBaseLength / 2);
  const suffixLength = Math.floor(availableBaseLength / 2);
  return `${baseName.slice(0, prefixLength)}${ellipsis}${baseName.slice(-suffixLength)}${extension}`;
};

const splitDisplayName = (name: string): { base: string; ext: string } => {
  const dotIndex = name.lastIndexOf(".");
  const hasExtension = dotIndex > 0 && dotIndex < name.length - 1;
  return {
    base: hasExtension ? name.slice(0, dotIndex) : name,
    ext: hasExtension ? name.slice(dotIndex) : "",
  };
};

const displayFilenameParts = (name: string): { base: string; ext: string } => {
  const maxLen = columnCount.value >= 7 ? 20 : 28;
  return splitDisplayName(formatDisplayFilename(name, maxLen));
};

const normalizeDisplayFolderPath = (path: string): string =>
  path.trim().replace(/\\/g, "/").replace(/\/+/g, "/").replace(/\/$/, "");

const folderPathFromRelativePath = (relativePath: string, filename: string): string => {
  const normalizedRelative = normalizeDisplayFolderPath(relativePath);
  if (!normalizedRelative || normalizedRelative === "." || normalizedRelative === filename) return "";
  const parts = normalizedRelative.split("/").filter(Boolean);
  if (!parts.length) return "";
  if (parts[parts.length - 1] === filename) {
    parts.pop();
  }
  return parts.join("/");
};

const searchResultFolderPath = (result: UnifiedSearchResult): string => {
  const normalizedRelativePath = normalizeDisplayFolderPath(result.relative_path);
  const relativeFolderPath = folderPathFromRelativePath(result.relative_path, result.name);
  if (relativeFolderPath || !normalizedRelativePath || normalizedRelativePath === "." || normalizedRelativePath === result.name) {
    return relativeFolderPath;
  }
  return folderPathFromRelativePath(result.parent_path, result.name);
};

const searchAlbums = computed(() => unifiedSearchQuery.albums.value);
const searchPhotos = computed(() => unifiedSearchQuery.photos.value);
const searchPhotoPathSet = computed(() => new Set(searchPhotos.value.map((result) => normalizeSearchPath(result.path))));
const searchPrompt = computed(() => {
  const seen = new Set<string>();
  return unifiedSearchQuery.prompt.value.filter((result) => {
    const normalizedPath = normalizeSearchPath(result.path);
    if (searchPhotoPathSet.value.has(normalizedPath) || seen.has(normalizedPath)) return false;
    seen.add(normalizedPath);
    return true;
  });
});
const searchAlbumNodesRef = computed(() =>
  searchAlbums.value.map((album) => {
    const node = searchResultToFileNode(album);
    if (!node.cover_images || node.cover_images.length === 0) {
      const match = scanFolders.value.find(
        (folder) => normalizeSearchPath(folder.path) === normalizeSearchPath(album.path)
      );
      if (match && match.cover_images && match.cover_images.length > 0) {
        node.cover_images = match.cover_images;
        if (!node.image_count && match.image_count) {
          node.image_count = match.image_count;
        }
      }
    }
    return node;
  })
);
const searchPhotoNodes = computed(() => searchPhotos.value.map(searchResultToFileNode));
const searchPromptNodes = computed(() => searchPrompt.value.map(searchResultToFileNode));
const allSearchImageNodes = computed(() => {
  const seen = new Set<string>();
  return [...searchPhotoNodes.value, ...searchPromptNodes.value].filter((image) => {
    if (seen.has(image.path)) return false;
    seen.add(image.path);
    return true;
  });
});

const images = computed(() =>
  hasSearchQuery.value ? allSearchImageNodes.value : filenameImages.value
);

const isLoading = computed(() => infiniteScanQuery.isLoading.value);
const isRefetching = computed(
  () => infiniteScanQuery.isFetching.value && !infiniteScanQuery.isLoading.value && !infiniteScanQuery.isFetchingNextPage.value
);
const isSearchLoading = computed(
  () => hasSearchQuery.value && (unifiedSearchQuery.isLoading.value || unifiedSearchQuery.isFetching.value),
);
const currentPath = computed(() => galleryStore.currentPath);
const canBack = computed(() => galleryStore.historyIndex > 0);
const canForward = computed(
  () => galleryStore.historyIndex < galleryStore.history.length - 1
);
const hasMoreImages = computed(() => !hasSearchQuery.value && infiniteScanQuery.hasNextPage.value);
const hasAnyItems = computed(() => scanFolders.value.length + scanImages.value.length > 0);

const pathReady = computed(() => Boolean(infiniteScanQuery.activeFolderPath.value || galleryStore.rootPath));

const hasAlbums = computed(() => folders.value.length > 0);
const hasPhotos = computed(() => images.value.length > 0);
const hasContent = computed(() => hasAlbums.value || hasPhotos.value);

const showEmptyFolder = computed(() =>
  pathReady.value &&
  infiniteScanQuery.isSuccess.value &&
  !infiniteScanQuery.isPending.value &&
  !infiniteScanQuery.isFetching.value &&
  !hasContent.value &&
  !hasSearchQuery.value
);

const showEmptyFolderDelayed = useDelayedBoolean(showEmptyFolder, 250);

const hasNoPath = computed(() => !galleryStore.currentPath && !galleryStore.rootPath);
const hasNotLoaded = computed(() => !galleryStore.hasEverLoaded && (!!galleryStore.currentPath || !!galleryStore.rootPath));
const showGallerySkeleton = computed(() =>
  !hasSearchQuery.value &&
  (hasNotLoaded.value || (isLoading.value && !galleryStore.hasEverLoaded))
);
const showSearchSkeleton = computed(() =>
  hasSearchQuery.value &&
  isSearchLoading.value &&
  !searchAlbums.value.length &&
  !searchPhotos.value.length &&
  !searchPrompt.value.length
);
const noSearchResults = computed(
  () =>
    hasSearchQuery.value &&
    !isSearchLoading.value &&
    unifiedSearchQuery.isSuccess.value &&
    !unifiedSearchQuery.isFetching.value &&
    searchAlbums.value.length === 0 &&
    searchPhotos.value.length === 0 &&
    searchPrompt.value.length === 0
);
const scanQueryErrorMessage = computed(() => {
  const error = infiniteScanQuery.error.value;
  if (!error) return "";
  const suggestion = (error as { suggestion?: string }).suggestion;
  if (suggestion) return suggestion;
  return error instanceof Error ? error.message : "Unable to load folder.";
});
const errorMessage = computed(() => galleryStore.errorMessage || scanQueryErrorMessage.value);
const showAllIndexedHint = computed(() => noSearchResults.value && galleryStore.searchScope === "current");

const handleOpenFolder = (path: string) => {
  galleryStore.selectFolder(path);
  galleryStore.clearSearch();
};

const handleOpenImage = (path: string, name: string) => {
  // Pass the full list of images to the lightbox for navigation
  lightboxStore.open({ path, name }, images.value);
};

const handlePhotoDimensions = (dimensions: { path: string; width: number; height: number }) => {
  lightboxStore.rememberDimensions(dimensions.path, {
    width: dimensions.width,
    height: dimensions.height,
    source: "thumbnail",
  });
};

const goBack = () => galleryStore.goBack();
const goForward = () => galleryStore.goForward();
const openFolder = () => galleryStore.openInExplorer();
const isLoadingMore = computed(() => infiniteScanQuery.isFetchingNextPage.value);

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

const rowVirtualizer = useVirtualizer<HTMLElement, HTMLElement>(
  computed(() => ({
    count: imageRows.value.length,
    getScrollElement: () => scrollParentRef.value,
    estimateSize: () => rowHeight.value || 1,
    overscan: 5,
    getItemKey: (index: number) => imageRows.value[index]?.id ?? index,
  }))
);

watch(
  [rowHeight, columnCount, () => imageRows.value.length],
  () => {
    rowVirtualizer.value.measure();
  },
  { flush: "post" }
);

const searchPhotoRows = computed(() => {
  const rows: { id: string; items: typeof searchPhotos.value }[] = [];
  for (let i = 0; i < searchPhotos.value.length; i += columnCount.value) {
    rows.push({
      id: `photo-row-${columnCount.value}-${i}`,
      items: searchPhotos.value.slice(i, i + columnCount.value)
    });
  }
  return rows;
});

const searchPromptRows = computed(() => {
  const rows: { id: string; items: typeof searchPrompt.value }[] = [];
  for (let i = 0; i < searchPrompt.value.length; i += columnCount.value) {
    rows.push({
      id: `prompt-row-${columnCount.value}-${i}`,
      items: searchPrompt.value.slice(i, i + columnCount.value)
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
      if (!hasMoreImages.value || isLoadingMore.value || infiniteScanQuery.isFetching.value) return;
      if (entries.some((e) => e.isIntersecting)) {
        infiniteScanQuery.fetchNextPage();
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
    <div v-if="deviceCategory === 'desktop'" class="grid-header grid grid-cols-[auto_1fr_auto_auto_auto_auto] items-center gap-3 shrink-0">
      <div class="nav-group inline-flex items-center gap-2">
        <Button
          variant="ghost"
          size="nav"
          class="nav-btn border border-border"
          :disabled="!canBack"
          @click="goBack"
          title="Back"
        >
          <ArrowLeft />
        </Button>
        <Button
          variant="ghost"
          size="nav"
          class="nav-btn border border-border"
          :disabled="!canForward"
          @click="goForward"
          title="Forward"
        >
          <ArrowRight />
        </Button>
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

      <Badge v-if="isLoading || isRefetching" variant="loading" :class="{ 'opacity-70': isRefetching && !isLoading }" class="loading-badge">
        <Loader class="gallery-icon-md lucide-spin" /> 
        <span>{{ isRefetching && !isLoading ? 'Refreshing' : 'Loading' }}</span>
      </Badge>
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

    <div v-if="showGallerySkeleton || showSearchSkeleton" class="skeleton-container">
      <div class="skeleton-grid" :style="{ gridTemplateColumns: `repeat(${columnCount}, 1fr)` }">
        <SkeletonLoader
          v-for="i in skeletonItems"
          :key="i"
          type="photo"
        />
      </div>
    </div>

    <!-- Search results: backend indexed albums, photos, and prompt matches -->
    <div
      v-else-if="hasSearchQuery"
      :ref="setScrollContainerRef"
      class="search-results-container"
    >
      <section v-if="searchAlbums.length" class="search-photo-section">
        <GallerySectionHeader
          title="Album suggestions"
          :count="searchAlbums.length"
          :badge-icon="FolderOpen"
        />
        <div class="search-album-grid">
          <AlbumCard
            v-for="(album, index) in searchAlbums"
            :key="album.path"
            :node="searchAlbumNodesRef[index]"
            @click="handleOpenFolder(album.path)"
          />
        </div>
      </section>

      <section v-if="searchPhotos.length" class="search-photo-section">
        <GallerySectionHeader
          title="Photos"
          :count="searchPhotos.length"
          :badge-icon="Images"
        />

        <div
          v-for="row in searchPhotoRows"
          :key="row.id"
          class="virtual-row"
          :style="{ gridTemplateColumns: `repeat(${columnCount}, 1fr)` }"
        >
          <div v-for="img in row.items" :key="img.path" class="search-result-card">
            <PhotoCard
              :src="img.path"
              :name="img.name"
              @dimensions="handlePhotoDimensions"
              @click="handleOpenImage(img.path, img.name)"
              @keydown.enter="handleOpenImage(img.path, img.name)"
              @keydown.space.prevent="handleOpenImage(img.path, img.name)"
            />
            <span class="search-result-name file-name-display" :title="img.name">
              <span class="file-name-base">{{ displayFilenameParts(img.name).base }}</span>
              <span class="file-name-ext">{{ displayFilenameParts(img.name).ext }}</span>
            </span>
            <span v-if="searchResultFolderPath(img)" class="search-result-path" :title="searchResultFolderPath(img)">
              <Folder class="search-result-path-icon" />
              <span :title="searchResultFolderPath(img)">{{ searchResultFolderPath(img) }}</span>
            </span>
          </div>
        </div>
      </section>

      <section v-if="searchPrompt.length" class="search-photo-section">
        <GallerySectionHeader
          title="Prompt"
          :count="searchPrompt.length"
          :badge-icon="Images"
        />

        <div
          v-for="row in searchPromptRows"
          :key="row.id"
          class="virtual-row"
          :style="{ gridTemplateColumns: `repeat(${columnCount}, 1fr)` }"
        >
          <div v-for="img in row.items" :key="img.path" class="search-result-card">
            <PhotoCard
              :src="img.path"
              :name="img.name"
              @dimensions="handlePhotoDimensions"
              @click="handleOpenImage(img.path, img.name)"
              @keydown.enter="handleOpenImage(img.path, img.name)"
              @keydown.space.prevent="handleOpenImage(img.path, img.name)"
            />
            <span class="search-result-name file-name-display" :title="img.name">
              <span class="file-name-base">{{ displayFilenameParts(img.name).base }}</span>
              <span class="file-name-ext">{{ displayFilenameParts(img.name).ext }}</span>
            </span>
            <span v-if="searchResultFolderPath(img)" class="search-result-path" :title="searchResultFolderPath(img)">
              <Folder class="search-result-path-icon" />
              <span :title="searchResultFolderPath(img)">{{ searchResultFolderPath(img) }}</span>
            </span>
          </div>
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
        <p v-if="showAllIndexedHint" class="search-scope-hint">
          Try All indexed to search outside this folder.
        </p>
      </div>
    </div>

    <!-- Has content: images or folders -->
    <template v-else-if="images.length > 0 || folders.length > 0">
      <div class="scroller-container" :ref="setGridRef">

      <div
        v-if="!props.isMobile && imageRows.length > 0"
        :ref="setVirtualScrollContainerRef"
        class="scroller tanstack-scroller"
        :class="{ 'fade-slide': !isMobile }"
      >
        <GlowContainer v-if="folders.length" :disabled="false">
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
          class="tanstack-virtual-spacer"
          :style="{ height: `${rowVirtualizer.getTotalSize()}px`, position: 'relative' }"
        >
          <div
            v-for="virtualRow in rowVirtualizer.getVirtualItems()"
            :key="String(virtualRow.key)"
            class="virtual-row tanstack-virtual-row"
            :style="{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${virtualRow.start}px)`,
              gridTemplateColumns: `repeat(${columnCount}, 1fr)`
            }"
          >
            <PhotoCard
              v-for="img in imageRows[virtualRow.index]?.items ?? []"
              :key="img.path"
              :src="img.path"
              :name="img.name"
              @dimensions="handlePhotoDimensions"
              @click="handleOpenImage(img.path, img.name)"
              @keydown.enter="handleOpenImage(img.path, img.name)"
              @keydown.space.prevent="handleOpenImage(img.path, img.name)"
            />
          </div>
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
            @dimensions="handlePhotoDimensions"
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

      <!-- Fallback: Only folders, no images -->
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
        v-else-if="showEmptyFolderDelayed"
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
  /* Grid layout handled by Tailwind utilities */
  /* Keep only responsive overrides below */
}

.nav-group {
  /* Inline-flex layout handled by Tailwind utilities */
  /* Keep only responsive overrides */
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

.search-album-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  padding: 12px 12px;
}

.search-album-grid > * {
  flex-shrink: 0;
  min-width: 180px;
  max-width: 240px;
}

.search-result-card {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.search-result-name {
  display: block;
  min-width: 0;
  max-width: 100%;
  color: var(--title-color);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.25;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-name-display {
  display: flex;
  align-items: baseline;
  min-width: 0;
  max-width: 100%;
  white-space: nowrap;
  overflow: visible;
  text-overflow: clip;
}

.file-name-base {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-name-ext {
  flex: 0 0 auto;
  white-space: nowrap;
}

.search-result-path {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  color: var(--muted-text);
  font-size: 12px;
  line-height: 1.3;
}

.search-result-path span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-result-path-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  color: color-mix(in srgb, var(--muted-text) 82%, var(--primary-color));
}

.search-album-path {
  display: flex;
}

.search-scope-hint {
  margin: 10px 0 0;
  color: var(--muted-text);
  font-size: 13px;
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

/* nav-btn base and ghost styles handled by shadcn Button size="nav" variant="ghost" */
/* Keep only open-folder (color-mix), responsive overrides, and focus-visible */

.nav-btn {
  /* Base class preserved for responsive grid (mobile overrides) and open-folder variant */
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

/* loading-badge base styles handled by shadcn Badge variant="loading" */
/* Only responsive rules remain */
.loading-badge {
  /* Class preserved for responsive overrides */
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
/* content-visibility:auto removed because it causes flicker on mobile Safari */

@media (max-width: 1199px) {
  .grid-header {
    gap: 8px;
  }

  .search-results-container {
    padding-left: 8px;
    padding-right: 8px;
  }

  .search-photo-section {
    gap: 10px;
  }

  .search-album-grid {
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 8px;
  }

  .search-result-name {
    font-size: 12.5px;
  }

  .search-result-path {
    font-size: 11.5px;
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

  .search-results-container {
    padding-left: 4px;
    padding-right: 4px;
  }

  .search-photo-section {
    gap: 8px;
    margin-top: 10px;
  }

  .search-album-grid {
    grid-template-columns: 1fr;
    gap: 7px;
  }

  .search-result-card {
    gap: 3px;
  }

  .search-result-name {
    font-size: 12px;
  }

  .search-result-path {
    font-size: 11px;
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
