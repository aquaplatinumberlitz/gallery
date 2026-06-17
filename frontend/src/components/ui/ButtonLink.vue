<script setup lang="ts">
import type { HTMLAttributes } from "vue";
import type { RouterLinkProps } from "vue-router";
import { RouterLink } from "vue-router";
import { buttonVariants, type ButtonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const props = withDefaults(
  defineProps<{
    to: RouterLinkProps["to"];
    replace?: boolean;
    variant?: ButtonVariants["variant"];
    size?: ButtonVariants["size"];
    class?: HTMLAttributes["class"];
  }>(),
  {
    replace: false,
    variant: "ghost",
    size: "sm",
  },
);
</script>

<template>
  <RouterLink :to="to" :replace="replace" :class="cn(buttonVariants({ variant, size }), props.class)">
    <slot />
  </RouterLink>
</template>
