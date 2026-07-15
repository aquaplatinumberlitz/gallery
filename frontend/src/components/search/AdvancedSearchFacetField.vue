<script setup lang="ts">
import { computed, shallowRef } from "vue";
import { ChevronDown, Search } from "lucide-vue-next";
import Input from "@/components/ui/Input.vue";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { FacetEntry } from "@/types";

interface Props {
  id: string;
  label: string;
  modelValue: string;
  options: FacetEntry[];
  placeholder?: string;
  statusText?: string;
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: undefined,
  statusText: undefined,
});

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const countFormatter = new Intl.NumberFormat();
const open = shallowRef(false);
const filterText = shallowRef("");

const filteredOptions = computed(() => {
  const query = filterText.value.trim().toLowerCase();
  if (!query) return props.options.slice(0, 50);
  return props.options.filter((entry) => entry.value.toLowerCase().includes(query)).slice(0, 50);
});

function selectOption(value: string) {
  emit("update:modelValue", value);
  open.value = false;
  filterText.value = "";
}

function formatCount(count: number) {
  return countFormatter.format(count);
}

function handleOpenChange(value: boolean) {
  open.value = value;
  if (!value) filterText.value = "";
}
</script>

<template>
  <Field class="gap-1.5">
    <FieldLabel :for="id">{{ label }}</FieldLabel>
    <Popover :open="open" @update:open="handleOpenChange">
      <div
        class="advanced-search-facet-control flex items-stretch rounded-md border border-input bg-background shadow-xs transition-colors"
      >
        <Input
          :id="id"
          :model-value="modelValue"
          :placeholder="placeholder"
          variant="ghost"
          data-focus-ring="none"
          class="h-full min-w-0 flex-1 rounded-r-none px-3 focus-visible:border-transparent focus-visible:ring-0"
          aria-describedby="statusText ? `${id}-status` : undefined"
          @update:model-value="emit('update:modelValue', $event)"
        />
        <PopoverTrigger as-child>
          <button
            type="button"
            class="advanced-search-facet-toggle flex shrink-0 items-center rounded-l-none rounded-r-md border-l border-input px-2 text-muted-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:[box-shadow:var(--focus-ring-shadow)]"
            :aria-label="`Browse ${label} suggestions`"
            :disabled="options.length === 0"
          >
            <ChevronDown class="size-4" aria-hidden="true" />
          </button>
        </PopoverTrigger>
      </div>
      <PopoverContent
        align="end"
        :side-offset="4"
        class="advanced-search-facet-content w-[--reka-popover-trigger-width] min-w-[240px] p-0"
      >
        <div class="border-b px-2 py-2">
          <div class="relative">
            <Search
              class="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <input
              v-model="filterText"
              type="text"
              class="h-8 w-full rounded-md border border-input bg-background pl-7 pr-2 text-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
              :placeholder="`Filter ${label}…`"
              :aria-label="`Filter ${label} suggestions`"
            />
          </div>
        </div>
        <ul
          v-if="filteredOptions.length"
          class="advanced-search-facet-list max-h-60 overflow-y-auto"
          :aria-label="`${label} suggestions`"
        >
          <li v-for="entry in filteredOptions" :key="entry.value">
            <button
              type="button"
              class="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
              @click="selectOption(entry.value)"
            >
              <span class="min-w-0 truncate text-foreground">{{ entry.value }}</span>
              <span class="shrink-0 tabular-nums text-muted-foreground">{{ formatCount(entry.count) }}</span>
            </button>
          </li>
        </ul>
        <p v-else class="px-3 py-4 text-center text-xs text-muted-foreground">No matches</p>
      </PopoverContent>
    </Popover>
    <FieldDescription v-if="statusText" :id="`${id}-status`" class="text-xs" aria-live="polite">
      {{ statusText }}
    </FieldDescription>
  </Field>
</template>

<style scoped>
.advanced-search-facet-control:has(input:focus-visible) {
  border-color: var(--ring);
  box-shadow: var(--focus-within-ring-shadow);
}

.advanced-search-facet-toggle {
  min-height: 36px;
}

@media (max-width: 1023px) {
  .advanced-search-facet-toggle {
    min-height: 44px;
    padding-block: 0.625rem;
  }
}
</style>
