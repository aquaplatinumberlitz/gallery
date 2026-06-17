<script setup lang="ts">
import { computed } from "vue";
import { ArrowUpDown, Check, ChevronDown } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { SortValue } from "@/types";

const SORT_OPTIONS: { value: SortValue; label: string }[] = [
  { value: "date_desc", label: "Date modified ↓" },
  { value: "date_asc", label: "Date modified ↑" },
  { value: "name_asc", label: "Name A–Z" },
  { value: "name_desc", label: "Name Z–A" },
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

const selectedOption = computed(
  () => SORT_OPTIONS.find((option) => option.value === props.modelValue) ?? SORT_OPTIONS[0],
);
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
        <ArrowUpDown
          class="gallery-icon-sm"
          aria-hidden="true"
        />
        <span>{{ selectedOption.label }}</span>
        <ChevronDown
          class="gallery-icon-xs opacity-60"
          aria-hidden="true"
        />
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
        <span class="truncate">{{ selectedOption.label }}</span>
        <ChevronDown
          class="h-4 w-4 shrink-0 opacity-50"
          aria-hidden="true"
        />
      </Button>
    </DropdownMenuTrigger>

    <DropdownMenuContent
      align="end"
      :class="['w-48', contentClass]"
    >
      <DropdownMenuItem
        v-for="option in SORT_OPTIONS"
        :key="option.value"
        class="gap-2"
        @select="emit('update:modelValue', option.value)"
      >
        <Check
          class="gallery-icon-sm"
          :class="option.value === modelValue ? 'opacity-100' : 'opacity-0'"
          aria-hidden="true"
        />
        <span class="flex-1">{{ option.label }}</span>
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
