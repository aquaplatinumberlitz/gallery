<script setup lang="ts">
import { computed, inject, onMounted, ref } from "vue";
import {
  Landmark,
  Settings,
  Loader2,
  Menu,
  Sun,
  Moon,
  SlidersHorizontal,
  Table2,
  Library,
  Wrench,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  ChevronDown,
  LayoutGrid,
} from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import Badge from "@/components/ui/Badge.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import Breadcrumb from "@/components/Breadcrumb.vue";
import SortSelect from "@/components/SortSelect.vue";
import HeaderSearchBox from "@/components/HeaderSearchBox.vue";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useGalleryTheme } from "@/composables/useGalleryTheme";
import { useFieldedSearch } from "@/composables/useFieldedSearch";
import { useColumnResize, PHOTO_GRID_LEVELS, GRID_COLUMN_MAP } from "@/composables/useColumnResize";
import AdvancedSearchDrawer from "@/components/search/AdvancedSearchDrawer.vue";
import SearchScopeSelect from "@/components/SearchScopeSelect.vue";
import SearchFilterChips from "@/components/SearchFilterChips.vue";
import type { FieldFilter, SortValue } from "@/types";
import { parseFieldedQuery, serializeAdvancedSearchToQuery } from "@/utils/serializeAdvancedSearchToQuery";
import { prefetchLibrariesRoute, prefetchMetadataRoute } from "@/router";
import { useGalleryStore } from "@/stores/gallery";
import { queryClient } from "@/query";
import { normalizeQueryPath, queryKeys } from "@/query/keys";
import { fetchLibraryInspector } from "@/services/api";
import { useRouteChrome } from "@/composables/useRouteChrome";
import { galleryScrollContainerRefKey } from "@/injectionKeys";
import { useCollapsibleHeader } from "@/composables/useCollapsibleHeader";
import { useInfiniteBrowseQuery } from "@/composables/useInfiniteBrowseQuery";

interface Props {
  isMobile: boolean;
  isSidebarOpen: boolean;
  isDark: boolean;
  searchQuery: string;
  searchScope: "current" | "all";
  searchLoading: boolean;
}
const props = defineProps<Props>();

const emit = defineEmits<{
  "update:searchQuery": [value: string];
  "scope-change": [value: "current" | "all"];
  "toggle-sidebar": [];
  "toggle-theme": [];
  "open-settings": [];
}>();

const { resolvedTheme, toggleTheme } = useGalleryTheme();
const {
  fieldedFilters,
  isActive: isFieldedSearchActive,
  queryString: fieldedQueryString,
  applyFilters,
  removeFilter,
  clearAll,
} = useFieldedSearch();
const galleryStore = useGalleryStore();
const { activeNav, isMetadataRoute, isAdminRoute, showBackToGallery } = useRouteChrome();
const isLibrariesRoute = computed(() => activeNav.value === "libraries");
const isMaintenanceRoute = computed(() => activeNav.value === "maintenance");
const showGalleryHeader = computed(() => !isMetadataRoute.value && !isAdminRoute.value);

const isAdvancedSearchOpen = ref(false);
const advancedSearchInitialFilters = ref<FieldFilter[]>([]);
let metadataDataPrefetchStarted = false;

const injectedScrollContainerRef = inject(galleryScrollContainerRefKey, null);
const { isHeaderCollapsed } = useCollapsibleHeader(injectedScrollContainerRef, { enabled: showGalleryHeader });

