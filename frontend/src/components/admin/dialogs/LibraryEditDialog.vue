<script setup lang="ts">
import { Dialog, DialogDescription, DialogHeader, DialogScrollContent, DialogTitle } from "@/components/ui/dialog";
import type { RegisteredLibrary } from "@/types";
import LibraryForm from "./LibraryForm.vue";

defineProps<{ open: boolean; library: RegisteredLibrary | null; libraries?: RegisteredLibrary[] }>();
const emit = defineEmits<{ "update:open": [value: boolean]; updated: [library: RegisteredLibrary] }>();
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogScrollContent class="max-h-[95svh] max-w-2xl overflow-y-auto">
      <DialogHeader>
        <DialogTitle>Edit {{ library?.name }}</DialogTitle>
        <DialogDescription>
          Changes to paths and exclusions reconcile the catalog without deleting source files.
        </DialogDescription>
      </DialogHeader>
      <LibraryForm
        v-if="library"
        :library="library"
        :libraries="libraries"
        @cancel="emit('update:open', false)"
        @saved="emit('updated', $event)"
      />
    </DialogScrollContent>
  </Dialog>
</template>
