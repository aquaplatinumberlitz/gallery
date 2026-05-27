<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { Menu, Search, Settings, X } from 'lucide-vue-next'

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
  'open-settings': []
}>()

const searchExpanded = ref(false)
const searchInputRef = ref<HTMLInputElement | null>(null)

function openSearch() {
  searchExpanded.value = true
  nextTick(() => {
    searchInputRef.value?.focus()
  })
}

function closeSearch() {
  // Delay to allow clear button click to fire before collapsing
  setTimeout(() => {
    if (!props.searchQuery) {
      searchExpanded.value = false
    }
  }, 150)
}

function onSearchInput(e: Event) {
  const target = e.target as HTMLInputElement
  emit('update:searchQuery', target.value)
}

function clearSearch() {
  emit('update:searchQuery', '')
  searchExpanded.value = false
}
</script>

<template>
  <header class="mobile-header" :class="{ hidden: !barsVisible }">
    <button class="mh-btn" @click="emit('toggle-sidebar')" aria-label="Toggle sidebar">
      <Menu :size="20" />
    </button>
    
    <div class="mh-search" :class="{ expanded: searchExpanded }">
      <button v-if="!searchExpanded" class="mh-btn" @click="openSearch" aria-label="Open search">
        <Search :size="20" />
      </button>
      <div v-else class="search-input-wrap">
        <Search :size="16" class="search-input-icon" />
        <input
          ref="searchInputRef"
          :value="searchQuery"
          @input="onSearchInput"
          type="search"
          placeholder="Search..."
          autocomplete="off"
          @blur="closeSearch"
        />
        <button v-if="searchQuery" class="clear-btn" @click="clearSearch" aria-label="Clear search">
          <X :size="14" />
        </button>
      </div>
    </div>

    <button class="mh-btn" @click="emit('toggle-theme')" :aria-label="isDark ? 'Switch to light mode' : 'Switch to dark mode'">
      <!-- SVG sun/moon from AppHeader — same icons as desktop -->
      <svg v-if="isDark" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="20" height="20"><path fill="currentColor" d="M423.7 85.9C336.6 107.5 272 186.2 272 280C272 390.4 361.5 480 472 480C490.5 480 508.4 477.5 525.4 472.8C478.8 535.4 404.1 576 320 576C178.6 576 64 461.4 64 320C64 178.6 178.6 64 320 64C356.9 64 392 71.8 423.7 85.9z"/></svg>
      <svg v-else xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="20" height="20"><path fill="currentColor" d="M340.8 43.6L396.3 136.2C477.1 115.9 525 104 539.9 100.2C536.2 115.1 524.2 163 503.9 243.8C575.4 286.6 617.7 312 630.9 319.9C617.7 327.8 575.4 353.2 503.9 396C524.2 476.8 536.2 524.7 539.9 539.6C525 535.9 477.1 523.9 396.3 503.6C353.5 575.1 328.1 617.4 320.2 630.6C312.3 617.4 286.9 575.1 244.1 503.6C163.3 523.9 115.5 535.9 100.5 539.6C104.2 524.7 116.2 476.8 136.5 396C65 353.2 22.7 327.8 9.5 319.9C22.7 312 65 286.6 136.5 243.8C116.2 163 104.3 115.2 100.5 100.2C115.4 103.9 163.3 115.9 244.1 136.2C286.9 64.7 312.3 22.4 320.2 9.2L340.8 43.5zM320.2 176C240.7 175.9 176.1 240.3 176 319.8C175.9 399.3 240.3 463.9 319.8 464C399.3 464.1 463.9 399.7 464 320.2C464.1 240.7 399.7 176.1 320.2 176zM319.8 416C266.8 415.9 223.9 372.8 224 319.8C224.1 266.8 267.2 223.9 320.2 224C373.2 224.1 416.1 267.2 416 320.2C415.9 373.2 372.8 416.1 319.8 416z"/></svg>
    </button>
    <button class="mh-btn" @click="emit('open-settings')" aria-label="Open settings">
      <Settings :size="20" />
    </button>
  </header>
</template>

<style scoped>
.mobile-header {
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
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease;
}

.mobile-header.hidden {
  transform: translateY(-100%);
  opacity: 0;
  pointer-events: none;
}

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

.mh-btn:hover {
  background: color-mix(in srgb, var(--text-color) 8%, transparent);
}

.mh-btn:active {
  background: color-mix(in srgb, var(--text-color) 14%, transparent);
}

.mh-search {
  flex: 1;
  display: flex;
  justify-content: flex-end;
  min-width: 0;
}

.mh-search.expanded {
  justify-content: stretch;
}

.search-input-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  background: color-mix(in srgb, var(--surface-color) 60%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-color, rgba(0, 0, 0, 0.12)) 60%, transparent);
  border-radius: 10px;
  padding: 0 10px;
  height: 36px;
}

.search-input-icon {
  color: var(--muted-text);
  flex-shrink: 0;
}

.search-input-wrap input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 14px;
  color: var(--text-color);
  outline: none;
  min-width: 0;
}

.search-input-wrap input::placeholder {
  color: var(--muted-text);
}

.clear-btn {
  background: transparent;
  border: none;
  color: var(--muted-text);
  cursor: pointer;
  padding: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  flex-shrink: 0;
}

.clear-btn:hover {
  background: rgba(0, 0, 0, 0.06);
  color: var(--text-color);
}
</style>
