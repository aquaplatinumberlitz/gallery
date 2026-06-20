<script setup lang="ts">
import { computed } from "vue";
import { useLibraryProgressQuery } from "@/composables/admin/useLibraryProgressQuery";
import { useLibraryStatsQuery } from "@/composables/admin/useLibraryStatsQuery";
import { formatAssetCount } from "@/utils/libraryStatus";
import LibraryProgressBar from "./LibraryProgressBar.vue";
import Skeleton from "@/components/ui/skeleton/Skeleton.vue";

const props = defineProps<{ libraryId: number }>();
const id = computed(() => props.libraryId);
const statsQuery = useLibraryStatsQuery(id);
const progressQuery = useLibraryProgressQuery(id);
</script>

<template>
  <div class="min-w-40 space-y-2">
    <template v-if="statsQuery.data.value">
      <div class="text-sm font-medium">{{ formatAssetCount(statsQuery.data.value.total_assets) }} assets</div>
      <div class="text-xs text-muted-foreground">
        {{ formatAssetCount(statsQuery.data.value.photos) }} photos ·
        {{ formatAssetCount(statsQuery.data.value.videos) }} videos
      </div>
    </template>
    <Skeleton v-else-if="statsQuery.isPending.value" class="h-9 w-36" />
    <span v-else class="text-xs text-destructive">Stats unavailable</span>
    <LibraryProgressBar :progress="progressQuery.data.value" compact />
  </div>
</template>
