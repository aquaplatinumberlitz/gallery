<script setup lang="ts">
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-2 rounded-xl px-3 py-2 text-[13px] font-medium transition-colors focus:outline-none",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-surface-hover text-foreground",
        secondary:
          "border-transparent bg-muted text-muted-foreground",
        destructive:
          "border-transparent bg-error-bg text-error",
        outline: "text-foreground border border-border",
        loading:
          "bg-black/5 text-foreground dark:bg-white/5",
        subtle:
          "opacity-70",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

type BadgeVariants = VariantProps<typeof badgeVariants>;

interface Props {
  variant?: BadgeVariants["variant"];
  class?: string;
}

withDefaults(defineProps<Props>(), {
  variant: "default",
});
</script>

<template>
  <span :class="cn(badgeVariants({ variant }), $props.class)">
    <slot />
  </span>
</template>
