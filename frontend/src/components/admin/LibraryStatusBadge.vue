<script setup lang="ts">
import { computed } from "vue";
import Badge from "@/components/ui/Badge.vue";
import type { LibraryProgress, RegisteredLibrary } from "@/types";
import { getLibraryStatusPresentation } from "@/utils/libraryStatus";

const props = defineProps<{
  library?: Pick<RegisteredLibrary, "state"> | null;
  progress?: Pick<LibraryProgress, "library_state"> | null;
}>();

const status = computed(() => getLibraryStatusPresentation(props.library, props.progress));
</script>

<template>
  <Badge :variant="status.variant" :title="status.meaning">{{ status.label }}</Badge>
</template>
