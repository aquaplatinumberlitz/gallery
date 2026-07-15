<script setup lang="ts">
import { computed, shallowRef } from "vue";
import { ChevronDown } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import type { FacetEntry } from "@/types";

interface IndexedFacetGroup {
  id: string;
  label: string;
  field?: string;
  entries: FacetEntry[];
}

interface Props {
  groups: IndexedFacetGroup[];
  initialVisible?: number;
}

const props = withDefaults(defineProps<Props>(), {
  initialVisible: 4,
});

const emit = defineEmits<{
  apply: [field: string, value: string];
}>();

const expandedGroupIds = shallowRef<Set<string>>(new Set());
const countFormatter = new Intl.NumberFormat();

const visibleEntryLimit = computed(() => Math.max(1, props.initialVisible));
const hasIndexedValues = computed(() => props.groups.some((group) => group.entries.length > 0));
const facetGroups = computed(() =>
  props.groups.map((group) => {
    const expanded = expandedGroupIds.value.has(group.id);
    const overflowCount = Math.max(0, group.entries.length - visibleEntryLimit.value);
    return {
      ...group,
      expanded,
      overflowCount,
      visibleEntries: expanded ? group.entries : group.entries.slice(0, visibleEntryLimit.value),
    };
  }),
);

function formatCount(count: number) {
  return countFormatter.format(count);
}

function toggleGroup(groupId: string) {
  const next = new Set(expandedGroupIds.value);
  if (next.has(groupId)) next.delete(groupId);
  else next.add(groupId);
  expandedGroupIds.value = next;
}
</script>

<template>
  <section v-if="hasIndexedValues" class="mb-4" aria-labelledby="indexed-facets-title">
    <div class="mb-2">
      <p id="indexed-facets-title" class="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Indexed facets
      </p>
      <p class="mt-0.5 text-xs text-muted-foreground">Values available in the current search scope.</p>
    </div>

    <div class="overflow-hidden rounded-lg border bg-background">
      <div
        v-for="(group, index) in facetGroups"
        :key="group.id"
        class="grid min-w-0 gap-2 px-3 py-2.5 sm:grid-cols-[7rem_minmax(0,1fr)] sm:gap-3"
        :class="index > 0 ? 'border-t' : ''"
      >
        <div class="flex items-baseline justify-between gap-3 sm:block">
          <p class="text-sm font-medium text-foreground">{{ group.label }}</p>
          <p class="text-xs tabular-nums text-muted-foreground">
            {{ group.entries.length }} {{ group.entries.length === 1 ? "value" : "values" }}
          </p>
        </div>

        <div class="min-w-0">
          <ul
            v-if="group.visibleEntries.length"
            :id="`indexed-facet-${group.id}`"
            class="flex min-w-0 flex-wrap gap-1.5"
            :aria-label="`${group.label} indexed values`"
          >
            <li
              v-for="entry in group.visibleEntries"
              :key="entry.value"
              class="inline-flex max-w-full items-baseline gap-1.5 rounded-md bg-muted px-2 py-1 text-xs"
              :class="group.field ? 'p-0 bg-transparent' : ''"
            >
              <button
                v-if="group.field"
                type="button"
                class="inline-flex max-w-full items-baseline gap-1.5 rounded-md bg-muted px-2 py-1 text-xs transition-colors hover:bg-accent focus-visible:outline-none focus-visible:[box-shadow:var(--focus-ring-shadow)]"
                :aria-label="`Filter by ${group.label}: ${entry.value} (${formatCount(entry.count)} assets)`"
                @click="emit('apply', group.field!, entry.value)"
              >
                <span class="min-w-0 break-words text-foreground">{{ entry.value }}</span>
                <span
                  class="shrink-0 font-medium tabular-nums text-muted-foreground"
                  :aria-label="`${formatCount(entry.count)} assets`"
                >
                  {{ formatCount(entry.count) }}
                </span>
              </button>
              <template v-else>
                <span class="min-w-0 break-words text-foreground">{{ entry.value }}</span>
                <span
                  class="shrink-0 font-medium tabular-nums text-muted-foreground"
                  :aria-label="`${formatCount(entry.count)} assets`"
                >
                  {{ formatCount(entry.count) }}
                </span>
              </template>
            </li>
          </ul>
          <p v-else :id="`indexed-facet-${group.id}`" class="text-xs text-muted-foreground">None indexed</p>

          <Button
            v-if="group.overflowCount > 0"
            type="button"
            variant="ghost"
            size="sm"
            class="mt-1 h-8 justify-start px-2 text-xs text-muted-foreground"
            :aria-expanded="group.expanded"
            :aria-controls="`indexed-facet-${group.id}`"
            @click="toggleGroup(group.id)"
          >
            <ChevronDown
              class="transition-transform duration-200 motion-reduce:transition-none"
              :class="group.expanded ? 'rotate-180' : ''"
            />
            {{ group.expanded ? "Show less" : `Show ${group.overflowCount} more` }}
          </Button>
        </div>
      </div>
    </div>
  </section>
</template>
