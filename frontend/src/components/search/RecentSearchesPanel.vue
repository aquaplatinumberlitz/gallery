<script setup lang="ts">
import { computed, shallowRef } from "vue";
import { ChevronDown, ChevronRight, History } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import { useRecentSearches } from "@/composables/useRecentSearches";
import type { PersistableSearchRequestV1 } from "@/types";

const emit = defineEmits<{
  apply: [request: PersistableSearchRequestV1];
}>();

const history = useRecentSearches();
const showAll = shallowRef(false);
const initialVisibleCount = 5;

const visibleSearches = computed(() =>
  showAll.value ? history.recent.value : history.recent.value.slice(0, initialVisibleCount),
);
const hiddenSearchCount = computed(() => Math.max(0, history.recent.value.length - initialVisibleCount));

function structuredFilterLabels(request: PersistableSearchRequestV1) {
  const labels: string[] = [];
  const promptGroups = request.filters.prompt_groups;
  const workflowGroups = request.filters.workflow_groups;

  if (promptGroups.length === 1) {
    labels.push(`Exact ${promptGroups[0]?.kind} prompt`);
  } else if (promptGroups.length > 1) {
    labels.push(`${promptGroups.length} exact prompt groups`);
  }

  if (workflowGroups.length === 1) {
    labels.push(`${workflowGroups[0]?.node_type} workflow filter`);
  } else if (workflowGroups.length > 1) {
    labels.push(`${workflowGroups.length} workflow filters`);
  }

  return labels;
}

function primaryLabel(request: PersistableSearchRequestV1) {
  if (request.text) return request.text;
  return structuredFilterLabels(request).join(" · ") || "Filtered search";
}

function scopeLabel(request: PersistableSearchRequestV1) {
  if (request.scope.kind === "all") return "All libraries";
  if (request.scope.kind === "library") return "Library";
  return request.scope.relative_path ? `Folder · ${request.scope.relative_path}` : "Library root";
}

function secondaryLabel(request: PersistableSearchRequestV1) {
  return [scopeLabel(request), ...structuredFilterLabels(request)].join(" · ");
}

function clearHistory() {
  if (history.clear()) showAll.value = false;
}
</script>

<template>
  <section class="recent-searches" aria-labelledby="recent-searches-title">
    <div class="recent-header">
      <div class="min-w-0">
        <p id="recent-searches-title" class="recent-title"><History aria-hidden="true" /> Recent searches</p>
        <p class="recent-copy">Successful searches are kept only in this browser.</p>
      </div>
      <Button
        v-if="history.recent.value.length"
        type="button"
        variant="ghost"
        size="sm"
        class="recent-clear"
        @click="clearHistory"
      >
        Clear history
      </Button>
    </div>

    <div v-if="history.recent.value.length === 0" class="recent-empty">
      Your recent searches will appear here automatically.
    </div>

    <ul v-else id="recent-search-list" class="recent-list" aria-label="Recent searches">
      <li v-for="item in visibleSearches" :key="`${item.used_at}-${primaryLabel(item.request)}`">
        <button
          type="button"
          class="recent-row"
          :aria-label="`Run recent search: ${primaryLabel(item.request)}. ${secondaryLabel(item.request)}`"
          @click="emit('apply', item.request)"
        >
          <span class="recent-icon" aria-hidden="true"><History /></span>
          <span class="recent-content">
            <span class="recent-query">{{ primaryLabel(item.request) }}</span>
            <span class="recent-meta">{{ secondaryLabel(item.request) }}</span>
          </span>
          <ChevronRight class="recent-chevron" aria-hidden="true" />
        </button>
      </li>
    </ul>

    <Button
      v-if="hiddenSearchCount > 0"
      type="button"
      variant="ghost"
      size="sm"
      class="recent-show-more"
      :aria-expanded="showAll"
      aria-controls="recent-search-list"
      @click="showAll = !showAll"
    >
      <ChevronDown :class="['recent-expand-icon', showAll ? 'rotate-180' : '']" />
      {{ showAll ? "Show less" : `Show ${hiddenSearchCount} more` }}
    </Button>
  </section>
</template>

<style scoped>
.recent-searches {
  display: grid;
  gap: 10px;
}

.recent-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.recent-title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
  font-weight: 650;
}

.recent-title svg,
.recent-icon svg,
.recent-chevron,
.recent-expand-icon {
  width: 16px;
  height: 16px;
}

.recent-copy,
.recent-meta,
.recent-empty {
  color: var(--muted-foreground);
  font-size: 12px;
}

.recent-clear {
  height: 32px;
  flex: none;
  padding-inline: 8px;
  color: var(--muted-foreground);
}

.recent-empty {
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 14px;
  background: color-mix(in srgb, var(--muted) 45%, transparent);
  line-height: 1.5;
}

.recent-list {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--background);
}

.recent-list li:first-child .recent-row {
  border-radius: 7px 7px 0 0;
}

.recent-list li:last-child .recent-row {
  border-radius: 0 0 7px 7px;
}

.recent-list li:only-child .recent-row {
  border-radius: 7px;
}

.recent-list li + li {
  border-top: 1px solid var(--border);
}

.recent-row {
  display: grid;
  width: 100%;
  min-height: 54px;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 9px 11px;
  text-align: left;
  transition: background-color 180ms var(--ease-gallery);
}

.recent-row:hover {
  background: var(--muted);
}

.recent-row:focus-visible {
  position: relative;
  z-index: 1;
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

.recent-row:active {
  background: var(--accent);
}

.recent-icon {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 50%;
  background: var(--muted);
  color: var(--muted-foreground);
}

.recent-content {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.recent-query,
.recent-meta {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-query {
  color: var(--foreground);
  font-size: 13px;
  font-weight: 600;
}

.recent-chevron {
  color: var(--muted-foreground);
}

.recent-show-more {
  min-height: 36px;
  justify-self: start;
  padding-inline: 8px;
  color: var(--muted-foreground);
}

.recent-expand-icon {
  transition: transform 180ms var(--ease-gallery);
}

@media (hover: none) {
  .recent-row:hover {
    background: var(--background);
  }
}

@media (max-width: 1023px) {
  .recent-clear,
  .recent-show-more {
    min-height: 44px;
  }

  .recent-row {
    min-height: 58px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .recent-row,
  .recent-expand-icon {
    transition: none;
  }
}
</style>
