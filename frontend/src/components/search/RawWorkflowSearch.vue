<script setup lang="ts">
import { computed, shallowRef } from "vue";
import { useMutation } from "@tanstack/vue-query";
import { AlertTriangle, Search } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import { searchRawWorkflows } from "@/services/api";
import type { RawWorkflowSearchResponseV1, SearchCapabilitiesV1, SearchScopeV1 } from "@/types";

const props = defineProps<{ capability: SearchCapabilitiesV1["raw_search"]; scope: SearchScopeV1 | null }>();
const acknowledged = shallowRef(false);
const term = shallowRef("");
const result = shallowRef<RawWorkflowSearchResponseV1 | null>(null);
const validation = computed(() => {
  const length = term.value.trim().length;
  if (!acknowledged.value) return "Acknowledge the cost before searching.";
  if (length < props.capability.query_min_chars || length > props.capability.query_max_chars) {
    return `Enter ${props.capability.query_min_chars}-${props.capability.query_max_chars} characters.`;
  }
  return "";
});

const rawSearch = useMutation({
  mutationFn: (cursor: string | null = null) =>
    searchRawWorkflows({ query: term.value.trim(), scope: props.scope!, cursor, limit: props.capability.limit_max }),
  onSuccess: (data, cursor) => {
    result.value = cursor && result.value ? { ...data, items: [...result.value.items, ...data.items] } : data;
  },
});

function apply(cursor: string | null = null) {
  if (!props.scope || validation.value) return;
  rawSearch.mutate(cursor);
}
</script>

<template>
  <section class="raw-search" aria-labelledby="raw-search-title">
    <div class="warning">
      <AlertTriangle />
      <div>
        <p id="raw-search-title">Raw workflow search</p>
        <span>Expensive literal search over bounded canonical JSON. It never runs while you type.</span>
      </div>
    </div>
    <label class="acknowledgement"
      ><input v-model="acknowledged" type="checkbox" /> I understand this can take up to
      {{ capability.deadline_ms }} ms.</label
    >
    <div class="apply-row">
      <Input
        v-model="term"
        aria-label="Raw workflow search term"
        :maxlength="capability.query_max_chars"
        placeholder="Exact workflow fragment"
        @keydown.enter.prevent="apply()"
      /><Button type="button" :disabled="Boolean(validation) || rawSearch.isPending.value || !scope" @click="apply()">
        <Search /> Apply
      </Button>
    </div>
    <p v-if="validation && term" class="validation">{{ validation }}</p>
    <p v-if="rawSearch.isError.value" class="validation" role="alert">
      {{ rawSearch.error.value instanceof Error ? rawSearch.error.value.message : "Raw search failed." }}
    </p>
    <div v-if="result" class="raw-results" aria-live="polite">
      <p>{{ result.returned }} result{{ result.returned === 1 ? "" : "s" }}</p>
      <ul>
        <li v-for="item in result.items" :key="`${item.library_id}:${item.asset_id}`">
          <span>{{ item.name }}</span
          ><small>{{ item.library_name }}</small>
        </li>
      </ul>
      <Button
        v-if="result.has_more"
        type="button"
        variant="outline"
        size="sm"
        :disabled="rawSearch.isPending.value"
        @click="apply(result.next_cursor)"
      >
        Load more
      </Button>
    </div>
  </section>
</template>

<style scoped>
.raw-search {
  display: grid;
  gap: 11px;
}
.warning {
  display: flex;
  gap: 9px;
  border: 1px solid color-mix(in srgb, var(--warning, #b7791f) 45%, var(--border));
  border-radius: 9px;
  padding: 10px;
  background: color-mix(in srgb, #b7791f 8%, var(--background));
}
.warning svg {
  width: 18px;
  flex: none;
  color: #b7791f;
}
.warning p {
  font-size: 14px;
  font-weight: 650;
}
.warning span,
.acknowledgement,
.validation {
  font-size: 12px;
  color: var(--muted-foreground);
}
.acknowledgement {
  display: flex;
  align-items: center;
  gap: 8px;
}
.acknowledgement input {
  width: 16px;
  height: 16px;
}
.apply-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}
.validation {
  color: var(--destructive);
}
.raw-results {
  display: grid;
  gap: 8px;
}
.raw-results > p {
  font-size: 12px;
  font-weight: 600;
}
.raw-results ul {
  display: grid;
  max-height: 180px;
  gap: 5px;
  overflow-y: auto;
}
.raw-results li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-bottom: 1px solid var(--border);
  padding: 6px 2px;
  font-size: 12px;
}
.raw-results small {
  color: var(--muted-foreground);
}
</style>
