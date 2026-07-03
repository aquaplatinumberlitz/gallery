<script setup lang="ts">
import { Dialog, DialogDescription, DialogHeader, DialogScrollContent, DialogTitle } from "@/components/ui/dialog";
import type { RegisteredLibrary } from "@/types";
import LibraryForm from "./LibraryForm.vue";

defineProps<{ open: boolean; libraries?: RegisteredLibrary[] }>();
const emit = defineEmits<{ "update:open": [value: boolean]; created: [library: RegisteredLibrary] }>();
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogScrollContent class="max-h-[95svh] max-w-2xl overflow-y-auto">
      <DialogHeader class="gap-2">
        <DialogTitle class="text-2xl font-semibold tracking-tight">Add library</DialogTitle>
        <DialogDescription>Register one or more absolute folders. Source files remain in place.</DialogDescription>
      </DialogHeader>
      <LibraryForm :libraries="libraries" @cancel="emit('update:open', false)" @saved="emit('created', $event)" />
    </DialogScrollContent>
  </Dialog>
</template>
