<script setup lang="ts">
import { computed } from 'vue'
import { ArrowLeft, ArrowRight, ArrowUpRight, FolderOpen } from 'lucide-vue-next'

interface Props {
  canBack: boolean
  canForward: boolean
  currentPath: string
  barsVisible: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'back': []
  'forward': []
  'open-folder': []
}>()

const folderName = computed(() => {
  if (!props.currentPath) return 'Albums'
  const segments = props.currentPath.replace(/\\/g, '/').split('/').filter(Boolean)
  return segments.length > 0 ? segments[segments.length - 1] : 'Albums'
})
</script>

<template>
  <nav class="mobile-bottom-bar" :class="{ hidden: !barsVisible }">
    <button class="mbb-btn" :disabled="!canBack" @click="emit('back')" aria-label="Go back">
      <ArrowLeft :size="18" />
    </button>
    
    <div class="mbb-path">
      <FolderOpen :size="14" class="path-icon" />
      <span class="path-text">{{ folderName }}</span>
    </div>
    
    <button class="mbb-btn" :disabled="!canForward" @click="emit('forward')" aria-label="Go forward">
      <ArrowRight :size="18" />
    </button>
    
    <button class="mbb-btn mbb-open" @click="emit('open-folder')" aria-label="Open in file explorer">
      <ArrowUpRight :size="18" />
    </button>
  </nav>
</template>

<style scoped>
.mobile-bottom-bar {
  position: fixed;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%) translateY(0);
  z-index: 80;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  margin-bottom: env(safe-area-inset-bottom, 0px);
  border-radius: 24px;
  background: color-mix(in srgb, var(--surface-color) 85%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid color-mix(in srgb, var(--border-color, rgba(0, 0, 0, 0.08)) 50%, transparent);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  opacity: 1;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease;
}

.mobile-bottom-bar.hidden {
  transform: translateX(-50%) translateY(calc(100% + 24px));
  opacity: 0;
  pointer-events: none;
}

.mbb-btn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-color);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s ease, color 0.15s ease, opacity 0.15s ease;
}

.mbb-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--text-color) 8%, transparent);
}

.mbb-btn:active:not(:disabled) {
  background: color-mix(in srgb, var(--text-color) 14%, transparent);
}

.mbb-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.mbb-open {
  margin-left: 4px;
}

.mbb-path {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 8px;
  min-width: 0;
  max-width: 160px;
}

.path-icon {
  color: var(--primary-color, #d4af37);
  flex-shrink: 0;
}

.path-text {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
