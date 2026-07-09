<script setup lang="ts">
import type { HTMLAttributes } from "vue";
import Button from "@/components/ui/Button.vue";
import CopyStateIcon from "@/components/ui/CopyStateIcon.vue";

defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    copied: boolean;
    label: string;
    copiedLabel?: string;
    successAriaLabel: string;
    variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
    size?: "default" | "sm" | "lg" | "icon" | "icon-sm" | "icon-lg";
    class?: HTMLAttributes["class"];
  }>(),
  {
    copiedLabel: "Copied",
    variant: "secondary",
    size: "sm",
    class: undefined,
  },
);

const emit = defineEmits<{
  click: [event: MouseEvent];
}>();
</script>

<template>
  <Button
    v-bind="$attrs"
    :variant="variant"
    :size="size"
    :class="['border border-border/60', props.class]"
    :aria-label="copied ? successAriaLabel : label"
    :data-copied="copied ? 'true' : 'false'"
    @pointerdown.stop
    @click.stop.prevent="emit('click', $event)"
  >
    <CopyStateIcon :copied="copied" />
    {{ copied ? copiedLabel : label }}
  </Button>
</template>
