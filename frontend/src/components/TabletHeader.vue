<script setup lang="ts">
import { ref, nextTick, onBeforeUnmount, watch, computed } from "vue";
import { Menu, Search, X, ArrowLeft, Library, Loader2, SlidersHorizontal } from "lucide-vue-next";
import { RouterLink } from "vue-router";
import Breadcrumb from "./Breadcrumb.vue";
import SearchScopeSelect from "./SearchScopeSelect.vue";
import { useGalleryStore } from "../stores/gallery";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useRouteChrome } from "@/composables/useRouteChrome";
import { AnimatePresence, motion } from "motion-v";

interface Props {
  isDark: boolean;
  searchQuery: string;
  searchScope: "current" | "all";
  searchLoading: boolean;
  currentPath: string;
}
const props = defineProps<Props>();

const emit = defineEmits<{
  "toggle-sidebar": [];
  "toggle-theme": [];
  "update:searchQuery": [value: string];
  "scope-change": [value: "current" | "all"];
  "open-advanced-search": [];
}>();

const galleryStore = useGalleryStore();
const { pageTitle, showBackToGallery } = useRouteChrome();

const handleBreadcrumbNavigate = (path: string) => {
  galleryStore.selectFolder(path);
};

// ── Expandable search ──
const isSearchActive = ref(false);
const searchInputRef = ref<HTMLInputElement | null>(null);
const searchBtnRef = ref<HTMLButtonElement | null>(null);

const hasQuery = computed(() => props.searchQuery.length > 0);

function openSearch() {
  isSearchActive.value = true;
  nextTick(() => {
    searchInputRef.value?.focus();
  });
}

function closeSearch() {
  emit("update:searchQuery", "");
  isSearchActive.value = false;
  nextTick(() => {
    searchBtnRef.value?.focus();
  });
}

function clearSearch() {
  emit("update:searchQuery", "");
  nextTick(() => {
    searchInputRef.value?.focus();
  });
}

function handleOverlayClick() {
  if (!hasQuery.value) {
    closeSearch();
  } else {
    searchInputRef.value?.blur();
  }
}

function onInputKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") {
    e.preventDefault();
    closeSearch();
  } else if (e.key === "Enter") {
    galleryStore.submitSearch();
    searchInputRef.value?.blur();
  }
}

function handleGlobalKeydown(e: KeyboardEvent) {
  if (e.key === "Escape" && isSearchActive.value) {
    e.preventDefault();
    closeSearch();
  }
}

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleGlobalKeydown);
});

watch(isSearchActive, (active) => {
  if (active) {
    window.addEventListener("keydown", handleGlobalKeydown);
  } else {
    window.removeEventListener("keydown", handleGlobalKeydown);
  }
});

function onSearchInput(e: Event) {
  const target = e.target as HTMLInputElement;
  emit("update:searchQuery", target.value);
}

function openAdvancedSearch() {
  isSearchActive.value = false;
  emit("open-advanced-search");
}
</script>