const activeLibraryId = computed(() => (showGalleryHeader.value ? galleryStore.activeLibraryId : null));
const activeBrowsePath = computed(() => galleryStore.currentBrowsePath || null);
const infiniteBrowseQuery = useInfiniteBrowseQuery(activeLibraryId, activeBrowsePath);
const currentPath = computed(() => galleryStore.currentBrowsePath);
const activeImportRootPath = computed(() => galleryStore.activeImportRootPath);
const canBack = computed(() => galleryStore.historyIndex > 0);
const canForward = computed(() => galleryStore.historyIndex < galleryStore.history.length - 1);
const isBrowseLoading = computed(() => showGalleryHeader.value && infiniteBrowseQuery.isLoading.value);
const isBrowseRefetching = computed(
  () =>
    showGalleryHeader.value &&
    infiniteBrowseQuery.isFetching.value &&
    !infiniteBrowseQuery.isLoading.value &&
    !infiniteBrowseQuery.isFetchingNextPage.value,
);
const compactBreadcrumbMaxVisible = computed(() => (isHeaderCollapsed.value ? 2 : 4));
const gallerySortValue = computed<SortValue>({
  get() {
    return `${galleryStore.sortField === "name" ? "name" : "date"}_${galleryStore.sortOrder}` as SortValue;
  },
  set(value) {
    const [field, order] = value.split("_") as ["date" | "name", "asc" | "desc"];
    galleryStore.setSortField(field);
    galleryStore.setSortOrder(order);
  },
});
const { sliderLevel } = useColumnResize("desktop");

const densityOptions = computed(() =>
  [...PHOTO_GRID_LEVELS]
    .map((option, index) => ({ ...option, columns: GRID_COLUMN_MAP.desktop[index] }))
    .sort((a, b) => a.columns - b.columns),
);

function selectDensity(level: number) {
  sliderLevel.value = level;
}

function goBack() {
  galleryStore.goBack();
}

function goForward() {
  galleryStore.goForward();
}

function handleOpenFolder(path: string) {
  galleryStore.selectFolder(path);
  galleryStore.clearSearch();
}

function openFolder() {
  galleryStore.openInExplorer();
}

function requestIdle(callback: () => void) {
  if (typeof window === "undefined") return;
  const idleCallback =
    "requestIdleCallback" in window
      ? window.requestIdleCallback
      : (cb: IdleRequestCallback) =>
          window.setTimeout(() => cb({ didTimeout: false, timeRemaining: () => 0 } as IdleDeadline), 800);
  idleCallback(() => callback());
}

function prefetchMetadataData() {
  if (metadataDataPrefetchStarted || isMetadataRoute.value) return;
  metadataDataPrefetchStarted = true;

  const state = galleryStore.metadataInspector;
  const requestScope = state.scope;
  const requestPath = requestScope === "current" ? normalizeQueryPath(galleryStore.currentBrowsePath || "") : "";
  const requestLimit = 100;
  const requestSort = state.sort;
  const requestQuery = state.query.trim();

  void queryClient.prefetchQuery({
    queryKey: queryKeys.libraryInspector(requestQuery, requestScope, requestPath, requestLimit, requestSort),
    queryFn: () =>
      fetchLibraryInspector({
        q: requestQuery,
        scope: requestScope,
        path: requestPath,
        limit: requestLimit,
        sort: requestSort,
      }),
    staleTime: 15_000,
  });
}

function prefetchMetadataResources() {
  void prefetchMetadataRoute();
  prefetchMetadataData();
}

onMounted(() => {
  requestIdle(() => {
    if (!isMetadataRoute.value) void prefetchMetadataRoute();
  });
});

function getFilterFieldKey(filter: FieldFilter) {
  return filter.field.toLowerCase();
}

function getAdvancedSearchInitialFilters() {
  const parsedFilters = parseFieldedQuery(props.searchQuery);

  if (parsedFilters.length === 0) {
    return [...fieldedFilters.value];
  }

  const mergedByField = new Map<string, FieldFilter>();
  for (const filter of parsedFilters) {
    mergedByField.set(getFilterFieldKey(filter), filter);
  }
  for (const filter of fieldedFilters.value) {
    mergedByField.set(getFilterFieldKey(filter), filter);
  }
  return Array.from(mergedByField.values());
}

function openAdvancedSearch() {
  advancedSearchInitialFilters.value = getAdvancedSearchInitialFilters();
  isAdvancedSearchOpen.value = true;
}

function clearSearch() {
  clearAll();
  emit("update:searchQuery", "");
}

function submitSearch() {
  galleryStore.submitSearch();
}

