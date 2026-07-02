<script setup lang="ts">
import { computed } from "vue";
import { ArrowUpDown, Check, ChevronDown } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { SortValue } from "@/types";

type SortField = "name" | "date";
type SortDirection = "asc" | "desc";

const SORT_FIELDS: { field: SortField; label: string }[] = [
  { field: "name", label: "Name" },
  { field: "date", label: "Modified" },
];

const props = defineProps<{
  modelValue: SortValue;
  ariaLabel?: string;
  triggerClass?: string;
  contentClass?: string;
  triggerStyle?: "button" | "select";
}>();

const emit = defineEmits<{
  "update:modelValue": [value: SortValue];
}>();

const activeField = computed<SortField>(() => (props.modelValue.startsWith("name") ? "name" : "date"));
const activeDirection = computed<SortDirection>(() => (props.modelValue.endsWith("_asc") ? "asc" : "desc"));
const activeArrow = computed(() => (activeDirection.value === "asc" ? "↑" : "↓"));
const selectedLabel = computed(() => `${activeField.value === "name" ? "Name" : "Modified"} ${activeArrow.value}`);

function defaultDirectionFor(field: SortField): SortDirection {
  return field === "name" ? "asc" : "desc";
}

function toSortValue(field: SortField, direction: SortDirection): SortValue {
  return `${field === "name" ? "name" : "date"}_${direction}` as SortValue;
}

function selectField(field: SortField) {
  const direction =
    field === activeField.value ? (activeDirection.value === "asc" ? "desc" : "asc") : defaultDirectionFor(field);

  emit("update:modelValue", toSortValue(field, direction));
}
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button
        v-if="triggerStyle !== 'select'"
        variant="outline"
        size="sm"
        type="button"
        :class="triggerClass"
        :aria-label="ariaLabel || 'Sort'"
      >
        <ArrowUpDown class="gallery-icon-sm" aria-hidden="true" />
        <span>{{ selectedLabel }}</span>
        <ChevronDown class="gallery-icon-xs opacity-60" aria-hidden="true" />
      </Button>
      <Button
        v-else
        variant="outline"
        type="button"
        :class="
          cn(
            'h-9 w-[150px] justify-between gap-2 px-3 text-sm font-normal text-foreground shadow-none flex-none max-[900px]:w-full',
            triggerClass,
          )
        "
        :aria-label="ariaLabel || 'Sort'"
      >
        <span class="truncate">{{ selectedLabel }}</span>
        <ChevronDown class="h-4 w-4 shrink-0 opacity-50" aria-hidden="true" />
      </Button>
    </DropdownMenuTrigger>

    <DropdownMenuContent align="end" :class="['w-40', contentClass]">
      <DropdownMenuGroup>
        <DropdownMenuItem
          v-for="option in SORT_FIELDS"
          :key="option.field"
          class="gap-2"
          @select="selectField(option.field)"
        >
          <Check
            class="gallery-icon-sm"
            :class="option.field === activeField ? 'opacity-100' : 'opacity-0'"
            aria-hidden="true"
          />
          <span class="flex-1">{{ option.label }}</span>
          <span v-if="option.field === activeField" class="text-muted-foreground" aria-hidden="true">
            {{ activeArrow }}
          </span>
        </DropdownMenuItem>
      </DropdownMenuGroup>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
