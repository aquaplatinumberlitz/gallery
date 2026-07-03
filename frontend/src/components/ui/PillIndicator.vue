<script setup lang="ts">
import type { HTMLAttributes } from "vue";
import { cn } from "@/lib/utils";

type PillIndicatorVariant = "success" | "error" | "warning" | "info" | "muted";

const props = withDefaults(
  defineProps<{
    variant?: PillIndicatorVariant;
    pulse?: boolean;
    class?: HTMLAttributes["class"];
  }>(),
  {
    variant: "success",
    pulse: false,
    class: undefined,
  },
);

const pulseClasses: Record<PillIndicatorVariant, string> = {
  success: "bg-emerald-400",
  error: "bg-rose-400",
  warning: "bg-amber-400",
  info: "bg-sky-400",
  muted: "bg-gray-400",
};

const indicatorClasses: Record<PillIndicatorVariant, string> = {
  success: "bg-emerald-500",
  error: "bg-rose-500",
  warning: "bg-amber-500",
  info: "bg-sky-500",
  muted: "bg-gray-500",
};
</script>

<template>
  <span :class="cn('relative flex size-[6.8px]', props.class)">
    <span
      v-if="pulse"
      :class="
        cn(
          'absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 motion-reduce:animate-none',
          pulseClasses[variant],
        )
      "
    />
    <span :class="cn('relative inline-flex h-full w-full rounded-full', indicatorClasses[variant])" />
  </span>
</template>