function handleAdvancedSearchApply(filters: FieldFilter[]) {
  applyFilters(filters);
  emit("update:searchQuery", serializeAdvancedSearchToQuery(filters));
}

function handleAdvancedSearchClose() {
  isAdvancedSearchOpen.value = false;
}

function handleRemoveFilter(index: number) {
  removeFilter(index);
  emit("update:searchQuery", fieldedQueryString.value);
}

function handleClearAll() {
  clearAll();
  emit("update:searchQuery", "");
}
</script>

<template>
  <header
    role="banner"
    class="content-header gallery-header"
    :class="{
      'is-gallery-header': showGalleryHeader,
      'is-collapsed': isHeaderCollapsed,
      'is-expanded': !isHeaderCollapsed,
    }"
  >
    <template v-if="showGalleryHeader">
      <div class="expanded-header" :aria-hidden="isHeaderCollapsed" :inert="isHeaderCollapsed">
        <div class="expanded-primary">
          <div class="header-left flex items-center gap-3">
            <Tooltip>
              <TooltipTrigger as-child>
                <Button
                  v-if="!isMobile"
                  variant="ghost"
                  size="icon"
                  class="hamburger-btn"
                  aria-label="Toggle sidebar"
                  @click="emit('toggle-sidebar')"
                >
                  <Menu class="gallery-icon-toolbar" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Toggle sidebar</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger as-child>
                <Button
                  variant="ghost"
                  size="icon"
                  class="settings-btn"
                  aria-label="Change Intro Page"
                  @click="emit('open-settings')"
                >
                  <Settings class="gallery-icon-toolbar" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Change Intro Page</TooltipContent>
            </Tooltip>
          </div>

          <div class="brand-hero flex items-center justify-center gap-3 text-center">
            <div class="brand-icon flicker-effect">
              <Landmark :size="40" />
            </div>
            <div class="brand-text text-left">
              <p class="eyebrow">Local collections</p>
              <h1 class="brand-title">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 640 640"
                  width="18"
                  height="18"
                  class="title-sparkle"
                >
                  <path
                    fill="currentColor"
                    d="M480 96L512 24L544 96L616 128L544 160L512 232L480 160L408 128L480 96zM160 256L224 112L288 256L432 320L288 384L224 528L160 384L16 320L160 256zM480 408L512 480L584 512L512 544L480 616L448 544L376 512L448 480L480 408z"
                  />
                </svg>
                Museum Art Gallery
              </h1>
            </div>
          </div>

          <div class="header-actions flex flex-col items-end gap-2">
            <div class="flex items-center gap-2">
              <ButtonLink
                to="/admin/libraries"
                :variant="isLibrariesRoute ? 'secondary' : 'ghost'"
                size="sm"
                :aria-current="isLibrariesRoute ? 'page' : undefined"
                class="h-8 text-xs"
                @pointerenter="prefetchLibrariesRoute"
                @focus="prefetchLibrariesRoute"
              >
                <Library class="size-4" />
                <span>Libraries</span>
              </ButtonLink>
              <ButtonLink
                v-if="!isMobile"
                to="/metadata"
                :variant="isMetadataRoute ? 'secondary' : 'ghost'"
                size="sm"
                :aria-current="isMetadataRoute ? 'page' : undefined"
                class="metadata-link h-8 text-xs"
                @pointerenter="prefetchMetadataResources"
                @focus="prefetchMetadataResources"
              >
                <Table2 class="size-4" />
                <span>Metadata</span>
              </ButtonLink>
              <ButtonLink
                v-if="!isMobile"
                to="/admin/maintenance"
                :variant="isMaintenanceRoute ? 'secondary' : 'ghost'"
                size="sm"
                :aria-current="isMaintenanceRoute ? 'page' : undefined"
                class="h-8 text-xs"
              >
                <Wrench class="size-4" />
                <span>Maintenance</span>
              </ButtonLink>
              <Tooltip>
                <TooltipTrigger as-child>
                  <button
                    type="button"
                    class="theme-pill-toggle"
                    :class="{ 'is-dark': resolvedTheme === 'dark' }"
                    :aria-label="resolvedTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
                    @click="toggleTheme"
                  >
                    <span class="theme-pill-thumb" aria-hidden="true">
                      <Sun class="theme-pill-icon theme-pill-icon-sun" />
                      <Moon class="theme-pill-icon theme-pill-icon-moon" />
                    </span>
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  {{ resolvedTheme === "dark" ? "Switch to light mode" : "Switch to dark mode" }}
                </TooltipContent>
              </Tooltip>
            </div>

            <div class="header-search-area">
              <HeaderSearchBox
                id="gallery-search"
                :model-value="searchQuery"
                :loading="searchLoading"
                placeholder="Photos, albums, prompts"
                @update:model-value="emit('update:searchQuery', $event)"
                @submit="submitSearch"
                @clear="clearSearch"
              >
                <template #actions>
                  <SearchScopeSelect :model-value="searchScope" @update:model-value="emit('scope-change', $event)" />
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <Button
                        variant="ghost"
                        size="icon"
                        class="advanced-search-btn search-action-btn size-7 p-0"
                        type="button"
                        :class="{ 'text-primary': isFieldedSearchActive }"
                        aria-label="Advanced Search"
                        @click="openAdvancedSearch"
                      >
                        <SlidersHorizontal class="gallery-icon-toolbar" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Advanced Search</TooltipContent>
                  </Tooltip>
                </template>
              </HeaderSearchBox>
              <SearchFilterChips :filters="fieldedFilters" @remove="handleRemoveFilter" @clear-all="handleClearAll" />
            </div>
          </div>
        </div>

        <div class="gallery-toolbar expanded-gallery-toolbar">
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
            trigger-class="sort-trigger h-8 w-[74px] gap-1.5 px-2 py-0 text-xs font-normal shadow-none"
          />

          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button
                variant="outline"
                type="button"
                class="gallery-density-trigger h-8 w-[74px] justify-between gap-1.5 px-2 text-xs font-normal text-foreground shadow-none"
                aria-label="View density"
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
            v-if="isBrowseLoading || isBrowseRefetching"
            variant="loading"
            :class="{ 'opacity-70': isBrowseRefetching && !isBrowseLoading }"
            class="loading-badge"
          >
            <Loader2 class="gallery-icon-md search-leading-loading" />
            <span>{{ isBrowseRefetching && !isBrowseLoading ? "Refreshing" : "Loading" }}</span>
          </Badge>
        </div>
      </div>

      <div class="compact-header" :aria-hidden="!isHeaderCollapsed" :inert="!isHeaderCollapsed">
        <div class="nav-group inline-flex items-center gap-2">
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                variant="ghost"
                size="icon-sm"
                class="nav-btn compact-back-btn"
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
                class="nav-btn compact-forward-btn"
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
          class="breadcrumb-wrap compact-breadcrumb"
          :path="currentPath"
          :root-path="activeImportRootPath"
          :max-visible="compactBreadcrumbMaxVisible"
          @navigate="handleOpenFolder"
        />

        <div class="compact-controls">
          <HeaderSearchBox
            id="gallery-search-compact"
            class="compact-search-box"
            compact
            :model-value="searchQuery"
            :loading="searchLoading"
            placeholder="Search"
            @update:model-value="emit('update:searchQuery', $event)"
            @submit="submitSearch"
            @clear="clearSearch"
          />

          <SortSelect
            v-model="gallerySortValue"
            aria-label="Sort gallery"
            trigger-label="Sort"
            trigger-class="sort-trigger h-8 w-[74px] gap-1.5 px-2 py-0 text-xs font-normal shadow-none"
          />

          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button
                variant="outline"
                type="button"
                class="gallery-density-trigger h-8 w-[74px] justify-between gap-1.5 px-2 text-xs font-normal text-foreground shadow-none"
                aria-label="View density"
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
            v-if="isBrowseLoading || isBrowseRefetching"
            variant="loading"
            :class="{ 'opacity-70': isBrowseRefetching && !isBrowseLoading }"
            class="loading-badge compact-loading-badge"
          >
            <Loader2 class="gallery-icon-md search-leading-loading" />
            <span>{{ isBrowseRefetching && !isBrowseLoading ? "Refreshing" : "Loading" }}</span>
          </Badge>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="header-left flex items-center gap-3">
        <Tooltip>
          <TooltipTrigger as-child>
            <Button
              v-if="!isMobile"
              variant="ghost"
              size="icon"
              class="hamburger-btn"
              aria-label="Toggle sidebar"
              @click="emit('toggle-sidebar')"
            >
              <Menu class="gallery-icon-toolbar" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Toggle sidebar</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger as-child>
            <Button
              variant="ghost"
              size="icon"
              class="settings-btn"
              aria-label="Change Intro Page"
              @click="emit('open-settings')"
            >
              <Settings class="gallery-icon-toolbar" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Change Intro Page</TooltipContent>
        </Tooltip>
      </div>

      <div class="header-actions flex flex-col items-end gap-2">
        <div class="flex items-center gap-2">
          <ButtonLink
            v-if="showBackToGallery"
            to="/"
            variant="ghost"
            size="sm"
            class="h-8 text-xs"
            aria-label="Back to gallery"
          >
            <ArrowLeft class="size-4" />
            <span>Gallery</span>
          </ButtonLink>
          <ButtonLink
            to="/admin/libraries"
            :variant="isLibrariesRoute ? 'secondary' : 'ghost'"
            size="sm"
            :aria-current="isLibrariesRoute ? 'page' : undefined"
            class="h-8 text-xs"
            @pointerenter="prefetchLibrariesRoute"
            @focus="prefetchLibrariesRoute"
          >
            <Library class="size-4" />
            <span>Libraries</span>
          </ButtonLink>
          <ButtonLink
            v-if="!isMobile"
            to="/metadata"
            :variant="isMetadataRoute ? 'secondary' : 'ghost'"
            size="sm"
            :aria-current="isMetadataRoute ? 'page' : undefined"
            class="metadata-link h-8 text-xs"
            @pointerenter="prefetchMetadataResources"
            @focus="prefetchMetadataResources"
          >
            <Table2 class="size-4" />
            <span>Metadata</span>
          </ButtonLink>
          <ButtonLink
            v-if="!isMobile"
            to="/admin/maintenance"
            :variant="isMaintenanceRoute ? 'secondary' : 'ghost'"
            size="sm"
            :aria-current="isMaintenanceRoute ? 'page' : undefined"
            class="h-8 text-xs"
          >
            <Wrench class="size-4" />
            <span>Maintenance</span>
          </ButtonLink>
          <Tooltip>
            <TooltipTrigger as-child>
              <button
                type="button"
                class="theme-pill-toggle"
                :class="{ 'is-dark': resolvedTheme === 'dark' }"
                :aria-label="resolvedTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
                @click="toggleTheme"
              >
                <span class="theme-pill-thumb" aria-hidden="true">
                  <Sun class="theme-pill-icon theme-pill-icon-sun" />
                  <Moon class="theme-pill-icon theme-pill-icon-moon" />
                </span>
              </button>
            </TooltipTrigger>
            <TooltipContent>
              {{ resolvedTheme === "dark" ? "Switch to light mode" : "Switch to dark mode" }}
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
    </template>

    <AdvancedSearchDrawer
      :is-open="isAdvancedSearchOpen"
      :initial-filters="advancedSearchInitialFilters"
      @close="handleAdvancedSearchClose"
      @apply="handleAdvancedSearchApply"
    />
  </header>
