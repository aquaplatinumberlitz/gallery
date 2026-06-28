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
        <DialogTitle>Rebuild outdated thumbnails and previews?</DialogTitle>
        <DialogDescription>
          Queues new thumbnail and preview files for images whose source file changed{{ scopeLabel }}. Source images and
          metadata jobs are not changed.
        </DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <Button variant="outline" :disabled="pending" @click="emit('update:open', false)">Cancel</Button>
        <Button variant="secondary" :disabled="pending" @click="emit('confirm')">
          {{ pending ? "Rebuilding\u2026" : "Rebuild previews" }}
        </Button>
      </DialogFooter>
    </DialogScrollContent>
  </Dialog>
</template>
