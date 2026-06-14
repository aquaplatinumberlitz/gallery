<script setup lang="ts">
import { cn } from "../../lib/utils";

interface Props {
  class?: string;
  orientation?: "horizontal" | "vertical";
  decorative?: boolean;
  label?: string;
}

withDefaults(defineProps<Props>(), {
  orientation: "horizontal",
  decorative: true,
});
</script>

<template>
  <div
    :data-orientation="orientation"
    :role="decorative ? 'none' : 'separator'"
    :aria-orientation="decorative ? undefined : orientation"
    :aria-label="!decorative && label ? label : undefined"
    :class="
      cn(
        'shrink-0 bg-border',
        orientation === 'horizontal' ? 'h-px w-full' : 'h-full w-px',
        $props.class,
      )
    "
  />
</template>
