<script setup lang="ts">
import { ref, nextTick, onBeforeUnmount, onMounted, computed, watch } from 'vue'
import { Menu, Search, X, ArrowLeft, ArrowUpDown } from 'lucide-vue-next'
import { useGalleryStore } from '../stores/gallery'
import type { SortField, SortOrder } from '../types'

interface Props {
  isDark: boolean
  searchQuery: string
  barsVisible: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:searchQuery': [value: string]
  'toggle-sidebar': []
  'toggle-theme': []
}>()

const isSearchActive = ref(false)
const searchInputRef = ref<HTMLInputElement | null>(null)
const searchBtnRef = ref<HTMLButtonElement | null>(null)
const overlayRef = ref<HTMLElement | null>(null)

// ── Derived ──
const hasQuery = computed(() => props.searchQuery.length > 0)

// ── Open / Close ──
function openSearch() {
  isSearchActive.value = true
  nextTick(() => {
    searchInputRef.value?.focus()
  })
}

function closeSearch() {
  emit('update:searchQuery', '')
  isSearchActive.value = false
  nextTick(() => {
    searchBtnRef.value?.focus()
  })
}

function clearSearch() {
  emit('update:searchQuery', '')
  nextTick(() => {
    searchInputRef.value?.focus()
  })
}

// ── Overlay / tap-outside handler ──
function handleOverlayClick() {
  if (!hasQuery.value) {
    closeSearch()
  } else {
    searchInputRef.value?.blur()
  }
}

// ── Keyboard handlers ──
function onInputKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    closeSearch()
  } else if (e.key === 'Enter') {
    searchInputRef.value?.blur()
  }
}

function handleGlobalKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isSearchActive.value) {
    e.preventDefault()
    closeSearch()
  }
}

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleGlobalKeydown)
  document.removeEventListener('click', closeSortPopover)
})

// Watch for activation to add global listener
watch(isSearchActive, (active) => {
  if (active) {
    window.addEventListener('keydown', handleGlobalKeydown)
  } else {
    window.removeEventListener('keydown', handleGlobalKeydown)
  }
})

// ── Input handler ──
function onSearchInput(e: Event) {
  const target = e.target as HTMLInputElement
  emit('update:searchQuery', target.value)
}

// ── Sort popover ──
const galleryStore = useGalleryStore()

const showSortPopover = ref(false)
const sortPopoverRef = ref<HTMLElement | null>(null)

const sortField = computed(() => galleryStore.sortField)
const sortOrder = computed(() => galleryStore.sortOrder)

interface MobileSortOption {
  field: SortField
  order: SortOrder
  label: string
}

const mobileSortOptions: MobileSortOption[] = [
  { field: 'date', order: 'desc', label: 'Newest' },
  { field: 'date', order: 'asc', label: 'Oldest' },
  { field: 'name', order: 'asc', label: 'Name A–Z' },
  { field: 'name', order: 'desc', label: 'Name Z–A' },
]

const isActiveSort = (opt: MobileSortOption): boolean =>
  sortField.value === opt.field && sortOrder.value === opt.order

function toggleSortPopover() {
  showSortPopover.value = !showSortPopover.value
}

function selectMobileSort(opt: MobileSortOption) {
  galleryStore.setSortField(opt.field)
  galleryStore.setSortOrder(opt.order)
  showSortPopover.value = false
}

