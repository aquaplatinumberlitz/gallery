<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from "vue";
import type { Toast } from "../stores/toast";
import { CheckCircle, XCircle, TriangleAlert, Info, X } from "lucide-vue-next";

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- Lucide Vue component exports do not share a simple local component type across all icon imports.
const _icons: Record<string, any> = { CheckCircle, XCircle, TriangleAlert, Info };

const props = defineProps<{
  toast: Toast;
}>();

const emit = defineEmits<{
  (e: "dismiss"): void;
}>();

// Progress bar for auto-dismiss
const progress = ref(100);
const isPaused = ref(false);
let animationFrame: number | null = null;
let startTime: number | null = null;
let pausedProgress: number = 100;

const iconClass = computed(() => {
  switch (props.toast.type) {
    case "success":
      return "CheckCircle";
    case "error":
      return "XCircle";
    case "warning":
      return "TriangleAlert";
    case "info":
      return "Info";
    default:
      return "Info";
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
  emit("dismiss");
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
    role="alert"
    :class="[
      'toast flex items-start gap-3 py-3.5 px-4 bg-[var(--toast-bg,#fff)] rounded-xl pointer-events-auto relative overflow-hidden border-l-4 border-l-[var(--toast-accent)] shadow-[0_4px_12px_rgba(0,0,0,0.15),0_0_1px_rgba(0,0,0,0.1)] dark:shadow-[0_4px_12px_rgba(0,0,0,0.4),0_0_1px_rgba(0,0,0,0.2)]',
      typeClass,
    ]"
    @mouseenter="pauseProgress"
    @mouseleave="resumeProgress"
    @focusin="pauseProgress"
    @focusout="resumeProgress"
  >
    <!-- Icon -->
    <div class="toast__icon">
      <component :is="_icons[iconClass]" :stroke-width="1.5" class="icon-lg" />
    </div>

    <!-- Content -->
    <div class="toast__content">
      <div class="toast__title">{{ toast.title }}</div>
      <div v-if="toast.message && toast.html" class="toast__message" v-html="toast.message"></div>
      <div v-else-if="toast.message" class="toast__message">{{ toast.message }}</div>

      <!-- Action button -->
      <button v-if="toast.action" class="toast__action" type="button" @click="handleAction">
        {{ toast.action.label }}
      </button>
    </div>

    <!-- Dismiss button -->
    <button v-if="toast.dismissible" class="toast__dismiss" type="button" @click="emit('dismiss')">
      <X class="icon-sm" />
    </button>

    <!-- Progress bar -->
    <div v-if="toast.duration && toast.duration > 0" class="toast__progress">
      <div class="toast__progress-bar" :style="{ width: `${progress}%` }"></div>
    </div>
  </div>
</template>

<style scoped>
/* Toast item layout (flex, gap, padding, border-radius, shadows) handled by Tailwind utilities */
/* Keep type variants and interactive elements */

/* Type variants */
.toast--success {
  --toast-accent: var(--gallery-success, #22c55e);
  --toast-icon-color: var(--gallery-success, #22c55e);
  --toast-icon-bg: var(--gallery-success-bg, rgba(34, 197, 94, 0.1));
}

.toast--error {
  --toast-accent: var(--gallery-error, #ef4444);
  --toast-icon-color: var(--gallery-error, #ef4444);
  --toast-icon-bg: var(--gallery-error-bg, rgba(239, 68, 68, 0.1));
}

.toast--warning {
  --toast-accent: var(--gallery-warning, #f59e0b);
  --toast-icon-color: var(--gallery-warning, #f59e0b);
  --toast-icon-bg: var(--gallery-warning-bg, rgba(245, 158, 11, 0.1));
}

.toast--info {
  --toast-accent: var(--gallery-info, #3b82f6);
  --toast-icon-color: var(--gallery-info, #3b82f6);
  --toast-icon-bg: var(--gallery-info-bg, rgba(59, 130, 246, 0.1));
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
  color: var(--toast-title, var(--foreground));
  line-height: 1.4;
}

.toast__message {
  font-size: 13px;
  color: var(--toast-message, var(--muted-foreground));
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
  color: var(--toast-dismiss, var(--muted-foreground));
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
  --toast-bg: var(--popover);
  --toast-title: var(--foreground);
  --toast-message: var(--muted-foreground);
  --toast-dismiss: var(--muted-foreground);
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

/* Icon sizing tokens */
.icon-lg {
  width: var(--gallery-icon-lg);
  height: var(--gallery-icon-lg);
}

.icon-sm {
  width: var(--gallery-icon-sm);
  height: var(--gallery-icon-sm);
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .toast__progress-bar {
    transition: none;
  }
}
</style>
