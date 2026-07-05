<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch, type ComponentPublicInstance } from "vue";
import { useIntersectionObserver } from "@vueuse/core";
import { useVirtualizer } from "@tanstack/vue-virtual";
import { useGalleryStore } from "../stores/gallery";
import { useLightboxStore } from "../stores/lightbox";
import type { FileNode, SortValue, UnifiedSearchResult } from "../types";
import { normalizeAssetType } from "../utils/assetType";
import AlbumCard from "./AlbumCard.vue";
import AlbumScroller from "./AlbumScroller.vue";
import GallerySectionHeader from "./GallerySectionHeader.vue";
import GlowContainer from "./GlowContainer.vue";
import PhotoCard from "./PhotoCard.vue";
import VideoCard from "./VideoCard.vue";
import VideoPlayerDialog from "./VideoPlayerDialog.vue";
import SkeletonLoader from "./SkeletonLoader.vue";
import Breadcrumb from "./Breadcrumb.vue";
import EmptyState from "./EmptyState.vue";
import TabletGalleryToolbar from "./TabletGalleryToolbar.vue";
import SortSelect from "./SortSelect.vue";
import { compareNatural } from "../composables/useNaturalSort";
import { useColumnResize, PHOTO_GRID_LEVELS, GRID_COLUMN_MAP } from "../composables/useColumnResize";
import { useDevice } from "../composables/useDevice";
import { usePullToRefresh } from "../composables/usePullToRefresh";
import { useDelayedBoolean } from "../composables/useDelayedBoolean";
import { useInfiniteBrowseQuery } from "../composables/useInfiniteBrowseQuery";
import { useUnifiedSearchQuery } from "../composables/useUnifiedSearchQuery";
import { galleryScrollContainerRefKey } from "../injectionKeys";
import type { ErrorType } from "../services/api";
import { fuzzySearchFileNodes } from "../utils/fuzzySearch";
import { shouldLoadMoreImages } from "../utils/gallery";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  ChevronDown,
  LayoutGrid,
  Loader,
  TriangleAlert,
  X,
  ArrowDownToLine,
  Images,
  Clapperboard,
  Folder,
  FolderOpen,
} from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import OverflowTooltip from "@/components/ui/OverflowTooltip.vue";
import Badge from "./ui/Badge.vue";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useRouter } from "vue-router";

const galleryStore = useGalleryStore();
const router = useRouter();
const lightboxStore = useLightboxStore();
const activeLibraryId = computed(() => galleryStore.activeLibraryId);
const activeBrowsePath = computed(() => galleryStore.currentBrowsePath || null);
const infiniteBrowseQuery = useInfiniteBrowseQuery(activeLibraryId, activeBrowsePath);

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
    await infiniteBrowseQuery.refetch();
  },
});

interface Props {
  isMobile: boolean;
  barsVisible?: boolean;
  showToolbarBreadcrumb?: boolean;
  showDesktopToolbar?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  barsVisible: true,
  showToolbarBreadcrumb: true,
  showDesktopToolbar: true,
});
const injectedScrollContainerRef = inject(galleryScrollContainerRefKey, null);
const scrollParentRef = ref<HTMLElement | null>(null);
const searchScrollParentRef = ref<HTMLElement | null>(null);

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
const searchContextPath = computed(() => infiniteBrowseQuery.activeFolderPath.value);
const unifiedSearchQuery = useUnifiedSearchQuery(searchQuery, searchScope, searchContextPath);
const sortField = computed(() => galleryStore.sortField);
const sortOrder = computed(() => galleryStore.sortOrder);

const gallerySortValue = computed<SortValue>({
  get() {
    return `${sortField.value === "name" ? "name" : "date"}_${sortOrder.value}` as SortValue;
  },
  set(value) {
    const [field, order] = value.split("_") as ["date" | "name", "asc" | "desc"];
    galleryStore.setSortField(field);
    galleryStore.setSortOrder(order);
  },
});

const showDensityMenu = ref(false);

const toggleDensityMenu = () => {
  showDensityMenu.value = !showDensityMenu.value;
};

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

const hasBrowseScope = computed(() =>
  Boolean(activeLibraryId.value && (activeBrowsePath.value || galleryStore.activeImportPathId)),
);
const hasActiveBrowsePage = computed(
  () => infiniteBrowseQuery.isSuccess.value && infiniteBrowseQuery.hasActivePage.value,
);
const scanFolders = computed(() => (hasActiveBrowsePage.value ? infiniteBrowseQuery.folders.value : []));
const scanMedia = computed(() => (hasActiveBrowsePage.value ? infiniteBrowseQuery.media.value : []));
const scanImages = computed(() => scanMedia.value.filter((item) => item.type === "image"));

