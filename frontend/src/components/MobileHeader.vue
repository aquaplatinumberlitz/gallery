<script setup lang="ts">
import { ref, nextTick, onBeforeUnmount, computed, watch } from "vue";
import { Menu, Search, X, ArrowLeft, Loader2, SlidersHorizontal } from "lucide-vue-next";
import { RouterLink } from "vue-router";
import { useGalleryStore } from "../stores/gallery";
import { useFieldedSearch } from "@/composables/useFieldedSearch";
import SortDropdown from "./SortDropdown.vue";
import SearchScopeSelect from "./SearchScopeSelect.vue";
import SearchFilterChips from "./SearchFilterChips.vue";
import type { SearchScope, SortValue } from "../types";
import { AnimatePresence, motion } from "motion-v";

interface Props {
  isDark: boolean;
  searchQuery: string;
  searchScope: SearchScope;
  searchLoading: boolean;
  currentPath: string;
  barsVisible: boolean;
  showBackToGallery?: boolean;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  "update:searchQuery": [value: string];
  "scope-change": [value: SearchScope];
  "toggle-sidebar": [];
  "toggle-theme": [];
  "open-advanced-search": [];
}>();

const { fieldedFilters, removeFilter, clearAll } = useFieldedSearch(() => props.searchQuery);

function handleRemoveFilter(index: number) {
  emit("update:searchQuery", removeFilter(index));
}

function handleClearAll() {
  emit("update:searchQuery", clearAll());
}

const isSearchActive = ref(false);
const searchInputRef = ref<HTMLInputElement | null>(null);
const searchBtnRef = ref<HTMLButtonElement | null>(null);

// ── Derived ──
const hasQuery = computed(() => props.searchQuery.length > 0);
const folderName = computed(() => {
  const segments = props.currentPath.replace(/\\/g, "/").split("/").filter(Boolean);
  return segments.at(-1) || "Gallery";
});

// ── Open / Close ──
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

// ── Overlay / tap-outside handler ──
function handleOverlayClick() {
  if (!hasQuery.value) {
    closeSearch();
  } else {
    searchInputRef.value?.blur();
  }
}

// ── Keyboard handlers ──
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

// Watch for activation to add global listener
watch(isSearchActive, (active) => {
  if (active) {
    window.addEventListener("keydown", handleGlobalKeydown);
  } else {
    window.removeEventListener("keydown", handleGlobalKeydown);
  }
});

// ── Input handler ──
function onSearchInput(e: Event) {
  const target = e.target as HTMLInputElement;
  emit("update:searchQuery", target.value);
}

function openAdvancedSearch() {
  isSearchActive.value = false;
  emit("open-advanced-search");
}

const galleryStore = useGalleryStore();

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
</script>

