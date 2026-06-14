<script setup lang="ts">
import type { HTMLAttributes } from "vue";
import { cn } from "../../lib/utils";

defineProps<{
  class?: HTMLAttributes["class"];
  disabled?: boolean;
  title?: string;
}>();

const emit = defineEmits<{
  (e: "click", event: MouseEvent): void;
}>();
</script>

<template>
  <button
    type="button"
    :class="
      cn(
        'text-sm text-muted-foreground hover:text-foreground px-2 py-1 transition-colors max-w-[150px] truncate',
        disabled && 'opacity-50 cursor-default',
        $props.class,
      )
    "
    :disabled="disabled"
    :title="title"
    @click="!disabled && emit('click', $event)"
  >
    <slot />
  </button>
</template>