const folders = computed(() =>
  sortItems(hasSearchQuery.value ? scanFolders.value : fuzzySearchFileNodes(scanFolders.value, searchQuery.value)),
);

// Fuse search is client-side and only covers images currently loaded in the active scan view.
const filenameImages = computed(() =>
  sortItems(hasSearchQuery.value ? scanImages.value : fuzzySearchFileNodes(scanImages.value, searchQuery.value)),
);
const filenameMedia = computed(() =>
  sortItems(hasSearchQuery.value ? scanMedia.value : fuzzySearchFileNodes(scanMedia.value, searchQuery.value)),
);

const searchResultToFileNode = (result: UnifiedSearchResult): FileNode => ({
  name: result.name,
  path: result.path,
  type: normalizeAssetType(result.type),
  has_children: false,
  cover_images: result.cover_images || [],
  image_count: result.image_count || 0,
  mtime: result.mtime,
  width: result.width ?? undefined,
  height: result.height ?? undefined,
  duration_ms: result.duration_ms,
  mime_type: result.mime_type,
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
  if (
    relativeFolderPath ||
    !normalizedRelativePath ||
    normalizedRelativePath === "." ||
    normalizedRelativePath === result.name
  ) {
    return relativeFolderPath;
  }
  return folderPathFromRelativePath(result.parent_path, result.name);
};

const searchAlbums = computed(() => unifiedSearchQuery.albums.value);
const searchPhotos = computed(() => unifiedSearchQuery.photos.value);
const searchVideos = computed(() => unifiedSearchQuery.videos.value);
const searchPhotoPathSet = computed(
  () => new Set(searchPhotos.value.map((result) => normalizeSearchPath(result.path))),
);
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
        (folder) => normalizeSearchPath(folder.path) === normalizeSearchPath(album.path),
      );
      if (match && match.cover_images && match.cover_images.length > 0) {
        node.cover_images = match.cover_images;
        if (!node.image_count && match.image_count) {
          node.image_count = match.image_count;
        }
      }
    }
    return node;
  }),
);
const searchPhotoNodes = computed(() => searchPhotos.value.map(searchResultToFileNode));
const searchVideoNodes = computed(() => searchVideos.value.map(searchResultToFileNode));
const searchPromptNodes = computed(() => searchPrompt.value.map(searchResultToFileNode));
const allSearchImageNodes = computed(() => {
  const seen = new Set<string>();
  return [...searchPhotoNodes.value, ...searchPromptNodes.value].filter((image) => {
    if (seen.has(image.path)) return false;
    seen.add(image.path);
    return true;
  });
});

const images = computed(() => (hasSearchQuery.value ? allSearchImageNodes.value : filenameImages.value));
const media = computed(() =>
  hasSearchQuery.value ? [...allSearchImageNodes.value, ...searchVideoNodes.value] : filenameMedia.value,
);

const isLoading = computed(() => infiniteBrowseQuery.isLoading.value);
const isRefetching = computed(
  () =>
    infiniteBrowseQuery.isFetching.value &&
    !infiniteBrowseQuery.isLoading.value &&
    !infiniteBrowseQuery.isFetchingNextPage.value,
);
const isSearchLoading = computed(
  () => hasSearchQuery.value && (unifiedSearchQuery.isLoading.value || unifiedSearchQuery.isFetching.value),
);
const isSearchIndicatorActive = computed(
  () =>
    hasSearchQuery.value &&
    (trimmedSearchQuery.value !== unifiedSearchQuery.debouncedQuery.value ||
      unifiedSearchQuery.isLoading.value ||
      unifiedSearchQuery.isFetching.value),
);
const currentPath = computed(() => galleryStore.currentBrowsePath);
const activeImportRootPath = computed(() => galleryStore.activeImportRootPath);
const canBack = computed(() => galleryStore.historyIndex > 0);
const canForward = computed(() => galleryStore.historyIndex < galleryStore.history.length - 1);
const hasMoreImages = computed(() => !hasSearchQuery.value && infiniteBrowseQuery.hasNextPage.value);
const hasAnyItems = computed(() => scanFolders.value.length + scanMedia.value.length > 0);

const browseLoading = computed(
  () =>
    hasBrowseScope.value &&
    !hasActiveBrowsePage.value &&
    !errorMessage.value &&
    (infiniteBrowseQuery.isPending.value ||
      infiniteBrowseQuery.isLoading.value ||
      infiniteBrowseQuery.isFetching.value),
);
const browsePreparing = computed(() => hasBrowseScope.value && !hasActiveBrowsePage.value && !errorMessage.value);

