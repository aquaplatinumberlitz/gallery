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
  <div v-if="filters.length > 0" class="flex flex-wrap items-center gap-2" data-testid="search-filter-chips">
    <Badge
      v-for="(filter, index) in filters"
      :key="index"
      variant="secondary"
      class="search-filter-chip gap-1 pl-2.5 pr-1.5 py-1 text-xs cursor-default"
    >
      {{ filterToDisplayString(filter) }}
      <button
        class="search-filter-remove ml-0.5 rounded-sm hover:bg-accent hover:text-accent-foreground inline-flex items-center justify-center size-4 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        @click="emit('remove', index)"
        :aria-label="`Remove filter: ${filterToDisplayString(filter)}`"
      >
        <X class="size-3" />
      </button>
    </Badge>
    <button
      v-if="filters.length > 1"
      class="search-filter-clear text-xs text-muted-foreground hover:text-foreground underline cursor-pointer rounded-sm focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
      @click="emit('clearAll')"
    >
      Clear All
    </button>
  </div>
</template>

<style scoped>
.search-filter-remove {
  width: 44px;
  height: 44px;
  margin-block: -0.375rem;
  margin-right: -0.375rem;
}

@media (max-width: 1023px) {
  .search-filter-chip {
    min-height: 44px;
    padding-block: 0.375rem;
  }

  .search-filter-clear {
    min-height: 44px;
    padding: 0.625rem 0.5rem;
  }
}
</style>