<template>
  <header class="mobile-header" :class="{ hidden: !barsVisible, 'search-active': isSearchActive }">
    <!-- Left: hamburger (hidden in search mode on mobile) / back button -->
    <button
      v-if="!isSearchActive"
      ref="searchBtnRef"
      class="mh-btn mh-hamburger"
      @click="emit('toggle-sidebar')"
      aria-label="Toggle sidebar"
    >
      <Menu />
    </button>
    <motion.button
      v-else
      class="mh-btn search-focus-back"
      :initial="{ opacity: 0, x: -6 }"
      :animate="{ opacity: 1, x: 0 }"
      :transition="{ type: 'spring', stiffness: 500, damping: 36, opacity: { type: 'tween', duration: 0.16 } }"
      @click="closeSearch"
      aria-label="Close search"
    >
      <ArrowLeft />
    </motion.button>

    <!-- Center: current browse context / search area -->
    <div class="mh-search">
      <div v-if="!isSearchActive" class="mh-context">
        <span class="mh-context-kicker">{{ showBackToGallery ? "Workspace" : "Browsing" }}</span>
        <span class="mh-context-title">{{ showBackToGallery ? "Gallery" : folderName }}</span>
      </div>
      <button
        v-if="!isSearchActive && !showBackToGallery"
        class="mh-btn mh-search-btn"
        @click="openSearch"
        aria-label="Open search"
      >
        <Search />
      </button>
      <motion.div
        v-if="isSearchActive"
        class="search-focus-bar"
        :initial="{ opacity: 0, scaleX: 0.72 }"
        :animate="{ opacity: 1, scaleX: 1 }"
        :transition="{ type: 'spring', stiffness: 520, damping: 38, opacity: { type: 'tween', duration: 0.16 } }"
      >
        <div class="search-focus-input-wrap">
          <Loader2 v-if="searchLoading" class="search-focus-input-icon search-focus-loading" />
          <Search v-else-if="!hasQuery" class="search-focus-input-icon" />
          <input
            id="mobile-gallery-search"
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
            class="search-focus-input"
            data-focus-ring="none"
          />
          <div class="search-focus-actions">
            <span v-if="hasQuery" class="search-focus-relevance">Relevance</span>
            <SearchScopeSelect
              :model-value="searchScope"
              :current-label="folderName"
              all-label="All libraries"
              size="icon"
              class="mobile-search-scope"
              @update:model-value="emit('scope-change', $event)"
            />
            <button v-if="hasQuery" class="search-focus-clear" @click="clearSearch" aria-label="Clear search">
              <X />
            </button>
            <span class="search-focus-divider" aria-hidden="true"></span>
            <button class="search-focus-advanced" @click="openAdvancedSearch" aria-label="Advanced Search">
              <SlidersHorizontal />
            </button>
          </div>
        </div>
      </motion.div>
      <SearchFilterChips
        v-if="isSearchActive"
        :filters="fieldedFilters"
        @remove="handleRemoveFilter"
        @clear-all="handleClearAll"
        class="mt-2 px-1"
      />
    </div>

    <RouterLink v-if="!isSearchActive && showBackToGallery" to="/" class="mh-btn" aria-label="Back to gallery">
      <ArrowLeft />
    </RouterLink>

    <!-- Right: sort, theme & settings (hidden in search mode) -->
    <SortDropdown
      v-if="!isSearchActive && !showBackToGallery"
      v-model="gallerySortValue"
      trigger-class="mh-sort-trigger"
      aria-label="Sort gallery"
    />
    <button
      v-if="!isSearchActive"
      class="mh-btn"
      @click="emit('toggle-theme')"
      :aria-label="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
    >
      <svg v-if="isDark" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640">
        <path
          fill="currentColor"
          d="M423.7 85.9C336.6 107.5 272 186.2 272 280C272 390.4 361.5 480 472 480C490.5 480 508.4 477.5 525.4 472.8C478.8 535.4 404.1 576 320 576C178.6 576 64 461.4 64 320C64 178.6 178.6 64 320 64C356.9 64 392 71.8 423.7 85.9z"
        />
      </svg>
      <svg v-else xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640">
        <path
          fill="currentColor"
          d="M340.8 43.6L396.3 136.2C477.1 115.9 525 104 539.9 100.2C536.2 115.1 524.2 163 503.9 243.8C575.4 286.6 617.7 312 630.9 319.9C617.7 327.8 575.4 353.2 503.9 396C524.2 476.8 536.2 524.7 539.9 539.6C525 535.9 477.1 523.9 396.3 503.6C353.5 575.1 328.1 617.4 320.2 630.6C312.3 617.4 286.9 575.1 244.1 503.6C163.3 523.9 115.5 535.9 100.5 539.6C104.2 524.7 116.2 476.8 136.5 396C65 353.2 22.7 327.8 9.5 319.9C22.7 312 65 286.6 136.5 243.8C116.2 163 104.3 115.2 100.5 100.2C115.4 103.9 163.3 115.9 244.1 136.2C286.9 64.7 312.3 22.4 320.2 9.2L340.8 43.5zM320.2 176C240.7 175.9 176.1 240.3 176 319.8C175.9 399.3 240.3 463.9 319.8 464C399.3 464.1 463.9 399.7 464 320.2C464.1 240.7 399.7 176.1 320.2 176zM319.8 416C266.8 415.9 223.9 372.8 224 319.8C224.1 266.8 267.2 223.9 320.2 224C373.2 224.1 416.1 267.2 416 320.2C415.9 373.2 372.8 416.1 319.8 416z"
        />
      </svg>
    </button>
  </header>

  <!-- Focus overlay — sibling element outside header -->
  <AnimatePresence :initial="false">
    <motion.div
      v-if="isSearchActive"
      ref="overlayRef"
      class="search-focus-overlay"
      :class="{ 'search-focus-has-query': hasQuery }"
      :initial="{ opacity: 0 }"
      :animate="{ opacity: 1 }"
      :exit="{ opacity: 0 }"
      :transition="{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }"
      @pointerdown="handleOverlayClick"
    />
  </AnimatePresence>
