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
        <DialogTitle>Refresh stale generated images?</DialogTitle>
        <DialogDescription>
          Queue regenerated thumbnail and preview files for assets whose source images have changed since the last
          generation{{ scopeLabel }}. Source image files are not deleted.
        </DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <Button variant="outline" :disabled="pending" @click="emit('update:open', false)">Cancel</Button>
        <Button variant="secondary" :disabled="pending" @click="emit('confirm')">
          {{ pending ? "Refreshing\u2026" : "Refresh stale" }}
        </Button>
      </DialogFooter>
    </DialogScrollContent>
  </Dialog>
</template>