function closeSortPopover(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.mobile-sort-dropdown')) {
    showSortPopover.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', closeSortPopover)
})
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
    <button
      v-else
      class="mh-btn search-focus-back"
      @click="closeSearch"
      aria-label="Close search"
    >
      <ArrowLeft />
    </button>

    <!-- Center: search area -->
    <div class="mh-search">
      <button
        v-if="!isSearchActive"
        class="mh-btn mh-search-btn"
        @click="openSearch"
        aria-label="Open search"
      >
        <Search />
      </button>
      <div
        v-else
        class="search-focus-bar"
      >
        <div class="search-focus-input-wrap">
          <Search class="search-focus-input-icon" :size="16" />
          <input
            ref="searchInputRef"
            :value="searchQuery"
            @input="onSearchInput"
            @keydown="onInputKeydown"
            type="text"
            placeholder="Search albums &amp; photos"
            autocomplete="off"
            spellcheck="false"
            aria-label="Search albums and photos"
            class="search-focus-input"
          />
          <button
            v-if="hasQuery"
            class="search-focus-clear"
            @click="clearSearch"
            aria-label="Clear search"
          >
            <X :size="16" />
          </button>
        </div>
      </div>
    </div>

    <!-- Right: sort, theme & settings (hidden in search mode) -->
    <div v-if="!isSearchActive" class="mobile-sort-dropdown" :class="{ open: showSortPopover }">
      <button
        class="mh-btn mh-sort-btn"
        @click.stop="toggleSortPopover"
        aria-label="Sort options"
      >
        <ArrowUpDown />
      </button>
      <Transition name="sort-popover">
        <div
          v-if="showSortPopover"
          ref="sortPopoverRef"
          class="mobile-sort-popover"
        >
          <button
            v-for="opt in mobileSortOptions"
            :key="`${opt.field}-${opt.order}`"
            class="mobile-sort-option"
            :class="{ active: isActiveSort(opt) }"
            @click="selectMobileSort(opt)"
          >
            <span class="sort-checkmark" :class="{ visible: isActiveSort(opt) }">✓</span>
            <span class="sort-label">{{ opt.label }}</span>
          </button>
        </div>
      </Transition>
    </div>
    <button
      v-if="!isSearchActive"
      class="mh-btn"
      @click="emit('toggle-theme')"
      :aria-label="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
    >
      <svg v-if="isDark" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="currentColor" d="M423.7 85.9C336.6 107.5 272 186.2 272 280C272 390.4 361.5 480 472 480C490.5 480 508.4 477.5 525.4 472.8C478.8 535.4 404.1 576 320 576C178.6 576 64 461.4 64 320C64 178.6 178.6 64 320 64C356.9 64 392 71.8 423.7 85.9z"/></svg>
      <svg v-else xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><path fill="currentColor" d="M340.8 43.6L396.3 136.2C477.1 115.9 525 104 539.9 100.2C536.2 115.1 524.2 163 503.9 243.8C575.4 286.6 617.7 312 630.9 319.9C617.7 327.8 575.4 353.2 503.9 396C524.2 476.8 536.2 524.7 539.9 539.6C525 535.9 477.1 523.9 396.3 503.6C353.5 575.1 328.1 617.4 320.2 630.6C312.3 617.4 286.9 575.1 244.1 503.6C163.3 523.9 115.5 535.9 100.5 539.6C104.2 524.7 116.2 476.8 136.5 396C65 353.2 22.7 327.8 9.5 319.9C22.7 312 65 286.6 136.5 243.8C116.2 163 104.3 115.2 100.5 100.2C115.4 103.9 163.3 115.9 244.1 136.2C286.9 64.7 312.3 22.4 320.2 9.2L340.8 43.5zM320.2 176C240.7 175.9 176.1 240.3 176 319.8C175.9 399.3 240.3 463.9 319.8 464C399.3 464.1 463.9 399.7 464 320.2C464.1 240.7 399.7 176.1 320.2 176zM319.8 416C266.8 415.9 223.9 372.8 224 319.8C224.1 266.8 267.2 223.9 320.2 224C373.2 224.1 416.1 267.2 416 320.2C415.9 373.2 372.8 416.1 319.8 416z"/></svg>
    </button>
  </header>

  <!-- Focus overlay — sibling element outside header -->
  <Transition name="overlay-fade">
    <div
      v-if="isSearchActive"
      ref="overlayRef"
      class="search-focus-overlay"
      :class="{ 'search-focus-has-query': hasQuery }"
      @click="handleOverlayClick"
      @touchend.prevent="handleOverlayClick"
    ></div>
  </Transition>
</template>

<style scoped>
/* ============================================================
   Mobile Header — Base
   ============================================================ */
