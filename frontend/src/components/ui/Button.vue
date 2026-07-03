<script setup lang="ts">
import { Primitive, type PrimitiveProps } from "reka-ui";
import { type HTMLAttributes } from "vue";
import { cn } from "@/lib/utils";

const props = withDefaults(
  defineProps<
    PrimitiveProps & {
      variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
      size?: "default" | "sm" | "lg" | "icon" | "icon-sm" | "icon-lg";
      class?: HTMLAttributes["class"];
    }
  >(),
  { as: "button", variant: "default", size: "default", class: undefined },
);
</script>

<template>
  <Primitive
    :as="as"
    :as-child="asChild"
    :class="
      cn(
        'inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
        variant === 'default' && 'bg-primary text-primary-foreground shadow hover:bg-primary/90',
        variant === 'destructive' && 'bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90',
        variant === 'outline' &&
          'border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground',
        variant === 'secondary' && 'bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80',
        variant === 'ghost' && 'hover:bg-accent hover:text-accent-foreground',
        variant === 'link' && 'text-primary underline-offset-4 hover:underline',
        size === 'default' && 'h-10 px-4 py-2',
        size === 'sm' && 'h-9 rounded-md px-3',
        size === 'lg' && 'h-11 rounded-md px-8',
        size === 'icon' && 'h-10 w-10',
        size === 'icon-sm' && 'size-9',
        size === 'icon-lg' && 'size-11',
        props.class,
      )
    "
    v-bind="$attrs"
  >
    <slot />
  </Primitive>
</template>
