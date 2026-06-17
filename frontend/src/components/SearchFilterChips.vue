<script setup lang="ts">
import { X } from "lucide-vue-next";
import Badge from "@/components/ui/Badge.vue";
import type { FieldFilter } from "@/types";
import { filterToDisplayString } from "@/utils/serializeAdvancedSearchToQuery";

interface Props {
  filters: FieldFilter[];
}

defineProps<Props>();

const emit = defineEmits<{
  remove: [index: number];
  clearAll: [];
}>();
</script>

<template>
  <div
    v-if="filters.length > 0"
    class="flex flex-wrap items-center gap-2"
  >
    <Badge
      v-for="(filter, index) in filters"
      :key="index"
      variant="secondary"
      class="gap-1 pl-2.5 pr-1.5 py-1 text-xs cursor-default"
    >
      {{ filterToDisplayString(filter) }}
      <button
        class="ml-0.5 rounded-sm hover:bg-accent hover:text-accent-foreground inline-flex items-center justify-center size-4 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        @click="emit('remove', index)"
        :aria-label="`Remove filter: ${filterToDisplayString(filter)}`"
      >
        <X class="size-3" />
      </button>
    </Badge>
    <button
      v-if="filters.length > 1"
      class="text-xs text-muted-foreground hover:text-foreground underline cursor-pointer"
      @click="emit('clearAll')"
    >
      Clear All
    </button>
  </div>
</template>
