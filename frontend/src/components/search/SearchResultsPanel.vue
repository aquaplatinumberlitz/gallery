<script setup lang="ts">
import { computed, inject, shallowRef, useTemplateRef, type ComponentPublicInstance } from "vue";
import { useResizeObserver } from "@vueuse/core";
import { Folder, FolderOpen, Images } from "lucide-vue-next";
import AlbumCard from "@/components/AlbumCard.vue";
import AlbumCardMobile from "@/components/AlbumCardMobile.vue";
import AlbumCardTablet from "@/components/AlbumCardTablet.vue";
import GallerySectionHeader from "@/components/GallerySectionHeader.vue";
import OverflowTooltip from "@/components/ui/OverflowTooltip.vue";
import PhotoCard from "@/components/PhotoCard.vue";
import VideoCard from "@/components/VideoCard.vue";
import { chunkItems, useVirtualGridRows } from "@/composables/useVirtualGridRows";
import { useInfiniteLoadSentinel } from "@/composables/useInfiniteLoadSentinel";
import { galleryScrollContainerRefKey } from "@/injectionKeys";
import type { FileNode, UnifiedSearchResult } from "@/types";
import { normalizeAssetType } from "@/utils/assetType";
import SearchFeedback from "./SearchFeedback.vue";
import SearchResultMetadata from "./SearchResultMetadata.vue";

interface Props {
  albums: UnifiedSearchResult[];
  media: UnifiedSearchResult[];
  fallbackFolders: FileNode[];
  isMobile: boolean;
  isTablet: boolean;
  columnCount: number;
  rowHeight: number;
  initialPending: boolean;
  blockingError: boolean;
  staleError: boolean;
  paginationError: boolean;
  successfulEmpty: boolean;
  errorMessage?: string;
  hasNextPage: boolean;
  fetchingNextPage: boolean;
  showAllIndexedHint: boolean;
}

const props = withDefaults(defineProps<Props>(), { errorMessage: "Unable to load search results." });
const emit = defineEmits<{
  openFolder: [path: string];
  openMedia: [result: UnifiedSearchResult];
  dimensions: [dimensions: { path: string; width: number; height: number }];
  retry: [];
  retryNext: [];
  clear: [];
  loadMore: [];
}>();

const DESKTOP_ALBUM_WIDTH = 240;
const TABLET_ALBUM_WIDTH = 180;
const injectedScrollContainerRef = inject(galleryScrollContainerRefKey, null);
const scrollParentRef = shallowRef<HTMLElement | null>(null);
const scrollContentWidth = shallowRef(0);

function resolveElement(target: Element | ComponentPublicInstance | null) {
  if (!target) return null;
  return target instanceof HTMLElement
    ? target
    : "$el" in target && target.$el instanceof HTMLElement
      ? target.$el
      : null;
}

function setScrollContainer(target: Element | ComponentPublicInstance | null) {
  const element = resolveElement(target);
  scrollParentRef.value = element;
  if (injectedScrollContainerRef) injectedScrollContainerRef.value = element;
  updateWidth(element);
}

function updateWidth(element: HTMLElement | null) {
  if (!element) {
    scrollContentWidth.value = 0;
    return;
  }
  const style = window.getComputedStyle(element);
  scrollContentWidth.value =
    element.clientWidth - Number.parseFloat(style.paddingLeft || "0") - Number.parseFloat(style.paddingRight || "0");
}

useResizeObserver(scrollParentRef, ([entry]) => {
  updateWidth(entry?.target instanceof HTMLElement ? entry.target : scrollParentRef.value);
});

const normalizePath = (path: string) => path.trim().replace(/\\/g, "/").replace(/\/+/g, "/").replace(/\/$/, "");

const toFileNode = (result: UnifiedSearchResult): FileNode => ({
  name: result.name,
  path: result.path,
  type: normalizeAssetType(result.type),
  has_children: false,
  cover_images: result.cover_images ?? [],
  image_count: result.image_count ?? 0,
  mtime: result.mtime,
  width: result.width ?? undefined,
  height: result.height ?? undefined,
  duration_ms: result.duration_ms,
  mime_type: result.mime_type,
});

const albumNodes = computed(() =>
  props.albums.map((album) => {
    const node = toFileNode(album);
    if (!node.cover_images?.length) {
      const fallback = props.fallbackFolders.find((folder) => normalizePath(folder.path) === normalizePath(album.path));
      if (fallback?.cover_images?.length) {
        node.cover_images = fallback.cover_images;
        node.image_count ||= fallback.image_count;
      }
    }
    return node;
  }),
);