</template>

<style scoped>
/* ============================================================
   Mobile Header — Base
   ============================================================ */
.mobile-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 60px;
  padding: 6px 8px;
  padding-top: max(6px, env(safe-area-inset-top));
  background: color-mix(in srgb, var(--background) 94%, transparent);
  backdrop-filter: blur(18px) saturate(1.15);
  -webkit-backdrop-filter: blur(18px) saturate(1.15);
  border-bottom: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
  transform: translateY(0);
  opacity: 1;
  transition:
    transform 0.3s cubic-bezier(0.4, 0, 0.2, 1),
    opacity 0.3s ease,
    padding 0.2s ease;
}

/* Search-active state: more compact padding */
.mobile-header.search-active {
  gap: 4px;
  padding-left: 4px;
  padding-right: 4px;
}

@media (max-width: 480px) {
  .mobile-header.search-active {
    padding-left: 2px;
    padding-right: 2px;
    gap: 2px;
  }
}

.mobile-header.hidden {
  transform: translateY(-100%);
  opacity: 0;
  pointer-events: none;
}

/* ============================================================
   Buttons — shared
   ============================================================ */
.mh-btn {
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

.mh-btn svg {
  width: var(--gallery-icon-mobile-toolbar);
  height: var(--gallery-icon-mobile-toolbar);
}

.mh-btn:hover {
  background: color-mix(in srgb, var(--foreground) 8%, transparent);
}

.mh-btn:active {
  background: color-mix(in srgb, var(--foreground) 14%, transparent);
  transform: scale(0.96);
}

/* ============================================================
   Search area — container
   ============================================================ */
.mh-search {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  min-width: 0;
}

.mh-context {
  min-width: 0;
  padding-left: 4px;
  display: flex;
  flex: 1;
  flex-direction: column;
  justify-content: center;
  gap: 1px;
}

.mh-context-kicker {
  color: var(--muted-foreground);
  font-size: 10px;
  font-weight: 650;
  letter-spacing: 0.08em;
  line-height: 1.1;
  text-transform: uppercase;
}

.mh-context-title {
  overflow: hidden;
  color: var(--foreground);
  font-size: 15px;
  font-weight: 650;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ============================================================
   Search button (collapsed state)
   ============================================================ */
.mh-search-btn {
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
  transition: background 0.15s ease;
}

.mh-search-btn:hover {
  background: color-mix(in srgb, var(--foreground) 8%, transparent);
}

.mh-search-btn:active {
  background: color-mix(in srgb, var(--foreground) 14%, transparent);
}

/* ============================================================
   Search bar — expanded (focused) state
   ============================================================ */
.search-focus-bar {
  flex: 1;
  width: 100%;
  min-width: 0;
  display: flex;
  align-items: center;
  transform-origin: right center;
  gap: 0;
}

/* ============================================================
   Search input wrap — pill
   ============================================================ */
.search-focus-input-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  height: 48px;
  overflow: visible;
  padding: 0 0 0 10px;
  border: 1px solid var(--input);
  border-radius: 14px;
  background: color-mix(in srgb, var(--card) 92%, var(--background));
  box-shadow: 0 1px 2px color-mix(in srgb, black 5%, transparent);
  transition:
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

/* When input is focused, subtle ring */
.search-focus-input-wrap:has(.search-focus-input:focus-visible) {
  border-color: var(--ring);
  box-shadow: var(--focus-within-ring-shadow);
}

.search-focus-input-icon {
  color: var(--muted-foreground);
  flex-shrink: 0;
  width: var(--gallery-icon-md);
  height: var(--gallery-icon-md);
}

.search-focus-loading {
  animation: searchFocusSpin 1s linear infinite;
}

@keyframes searchFocusSpin {
  to {
    transform: rotate(360deg);
  }
}

/* ============================================================
   Input
   ============================================================ */
.search-focus-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 16px; /* Prevent iOS auto-zoom */
  color: var(--foreground);
  outline: none;
  min-width: 0;
  line-height: 1.3;
  font-family: var(--gallery-font-family, inherit);
}

.search-focus-input::placeholder {
  color: var(--muted-foreground);
  font-weight: 400;
}

/* Prevent iOS zoom with smaller font */
.search-focus-input:focus {
  font-size: 16px;
}

/* Hide native search decorations */
.search-focus-input::-webkit-search-decoration,
.search-focus-input::-webkit-search-cancel-button,
.search-focus-input::-webkit-search-results-button,
.search-focus-input::-webkit-search-results-decoration {
  -webkit-appearance: none;
  appearance: none;
  display: none;
}

/* ============================================================
   Clear button — ghost, compact
   ============================================================ */
.search-focus-clear {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: 6px;
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--muted-foreground);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition:
    background 150ms ease,
    color 150ms ease,
    transform 150ms ease;
}

