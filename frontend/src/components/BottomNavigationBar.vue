<template>
  <nav class="bottom-nav" :class="{ hidden: !barsVisible }">
    <button 
      v-for="tab in tabs" :key="tab.id"
      class="nav-item" 
      :class="{ active: activeTab === tab.id }"
      @click="onNavigate(tab.id)"
    >
      <component :is="tab.icon" :size="22" />
      <span class="nav-label">{{ tab.label }}</span>
    </button>
  </nav>
</template>

<script setup lang="ts">
import { Home, FolderOpen, Search, Settings } from 'lucide-vue-next'
import { useHaptic } from '../composables/useHaptic'

const { light: hapticLight } = useHaptic()

defineProps<{
  activeTab: string
  barsVisible: boolean
}>()

const emit = defineEmits<{
  navigate: [tabId: string]
}>()

function onNavigate(tabId: string) {
  hapticLight()
  emit('navigate', tabId)
}

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
  padding-bottom: env(safe-area-inset-bottom, 0px);
  background: color-mix(in srgb, var(--surface-color) 92%, transparent);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-top: 1px solid color-mix(in srgb, var(--border-color, rgba(0,0,0,0.08)) 50%, transparent);
  flex-shrink: 0;
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 90;
  transform: translateY(0);
  opacity: 1;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease;
}

.bottom-nav.hidden {
  transform: translateY(100%);
  opacity: 0;
  pointer-events: none;
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
  transition: color 0.2s, transform 0.15s cubic-bezier(0.4, 0, 0.2, 1);
  flex: 1;
  min-height: 44px;
  min-width: 44px;
  -webkit-tap-highlight-color: transparent;
}

.nav-item:hover {
  color: var(--text-color);
}

.nav-item.active {
  color: var(--primary-color, #d6a15d);
  transform: scale(1.05);
}

.nav-item:active {
  transform: scale(0.95);
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

/* Slide-up enter animation */
.slide-up-enter-active {
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.slide-up-enter-from {
  transform: translateY(100%);
  opacity: 0;
}
</style>
