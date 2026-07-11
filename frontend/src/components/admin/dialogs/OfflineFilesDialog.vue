<script setup lang="ts">
import { computed } from "vue";
import { AlertTriangle, FileImage, RefreshCw } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import Skeleton from "@/components/ui/skeleton/Skeleton.vue";
import {
  Dialog,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogScrollContent,
  DialogTitle,
} from "@/components/ui/dialog";
import { useOfflineLibraryAssets } from "@/composables/admin/useOfflineLibraryAssets";
import { formatAssetCount } from "@/utils/libraryStatus";
import { formatBytes } from "@/utils/format";

const props = defineProps<{ open: boolean; libraryId: number; expectedCount: number }>();
const emit = defineEmits<{ "update:open": [value: boolean] }>();
const enabled = computed(() => props.open);
const { query, forgetMutation } = useOfflineLibraryAssets(() => props.libraryId, enabled);
const items = computed(() => query.data.value?.items ?? []);

async function forgetFiles() {
  if (!items.value.length) return;
  await forgetMutation.mutateAsync();
  emit("update:open", false);
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogScrollContent class="max-h-[90svh] max-w-2xl overflow-y-auto">
      <DialogHeader>
        <DialogTitle>Unavailable files</DialogTitle>
        <DialogDescription>
          These files remain in the catalog but were not available during the latest update. Review the exact names and
          paths before forgetting them.
        </DialogDescription>
      </DialogHeader>

      <div v-if="query.isPending.value" class="space-y-2" aria-label="Loading unavailable files">
        <Skeleton v-for="item in Math.min(expectedCount || 2, 4)" :key="item" class="h-16 w-full" />
      </div>
      <div
        v-else-if="query.isError.value"
        class="rounded-md border border-destructive/30 bg-destructive/5 p-4"
        role="alert"
      >
        <p class="text-sm font-medium">Unavailable files could not be loaded.</p>
        <Button variant="outline" size="sm" class="mt-3" @click="query.refetch()">
          <RefreshCw data-icon="inline-start" /> Try again
        </Button>
      </div>
      <div v-else-if="items.length" class="space-y-3">
        <div class="flex items-start gap-2 rounded-md border border-warning/30 bg-warning-bg p-3 text-sm">
          <AlertTriangle class="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
          <p>
            Forgetting removes only these catalog records. It does not delete source files. If a file appears again, a
            future library update can catalog it again.
          </p>
        </div>
        <ul
          class="divide-y divide-border rounded-md border border-border"
          :aria-label="`${items.length} unavailable files`"
        >
          <li v-for="item in items" :key="item.id" class="flex min-w-0 gap-3 p-3">
            <FileImage class="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <div class="min-w-0 flex-1">
              <p class="break-words text-sm font-medium text-foreground">{{ item.name }}</p>
              <p class="mt-1 break-all font-mono text-xs text-muted-foreground">{{ item.path }}</p>
              <p v-if="item.size !== null" class="mt-1 text-xs text-muted-foreground">{{ formatBytes(item.size) }}</p>
            </div>
          </li>
        </ul>
      </div>
      <div v-else class="rounded-md border border-border bg-muted/40 p-5 text-center">
        <p class="text-sm font-medium">No unavailable files remain.</p>
        <p class="mt-1 text-xs text-muted-foreground">The library count is already current.</p>
      </div>

      <DialogFooter>
        <Button variant="outline" :disabled="forgetMutation.isPending.value" @click="emit('update:open', false)">
          Close
        </Button>
        <Button
          v-if="items.length"
          variant="destructive"
          :disabled="forgetMutation.isPending.value"
          @click="forgetFiles"
        >
          {{
            forgetMutation.isPending.value
              ? "Forgetting…"
              : `Forget ${formatAssetCount(items.length)} ${items.length === 1 ? "file" : "files"}`
          }}
        </Button>
      </DialogFooter>
    </DialogScrollContent>
  </Dialog>
</template>