.search-focus-clear:hover {
  background: color-mix(in srgb, var(--foreground) 8%, transparent);
  color: var(--foreground);
}

.search-focus-clear:active {
  transform: scale(0.92);
}

.search-focus-clear svg {
  width: 14px;
  height: 14px;
}

/* ============================================================
   Scope select — icon-only, ghost
   ============================================================ */
:deep(.mobile-search-scope) {
  width: 36px;
  min-width: 36px;
  max-width: 36px;
  height: 36px;
  flex: 0 0 auto;
  border: none;
  border-radius: 8px;
  background: transparent;
  padding: 0;
  box-shadow: none;
  -webkit-tap-highlight-color: transparent;
  transition: background 150ms ease;
}

:deep(.mobile-search-scope:hover),
:deep(.mobile-search-scope[data-state="open"]) {
  border-color: transparent;
  background: color-mix(in srgb, var(--foreground) 8%, transparent);
  box-shadow: none;
}

:deep(.mobile-search-scope .search-scope-select-icon) {
  width: 16px;
  height: 16px;
  color: var(--muted-foreground);
  transition: color 150ms ease;
}

:deep(.mobile-search-scope:hover .search-scope-select-icon),
:deep(.mobile-search-scope[data-state="open"] .search-scope-select-icon) {
  color: var(--foreground);
}

/* ============================================================
   Actions container — scope + clear + divider + advanced
   ============================================================ */
.search-focus-actions {
  display: flex;
  align-items: center;
  align-self: stretch;
  flex-shrink: 0;
  gap: 2px;
}