.mobile-header {
  --icon-size: 22px;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  padding-top: max(8px, env(safe-area-inset-top));
  background: color-mix(in srgb, var(--surface-color) 85%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid color-mix(in srgb, var(--border-color, rgba(0, 0, 0, 0.08)) 50%, transparent);
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
  width: 38px;
  height: 38px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--text-color);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s ease, color 0.15s ease;
}

.mh-btn svg {
  width: var(--icon-size);
  height: var(--icon-size);
}

.mh-btn:hover {
  background: color-mix(in srgb, var(--text-color) 8%, transparent);
}

.mh-btn:active {
  background: color-mix(in srgb, var(--text-color) 14%, transparent);
}

/* ============================================================
   Search area — container
   ============================================================ */
.mh-search {
  flex: 1;
  display: flex;
  justify-content: flex-end;
  min-width: 0;
}

/* ============================================================
   Search button (collapsed state)
   ============================================================ */
.mh-search-btn {
  width: 38px;
  height: 38px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--text-color);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s ease;
}

.mh-search-btn:hover {
  background: color-mix(in srgb, var(--text-color) 8%, transparent);
}

.mh-search-btn:active {
  background: color-mix(in srgb, var(--text-color) 14%, transparent);
}

/* ============================================================
   Search bar — expanded (focused) state
   ============================================================ */
.search-focus-bar {
  flex: 1;
  display: flex;
  align-items: center;
  animation: searchBarExpand 200ms cubic-bezier(.2, .8, .2, 1) forwards;
  transform-origin: right center;
}

@keyframes searchBarExpand {
  from {
    opacity: 0;
    transform: scaleX(0.7);
  }
  to {
    opacity: 1;
    transform: scaleX(1);
  }
}

/* ============================================================
   Search input wrap — pill
   ============================================================ */
.search-focus-input-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  background: var(--gallery-surface-elevated, var(--surface-color));
  border: 1px solid color-mix(in srgb, var(--border-color, rgba(0, 0, 0, 0.12)) 80%, transparent);
  border-radius: var(--gallery-radius-full, 9999px);
  padding: 0 12px;
  height: 42px;
  box-shadow: var(--gallery-shadow-sm, 0 1px 3px rgba(0,0,0,0.08));
  transition:
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

/* When input is focused, subtle ring */
.search-focus-input-wrap:focus-within {
  border-color: var(--gallery-accent-default, var(--primary-color));
  box-shadow:
    0 0 0 1px var(--gallery-accent-default, var(--primary-color)),
    var(--gallery-shadow-sm, 0 1px 3px rgba(0,0,0,0.08));
}

.search-focus-input-icon {
  color: var(--gallery-text-tertiary, var(--muted-text));
  flex-shrink: 0;
  width: 16px;
  height: 16px;
}

/* ============================================================
   Input
   ============================================================ */
.search-focus-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 16px; /* Prevent iOS auto-zoom */
  color: var(--text-color);
  outline: none;
  min-width: 0;
  line-height: 1.3;
  font-family: var(--gallery-font-family, inherit);
}

