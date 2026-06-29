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
        <DialogTitle>Rebuild imported data?</DialogTitle>
        <DialogDescription>
          Clears imported catalog data, extracted metadata, jobs, and generated previews{{ scopeLabel }}, then rebuilds
          from registered libraries. Source image files and library registrations are not deleted.
        </DialogDescription>
      </DialogHeader>
      <p v-if="blockMessage" class="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
        {{ blockMessage }}
      </p>
      <DialogFooter>
        <Button variant="outline" :disabled="pending" @click="emit('update:open', false)">Cancel</Button>
        <Button variant="secondary" :disabled="pending || blocked" @click="emit('confirm')">
          {{ pending ? "Rebuilding\u2026" : "Rebuild" }}
        </Button>
      </DialogFooter>
    </DialogScrollContent>
  </Dialog>
</template>
