<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  Landmark,
  Search,
  X,
  Settings,
  Menu,
  Sun,
  Moon,
  Monitor,
  SlidersHorizontal,
  Table2,
  Library,
} from "lucide-vue-next";
import { useRoute } from "vue-router";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import Input from "@/components/ui/Input.vue";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useGalleryTheme } from "@/composables/useGalleryTheme";
import { useFieldedSearch } from "@/composables/useFieldedSearch";
import AdvancedSearchDrawer from "@/components/search/AdvancedSearchDrawer.vue";
import SearchFilterChips from "@/components/SearchFilterChips.vue";
import type { FieldFilter } from "@/types";
import { parseFieldedQuery, serializeAdvancedSearchToQuery } from "@/utils/serializeAdvancedSearchToQuery";
import { prefetchLibrariesRoute, prefetchMetadataRoute } from "@/router";
import { useGalleryStore } from "@/stores/gallery";
import { queryClient } from "@/query";
import { normalizeQueryPath, queryKeys } from "@/query/keys";
import { fetchLibraryInspector } from "@/services/api";

interface Props {
  isMobile: boolean;
  isSidebarOpen: boolean;
  isDark: boolean;
  searchQuery: string;
  searchScope: "current" | "all";
}
const props = defineProps<Props>();

const emit = defineEmits<{
  "update:searchQuery": [value: string];
  "scope-change": [value: "current" | "all"];
  "toggle-sidebar": [];
  "toggle-theme": [];
  "open-settings": [];
}>();

const { mode, resolvedTheme, setTheme } = useGalleryTheme();
const {
  fieldedFilters,
  isActive: isFieldedSearchActive,
  queryString: fieldedQueryString,
  applyFilters,
  removeFilter,
  clearAll,
} = useFieldedSearch();
const route = useRoute();
const galleryStore = useGalleryStore();
const isMetadataRoute = computed(() => route.path === "/metadata");
const isLibrariesRoute = computed(() => route.path.startsWith("/admin/libraries"));

const isAdvancedSearchOpen = ref(false);
const advancedSearchInitialFilters = ref<FieldFilter[]>([]);
let metadataDataPrefetchStarted = false;

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
  const requestPath = requestScope === "current" ? normalizeQueryPath(galleryStore.currentPath || "") : "";
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

function onScopeChange(e: Event) {
  const target = e.target as HTMLSelectElement;
  emit("scope-change", target.value as "current" | "all");
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
  <header role="banner" class="content-header grid grid-cols-[auto_1fr_auto] items-start gap-3 shrink-0">
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
    <div
      v-if="!isMetadataRoute && !isLibrariesRoute"
      class="brand-hero flex items-center justify-center gap-3 text-center"
    >
      <div class="brand-icon flicker-effect">
        <Landmark :size="40" />
      </div>
      <div class="brand-text text-left">
        <p class="eyebrow">Local collections</p>
        <h1 class="brand-title">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="18" height="18" class="title-sparkle">
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
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="ghost" size="icon" aria-label="Theme">
              <Sun v-if="resolvedTheme === 'light'" class="size-4" />
              <Moon v-else class="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem @click="setTheme('light')" :class="{ 'bg-accent': mode === 'light' }">
              <Sun class="mr-2 size-4" /> Light
            </DropdownMenuItem>
            <DropdownMenuItem @click="setTheme('dark')" :class="{ 'bg-accent': mode === 'dark' }">
              <Moon class="mr-2 size-4" /> Dark
            </DropdownMenuItem>
            <DropdownMenuItem @click="setTheme('system')" :class="{ 'bg-accent': mode === 'system' }">
              <Monitor class="mr-2 size-4" /> System
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div v-if="!isMetadataRoute && !isLibrariesRoute" class="header-search-area">
        <div class="search-box">
          <Tooltip>
            <TooltipTrigger as-child>
              <Button variant="ghost" size="icon" class="search-icon-btn" type="button" aria-label="Search">
                <Search class="gallery-icon-toolbar" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Search</TooltipContent>
          </Tooltip>
          <Input
            id="gallery-search"
            :model-value="searchQuery"
            @update:model-value="(v: string) => emit('update:searchQuery', v)"
            type="search"
            placeholder="Photos, albums, prompts"
            autocomplete="off"
            class="search-input"
          />
          <Tooltip v-if="searchQuery">
            <TooltipTrigger as-child>
              <Button
                variant="ghost"
                size="icon"
                class="clear-btn"
                type="button"
                aria-label="Clear search"
                @click="clearSearch"
              >
                <X class="gallery-icon-xs" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Clear search</TooltipContent>
          </Tooltip>
          <select class="scope-select" :value="searchScope" aria-label="Search scope" @change="onScopeChange">
            <option value="current">This folder</option>
            <option value="all">All indexed</option>
          </select>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                variant="ghost"
                size="icon"
                class="advanced-search-btn"
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
        </div>
        <SearchFilterChips :filters="fieldedFilters" @remove="handleRemoveFilter" @clear-all="handleClearAll" />
      </div>
      <AdvancedSearchDrawer
        :is-open="isAdvancedSearchOpen"
        :initial-filters="advancedSearchInitialFilters"
        @close="handleAdvancedSearchClose"
        @apply="handleAdvancedSearchApply"
      />
    </div>
  </header>
</template>

<style scoped lang="scss">
/* brand-hero, header-left, header-actions, content-header layout handled by Tailwind utilities */
/* Only visual effects, animations, and responsive overrides remain */

/* Hamburger: hidden on desktop, shown on tablet/mobile */
.hamburger-btn {
  display: none;
}

/* Search box container (visual shell - border, background, rounded, padding) */
/* Input and clear-btn styling handled by shadcn components */

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
  background: var(--card);
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
  gap: 6px;
  min-width: 220px;
  height: 40px;
}

.header-search-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-end;
}

.advanced-search-btn {
  flex-shrink: 0;
}

.search-input {
  min-width: 0;
}

.search-icon-btn,
.clear-btn {
  flex-shrink: 0;
}

/* Input and clear-btn styling handled by shadcn Button variant="ghost" size="icon" */
/* Only responsive rules remain */

.scope-select {
  border: 1px solid color-mix(in srgb, var(--border) 55%, transparent);
  background: color-mix(in srgb, var(--muted-foreground) 4%, var(--card));
  color: var(--muted-foreground);
  border-radius: 999px;
  height: 28px;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  outline: none;
}

/* Icon sizes using design tokens */
.gallery-icon-toolbar {
  width: var(--gallery-icon-toolbar);
  height: var(--gallery-icon-toolbar);
}
.gallery-icon-xs {
  width: var(--gallery-icon-xs);
  height: var(--gallery-icon-xs);
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

  .search-box {
    min-width: 180px;
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
    background: var(--card);
    transition:
      border-color 0.2s,
      box-shadow 0.2s;
  }

  .search-box:hover {
    border-color: var(--primary);
    box-shadow: 0 4px 12px color-mix(in srgb, var(--ring) 25%, transparent);
  }

  .search-box:focus-within {
    border-color: var(--primary);
    box-shadow: 0 4px 12px color-mix(in srgb, var(--ring) 25%, transparent);
  }

  .search-box input {
    flex: 1;
    border: none;
    background: transparent;
    padding: 0;
    font-size: 14px;
    color: var(--foreground);
    outline: none;
    min-width: 0;
  }

  .search-box input::placeholder {
    color: var(--muted-foreground);
  }

  .search-box .clear-btn {
    background: transparent;
    border: none;
    color: var(--muted-foreground);
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
    color: var(--foreground);
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
}
</style>
