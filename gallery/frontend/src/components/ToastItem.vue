<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue';
import type { Toast } from '../stores/toast';
import { CheckCircle, XCircle, TriangleAlert, Info, X } from 'lucide-vue-next';

// @ts-expect-error: used via :is dynamic component binding
const _icons = { CheckCircle, XCircle, TriangleAlert, Info }

const props = defineProps<{
  toast: Toast;
}>();

const emit = defineEmits<{
  (e: 'dismiss'): void;
}>();

// Progress bar for auto-dismiss
const progress = ref(100);
const isPaused = ref(false);
let animationFrame: number | null = null;
let startTime: number | null = null;
let pausedProgress: number = 100;

const iconClass = computed(() => {
  switch (props.toast.type) {
    case 'success': return 'CheckCircle';
    case 'error': return 'XCircle';
    case 'warning': return 'TriangleAlert';
    case 'info': return 'Info';
    default: return 'Info';
  }
});

const typeClass = computed(() => `toast--${props.toast.type}`);

// Animate progress bar
const animateProgress = (timestamp: number) => {
  if (!startTime) startTime = timestamp;
  
  if (isPaused.value) {
    animationFrame = requestAnimationFrame(animateProgress);
    return;
  }
  
  const duration = props.toast.duration || 5000;
  const elapsed = timestamp - startTime;
  const remaining = Math.max(0, pausedProgress - (elapsed / duration) * pausedProgress);
  
  progress.value = remaining;
  
  if (remaining > 0) {
    animationFrame = requestAnimationFrame(animateProgress);
  }
};

const pauseProgress = () => {
  isPaused.value = true;
  pausedProgress = progress.value;
  startTime = null;
};

const resumeProgress = () => {
  isPaused.value = false;
  startTime = null;
};

const handleAction = () => {
  if (props.toast.action?.onClick) {
    props.toast.action.onClick();
  }
  emit('dismiss');
};

onMounted(() => {
  if (props.toast.duration && props.toast.duration > 0) {
    animationFrame = requestAnimationFrame(animateProgress);
  }
});

onUnmounted(() => {
  if (animationFrame) {
    cancelAnimationFrame(animationFrame);
  }
});
</script>

<template>
  <div 
    :class="['toast', typeClass]"
    @mouseenter="pauseProgress"
    @mouseleave="resumeProgress"
    @focusin="pauseProgress"
    @focusout="resumeProgress"
  >
    <!-- Icon -->
    <div class="toast__icon">
      <component :is="iconClass" :size="18" :stroke-width="1.5" />
    </div>
    
    <!-- Content -->
    <div class="toast__content">
      <div class="toast__title">{{ toast.title }}</div>
      <div 
        v-if="toast.message && toast.html" 
        class="toast__message"
        v-html="toast.message"
      ></div>
      <div v-else-if="toast.message" class="toast__message">{{ toast.message }}</div>
      
      <!-- Action button -->
      <button 
        v-if="toast.action"
        class="toast__action"
        type="button"
        @click="handleAction"
      >
        {{ toast.action.label }}
      </button>
    </div>
    
    <!-- Dismiss button -->
    <button 
      v-if="toast.dismissible"
      class="toast__dismiss"
      type="button"
      @click="emit('dismiss')"
    >
      <X :size="14" />
    </button>
    
    <!-- Progress bar -->
    <div 
      v-if="toast.duration && toast.duration > 0" 
      class="toast__progress"
    >
      <div 
        class="toast__progress-bar"
        :style="{ width: `${progress}%` }"
      ></div>
    </div>
  </div>
</template>

<style scoped>
.toast {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  background: var(--toast-bg, #ffffff);
  border-radius: 12px;
  box-shadow: 
    0 4px 12px rgba(0, 0, 0, 0.15),
    0 0 1px rgba(0, 0, 0, 0.1);
  pointer-events: auto;
  position: relative;
  overflow: hidden;
  border-left: 4px solid var(--toast-accent);
}

/* Type variants */
.toast--success {
  --toast-accent: #22c55e;
  --toast-icon-color: #22c55e;
  --toast-icon-bg: rgba(34, 197, 94, 0.1);
}

.toast--error {
  --toast-accent: #ef4444;
  --toast-icon-color: #ef4444;
  --toast-icon-bg: rgba(239, 68, 68, 0.1);
}

.toast--warning {
  --toast-accent: #f59e0b;
  --toast-icon-color: #f59e0b;
  --toast-icon-bg: rgba(245, 158, 11, 0.1);
}

.toast--info {
  --toast-accent: #3b82f6;
  --toast-icon-color: #3b82f6;
  --toast-icon-bg: rgba(59, 130, 246, 0.1);
}

/* Icon */
.toast__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--toast-icon-bg);
  color: var(--toast-icon-color);
  font-size: 16px;
  flex-shrink: 0;
}

/* Content */
.toast__content {
  flex: 1;
  min-width: 0;
}

.toast__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--toast-title, #1f2937);
  line-height: 1.4;
}

.toast__message {
  font-size: 13px;
  color: var(--toast-message, #6b7280);
  line-height: 1.4;
  margin-top: 2px;
}

/* Colored stats in toast message */
:deep(.toast-stat) {
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}

:deep(.toast-stat--album) {
  color: #8b5cf6;
  background: rgba(139, 92, 246, 0.12);
}

:deep(.toast-stat--image) {
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.12);
}

:root[data-theme="dark"] :deep(.toast-stat--album) {
  color: #a78bfa;
  background: rgba(167, 139, 250, 0.2);
}

:root[data-theme="dark"] :deep(.toast-stat--image) {
  color: #fbbf24;
  background: rgba(251, 191, 36, 0.2);
}

/* Action button */
.toast__action {
  display: inline-flex;
  align-items: center;
  margin-top: 8px;
  padding: 4px 0;
  border: none;
  background: transparent;
  color: var(--toast-accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s ease;
}

.toast__action:hover {
  opacity: 0.8;
}

.toast__action:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
  border-radius: 4px;
}

/* Dismiss button */
.toast__dismiss {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--toast-dismiss, #9ca3af);
  font-size: 14px;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.15s ease;
  flex-shrink: 0;
  margin: -4px -4px -4px 0;
}

.toast__dismiss:hover {
  background: rgba(0, 0, 0, 0.05);
  color: var(--toast-title, #1f2937);
}

.toast__dismiss:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

/* Progress bar */
.toast__progress {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: rgba(0, 0, 0, 0.05);
}

.toast__progress-bar {
  height: 100%;
  background: var(--toast-accent);
  transition: width 0.1s linear;
}

/* Dark mode */
:root[data-theme="dark"] .toast {
  --toast-bg: #1f2937;
  --toast-title: #f9fafb;
  --toast-message: #9ca3af;
  --toast-dismiss: #6b7280;
  box-shadow: 
    0 4px 12px rgba(0, 0, 0, 0.4),
    0 0 1px rgba(0, 0, 0, 0.2);
}

:root[data-theme="dark"] .toast__dismiss:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--toast-title);
}

:root[data-theme="dark"] .toast__progress {
  background: rgba(255, 255, 255, 0.1);
}

/* High contrast mode */
@media (prefers-contrast: high) {
  .toast {
    border: 2px solid var(--toast-accent);
  }
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .toast__progress-bar {
    transition: none;
  }
}
</style>
