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

defineProps<{ open: boolean; pending: boolean; blocked?: boolean; blockMessage?: string; scopeLabel?: string }>();
const emit = defineEmits<{ "update:open": [value: boolean]; confirm: [] }>();
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogScrollContent class="max-w-md">
      <DialogHeader>
        <DialogTitle>Clear imported data{{ scopeLabel }}?</DialogTitle>
        <DialogDescription>
          Clears imported catalog data, extracted metadata, jobs, and generated previews{{ scopeLabel }}. Libraries,
          import paths, exclusion patterns, and source image files are not deleted.
        </DialogDescription>
      </DialogHeader>
      <p v-if="blockMessage" class="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
        {{ blockMessage }}
      </p>
      <DialogFooter>
        <Button variant="outline" :disabled="pending" @click="emit('update:open', false)">Cancel</Button>
        <Button variant="destructive" :disabled="pending || blocked" @click="emit('confirm')">
          {{ pending ? "Clearing\u2026" : "Clear" }}
        </Button>
      </DialogFooter>
    </DialogScrollContent>
  </Dialog>
</template>