</template>

<style scoped lang="scss">
/* brand-hero, header-left, header-actions, content-header layout handled by Tailwind utilities */
/* Only visual effects, animations, and responsive overrides remain */

.gallery-header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: 12px;
  flex-shrink: 0;
}

.gallery-header.is-gallery-header {
  display: block;
  container: gallery-header / inline-size;
  overflow: hidden;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 78%, transparent);
  background: color-mix(in srgb, var(--background) 80%, transparent);
  box-shadow: 0 2px 8px color-mix(in srgb, black 5%, transparent);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  transition:
    min-height 200ms cubic-bezier(0.22, 1, 0.36, 1),
    background-color 200ms cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 200ms cubic-bezier(0.22, 1, 0.36, 1);
}

.gallery-header.is-gallery-header.is-expanded {
  min-height: 130px;
}

.gallery-header.is-gallery-header.is-collapsed {
  min-height: 54px;
}

.expanded-header {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 180px;
  overflow: hidden;
  opacity: 1;
  transform: translateY(0);
  transition:
    max-height 200ms cubic-bezier(0.22, 1, 0.36, 1),
    opacity 180ms ease,
    transform 200ms cubic-bezier(0.22, 1, 0.36, 1);
}

.is-collapsed .expanded-header {
  max-height: 0;
  opacity: 0;
  pointer-events: none;
  transform: translateY(-8px);
}