const albumCardComponent = computed(() =>
  props.isMobile ? AlbumCardMobile : props.isTablet ? AlbumCardTablet : AlbumCard,
);
const albumColumns = computed(() => {
  if (props.isMobile) return 2;
  const width = props.isTablet ? TABLET_ALBUM_WIDTH : DESKTOP_ALBUM_WIDTH;
  const gap = props.isTablet ? 12 : 20;
  const maxColumns = props.isTablet ? 3 : 5;
  return Math.max(
    1,
    Math.min(maxColumns, Math.floor((Math.max(0, scrollContentWidth.value - 16) + gap) / (width + gap))),
  );
});
const albumGap = computed(() => (props.isMobile ? 8 : props.isTablet ? 12 : 20));
const albumTemplate = computed(() =>
  props.isMobile
    ? `repeat(${albumColumns.value}, minmax(0, 1fr))`
    : `repeat(${albumColumns.value}, ${props.isTablet ? TABLET_ALBUM_WIDTH : DESKTOP_ALBUM_WIDTH}px)`,
);

type SearchSection = "albums" | "media";
type SearchRow =
  | { id: string; kind: "header"; section: SearchSection; count: number }
  | { id: string; kind: "albums"; items: FileNode[] }
  | { id: string; kind: "media"; items: UnifiedSearchResult[] };

const rows = computed<SearchRow[]>(() => {
  const result: SearchRow[] = [];
  if (props.albums.length) {
    result.push({ id: "header-albums", kind: "header", section: "albums", count: props.albums.length });
    chunkItems(albumNodes.value, albumColumns.value).forEach((items, index) => {
      result.push({ id: `albums-${albumColumns.value}-${index}`, kind: "albums", items });
    });
  }
  if (props.media.length) {
    result.push({ id: "header-media", kind: "header", section: "media", count: props.media.length });
    chunkItems(props.media, props.columnCount).forEach((items, index) => {
      result.push({ id: `media-${props.columnCount}-${index}`, kind: "media", items });
    });
  }
  return result;
});

const estimateRowSize = (index: number) => {
  const row = rows.value[index];
  if (!row) return props.rowHeight || 220;
  if (row.kind === "header") return 48;
  if (row.kind === "albums") return props.isMobile ? 230 : props.isTablet ? 226 : 280;
  return (props.rowHeight || 220) + 132;
};

const virtualGrid = useVirtualGridRows({
  rows,
  scrollElement: scrollParentRef,
  estimateSize: estimateRowSize,
  overscan: 5,
  measureDeps: [computed(() => props.rowHeight), computed(() => props.columnCount), albumColumns, albumTemplate],
});
const virtualItems = virtualGrid.virtualItems;
const virtualSpacerStyle = virtualGrid.virtualSpacerStyle;

const loadMoreSentinel = useTemplateRef<HTMLElement>("loadMoreSentinel");
const canLoadMore = computed(() => props.hasNextPage && !props.fetchingNextPage && !props.paginationError);
useInfiniteLoadSentinel({
  sentinel: loadMoreSentinel,
  enabled: canLoadMore,
  loadMore: () => emit("loadMore"),
  rootMargin: "500px",
});

const hasResults = computed(() => props.albums.length > 0 || props.media.length > 0);
const showEmpty = computed(() => props.successfulEmpty && !hasResults.value);
const resultKey = (result: UnifiedSearchResult) =>
  result.library_id !== undefined && result.asset_id !== undefined
    ? `${result.library_id}:${result.asset_id}`
    : result.path;

const displayFolder = (result: UnifiedSearchResult) => {
  const normalized = normalizePath(result.relative_path);
  const parts = normalized.split("/").filter(Boolean);
  if (parts.at(-1) === result.name) parts.pop();
  return parts.join("/") || normalizePath(result.parent_path);
};
</script>