const hasAlbums = computed(() => folders.value.length > 0);
const hasMedia = computed(() => media.value.length > 0);
const hasContent = computed(() => hasAlbums.value || hasMedia.value);

const showEmptyFolder = computed(
  () =>
    hasActiveBrowsePage.value &&
    !infiniteBrowseQuery.isPending.value &&
    !infiniteBrowseQuery.isFetching.value &&
    !hasContent.value &&
    !hasSearchQuery.value,
);

const showEmptyFolderDelayed = useDelayedBoolean(showEmptyFolder, 250);

watch(isSearchIndicatorActive, (loading) => galleryStore.setSearchLoading(loading), { immediate: true });

onBeforeUnmount(() => {
  galleryStore.setSearchLoading(false);
});

const hasNoPath = computed(() => galleryStore.activeLibraryHydrated && !galleryStore.activeImportPathId);
const showBrowsePreparingEmpty = computed(() => !hasSearchQuery.value && browsePreparing.value && !browseLoading.value);
const showGallerySkeleton = computed(() => !hasSearchQuery.value && browseLoading.value);
const showSearchSkeleton = computed(
  () =>
    hasSearchQuery.value &&
    isSearchLoading.value &&
    !searchAlbums.value.length &&
    !searchPhotos.value.length &&
    !searchVideos.value.length &&
    !searchPrompt.value.length,
);
const noSearchResults = computed(
  () =>
    hasSearchQuery.value &&
    !isSearchLoading.value &&
    unifiedSearchQuery.isSuccess.value &&
    !unifiedSearchQuery.isFetching.value &&
    searchAlbums.value.length === 0 &&
    searchPhotos.value.length === 0 &&
    searchVideos.value.length === 0 &&
    searchPrompt.value.length === 0,
);
const scanQueryErrorMessage = computed(() => {
  const error = infiniteBrowseQuery.error.value;
  if (!error) return "";
  const suggestion = (error as { suggestion?: string }).suggestion;
  if (suggestion) return suggestion;
  return error instanceof Error ? error.message : "Unable to load folder.";
});
const errorMessage = computed(() => galleryStore.errorMessage || scanQueryErrorMessage.value);
const scanQueryErrorType = computed(() => {
  const type = (infiniteBrowseQuery.error.value as { type?: unknown } | null)?.type;
  return typeof type === "string" ? (type as ErrorType) : null;
});
const errorType = computed(() => galleryStore.errorType || scanQueryErrorType.value);
const errorActionConfig = computed(() => {
  const clearError = () => galleryStore.clearError();
  const retry = () => {
    galleryStore.clearError();
    void infiniteBrowseQuery.refetch();
  };

  switch (errorType.value) {
    case "library_not_registered":
      return {
        title: "Library not registered",
        label: "Manage Libraries",
        icon: undefined,
        action: () => {
          clearError();
          void router.push("/admin/libraries");
        },
      };
    case "library_not_indexed":
    case "library_discovering":
      return {
        title: "Library not imported yet",
        label: "Update library",
        icon: undefined,
        action: clearError,
      };
    case "library_offline":
      return {
        title: "Library is offline",
        label: "Retry",
        icon: "arrow-left",
        action: retry,
      };
    case "not_found":
      return {
        title: "Folder not found",
        label: "Clear",
        icon: "xmark",
        action: clearError,
      };
    case "not_directory":
      return {
        title: "Invalid path",
        label: "Clear",
        icon: "xmark",
        action: clearError,
      };
    default:
      return {
        title: "Unable to load folder",
        label: "Clear",
        icon: "xmark",
        action: clearError,
      };
  }
});
const showAllIndexedHint = computed(() => noSearchResults.value && galleryStore.searchScope === "current");

const handleOpenFolder = (path: string) => {
  galleryStore.selectFolder(path);
  galleryStore.clearSearch();
};

const handleOpenImage = (path: string, name: string) => {
  // Pass the full list of images to the lightbox for navigation
  lightboxStore.open({ path, name }, images.value);
};

const selectedVideo = ref<FileNode | null>(null);
const videoPlayerOpen = ref(false);
const handleOpenVideo = (video: FileNode) => {
  selectedVideo.value = video;
  videoPlayerOpen.value = true;
};