.expanded-primary {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: 12px;
}

.compact-header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
  width: 100%;
  height: 0;
  max-height: 0;
  opacity: 0;
  overflow: hidden;
  pointer-events: none;
  transform: translateY(8px);
  transition:
    height 200ms cubic-bezier(0.22, 1, 0.36, 1),
    max-height 200ms cubic-bezier(0.22, 1, 0.36, 1),
    opacity 180ms ease,
    transform 200ms cubic-bezier(0.22, 1, 0.36, 1);
}

.is-collapsed .compact-header {
  height: 54px;
  max-height: 56px;
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}

.gallery-toolbar {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.breadcrumb-wrap {
  justify-self: start;
  width: fit-content;
  min-width: 0;
  max-width: 100%;
}

.compact-breadcrumb {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.compact-controls {
  display: grid;
  grid-template-columns: minmax(140px, 220px) auto auto auto;
  align-items: center;
  justify-self: end;
  gap: 8px;
  min-width: 0;
}

.compact-header :deep(.sort-trigger),
.compact-header :where(.gallery-density-trigger) {
  flex: 0 0 auto;
}

.loading-badge {
  justify-self: end;
  white-space: nowrap;
}

.compact-loading-badge {
  max-width: 112px;
}

.gallery-icon-md {
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}

@container gallery-header (max-width: 980px) {
  .compact-controls {
    grid-template-columns: minmax(140px, 180px) auto auto auto;
  }
}

@container gallery-header (max-width: 860px) {
  .compact-header {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .compact-breadcrumb {
    display: none;
  }
}

/* Hamburger: hidden on desktop, shown on tablet/mobile */
.hamburger-btn {
  display: none;
}

.eyebrow {
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 12px;
  color: var(--brand-hero-text);
}

h1 {
  margin: 4px 0 0 0;
  font-size: clamp(22px, 3vw, 30px);
  color: var(--foreground);
}

.theme-pill-toggle {
  position: relative;
  width: 56px;
  height: 32px;
  border: 2px solid #e8d5b7;
  background: #fef3c7;
  padding: 0;
  border-radius: 999px;
  cursor: pointer;
  transition:
    border-color 240ms cubic-bezier(0.22, 1, 0.36, 1),
    background-color 240ms cubic-bezier(0.22, 1, 0.36, 1),
    transform 160ms ease;
}

.theme-pill-toggle.is-dark {
  border-color: #2d2a4e;
  background: #1a1838;
}

.theme-pill-toggle:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ring) 50%, transparent);
}

