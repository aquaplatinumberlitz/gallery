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

defineProps<{ open: boolean; pending: boolean }>();
const emit = defineEmits<{ "update:open": [value: boolean]; confirm: [] }>();
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogScrollContent class="max-w-md">
      <DialogHeader>
        <DialogTitle>Clear generated files?</DialogTitle>
        <DialogDescription>
          Remove all generated thumbnail and preview files for this library. New previews will be created on demand when
          assets are viewed. Source image files are not deleted.
        </DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <Button variant="outline" :disabled="pending" @click="emit('update:open', false)">Cancel</Button>
        <Button variant="destructive" :disabled="pending" @click="emit('confirm')">
          {{ pending ? "Clearing…" : "Clear generated files" }}
        </Button>
      </DialogFooter>
    </DialogScrollContent>
  </Dialog>
</template>