.search-focus-input::placeholder {
  color: var(--gallery-text-placeholder, var(--muted-text));
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
   Clear button
   ============================================================ */
.search-focus-clear {
  background: color-mix(in srgb, var(--gallery-text-tertiary, var(--muted-text)) 12%, transparent);
  border: none;
  color: var(--gallery-text-secondary, var(--text-color));
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

.search-focus-clear:hover {
  background: color-mix(in srgb, var(--gallery-text-tertiary, var(--muted-text)) 20%, transparent);
}

.search-focus-clear:active {
  background: color-mix(in srgb, var(--gallery-text-tertiary, var(--muted-text)) 30%, transparent);
}

.search-focus-clear svg {
  width: 16px;
  height: 16px;
}

/* ============================================================
   Back button (search mode)
   ============================================================ */
.search-focus-back {
  width: 38px;
  height: 38px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--text-color);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  animation: backBtnIn 200ms cubic-bezier(.2, .8, .2, 1) forwards;
}

@keyframes backBtnIn {
  from {
    opacity: 0;
    transform: translateX(-6px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.search-focus-back:hover {
  background: color-mix(in srgb, var(--text-color) 8%, transparent);
}

.search-focus-back:active {
  background: color-mix(in srgb, var(--text-color) 14%, transparent);
}

.search-focus-back svg {
  width: var(--icon-size);
  height: var(--icon-size);
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
  z-index: 70;
  background: rgba(0, 0, 0, 0.18);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
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
   Overlay fade transition
   ============================================================ */
.overlay-fade-enter-active {
  transition:
    opacity 200ms cubic-bezier(.2, .8, .2, 1),
    backdrop-filter 200ms ease;
}

.overlay-fade-leave-active {
  transition:
    opacity 150ms ease,
    backdrop-filter 150ms ease;
}

.overlay-fade-enter-from,
.overlay-fade-leave-to {
  opacity: 0;
  backdrop-filter: blur(0px);
  -webkit-backdrop-filter: blur(0px);
}

/* ============================================================
   Reduced motion
   ============================================================ */
@media (prefers-reduced-motion: reduce) {
  .search-focus-bar {
    animation: none;
  }

  .search-focus-back {
    animation: none;
  }

  .overlay-fade-enter-active,
  .overlay-fade-leave-active {
    transition: opacity 150ms ease;
  }
}

/* ============================================================
   Compact (<480px)
   ============================================================ */
@media (max-width: 480px) {
  .mobile-header {
    padding: 8px 8px;
    padding-top: max(8px, env(safe-area-inset-top));
    gap: 4px;
  }

  .mh-btn,
  .mh-search-btn,
  .search-focus-back {
    width: 34px;
    height: 34px;
  }

  .search-focus-input-wrap {
    height: 38px;
    padding: 0 10px;
    gap: 6px;
  }

  .search-focus-input {
    font-size: 16px; /* Keep 16px to prevent iOS zoom */
  }

  .search-focus-clear {
    width: 22px;
    height: 22px;
  }

  .search-focus-clear svg,
  .search-focus-input-icon {
    width: 14px;
    height: 14px;
  }
}

/* ============================================================
   Mobile Sort Popover
   ============================================================ */
.mobile-sort-dropdown {
  position: relative;
}

.mh-sort-btn {
  position: relative;
  z-index: 1;
}

.mobile-sort-popover {
  position: absolute;
  bottom: auto;
  top: calc(100% + 8px);
  right: 0;
  min-width: 220px;
  background: var(--surface-color);
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
  padding: 6px;
  z-index: 200;
  overflow: hidden;
}

.mobile-sort-option {
  display: grid;
  grid-template-columns: 24px 1fr;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 48px;
  padding: 10px 14px;
  background: transparent;
  border: none;
  border-radius: 8px;
  color: var(--text-color);
  font-size: 14px;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
  font-weight: 500;
}

.mobile-sort-option:hover {
  background: rgba(0, 0, 0, 0.05);
}

.mobile-sort-option:active {
  background: rgba(0, 0, 0, 0.1);
}

.mobile-sort-option.active {
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  color: var(--primary-color);
  font-weight: 600;
}

.sort-checkmark {
  font-size: 14px;
  line-height: 1;
  visibility: hidden;
}

.sort-checkmark.visible {
  visibility: visible;
}

.sort-label {
  white-space: nowrap;
}

/* Dark theme active option */
:root[data-theme="dark"] .mobile-sort-option:hover {
  background: rgba(255, 255, 255, 0.08);
}

:root[data-theme="dark"] .mobile-sort-option:active {
  background: rgba(255, 255, 255, 0.14);
}

/* Sort popover animation */
.sort-popover-enter-active,
.sort-popover-leave-active {
  transition: all 0.2s ease;
  transform-origin: top right;
}

.sort-popover-enter-from,
.sort-popover-leave-to {
  opacity: 0;
  transform: scale(0.92) translateY(4px);
}

/* Compact popover on small screens */
@media (max-width: 480px) {
  .mobile-sort-popover {
    min-width: 200px;
    right: -4px;
  }

  .mobile-sort-option {
    padding: 8px 10px;
    font-size: 13px;
  }
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
