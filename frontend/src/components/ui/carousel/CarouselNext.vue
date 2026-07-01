<script setup lang="ts">
import { computed, useAttrs } from "vue";
import type { WithClassAsProps } from "./interface";
import { ArrowRight } from "lucide-vue-next";
import { cn } from "@/lib/utils";
import Button from "@/components/ui/Button.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useCarousel } from "./useCarousel";

defineOptions({
  inheritAttrs: false,
});

const props = defineProps<WithClassAsProps>();
const attrs = useAttrs();

const { orientation, canScrollNext, scrollNext } = useCarousel();
const label = computed(() => String(attrs["aria-label"] || "Next slide"));
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <Button
        v-bind="attrs"
        :disabled="!canScrollNext"
        :class="
          cn(
            'touch-manipulation absolute h-8 w-8 rounded-full p-0',
            orientation === 'horizontal'
              ? '-right-12 top-1/2 -translate-y-1/2'
              : '-bottom-12 left-1/2 -translate-x-1/2 rotate-90',
            props.class,
          )
        "
        variant="outline"
        :aria-label="label"
        @click="scrollNext"
      >
        <slot>
          <ArrowRight class="h-4 w-4 text-current" />
          <span class="sr-only">Next Slide</span>
        </slot>
      </Button>
    </TooltipTrigger>
    <TooltipContent>{{ label }}</TooltipContent>
  </Tooltip>
</template>