.search-focus-relevance {
  color: var(--muted-foreground);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

/* Subtle vertical divider */
.search-focus-divider {
  width: 1px;
  height: 20px;
  background: color-mix(in srgb, var(--border) 72%, transparent);
  flex-shrink: 0;
  margin: 0 2px;
}

/* ============================================================
   Advanced search — flush right inside pill
   ============================================================ */
.search-focus-advanced {
  width: 40px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 0;
  border-radius: 0 13px 13px 0;
  background: transparent;
  color: var(--muted-foreground);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition:
    background 150ms ease,
    color 150ms ease;
}

.search-focus-advanced:hover {
  background: color-mix(in srgb, var(--foreground) 6%, transparent);
  color: var(--foreground);
}

.search-focus-advanced:active {
  background: color-mix(in srgb, var(--foreground) 10%, transparent);
}

.search-focus-advanced svg {
  width: 16px;
  height: 16px;
}

/* ============================================================
   Back button (search mode)
   ============================================================ */
.search-focus-back {
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--foreground);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.search-focus-back:hover {
  background: color-mix(in srgb, var(--foreground) 8%, transparent);
}

.search-focus-back:active {
  background: color-mix(in srgb, var(--foreground) 14%, transparent);
}

.search-focus-back svg {
  width: var(--gallery-icon-mobile-toolbar);
  height: var(--gallery-icon-mobile-toolbar);
}

/* ============================================================
   Focus overlay — dims background content
   ============================================================ */
.search-focus-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: calc(var(--gallery-z-dropdown) - 1);
  background: color-mix(in srgb, black 24%, transparent);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  cursor: pointer;
  /* Don't block touch on the header above */
  touch-action: manipulation;
  /* Prevent body scroll interference */
  pointer-events: auto;
}

/* Dark theme: darker overlay */
:root[data-theme="dark"] .search-focus-overlay {
  background: rgba(0, 0, 0, 0.32);
}

/* When user has typed a query — remove blur/dim so results/empty state are readable.
   Also let clicks pass through so the "Clear search" button in the empty state works. */
.search-focus-overlay.search-focus-has-query {
  background: transparent;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  pointer-events: none;
}

/* ============================================================
   Reduced motion
   ============================================================ */
@media (prefers-reduced-motion: reduce) {
  .search-focus-loading {
    animation: none;
  }
}

/* ============================================================
   Compact (<480px)
   ============================================================ */
@media (max-width: 480px) {
  .mobile-header {
    min-height: 56px;
    padding: 4px;
    padding-top: max(4px, env(safe-area-inset-top));
    gap: 2px;
  }

  .mh-context {
    padding-left: 2px;
  }

  .mh-context-kicker {
    font-size: 9px;
  }

  .mh-context-title {
    font-size: 14px;
  }

  .mh-btn,
  .mh-search-btn,
  .search-focus-back {
    width: 44px;
    height: 44px;
  }

  .search-focus-input-wrap {
    height: 48px;
    padding: 0 0 0 8px;
    gap: 6px;
  }

  .search-focus-input {
    font-size: 16px; /* Keep 16px to prevent iOS zoom */
  }

  .search-focus-input-icon {
    width: 14px;
    height: 14px;
  }
}

/* ============================================================
   Very small screens (<420px) — tighter icons
   ============================================================ */
@media (max-width: 420px) {
  :deep(.mobile-search-scope) {
    width: 32px;
    min-width: 32px;
    max-width: 32px;
    height: 32px;
  }

  .search-focus-advanced {
    width: 36px;
  }

  .search-focus-divider {
    height: 18px;
  }
}

:deep(.mh-sort-trigger) {
  width: 44px;
  min-width: 44px;
  height: 44px;
  padding: 0;
  border-color: transparent;
  border-radius: 12px;
  background: transparent;
  box-shadow: none;
}

:deep(.mh-sort-trigger > span),
:deep(.mh-sort-trigger > svg:last-child) {
  display: none;
}

/* ============================================================
   Tablet: wider max-width for search bar
   ============================================================ */
/* Tablet-range search input sizing */
@media (min-width: 481px) and (max-width: 1199px) {
  .search-focus-input-wrap {
    max-width: 520px;
    margin: 0 auto;
  }

  .mobile-header.search-active {
    justify-content: center;
  }
}
</style>
