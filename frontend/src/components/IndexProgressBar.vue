<script setup lang="ts">
defineProps<{
  percent: number;
}>();
</script>

<template>
  <div
    class="index-progress-bar"
    aria-hidden="true"
  >
    <div
      class="index-progress-bar__fill"
      :style="{ width: `${percent}%` }"
    />
  </div>
</template>

<style scoped>
.index-progress-bar {
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.08);
}

.index-progress-bar__fill {
  height: 100%;
  border-radius: inherit;
  background: var(--gallery-warning);
  transition: width 300ms ease;
}
</style>