.theme-pill-toggle:hover {
  transform: translateY(-1px);
}

.theme-pill-toggle:active {
  transform: translateY(0) scale(0.98);
}

.theme-pill-thumb {
  position: absolute;
  top: 50%;
  left: 2px;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #ff9500;
  color: #fff;
  transform: translate3d(0, -50%, 0);
  transition:
    transform 240ms cubic-bezier(0.22, 1, 0.36, 1),
    background-color 240ms cubic-bezier(0.22, 1, 0.36, 1);
}

.theme-pill-toggle.is-dark .theme-pill-thumb {
  background: #e8e6f0;
  color: #1a1838;
  transform: translate3d(24px, -50%, 0);
}

.theme-pill-icon {
  grid-column: 1;
  grid-row: 1;
  display: block;
  width: 16px;
  height: 16px;
  transform-origin: center;
  transition:
    opacity 200ms cubic-bezier(0.22, 1, 0.36, 1),
    transform 200ms cubic-bezier(0.22, 1, 0.36, 1);
}

.theme-pill-icon-sun {
  opacity: 1;
  transform: rotate(0deg) scale(1);
}

.theme-pill-icon-moon {
  opacity: 0;
  transform: rotate(-90deg) scale(0.5);
}

.theme-pill-toggle.is-dark .theme-pill-icon-sun {
  opacity: 0;
  transform: rotate(90deg) scale(0.5);
}

