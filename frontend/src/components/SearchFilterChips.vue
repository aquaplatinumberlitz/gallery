<script setup lang="ts">
import { X } from 'lucide-vue-next'
import Badge from '@/components/ui/Badge.vue'

interface Props {
  filters: string[]
}

defineProps<Props>()

const emit = defineEmits<{
  remove: [index: number]
}>()
</script>

<template>
  <div v-if="filters.length > 0" class="flex flex-wrap gap-2">
    <Badge
      v-for="(filter, index) in filters"
      :key="index"
      variant="secondary"
      class="gap-1 pl-2.5 pr-1.5 py-1 text-xs cursor-default"
    >
      {{ filter }}
      <button
        class="ml-0.5 rounded-sm hover:bg-accent hover:text-accent-foreground inline-flex items-center justify-center size-4 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        @click="emit('remove', index)"
        :aria-label="`Remove filter: ${filter}`"
      >
        <X class="size-3" />
      </button>
    </Badge>
  </div>
</template>
