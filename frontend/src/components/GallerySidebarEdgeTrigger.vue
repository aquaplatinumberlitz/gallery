<script setup lang="ts">
import { ChevronLeft, ChevronRight } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useSidebar } from "@/components/ui/sidebar";

const { state } = useSidebar();
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <Button
        variant="ghost"
        size="icon"
        class="gallery-sidebar-edge-trigger border border-border bg-background shadow-xs"
        :data-state="state"
        type="button"
        :aria-label="state === 'expanded' ? 'Hide Sidebar' : 'Show Sidebar'"
        @click="$emit('toggle')"
      >
        <ChevronLeft v-if="state === 'expanded'" class="gallery-icon-sm" />
        <ChevronRight v-else class="gallery-icon-sm" />
      </Button>
    </TooltipTrigger>
    <TooltipContent>{{ state === 'expanded' ? 'Hide Sidebar' : 'Show Sidebar' }}</TooltipContent>
  </Tooltip>
</template>

<style scoped>
.gallery-sidebar-edge-trigger {
  position: fixed;
  left: calc(var(--sidebar-width) - 20px);
  top: 50%;
  transform: translateY(-50%);
  z-index: 101;
  width: 24px;
  height: 48px;
  border-radius: 0 8px 8px 0;
  transition: all 0.3s ease;
}

.gallery-sidebar-edge-trigger[data-state="collapsed"] {
  left: 0;
  border-radius: 0 8px 8px 0;
}

.gallery-icon-sm {
  width: var(--gallery-icon-sm);
  height: var(--gallery-icon-sm);
}
</style>