.theme-pill-toggle.is-dark .theme-pill-icon-moon {
  opacity: 1;
  transform: rotate(0deg) scale(1);
}

@media (prefers-reduced-motion: reduce) {
  .gallery-header.is-gallery-header,
  .expanded-header,
  .compact-header {
    transition: none;
  }

  .theme-pill-toggle,
  .theme-pill-thumb,
  .theme-pill-icon {
    transition: none;
  }
}

.header-search-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-end;
}

.search-leading-loading {
  animation: searchLeadingSpin 1s linear infinite;
}

@keyframes searchLeadingSpin {
  to {
    transform: rotate(360deg);
  }
}

/* Icon sizes using design tokens */
.gallery-icon-toolbar {
  width: var(--gallery-icon-toolbar);
  height: var(--gallery-icon-toolbar);
}

/* brand-hero and brand-text layout handled by Tailwind utilities */
/* Keep hover effects and keyframes */

/* === Brand icon (visual effects, NOT layout) === */

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
  color: var(--brand-hero-text);
  border: 2px solid transparent; /* Viền trong suốt (giữ chỗ) */
  box-shadow: none; /* Không bóng */
  filter: none; /* Không phát sáng */
}

/* Dark mode styles được chuyển xuống <style> block riêng (không scoped) ở cuối file */

/* brand-text layout handled by Tailwind text-left */

/* Keyframes for hover effects only - main animation in main.scss */
@keyframes underline-grow {
  0% {
    transform: scaleX(0);
  }
  100% {
    transform: scaleX(1);
  }
}

@keyframes subtle-float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-2px);
  }
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
  color: var(--brand-hero-text);

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
  background: linear-gradient(90deg, transparent 0%, #c9a962 10%, #d4af37 50%, #c9a962 90%, transparent 100%);
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

/* Base state cho animation - chỉ để tắt trong light mode */
.brand-icon.flicker-effect {
  animation: none;
}

/* Import breakpoint mixins */
@import "../styles/breakpoints";

/* =============================================
   RESPONSIVE BREAKPOINTS
   ============================================= */

/* Tablet & below: 1199px */
@media (max-width: 1199px) {
  .brand-icon {
    width: 48px;
    height: 48px;
    margin-right: 10px;
  }

  .brand-title {
    font-size: clamp(22px, 4vw, 32px) !important;
  }
}

/* Tablet range (768-1199px) — sidebar 240px persistent + hamburger always visible, edge-toggle hidden */
@include tablet {
  .hamburger-btn {
    display: inline-flex;
  }

  .brand-hero {
    transform: scale(0.8);
    transform-origin: left center;
  }
}

/* Phone: <768px — sidebar becomes overlay, hamburger appears */
@media (max-width: 767px) {
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

  .theme-pill-toggle {
    display: none;
  }

  .settings-btn {
    display: none;
  }

  .brand-hero {
    display: none;
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

/* Compact: <480px — compact layout */
@media (max-width: 480px) {
  .content-header {
    padding: 4px 12px;
    min-height: 44px;
    gap: 4px;
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
}

@media (prefers-reduced-motion: reduce) {
  .search-leading-loading {
    animation: none;
  }
}
</style>
