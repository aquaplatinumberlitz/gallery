<template>
  <nav class="bottom-nav">
    <button 
      v-for="tab in tabs" :key="tab.id"
      class="nav-item" 
      :class="{ active: activeTab === tab.id }"
      @click="$emit('navigate', tab.id)"
    >
      <component :is="tab.icon" :size="22" />
      <span class="nav-label">{{ tab.label }}</span>
    </button>
  </nav>
</template>

<script setup lang="ts">
import { Home, FolderOpen, Search, Settings } from 'lucide-vue-next'

defineProps<{
  activeTab: string
}>()

defineEmits<{
  navigate: [tabId: string]
}>()

const tabs = [
  { id: 'photos', icon: Home, label: 'Photos' },
  { id: 'albums', icon: FolderOpen, label: 'Albums' },
  { id: 'search', icon: Search, label: 'Search' },
  { id: 'more', icon: Settings, label: 'More' },
]
</script>

<style scoped>
.bottom-nav {
  display: flex;
  align-items: center;
  justify-content: space-around;
  height: 56px;
  background: var(--surface-color);
  border-top: 1px solid var(--border-color, rgba(0,0,0,0.08));
  padding: 4px 0;
  flex-shrink: 0;
}

.nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  border: none;
  background: transparent;
  color: var(--muted-text);
  cursor: pointer;
  padding: 4px 12px;
  border-radius: 8px;
  transition: color 0.2s;
  flex: 1;
}

.nav-item.active {
  color: var(--primary-color, #d6a15d);
}

.nav-label {
  font-size: 10px;
  line-height: 1;
}

@media (max-width: 360px) {
  .nav-label {
    display: none;
  }
}
</style>