const handleOpenMedia = (item: FileNode) => {
  if (item.type === "video") {
    handleOpenVideo(item);
    return;
  }
  handleOpenImage(item.path, item.name);
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
const isLoadingMore = computed(() => infiniteBrowseQuery.isFetchingNextPage.value);

// --- Virtual scroller state ---
const { isTablet } = useDevice();
const deviceCategory = computed(() => (props.isMobile ? "mobile" : isTablet.value ? "tablet" : "desktop"));
const { columnCount, sliderLevel, rowHeight, setGridRef } = useColumnResize(deviceCategory);

const setSearchScrollContainerRef = (target: Element | ComponentPublicInstance | null) => {
  const el = resolveTemplateRefElement(target);
  searchScrollParentRef.value = el;
  setScrollContainerRef(target);
  setGridRef(target);
};

// Density dropdown options
const densityOptions = computed(() => {
  if (deviceCategory.value !== "tablet") return [...PHOTO_GRID_LEVELS].sort((a, b) => a.columns - b.columns);
  const map = GRID_COLUMN_MAP.tablet;
  const seen = new Set<number>();
  const result: Array<{ level: number; label: string; columns: number }> = [];
  for (let i = 0; i < PHOTO_GRID_LEVELS.length; i++) {
    const cols = map[i];
    if (!seen.has(cols)) {
      seen.add(cols);
      result.push({ ...PHOTO_GRID_LEVELS[i], columns: cols });
    }
  }
  return result.sort((a, b) => a.columns - b.columns);
});

const selectDensity = (level: number) => {
  sliderLevel.value = level;
};

const mediaRows = computed(() => {
  const rows: { id: string; items: typeof media.value }[] = [];
  for (let i = 0; i < media.value.length; i += columnCount.value) {
    rows.push({
      id: `row-${columnCount.value}-${i}`,
      items: media.value.slice(i, i + columnCount.value),
    });
  }
  return rows;
});

const rowVirtualizer = useVirtualizer<HTMLElement, HTMLElement>(
  computed(() => ({
    count: mediaRows.value.length,
    getScrollElement: () => scrollParentRef.value,
    estimateSize: () => rowHeight.value || 1,
    overscan: 5,
    getItemKey: (index: number) => mediaRows.value[index]?.id ?? index,
  })),
);

watch(
  [rowHeight, columnCount, () => mediaRows.value.length],
  () => {
    rowVirtualizer.value.measure();
  },
  { flush: "post" },
);

type SearchSection = "albums" | "photos" | "videos" | "prompt";
type SearchVirtualRow =
  | { id: string; kind: "header"; section: SearchSection; count: number }
  | { id: string; kind: "albums"; items: FileNode[] }
  | { id: string; kind: "photos"; items: UnifiedSearchResult[] }
  | { id: string; kind: "videos"; items: FileNode[] }
  | { id: string; kind: "prompt"; items: UnifiedSearchResult[] };

const chunkItems = <T,>(items: T[], chunkSize: number): T[][] => {
  const size = Math.max(1, chunkSize);
  const rows: T[][] = [];
  for (let i = 0; i < items.length; i += size) {
    rows.push(items.slice(i, i + size));
  }
  return rows;
};

const searchAlbumColumnCount = computed(() => {
  if (props.isMobile) return 1;
  if (isTablet.value) return Math.min(3, columnCount.value);
  return Math.max(3, Math.min(5, columnCount.value - 1));
});

const searchVirtualRows = computed<SearchVirtualRow[]>(() => {
  const rows: SearchVirtualRow[] = [];

  if (searchAlbums.value.length) {
    rows.push({ id: "header-albums", kind: "header", section: "albums", count: searchAlbums.value.length });
    chunkItems(searchAlbumNodesRef.value, searchAlbumColumnCount.value).forEach((items, index) => {
      rows.push({ id: `albums-${searchAlbumColumnCount.value}-${index}`, kind: "albums", items });
    });
  }

  if (searchPhotos.value.length) {
    rows.push({ id: "header-photos", kind: "header", section: "photos", count: searchPhotos.value.length });
    chunkItems(searchPhotos.value, columnCount.value).forEach((items, index) => {
      rows.push({ id: `photos-${columnCount.value}-${index}`, kind: "photos", items });
    });
  }

  if (searchVideos.value.length) {
    rows.push({ id: "header-videos", kind: "header", section: "videos", count: searchVideos.value.length });
    chunkItems(searchVideoNodes.value, columnCount.value).forEach((items, index) => {
      rows.push({ id: `videos-${columnCount.value}-${index}`, kind: "videos", items });
    });
  }

  if (searchPrompt.value.length) {
    rows.push({ id: "header-prompt", kind: "header", section: "prompt", count: searchPrompt.value.length });
    chunkItems(searchPrompt.value, columnCount.value).forEach((items, index) => {
      rows.push({ id: `prompt-${columnCount.value}-${index}`, kind: "prompt", items });
    });
  }

  return rows;
});

const searchHeaderTitle = (section: SearchSection) => {
  switch (section) {
    case "albums":
      return "Album suggestions";
    case "photos":
      return "Photos";
    case "videos":
      return "Videos";
    case "prompt":
      return "Prompt";
  }
};

const searchHeaderIcon = (section: SearchSection) => {
  if (section === "albums") return FolderOpen;
  if (section === "videos") return Clapperboard;
  return Images;
};

const estimateSearchRowSize = (index: number) => {
  const row = searchVirtualRows.value[index];
  if (!row) return rowHeight.value || 220;
  if (row.kind === "header") return 48;
  if (row.kind === "albums") return props.isMobile ? 178 : isTablet.value ? 226 : 280;
  const mediaHeight = rowHeight.value || (props.isMobile ? 150 : isTablet.value ? 190 : 220);
  return mediaHeight + (row.kind === "videos" ? 28 : 48);
};

const searchVirtualizer = useVirtualizer<HTMLElement, HTMLElement>(
  computed(() => ({
    count: searchVirtualRows.value.length,
    getScrollElement: () => searchScrollParentRef.value,
    estimateSize: estimateSearchRowSize,
    overscan: 4,
    getItemKey: (index: number) => searchVirtualRows.value[index]?.id ?? index,
  })),
);

watch(
  [rowHeight, columnCount, searchAlbumColumnCount, () => searchVirtualRows.value.length],
  () => {
    searchVirtualizer.value.measure();
  },
  { flush: "post" },
);

const skeletonItems = computed(() => Array.from({ length: 12 }, (_, i) => i));

// Infinite load sentinel
const loadMoreSentinel = ref<HTMLElement | null>(null);

const canLoadMoreImages = computed(() =>
  shouldLoadMoreImages({
    hasMoreImages: hasMoreImages.value,
    isLoadingMore: isLoadingMore.value,
    isFetching: infiniteBrowseQuery.isFetching.value,
    hasSearchQuery: hasSearchQuery.value,
  }),
);

useIntersectionObserver(
  loadMoreSentinel,
  ([entry]) => {
    if (!entry?.isIntersecting) return;
    if (!canLoadMoreImages.value) return;

    infiniteBrowseQuery.fetchNextPage();
  },
  {
    root: null,
    rootMargin: "400px",
    threshold: 0,
  },
);

// ── Album Horizontal Scroll (handled by AlbumScroller component) ──
</script>

<template>
  <div
    class="gallery-grid"
    data-testid="gallery-grid"
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
      <span class="pull-label">{{ isRefreshing ? "Refreshing..." : "Pull to refresh" }}</span>
    </div>

    <!-- ============================================================
         Desktop toolbar
         ============================================================ -->
    <div
      v-if="deviceCategory === 'desktop' && showDesktopToolbar"
      class="grid-header grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-3 shrink-0"
    >
      <div class="nav-group inline-flex items-center gap-2">
        <Tooltip>
          <TooltipTrigger as-child>
            <Button
              variant="ghost"
              size="icon-sm"
              class="nav-btn"
              :disabled="!canBack"
              type="button"
              aria-label="Go back"
              @click="goBack"
            >
              <ArrowLeft class="gallery-icon-toolbar" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Back</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger as-child>
            <Button
              variant="ghost"
              size="icon-sm"
              class="nav-btn"
              :disabled="!canForward"
              type="button"
              aria-label="Go forward"
              @click="goForward"
            >
              <ArrowRight class="gallery-icon-toolbar" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Forward</TooltipContent>
        </Tooltip>
      </div>
      <Breadcrumb
        v-if="showToolbarBreadcrumb"
        class="breadcrumb-wrap"
        :path="currentPath"
        :root-path="activeImportRootPath"
        @navigate="handleOpenFolder"
      >
        <template #actions>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                variant="ghost"
                size="icon-sm"
                type="button"
                aria-label="Open current folder in file explorer"
                @click="openFolder"
              >
                <ArrowUpRight data-icon="inline-start" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Open current folder in file explorer</TooltipContent>
          </Tooltip>
        </template>
      </Breadcrumb>

      <SortSelect
        v-model="gallerySortValue"
        aria-label="Sort gallery"
        trigger-label="Sort"
        trigger-class="h-8 w-[74px] gap-1.5 px-2 py-0 text-xs font-normal shadow-none"
      />

      <!-- Density Dropdown -->
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button
            variant="outline"
            type="button"
            class="h-8 w-[74px] justify-between gap-1.5 px-2 text-xs font-normal text-foreground shadow-none gallery-density-trigger"
          >
            <span class="truncate">View</span>
            <ChevronDown data-icon="inline-end" class="opacity-50" />
          </Button>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="end">
          <DropdownMenuRadioGroup
            :model-value="String(sliderLevel)"
            @update:model-value="(value: unknown) => selectDensity(Number(value))"
          >
            <DropdownMenuRadioItem
              v-for="option in densityOptions"
              :key="option.level"
              :value="String(option.level)"
              class="gap-2"
            >
              <LayoutGrid class="gallery-icon-sm" />
              <span class="flex-1">{{ option.columns }} columns</span>
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      <Badge
        v-if="isLoading || isRefetching"
        variant="loading"
        :class="{ 'opacity-70': isRefetching && !isLoading }"
        class="loading-badge"
      >
        <Loader class="gallery-icon-md lucide-spin" />
        <span>{{ isRefetching && !isLoading ? "Refreshing" : "Loading" }}</span>
      </Badge>
    </div>

    <!-- ============================================================
         Tablet toolbar (dedicated component)
         ============================================================ -->
    <TabletGalleryToolbar
      v-else-if="deviceCategory === 'tablet'"
      :can-go-back="canBack"
      :can-go-forward="canForward"
      v-model:sort-value="gallerySortValue"
      :slider-level="sliderLevel"
      :column-count="columnCount"
      :density-options="densityOptions"
      :show-density-menu="showDensityMenu"
      @back="goBack"
      @forward="goForward"
      @toggle-density-menu="toggleDensityMenu"
      @select-density="selectDensity"
    />

    <div v-if="errorMessage" role="alert" class="error-banner" data-testid="error-banner">
      <div class="error-text">
        <TriangleAlert class="gallery-icon-md" />
        <span>{{ errorMessage }}</span>
      </div>
      <Tooltip>
        <TooltipTrigger as-child>
          <button class="error-close" type="button" aria-label="Dismiss error" @click="galleryStore.clearError()">
            <X class="gallery-icon-sm" />
          </button>
        </TooltipTrigger>
        <TooltipContent>Dismiss error</TooltipContent>
      </Tooltip>
    </div>

    <div v-if="showGallerySkeleton || showSearchSkeleton" class="skeleton-container">
      <div class="skeleton-grid" :style="{ gridTemplateColumns: `repeat(${columnCount}, 1fr)` }">
        <SkeletonLoader v-for="i in skeletonItems" :key="i" type="photo" />
      </div>
    </div>

    <!-- Search results: backend indexed albums, photos, and prompt matches -->
    <div v-else-if="hasSearchQuery" :ref="setSearchScrollContainerRef" class="search-results-container">
      <div
        v-if="searchVirtualRows.length"
        class="search-virtual-spacer"
        :style="{ height: `${searchVirtualizer.getTotalSize()}px`, position: 'relative' }"
      >
        <template v-for="virtualRow in searchVirtualizer.getVirtualItems()" :key="String(virtualRow.key)">
          <template v-for="row in [searchVirtualRows[virtualRow.index]]" :key="row?.id ?? String(virtualRow.key)">
            <div
              v-if="row?.kind === 'header'"
              class="search-virtual-row search-virtual-row--header"
              :style="{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
              }"
            >
              <GallerySectionHeader
                :title="searchHeaderTitle(row.section)"
                :count="row.count"
                :badge-icon="searchHeaderIcon(row.section)"
              />
            </div>

            <div
              v-else-if="row?.kind === 'albums'"
              class="search-virtual-row search-album-grid"
              :style="{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
                gridTemplateColumns: `repeat(${searchAlbumColumnCount}, minmax(0, 1fr))`,
              }"
            >
              <AlbumCard
                v-for="album in row.items"
                :key="album.path"
                :node="album"
                @click="handleOpenFolder(album.path)"
              />
            </div>

            <div
              v-else-if="row?.kind === 'photos'"
              class="search-virtual-row virtual-row"
              :style="{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
                gridTemplateColumns: `repeat(${columnCount}, 1fr)`,
              }"
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
                <OverflowTooltip :text="img.name" class="search-result-name file-name-display">
                  <span class="file-name-base">{{ displayFilenameParts(img.name).base }}</span>
                  <span class="file-name-ext">{{ displayFilenameParts(img.name).ext }}</span>
                </OverflowTooltip>
                <OverflowTooltip
                  v-if="searchResultFolderPath(img)"
                  :text="searchResultFolderPath(img)"
                  class="search-result-path"
                >
                  <Folder class="search-result-path-icon" />
                  <span>{{ searchResultFolderPath(img) }}</span>
                </OverflowTooltip>
              </div>
            </div>

            <div
              v-else-if="row?.kind === 'videos'"
              class="search-virtual-row virtual-row"
              :style="{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
                gridTemplateColumns: `repeat(${columnCount}, 1fr)`,
              }"
            >
              <div v-for="video in row.items" :key="video.path" class="search-result-card">
                <VideoCard
                  :src="video.path"
                  :name="video.name"
                  :duration-ms="video.duration_ms"
                  @click="handleOpenVideo(video)"
                />
                <OverflowTooltip :text="video.name" class="search-result-name file-name-display">
                  <span class="file-name-base">{{ displayFilenameParts(video.name).base }}</span>
                  <span class="file-name-ext">{{ displayFilenameParts(video.name).ext }}</span>
                </OverflowTooltip>
              </div>
            </div>

            <div
              v-else-if="row?.kind === 'prompt'"
              class="search-virtual-row virtual-row"
              :style="{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
                gridTemplateColumns: `repeat(${columnCount}, 1fr)`,
              }"
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
                <OverflowTooltip :text="img.name" class="search-result-name file-name-display">
                  <span class="file-name-base">{{ displayFilenameParts(img.name).base }}</span>
                  <span class="file-name-ext">{{ displayFilenameParts(img.name).ext }}</span>
                </OverflowTooltip>
                <OverflowTooltip
                  v-if="searchResultFolderPath(img)"
                  :text="searchResultFolderPath(img)"
                  class="search-result-path"
                >
                  <Folder class="search-result-path-icon" />
                  <span>{{ searchResultFolderPath(img) }}</span>
                </OverflowTooltip>
              </div>
            </div>
          </template>
        </template>
      </div>

      <div v-if="noSearchResults" class="search-empty-wrap">
        <EmptyState
          type="no-results"
          title="No results"
          description="Try a filename, album name, or prompt."
          action-label="Clear search"
          action-icon="xmark"
          @action="galleryStore.clearSearch()"
        />
        <p v-if="showAllIndexedHint" class="search-scope-hint">Try All indexed to search outside this folder.</p>
      </div>
    </div>

    <!-- Has content: mixed media or folders -->
    <template v-else-if="media.length > 0 || folders.length > 0">
      <div class="scroller-container" :ref="setGridRef">
        <div
          v-if="!props.isMobile && mediaRows.length > 0"
          :ref="setVirtualScrollContainerRef"
          class="scroller tanstack-scroller"
          :class="{ 'fade-slide': !isMobile }"
        >
          <GlowContainer v-if="folders.length" :disabled="false">
            <AlbumScroller :folders="folders" @open-folder="handleOpenFolder" />
          </GlowContainer>

          <GallerySectionHeader v-if="media.length" title="Media" :count="media.length" :badge-icon="Images" />

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
                gridTemplateColumns: `repeat(${columnCount}, 1fr)`,
              }"
            >
              <template v-for="item in mediaRows[virtualRow.index]?.items ?? []" :key="item.path">
                <VideoCard
                  v-if="item.type === 'video'"
                  :src="item.path"
                  :name="item.name"
                  :duration-ms="item.duration_ms"
                  @click="handleOpenVideo(item)"
                />
                <PhotoCard
                  v-else
                  :src="item.path"
                  :name="item.name"
                  @dimensions="handlePhotoDimensions"
                  @click="handleOpenMedia(item)"
                />
              </template>
            </div>
          </div>

          <div class="scroller-footer" :class="{ 'bars-hidden': !barsVisible }">
            <div ref="loadMoreSentinel" class="load-more-sentinel" />
            <div v-if="isLoadingMore" class="loading-more">
              <Loader class="gallery-icon-md lucide-spin" />
              <span>Loading more media...</span>
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
          v-else-if="props.isMobile && mediaRows.length > 0"
          :ref="setScrollContainerRef"
          class="scroller mobile-scroller"
        >
          <GlowContainer v-if="folders.length" :disabled="true">
            <AlbumScroller :folders="folders" @open-folder="handleOpenFolder" />
          </GlowContainer>

          <GallerySectionHeader v-if="media.length" title="Media" :count="media.length" :badge-icon="Images" />

          <div
            v-for="row in mediaRows"
            :key="row.id"
            class="virtual-row"
            :style="{ gridTemplateColumns: `repeat(${columnCount}, 1fr)` }"
          >
            <template v-for="item in row.items" :key="item.path">
              <VideoCard
                v-if="item.type === 'video'"
                :src="item.path"
                :name="item.name"
                :duration-ms="item.duration_ms"
                @click="handleOpenVideo(item)"
              />
              <PhotoCard
                v-else
                :src="item.path"
                :name="item.name"
                @dimensions="handlePhotoDimensions"
                @click="handleOpenMedia(item)"
              />
            </template>
          </div>

          <div class="scroller-footer" :class="{ 'bars-hidden': !barsVisible }">
            <div ref="loadMoreSentinel" class="load-more-sentinel" />
            <div v-if="isLoadingMore" class="loading-more">
              <Loader class="gallery-icon-md lucide-spin" />
              <span>Loading more media...</span>
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

        <!-- Fallback: Only folders, no media -->
        <div v-else-if="folders.length > 0" :ref="setScrollContainerRef" class="folders-only-container">
          <GlowContainer :disabled="props.isMobile">
            <AlbumScroller :folders="folders" @open-folder="handleOpenFolder" />
          </GlowContainer>

          <!-- Has only folders, no media -->
          <EmptyState
            v-if="!media.length && !isLoading"
            type="no-images"
            title="No media in this folder"
            description="This folder only contains subfolders. Browse the albums above."
            compact
          />
        </div>
      </div>
    </template>

    <!-- Empty States (when scroller-container is not rendered) -->
    <div v-else class="empty-state-container" data-testid="empty-state-container">
      <!-- Error State -->
      <EmptyState
        v-if="errorMessage && !hasAnyItems"
        type="error"
        :title="errorActionConfig.title"
        :description="errorMessage"
        :action-label="errorActionConfig.label"
        :action-icon="errorActionConfig.icon"
        @action="errorActionConfig.action()"
      />

      <!-- No Path Selected -->
      <EmptyState
        v-else-if="hasNoPath"
        type="no-path"
        title="No library selected"
        description="Select a registered library, or add one to start browsing."
        action-label="Manage Libraries"
        @action="router.push('/admin/libraries')"
      />

      <!-- Not Loaded Yet -->
      <EmptyState
        v-else-if="showBrowsePreparingEmpty"
        type="not-loaded"
        title="Loading library"
        description="Preparing the selected import path."
      />

      <!-- Empty Folder -->
      <EmptyState
        v-else-if="showEmptyFolderDelayed"
        type="empty-folder"
        title="This folder is empty"
        description="No images, videos, or subfolders found in this location"
        action-label="Go Back"
        action-icon="arrow-left"
        @action="goBack"
      />
    </div>

    <VideoPlayerDialog v-model:open="videoPlayerOpen" :video="selectedVideo" />
  </div>