<template>
  <header class="tablet-header" :class="{ 'search-active': isSearchActive }" data-testid="tablet-header">
    <!-- Left: hamburger -->
    <Tooltip v-if="!isSearchActive">
      <TooltipTrigger as-child>
        <button
          ref="searchBtnRef"
          class="th-btn th-hamburger"
          @click="emit('toggle-sidebar')"
          aria-label="Toggle sidebar"
        >
          <Menu class="th-header-icon" />
        </button>
      </TooltipTrigger>
      <TooltipContent>Toggle sidebar</TooltipContent>
    </Tooltip>

    <Tooltip v-if="isSearchActive">
      <TooltipTrigger as-child>
        <motion.button
          class="th-btn th-back-btn"
          :initial="{ opacity: 0, x: -6 }"
          :animate="{ opacity: 1, x: 0 }"
          :transition="{ type: 'spring', stiffness: 500, damping: 36, opacity: { type: 'tween', duration: 0.16 } }"
          @click="closeSearch"
          aria-label="Close search"
        >
          <ArrowLeft class="th-header-icon" />
        </motion.button>
      </TooltipTrigger>
      <TooltipContent>Close search</TooltipContent>
    </Tooltip>

    <!-- Center: breadcrumb (hidden in search mode) -->
    <div v-show="!isSearchActive" class="th-center">
      <span class="th-context-kicker">{{ showBackToGallery ? "Workspace" : "Gallery" }}</span>
      <div class="th-context-path">
        <Breadcrumb
          v-if="!showBackToGallery && currentPath"
          :path="currentPath"
          :root-path="galleryStore.activeImportRootPath"
          @navigate="handleBreadcrumbNavigate"
        />
        <span v-if="showBackToGallery" class="th-path-empty">{{ pageTitle }}</span>
        <span v-else-if="!currentPath" class="th-path-empty">All media</span>
      </div>
    </div>

    <!-- Center: expandable search input (search mode) -->
    <motion.div
      v-if="isSearchActive"
      class="th-search-expanded"
      :initial="{ opacity: 0, scaleX: 0.72 }"
      :animate="{ opacity: 1, scaleX: 1 }"
      :transition="{ type: 'spring', stiffness: 520, damping: 38, opacity: { type: 'tween', duration: 0.16 } }"
    >
      <div class="th-search-input-wrap">
        <Loader2 v-if="searchLoading" class="th-search-icon th-search-loading" />
        <Search v-else class="th-search-icon" />
        <input
          id="tablet-gallery-search"
          name="gallery-search"
          ref="searchInputRef"
          :value="searchQuery"
          @input="onSearchInput"
          @keydown="onInputKeydown"
          type="search"
          placeholder="Search gallery"
          autocomplete="off"
          spellcheck="false"
          aria-label="Search gallery"
          class="th-search-input"
          data-focus-ring="none"
        />
        <button v-if="hasQuery" class="th-search-clear" @click="clearSearch" aria-label="Clear search">
          <X />
        </button>
        <SearchScopeSelect
          :model-value="searchScope"
          size="compact"
          @update:model-value="emit('scope-change', $event)"
        />
      </div>
      <button class="th-btn th-advanced-search" @click="openAdvancedSearch" aria-label="Advanced Search">
        <SlidersHorizontal class="th-header-icon" />
      </button>
    </motion.div>

    <!-- Right: actions (hidden in search mode) -->
    <div v-show="!isSearchActive" class="th-actions">
      <RouterLink
        :to="showBackToGallery ? '/' : '/admin/libraries'"
        class="th-btn"
        :aria-label="showBackToGallery ? 'Back to gallery' : 'Libraries'"
      >
        <ArrowLeft v-if="showBackToGallery" class="th-header-icon" />
        <Library v-else class="th-header-icon" />
      </RouterLink>
      <!-- Search trigger -->
      <Tooltip v-if="!showBackToGallery">
        <TooltipTrigger as-child>
          <button class="th-btn" @click="openSearch" aria-label="Open search">
            <Search class="th-header-icon" />
          </button>
        </TooltipTrigger>
        <TooltipContent>Search</TooltipContent>
      </Tooltip>

      <!-- Theme toggle -->
      <Tooltip>
        <TooltipTrigger as-child>
          <button
            class="th-btn th-theme-btn"
            @click="emit('toggle-theme')"
            :aria-label="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
          >
            <svg v-if="isDark" class="th-theme-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640">
              <path
                fill="currentColor"
                d="M423.7 85.9C336.6 107.5 272 186.2 272 280C272 390.4 361.5 480 472 480C490.5 480 508.4 477.5 525.4 472.8C478.8 535.4 404.1 576 320 576C178.6 576 64 461.4 64 320C64 178.6 178.6 64 320 64C356.9 64 392 71.8 423.7 85.9z"
              />
            </svg>
            <svg v-else class="th-theme-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640">
              <path
                fill="currentColor"
                d="M340.8 43.6L396.3 136.2C477.1 115.9 525 104 539.9 100.2C536.2 115.1 524.2 163 503.9 243.8C575.4 286.6 617.7 312 630.9 319.9C617.7 327.8 575.4 353.2 503.9 396C524.2 476.8 536.2 524.7 539.9 539.6C525 535.9 477.1 523.9 396.3 503.6C353.5 575.1 328.1 617.4 320.2 630.6C312.3 617.4 286.9 575.1 244.1 503.6C163.3 523.9 115.5 535.9 100.5 539.6C104.2 524.7 116.2 476.8 136.5 396C65 353.2 22.7 327.8 9.5 319.9C22.7 312 65 286.6 136.5 243.8C116.2 163 104.3 115.2 100.5 100.2C115.4 103.9 163.3 115.9 244.1 136.2C286.9 64.7 312.3 22.4 320.2 9.2L340.8 43.5zM320.2 176C240.7 175.9 176.1 240.3 176 319.8C175.9 399.3 240.3 463.9 319.8 464C399.3 464.1 463.9 399.7 464 320.2C464.1 240.7 399.7 176.1 320.2 176zM319.8 416C266.8 415.9 223.9 372.8 224 319.8C224.1 266.8 267.2 223.9 320.2 224C373.2 224.1 416.1 267.2 416 320.2C415.9 373.2 372.8 416.1 319.8 416z"
              />
            </svg>
          </button>
        </TooltipTrigger>
        <TooltipContent>{{ isDark ? "Switch to light mode" : "Switch to dark mode" }}</TooltipContent>
      </Tooltip>
    </div>
  </header>

  <!-- Focus overlay -->
  <AnimatePresence :initial="false">
    <motion.div
      v-if="isSearchActive"
      class="th-search-overlay"
      :class="{ 'th-search-has-query': hasQuery }"
      :initial="{ opacity: 0 }"
      :animate="{ opacity: 1 }"
      :exit="{ opacity: 0 }"
      :transition="{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }"
      @click="handleOverlayClick"
      @touchend.prevent="handleOverlayClick"
    />
  </AnimatePresence>
