<script setup lang="ts">
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const badgeVariants = cva(
  "inline-flex gap-1 items-center rounded-full border border-border px-2.5 py-0.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
        secondary: "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive: "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80",
        outline: "text-foreground",
        loading: "border-transparent bg-accent text-accent-foreground", // local extension
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

type BadgeVariants = VariantProps<typeof badgeVariants>;

interface Props {
  variant?: BadgeVariants["variant"];
  class?: string;
}

withDefaults(defineProps<Props>(), {
  variant: "default",
  class: undefined,
});
</script>

<template>
  <div :class="cn(badgeVariants({ variant }), $props.class)">
    <slot />
  </div>
</template>