</template>

<style scoped>
.gallery-grid {
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: 100%;
  min-height: 0;
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
  background: color-mix(in srgb, var(--destructive) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--destructive) 40%, transparent);
  color: var(--foreground);
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

.search-album-grid {
  display: grid;
  gap: 20px;
  padding: 0 8px;
}

.search-album-grid > * {
  min-width: 0;
}

.search-virtual-row {
  contain: layout style;
}

.search-virtual-row--header {
  padding: 10px 8px 0;
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
  color: var(--foreground);
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
  color: var(--muted-foreground);
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
  color: color-mix(in srgb, var(--muted-foreground) 82%, var(--primary));
}

.search-scope-hint {
  margin: 10px 0 0;
  color: var(--muted-foreground);
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
  color: var(--foreground);
  border-radius: 10px;
}

/* ...existing code... */

.nav-group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.nav-btn {
  /* Layout hook only — visual styling owned by shadcn Button */
}

.breadcrumb-wrap {
  justify-self: start;
  width: fit-content;
  min-width: 0;
  max-width: 100%;
}

/* loading-badge base styles handled by shadcn Badge variant="loading" */
/* Only responsive rules remain */
.loading-badge {
  /* Class preserved for responsive overrides */
}

/* ── Album scroll styles are in AlbumScroller.vue ── */

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

  .search-album-grid {
    gap: 12px;
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

  .nav-group {
    flex-shrink: 0;
  }

  .breadcrumb-wrap {
    flex: 1;
    min-width: 0;
    overflow: hidden;
  }

  .nav-group {
    display: flex;
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

  .search-album-grid {
    gap: 8px;
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
}

/* Reduced motion support */
@media (prefers-reduced-motion: reduce) {
  .fade-slide {
    animation: none;
  }
}

/* ── Pull-to-refresh indicator ── */
.pull-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 0 8px;
  color: var(--primary);
  font-size: 13px;
  font-weight: 500;
  transition:
    transform 0.3s cubic-bezier(0.2, 0, 0, 1),
    opacity 0.2s ease;
  will-change: transform;
  flex-shrink: 0;
}

.pull-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s ease;
  color: var(--primary);
}

.pull-spinner {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary);
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
