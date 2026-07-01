<script setup lang="ts">
import type { HTMLAttributes } from "vue";
import Button from "@/components/ui/Button.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

defineOptions({
  inheritAttrs: false,
});

const props = withDefaults(
  defineProps<{
    label: string;
    tooltip?: string;
    variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
    size?: "default" | "sm" | "lg" | "icon" | "icon-sm";
    class?: HTMLAttributes["class"];
    side?: "top" | "right" | "bottom" | "left";
    align?: "start" | "center" | "end";
  }>(),
  {
    tooltip: undefined,
    variant: "ghost",
    size: "icon",
    class: undefined,
    side: "top",
    align: "center",
  },
);
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <Button :variant="variant" :size="size" :class="props.class" :aria-label="label" v-bind="$attrs">
        <slot />
      </Button>
    </TooltipTrigger>
    <TooltipContent :side="side" :align="align">{{ tooltip || label }}</TooltipContent>
  </Tooltip>
</template>
