<script setup lang="ts">
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:shadow-[var(--focus-ring-shadow)] disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-white hover:bg-primary-hover shadow-sm",
        destructive:
          "bg-error text-white hover:bg-error/90",
        outline:
          "border border-border bg-surface text-foreground hover:bg-surface-hover hover:text-primary hover:border-primary",
        secondary:
          "bg-surface-hover text-foreground hover:bg-surface-elevated",
        ghost:
          "text-foreground hover:bg-surface-hover hover:text-primary",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-lg px-6",
        icon: "h-[38px] w-[38px] rounded-[10px] border border-border bg-surface text-foreground hover:text-primary hover:border-primary hover:shadow-md hover:-translate-y-px active:scale-[0.98] transition-all duration-[120ms] ease-gallery",
        "icon-sm": "size-8 rounded-md bg-transparent text-muted-foreground hover:text-foreground hover:bg-surface-hover active:scale-95",
        nav: "h-10 w-10 rounded-xl border border-border bg-transparent text-foreground inline-flex items-center justify-center cursor-pointer transition-all duration-[120ms] ease-gallery disabled:opacity-40 disabled:cursor-not-allowed enabled:hover:border-primary enabled:hover:bg-black/5 dark:enabled:hover:bg-white/5 enabled:hover:shadow-sm enabled:hover:-translate-y-px",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

type ButtonVariants = VariantProps<typeof buttonVariants>;

interface Props {
  variant?: ButtonVariants["variant"];
  size?: ButtonVariants["size"];
  class?: string;
  disabled?: boolean;
  type?: "button" | "submit" | "reset";
}

withDefaults(defineProps<Props>(), {
  variant: "default",
  size: "default",
  type: "button",
});
</script>

<template>
  <button
    :type="type"
    :disabled="disabled"
    :class="cn(buttonVariants({ variant, size }), $props.class)"
  >
    <slot />
  </button>
</template>
