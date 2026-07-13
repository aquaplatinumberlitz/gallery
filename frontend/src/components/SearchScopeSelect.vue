<script setup lang="ts">
import type { Component, HTMLAttributes } from "vue";
import { computed } from "vue";
import { Earth, FolderSearch, Library } from "lucide-vue-next";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { SearchScope } from "@/types";

interface ScopeOption {
  value: SearchScope;
  label: string;
  description: string;
  icon: Component;
}

const props = withDefaults(
  defineProps<{
    modelValue: SearchScope;
    size?: "default" | "compact" | "icon";
    align?: "start" | "center" | "end";
    currentLabel?: string;
    libraryLabel?: string;
    allLabel?: string;
    class?: HTMLAttributes["class"];
  }>(),
  {
    size: "default",
    align: "end",
    currentLabel: "This folder",
    libraryLabel: "This library",
    allLabel: "All indexed",
    class: undefined,
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: SearchScope];
}>();

const scopeOptions = computed<ScopeOption[]>(() => [
  {
    value: "current",
    label: props.currentLabel,
    description: "Search the folder you are viewing.",
    icon: FolderSearch,
  },
  {
    value: "library",
    label: props.libraryLabel,
    description: "Search the active registered library.",
    icon: Library,
  },
  {
    value: "all",
    label: props.allLabel,
    description: "Search across indexed libraries.",
    icon: Earth,
  },
]);

const selectedOption = computed(
  () => scopeOptions.value.find((option) => option.value === props.modelValue) ?? scopeOptions.value[0],
);

function handleUpdate(value: unknown) {
  if (value === "current" || value === "library" || value === "all") {
    emit("update:modelValue", value);
  }
}
</script>

<template>
  <Select :model-value="modelValue" @update:model-value="handleUpdate">
    <SelectTrigger
      :aria-label="`Search scope: ${selectedOption.label}`"
      :class="
        cn(
          'search-scope-select-trigger',
          size === 'compact' && 'search-scope-select-trigger-compact',
          size === 'icon' && 'search-scope-select-trigger-icon',
          props.class,
        )
      "
    >
      <span class="search-scope-select-inner">
        <component :is="selectedOption.icon" class="search-scope-select-icon" aria-hidden="true" />
        <span v-if="size !== 'icon'" class="search-scope-select-label">{{ selectedOption.label }}</span>
      </span>
    </SelectTrigger>
    <SelectContent :align="align" class="search-scope-select-content">
      <SelectGroup>
        <SelectItem
          v-for="option in scopeOptions"
          :key="option.value"
          :value="option.value"
          class="search-scope-select-item"
        >
          <span class="search-scope-option">
            <component :is="option.icon" class="search-scope-option-icon" aria-hidden="true" />
            <span class="search-scope-option-copy">
              <span class="search-scope-option-title">{{ option.label }}</span>
              <span class="search-scope-option-description">{{ option.description }}</span>
            </span>
          </span>
        </SelectItem>
      </SelectGroup>
    </SelectContent>
  </Select>
</template>

<style scoped>
.search-scope-select-trigger {
  width: auto;
  min-width: 136px;
  height: 30px;
  border-color: color-mix(in srgb, var(--border) 72%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--background) 90%, var(--muted) 10%);
  color: var(--foreground);
  padding: 0 9px 0 10px;
  font-size: 12px;
  font-weight: 650;
  box-shadow: inset 0 1px 0 color-mix(in srgb, white 36%, transparent);
  transition:
    background-color 160ms ease,
    border-color 160ms ease,
    color 160ms ease,
    box-shadow 160ms ease;
}

.search-scope-select-trigger:hover,
.search-scope-select-trigger[data-state="open"] {
  border-color: color-mix(in srgb, var(--ring) 45%, var(--border));
  background: color-mix(in srgb, var(--accent) 42%, var(--background));
  color: var(--accent-foreground);
}

.search-scope-select-trigger:focus-visible {
  border-color: var(--ring);
  box-shadow: var(--focus-ring-shadow);
}

.search-scope-select-trigger-compact {
  min-width: 96px;
  height: 44px;
  padding-inline: 8px;
}

.search-scope-select-trigger-icon {
  width: 44px;
  min-width: 44px;
  height: 44px;
  justify-content: center;
  border: 0;
  border-radius: 10px;
  background: transparent;
  padding: 0;
  box-shadow: inset 1px 0 0 color-mix(in srgb, var(--border) 72%, transparent);
}

.search-scope-select-trigger-icon:hover,
.search-scope-select-trigger-icon[data-state="open"] {
  border-color: transparent;
  background: color-mix(in srgb, var(--foreground) 7%, transparent);
  box-shadow: inset 1px 0 0 color-mix(in srgb, var(--border) 72%, transparent);
}

.search-scope-select-trigger-icon :deep(.lucide-chevron-down) {
  display: none;
}

.search-scope-select-trigger-icon .search-scope-select-inner {
  justify-content: center;
}

.search-scope-select-trigger-icon .search-scope-select-icon {
  width: 17px;
  height: 17px;
  color: var(--foreground);
}

.search-scope-select-inner {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 6px;
}

.search-scope-select-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--muted-foreground);
  transition: color 160ms ease;
}

.search-scope-select-trigger:hover .search-scope-select-icon,
.search-scope-select-trigger[data-state="open"] .search-scope-select-icon {
  color: var(--foreground);
}

.search-scope-select-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-scope-select-content {
  min-width: 220px;
  border-radius: 12px;
  padding: 4px;
  box-shadow:
    0 10px 30px color-mix(in srgb, black 14%, transparent),
    0 1px 0 color-mix(in srgb, white 10%, transparent) inset;
}

.search-scope-select-item {
  border-radius: 9px;
  padding-top: 8px;
  padding-bottom: 8px;
}

.search-scope-option {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  gap: 9px;
}

.search-scope-option-icon {
  width: 15px;
  height: 15px;
  margin-top: 2px;
  flex-shrink: 0;
  color: var(--muted-foreground);
}

.search-scope-option-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.search-scope-option-title {
  color: var(--foreground);
  font-size: 13px;
  font-weight: 650;
  line-height: 1.15;
}

.search-scope-option-description {
  color: var(--muted-foreground);
  font-size: 11px;
  font-weight: 400;
  line-height: 1.25;
}

@media (max-width: 420px) {
  .search-scope-select-trigger-compact {
    min-width: 76px;
    padding-inline: 8px;
  }

  .search-scope-select-inner {
    gap: 5px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .search-scope-select-trigger,
  .search-scope-select-icon {
    transition: none;
  }
}
</style>
