<script setup lang="ts">
import { useToastStore } from "../stores/toast";
import ToastItem from "./ToastItem.vue";

const toastStore = useToastStore();
</script>

<template>
  <Teleport to="body">
    <div
      class="toast-container fixed bottom-6 right-6 z-[10000] flex flex-col-reverse gap-3 max-w-[420px] w-full pointer-events-none max-[480px]:bottom-4 max-[480px]:right-4 max-[480px]:left-4 max-[480px]:max-w-none"
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
/* Container positioning and layout handled by Tailwind utilities */
/* Only animation and reduced motion rules remain */

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
