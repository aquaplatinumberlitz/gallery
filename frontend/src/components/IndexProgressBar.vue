<script setup lang="ts">
import { Progress } from "@/components/ui/progress";

defineProps<{
  percent: number;
}>();
</script>

<template>
  <Progress
    :model-value="percent"
    class="h-1 bg-muted"
    :indicator-class="percent >= 100 ? 'bg-success' : 'bg-warning'"
    aria-hidden="true"
    data-testid="index-progress-bar"
  />
</template>
