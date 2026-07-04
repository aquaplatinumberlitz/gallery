<script setup lang="ts">
import { computed } from "vue";
import { Check, ChevronDown, ChevronUp } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

type SortValue = "date_desc" | "date_asc" | "name_asc" | "name_desc";
type SortField = "name" | "date";
type SortDirection = "asc" | "desc";

const SORT_FIELDS: { field: SortField; label: string }[] = [
  { field: "name", label: "Name" },
  { field: "date", label: "Modified" },
];

defineProps<{
  ariaLabel?: string;
  prefix?: string;
  triggerLabel?: string;
  triggerClass?: string;
}>();

const modelValue = defineModel<SortValue>({ required: true });

const activeField = computed<SortField>(() => (modelValue.value.startsWith("name") ? "name" : "date"));
const activeDirection = computed<SortDirection>(() => (modelValue.value.endsWith("_asc") ? "asc" : "desc"));
const activeDirectionLabel = computed(() => (activeDirection.value === "asc" ? "ascending" : "descending"));
const selectedLabel = computed(() => (activeField.value === "name" ? "Name" : "Modified"));

function defaultDirectionFor(field: SortField): SortDirection {
  return field === "name" ? "asc" : "desc";
}

function toSortValue(field: SortField, direction: SortDirection): SortValue {
  return `${field === "name" ? "name" : "date"}_${direction}` as SortValue;
}

function selectField(field: SortField) {
  const direction =
    field === activeField.value ? (activeDirection.value === "asc" ? "desc" : "asc") : defaultDirectionFor(field);

  modelValue.value = toSortValue(field, direction);
}
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button
        variant="outline"
        type="button"
        :class="cn('h-9 w-[150px] justify-between px-3 text-sm font-normal text-foreground shadow-none', triggerClass)"
        :aria-label="ariaLabel || `Sort by ${selectedLabel} ${activeDirectionLabel}`"
      >
        <span class="truncate">{{ triggerLabel ?? (prefix ? `${prefix} ${selectedLabel}` : selectedLabel) }}</span>
        <ChevronUp v-if="activeDirection === 'asc'" data-icon="inline-end" class="opacity-60" aria-hidden="true" />
        <ChevronDown v-else data-icon="inline-end" class="opacity-60" aria-hidden="true" />
      </Button>
    </DropdownMenuTrigger>

    <DropdownMenuContent align="end" class="w-40">
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
          <ChevronUp
            v-if="option.field === activeField && activeDirection === 'asc'"
            class="gallery-icon-sm text-muted-foreground"
            aria-hidden="true"
          />
          <ChevronDown
            v-else-if="option.field === activeField"
            class="gallery-icon-sm text-muted-foreground"
            aria-hidden="true"
          />
        </DropdownMenuItem>
      </DropdownMenuGroup>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
