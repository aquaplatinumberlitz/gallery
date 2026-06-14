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
    data-reka-collection-item
    :class="
      cn(
        'transition-colors hover:text-foreground',
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
