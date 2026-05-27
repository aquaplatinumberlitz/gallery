<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { Menu, Search, Sun, Moon, Settings, X } from 'lucide-vue-next'

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
      <Sun v-if="isDark" :size="20" />
      <Moon v-else :size="20" />
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
