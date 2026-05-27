<script setup lang="ts">
import { useToastStore } from '../stores/toast';
import ToastItem from './ToastItem.vue';

const toastStore = useToastStore();
</script>

<template>
  <Teleport to="body">
    <div 
      class="toast-container"
    >
      <TransitionGroup name="toast">
        <ToastItem
          v-for="toast in toastStore.activeToasts"
          :key="toast.id"
          :toast="toast"
          @dismiss="toastStore.removeToast(toast.id)"
        />
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 10000;
  display: flex;
  flex-direction: column-reverse;
  gap: 12px;
  max-width: 420px;
  width: 100%;
  pointer-events: none;
}

/* Responsive positioning */
@media (max-width: 480px) {
  .toast-container {
    bottom: 16px;
    right: 16px;
    left: 16px;
    max-width: none;
  }
}

/* Toast animations */
.toast-enter-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.toast-leave-active {
  transition: all 0.2s cubic-bezier(0.4, 0, 1, 1);
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(100%) scale(0.95);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(100%) scale(0.95);
}

.toast-move {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .toast-enter-active,
  .toast-leave-active,
  .toast-move {
    transition: opacity 0.15s ease;
  }
  
  .toast-enter-from,
  .toast-leave-to {
    transform: none;
  }
}
</style>