</template>

<style scoped>
/* ============================================================
   Tablet Header — Compact (52px), no brand hero
   ============================================================ */
.tablet-header {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 68px;
  min-height: 68px;
  padding: 8px 10px;
  background: color-mix(in srgb, var(--card) 92%, transparent);
  backdrop-filter: blur(18px) saturate(1.1);
  -webkit-backdrop-filter: blur(18px) saturate(1.1);
  border: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
  border-radius: 16px;
  flex-shrink: 0;
  position: relative;
  z-index: 20;
}

/* ============================================================
   Buttons — shared
   ============================================================ */
.th-btn {
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 12px;
  background: transparent;
  color: var(--foreground);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}

.th-btn:hover {
  background: color-mix(in srgb, var(--foreground) 8%, transparent);
}

.th-btn:active {
  background: color-mix(in srgb, var(--foreground) 14%, transparent);
}

/* ============================================================
   Icon sizing — CSS token classes (no :size prop, Lucide defaults 2px stroke)
   ============================================================ */
:deep(.th-header-icon) {
  width: var(--gallery-icon-nav);
  height: var(--gallery-icon-nav);
  flex-shrink: 0;
}

:deep(.th-theme-icon) {
  width: var(--gallery-icon-nav);
  height: var(--gallery-icon-nav);
  flex-shrink: 0;
}

/* ============================================================
   Center: breadcrumb area
   ============================================================ */
.th-center {
  flex: 1;
  display: flex;
  align-items: flex-start;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  min-width: 0;
  overflow: hidden;
}

.th-context-kicker {
  color: var(--muted-foreground);
  font-size: 10px;
  font-weight: 650;
  letter-spacing: 0.08em;
  line-height: 1.1;
  text-transform: uppercase;
}

.th-context-path {
  width: 100%;
  min-width: 0;
  overflow: hidden;
}

.th-path-empty {
  color: var(--foreground);
  font-size: 16px;
  font-weight: 650;
  white-space: nowrap;
}

/* ============================================================
   Right: actions
   ============================================================ */
.th-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

/* ============================================================
   Expandable search (full-width when active)
   ============================================================ */
.th-search-expanded {
  flex: 1;
  display: flex;
  align-items: center;
  transform-origin: right center;
  gap: 4px;
}

.th-search-input-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  height: 44px;
  padding: 0 6px 0 12px;
  border: 1px solid var(--input);
  border-radius: 14px;
  background: color-mix(in srgb, var(--background) 88%, var(--card));
  box-shadow: 0 1px 2px color-mix(in srgb, black 6%, transparent);
  transition:
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.th-search-input-wrap:focus-within {
  border-color: var(--ring);
  box-shadow: var(--focus-within-ring-shadow);
}

.th-search-icon {
  color: var(--muted-foreground);
  flex-shrink: 0;
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}

.th-search-loading {
  animation: thSearchSpin 1s linear infinite;
}

@keyframes thSearchSpin {
  to {
    transform: rotate(360deg);
  }
}

.th-search-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 15px;
  color: var(--foreground);
  outline: none;
  min-width: 0;
  line-height: 1.3;
  font-family: var(--gallery-font-family, inherit);
}

.th-search-input::placeholder {
  color: var(--muted-foreground);
  font-weight: 400;
}

/* Hide native search decorations */
.th-search-input::-webkit-search-decoration,
.th-search-input::-webkit-search-cancel-button,
.th-search-input::-webkit-search-results-button,
.th-search-input::-webkit-search-results-decoration {
  -webkit-appearance: none;
  appearance: none;
  display: none;
}

.th-search-clear {
  background: color-mix(in srgb, var(--muted-foreground) 12%, transparent);
  border: none;
  color: var(--foreground);
  cursor: pointer;
  padding: 0;
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  flex-shrink: 0;
  transition: background 0.15s ease;
}

.th-search-clear:hover {
  background: color-mix(in srgb, var(--muted-foreground) 20%, transparent);
}

.th-search-clear:active {
  background: color-mix(in srgb, var(--muted-foreground) 30%, transparent);
}

.th-search-clear svg {
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}

/* ============================================================
   Focus overlay
   ============================================================ */
.th-search-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 10;
  background: color-mix(in srgb, black 24%, transparent);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  cursor: pointer;
  touch-action: manipulation;
  pointer-events: auto;
}

:root[data-theme="dark"] .th-search-overlay {
  background: rgba(0, 0, 0, 0.32);
}

.th-search-overlay.th-search-has-query {
  background: transparent;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  pointer-events: none;
}

/* ============================================================
   Tablet: larger touch targets (44×44)
   ============================================================ */
@media (min-width: 768px) and (max-width: 1199px) {
  .th-btn {
    width: 44px;
    height: 44px;
  }
}

/* ============================================================
   Reduced motion
   ============================================================ */
@media (prefers-reduced-motion: reduce) {
  .th-search-loading {
    animation: none;
  }
}
</style>