<template>
  <SearchFeedback v-if="initialPending" state="pending" :column-count="columnCount" />
  <SearchFeedback v-else-if="blockingError" state="blocking-error" :message="errorMessage" @retry="emit('retry')" />
  <SearchFeedback
    v-else-if="showEmpty"
    state="empty"
    :show-all-indexed-hint="showAllIndexedHint"
    @clear="emit('clear')"
  />

  <div v-else :ref="setScrollContainer" class="search-results-panel">
    <SearchFeedback v-if="staleError" state="stale-warning" :message="errorMessage" @retry="emit('retry')" />

    <div class="search-sort-context" aria-label="Search results sorted by relevance">Sorted by Relevance</div>

    <div v-if="rows.length" class="search-virtual-spacer" :style="virtualSpacerStyle">
      <template v-for="virtualRow in virtualItems" :key="String(virtualRow.key)">
        <template v-for="row in [rows[virtualRow.index]]" :key="row?.id ?? String(virtualRow.key)">
          <div
            v-if="row?.kind === 'header'"
            class="search-row search-row-header"
            :style="virtualGrid.getVirtualRowStyle(virtualRow.start)"
          >
            <GallerySectionHeader
              :title="row.section === 'albums' ? 'Album suggestions' : 'Media'"
              :count="row.count"
              :badge-icon="row.section === 'albums' ? FolderOpen : Images"
            />
          </div>

          <div
            v-else-if="row?.kind === 'albums'"
            class="search-row search-album-grid"
            :style="
              virtualGrid.getVirtualRowStyle(virtualRow.start, {
                gap: `${albumGap}px`,
                gridTemplateColumns: albumTemplate,
              })
            "
          >
            <component
              :is="albumCardComponent"
              v-for="album in row.items"
              :key="album.path"
              :node="album"
              @click="emit('openFolder', album.path)"
            />
          </div>

          <div
            v-else-if="row?.kind === 'media'"
            class="search-row search-media-grid"
            :style="
              virtualGrid.getVirtualRowStyle(virtualRow.start, { gridTemplateColumns: `repeat(${columnCount}, 1fr)` })
            "
          >
            <article v-for="item in row.items" :key="resultKey(item)" class="search-result-card">
              <VideoCard
                v-if="normalizeAssetType(item.type) === 'video'"
                :src="item.path"
                :name="item.name"
                :duration-ms="item.duration_ms"
                @click="emit('openMedia', item)"
              />
              <PhotoCard
                v-else
                :src="item.path"
                :name="item.name"
                @dimensions="emit('dimensions', $event)"
                @click="emit('openMedia', item)"
                @keydown.enter="emit('openMedia', item)"
                @keydown.space.prevent="emit('openMedia', item)"
              />
              <OverflowTooltip :text="item.name" class="search-result-name">{{ item.name }}</OverflowTooltip>
              <OverflowTooltip v-if="displayFolder(item)" :text="displayFolder(item)" class="search-result-path">
                <Folder />
                <span>{{ displayFolder(item) }}</span>
              </OverflowTooltip>
              <SearchResultMetadata :result="item" />
            </article>
          </div>
        </template>
      </template>
    </div>

    <div ref="loadMoreSentinel" class="search-load-more-sentinel">
      <span v-if="fetchingNextPage">Loading more…</span>
    </div>
    <SearchFeedback
      v-if="paginationError"
      state="pagination-error"
      :message="errorMessage"
      @retry="emit('retryNext')"
    />
  </div>
</template>

<style scoped>
.search-results-panel {
  height: 100%;
  min-height: 0;
  flex: 1;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 0 14px 0 10px;
  scrollbar-width: thin;
}

.search-sort-context {
  margin: 0 8px 4px;
  color: var(--muted-foreground);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.search-row {
  contain: layout style;
}

.search-row-header {
  padding: 10px 8px 0;
}

.search-album-grid,
.search-media-grid {
  display: grid;
  padding: 0 8px;
}

.search-media-grid {
  gap: 20px;
}

.search-result-card {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
}

.search-result-name {
  display: block;
  min-width: 0;
  overflow: hidden;
  color: var(--foreground);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-result-path {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 4px;
  overflow: hidden;
  color: var(--muted-foreground);
  font-size: 11px;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-result-path svg {
  width: 12px;
  height: 12px;
  flex: 0 0 auto;
}

.search-load-more-sentinel {
  display: flex;
  min-height: 32px;
  align-items: center;
  justify-content: center;
  color: var(--muted-foreground);
  font-size: 13px;
}

@media (max-width: 1199px) {
  .search-results-panel {
    padding-inline: 8px;
  }

  .search-media-grid {
    gap: 10px;
  }
}

@media (max-width: 767px) {
  .search-results-panel {
    padding-inline: 4px;
  }

  .search-media-grid {
    gap: 8px;
  }

  .search-result-name {
    font-size: 12px;
  }
}
</style>
