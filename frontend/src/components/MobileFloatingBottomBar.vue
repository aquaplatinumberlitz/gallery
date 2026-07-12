<script setup lang="ts">
import { computed } from "vue";
import { ArrowLeft, ArrowRight, FolderOpen } from "lucide-vue-next";

interface Props {
  canBack: boolean;
  canForward: boolean;
  currentPath: string;
  barsVisible: boolean;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  back: [];
  forward: [];
}>();

const folderName = computed(() => {
  if (!props.currentPath) return "Albums";
  const segments = props.currentPath.replace(/\\/g, "/").split("/").filter(Boolean);
  return segments.length > 0 ? segments[segments.length - 1] : "Albums";
});
</script>

<template>
  <nav class="mobile-bottom-bar" :class="{ hidden: !barsVisible }">
    <button class="mbb-btn" :disabled="!canBack" @click="emit('back')" aria-label="Go back">
      <ArrowLeft />
    </button>

    <div class="mbb-path" aria-live="polite">
      <FolderOpen class="path-icon" />
      <span class="path-copy">
        <span class="path-kicker">Current folder</span>
        <span class="path-text">{{ folderName }}</span>
      </span>
    </div>

    <button class="mbb-btn" :disabled="!canForward" @click="emit('forward')" aria-label="Go forward">
      <ArrowRight />
    </button>
  </nav>
</template>

<style scoped>
.mobile-bottom-bar {
  position: fixed;
  bottom: 10px;
  left: 50%;
  width: min(440px, calc(100vw - 20px));
  box-sizing: border-box;
  transform: translateX(-50%) translateY(0);
  z-index: 80;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px;
  margin-bottom: env(safe-area-inset-bottom, 0px);
  border-radius: 20px;
  background: color-mix(in srgb, var(--card) 94%, transparent);
  backdrop-filter: blur(18px) saturate(1.1);
  -webkit-backdrop-filter: blur(18px) saturate(1.1);
  border: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
  box-shadow: 0 10px 30px color-mix(in srgb, black 12%, transparent);
  opacity: 1;
  transition:
    transform 0.3s cubic-bezier(0.4, 0, 0.2, 1),
    opacity 0.3s ease;
}

.mobile-bottom-bar.hidden {
  transform: translateX(-50%) translateY(calc(100% + 24px));
  opacity: 0;
  pointer-events: none;
}

.mbb-btn {
  width: 44px;
  height: 44px;
  min-width: 44px;
  min-height: 44px;
  border: none;
  border-radius: 14px;
  background: transparent;
  color: var(--foreground);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition:
    background 0.15s ease,
    color 0.15s ease,
    opacity 0.15s ease;
}

.mbb-btn svg {
  width: var(--gallery-icon-mobile-toolbar);
  height: var(--gallery-icon-mobile-toolbar);
}

.mbb-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--foreground) 8%, transparent);
}

.mbb-btn:active:not(:disabled) {
  background: color-mix(in srgb, var(--foreground) 14%, transparent);
}

.mbb-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.mbb-path {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  padding: 0 8px;
  min-width: 0;
}

.path-icon {
  color: var(--primary);
  flex-shrink: 0;
}

.path-copy {
  min-width: 0;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 1px;
}

.path-kicker {
  color: var(--muted-foreground);
  font-size: 9px;
  font-weight: 650;
  letter-spacing: 0.08em;
  line-height: 1.1;
  text-transform: uppercase;
}

.path-text {
  font-size: 14px;
  font-weight: 650;
  color: var(--foreground);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Compact (<480px): smaller pill, tighter spacing */
@media (max-width: 480px) {
  .mobile-bottom-bar {
    bottom: 8px;
    padding: 5px;
    border-radius: 18px;
    gap: 2px;
  }

  .mbb-btn {
    width: 44px;
    height: 44px;
  }

  .mbb-path {
    padding: 0 4px;
    gap: 4px;
  }

  .path-text {
    font-size: 13px;
  }
}
</style>
