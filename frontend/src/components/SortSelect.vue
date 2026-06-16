<script setup lang="ts">
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type SortValue = "date_desc" | "date_asc" | "name_asc" | "name_desc";

defineProps<{
  ariaLabel?: string;
}>();

const modelValue = defineModel<SortValue>({ required: true });
</script>

<template>
  <Select v-model="modelValue">
    <SelectTrigger class="w-[150px]">
      <SelectValue />
    </SelectTrigger>
    <SelectContent>
      <SelectItem value="date_desc">Date modified ↓</SelectItem>
      <SelectItem value="date_asc">Date modified ↑</SelectItem>
      <SelectItem value="name_asc">Name A–Z</SelectItem>
      <SelectItem value="name_desc">Name Z–A</SelectItem>
    </SelectContent>
  </Select>
</template>
