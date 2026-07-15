<script setup lang="ts">
import Button from "@/components/ui/Button.vue";
import {
  Dialog,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogScrollContent,
  DialogTitle,
} from "@/components/ui/dialog";

defineProps<{ open: boolean; pending: boolean; scopeLabel?: string }>();
const emit = defineEmits<{ "update:open": [value: boolean]; confirm: [] }>();
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogScrollContent class="max-w-md">
      <DialogHeader>
        <DialogTitle>Clear imported data{{ scopeLabel }}?</DialogTitle>
        <DialogDescription>
          Clears the file catalog, extracted metadata, search indexes, job history, thumbnails, and previews{{
            scopeLabel
          }}. Library settings, folders, exclusion patterns, and source files are kept.
        </DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <Button variant="outline" :disabled="pending" @click="emit('update:open', false)">Cancel</Button>
        <Button variant="destructive" :disabled="pending" @click="emit('confirm')">
          {{ pending ? "Clearing imported data\u2026" : "Clear imported data" }}
        </Button>
      </DialogFooter>
    </DialogScrollContent>
  </Dialog>
</template>
