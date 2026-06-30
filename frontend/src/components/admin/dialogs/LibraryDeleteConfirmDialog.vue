<script setup lang="ts">
import { computed } from "vue";
import Button from "@/components/ui/Button.vue";
import {
  Dialog,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogScrollContent,
  DialogTitle,
} from "@/components/ui/dialog";
import type { RegisteredLibrary } from "@/types";
import { formatAssetCount } from "@/utils/libraryStatus";

const props = defineProps<{
  open: boolean;
  library: RegisteredLibrary | null;
  estimatedAssets?: number;
  pending?: boolean;
}>();
const emit = defineEmits<{ "update:open": [value: boolean]; confirm: [] }>();
const countCopy = computed(() =>
  props.estimatedAssets && props.estimatedAssets > 0
    ? ` This library currently contains approximately ${formatAssetCount(props.estimatedAssets)} media files.`
    : "",
);
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogScrollContent class="max-w-md">
      <DialogHeader>
        <DialogTitle>Unregister {{ library?.name }}?</DialogTitle>
        <DialogDescription>
          Source files will not be deleted. Catalog rows, metadata records, and cached thumbnails for this library may
          be removed.{{ countCopy }}
        </DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <Button variant="outline" :disabled="pending" @click="emit('update:open', false)">Cancel</Button>
        <Button variant="destructive" :disabled="pending || !library" @click="emit('confirm')">
          {{ pending ? "Unregistering…" : "Unregister library" }}
        </Button>
      </DialogFooter>
    </DialogScrollContent>
  </Dialog>
</template>
