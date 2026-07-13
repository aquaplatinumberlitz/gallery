<script setup lang="ts">
import { Columns3, Search, X } from "lucide-vue-next";
import Badge from "@/components/ui/Badge.vue";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import SortSelect from "@/components/SortSelect.vue";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { PromptPresenceFilter, SortValue } from "@/types";

interface ColumnOption {
  id: string;
  label: string;
}

defineProps<{
  activeFilterCount: number;
  modelOptions: string[];
  columns: ColumnOption[];
  hiddenColumnIds: string[];
}>();

const emit = defineEmits<{
  toggleColumn: [id: string, visible: boolean];
}>();

const query = defineModel<string>("query", { required: true });
const modelFilter = defineModel<string>("modelFilter", { required: true });
const promptFilter = defineModel<PromptPresenceFilter>("promptFilter", { required: true });
const sort = defineModel<SortValue>("sort", { required: true });
</script>

<template>
  <div class="table-toolbar">
    <div class="inspector-search relative">
      <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground/80" />
      <Input
        id="metadata-table-search"
        v-model="query"
        name="metadata-table-search"
        type="search"
        class="inspector-search-input h-10 pl-9 pr-9 shadow-sm focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
        placeholder="Search metadata, prompt, model, seed..."
        aria-label="Search metadata table"
      />
      <button
        v-if="query"
        type="button"
        class="search-clear-button"
        aria-label="Clear metadata search"
        @click="query = ''"
      >
        <X class="size-4" aria-hidden="true" />
      </button>
    </div>

    <Badge v-if="activeFilterCount" variant="secondary" class="filter-count-badge">
      {{ activeFilterCount }} {{ activeFilterCount === 1 ? "filter" : "filters" }}
    </Badge>

    <Select v-model="modelFilter">
      <SelectTrigger class="metadata-toolbar-trigger toolbar-select">
        <SelectValue placeholder="Model" />
      </SelectTrigger>
      <SelectContent align="end">
        <SelectGroup>
          <SelectItem value="all">All models</SelectItem>
          <SelectItem v-for="model in modelOptions" :key="model" :value="model">{{ model }}</SelectItem>
        </SelectGroup>
      </SelectContent>
    </Select>

    <Select v-model="promptFilter">
      <SelectTrigger class="metadata-toolbar-trigger toolbar-select">
        <SelectValue placeholder="Has prompt" />
      </SelectTrigger>
      <SelectContent align="end">
        <SelectGroup>
          <SelectItem value="all">All prompts</SelectItem>
          <SelectItem value="has_prompt">Has prompt</SelectItem>
          <SelectItem value="no_prompt">No prompt</SelectItem>
        </SelectGroup>
      </SelectContent>
    </Select>

    <SortSelect
      v-model="sort"
      aria-label="Sort metadata table"
      trigger-class="h-10 w-[150px] border-input bg-background text-sm font-normal text-foreground shadow-sm"
    />

    <DropdownMenu>
      <DropdownMenuTrigger as-child>
        <Button
          variant="outline"
          type="button"
          class="metadata-toolbar-trigger toolbar-view-button"
          aria-label="Toggle metadata table columns"
        >
          <span class="inline-flex min-w-0 items-center gap-2">
            <Columns3 class="size-4 opacity-60" aria-hidden="true" />
            <span class="truncate">View</span>
          </span>
          <span v-if="hiddenColumnIds.length" class="toolbar-count-pill" aria-hidden="true">
            {{ hiddenColumnIds.length }}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel class="text-xs text-muted-foreground">Columns</DropdownMenuLabel>
        <DropdownMenuGroup>
          <DropdownMenuCheckboxItem
            v-for="column in columns"
            :key="column.id"
            :model-value="!hiddenColumnIds.includes(column.id)"
            @update:model-value="(value: boolean | 'indeterminate') => emit('toggleColumn', column.id, !!value)"
            @select="(event: Event) => event.preventDefault()"
          >
            {{ column.label }}
          </DropdownMenuCheckboxItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
</template>

<style scoped>
.table-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.inspector-search {
  min-width: 240px;
  flex: 1 1 420px;
  margin-block: 3px;
  margin-left: 3px;
}

.toolbar-select {
  height: 40px;
  width: 150px;
  flex: 0 0 auto;
  border-color: var(--input);
  background: var(--background);
  color: var(--foreground);
  font-size: 14px;
  font-weight: 400;
  box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.05);
}

.metadata-toolbar-trigger {
  height: 40px;
  border-color: var(--input);
  background: var(--background);
  color: var(--foreground);
  font-size: 14px;
  font-weight: 400;
  box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.05);
}

.metadata-toolbar-trigger:hover,
.metadata-toolbar-trigger[data-state="open"] {
  background: var(--accent);
  color: var(--accent-foreground);
}

.search-clear-button {
  position: absolute;
  inset-block: 0;
  right: 0;
  display: inline-flex;
  width: 40px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 0 6px 6px 0;
  background: transparent;
  color: color-mix(in srgb, var(--muted-foreground) 80%, transparent);
}

.inspector-search-input::-webkit-search-decoration,
.inspector-search-input::-webkit-search-cancel-button,
.inspector-search-input::-webkit-search-results-button,
.inspector-search-input::-webkit-search-results-decoration {
  appearance: none;
  display: none;
}

.search-clear-button:hover {
  color: var(--foreground);
}

.search-clear-button:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

.filter-count-badge,
.toolbar-count-pill {
  display: inline-flex;
  min-width: 18px;
  height: 20px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--background);
  color: color-mix(in srgb, var(--muted-foreground) 70%, transparent);
  padding-inline: 4px;
  font-size: 10px;
  font-weight: 500;
  line-height: 1;
}

.toolbar-view-button {
  width: auto;
  justify-content: space-between;
  padding-inline: 12px;
}

@media (max-width: 900px) {
  .table-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .inspector-search,
  .toolbar-select {
    width: 100%;
  }
}
</style>
