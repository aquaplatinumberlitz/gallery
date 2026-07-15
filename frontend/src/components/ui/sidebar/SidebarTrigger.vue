<script setup lang="ts">
import type { HTMLAttributes } from "vue";
import { ChevronLeft, ChevronRight } from "lucide-vue-next";
import { computed } from "vue";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useSidebar } from "./utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const props = defineProps<{
  class?: HTMLAttributes["class"];
}>();

const { state, toggleSidebar } = useSidebar();

const label = computed(() => (state.value === "expanded" ? "Collapse sidebar" : "Expand sidebar"));
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <Button
        data-sidebar="trigger"
        variant="ghost"
        size="icon"
        :class="cn('h-7 w-7', props.class)"
        :aria-label="label"
        @click="toggleSidebar"
      >
        <ChevronLeft v-if="state === 'expanded'" />
        <ChevronRight v-else />
      </Button>
    </TooltipTrigger>
    <TooltipContent side="right" align="center">{{ label }}</TooltipContent>
  </Tooltip>
</template>
