<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  bleed?: number
  bleedX?: number
  bleedY?: number
  disabled?: boolean
}>(), {
  bleed: 50,
  disabled: false
})

const containerStyle = computed(() => {
  if (props.disabled) return {}
  const bx = `${props.bleedX ?? props.bleed}px`
  const by = `${props.bleedY ?? props.bleed}px`
  return {
    '--glow-bleed-x': bx,
    '--glow-bleed-y': by,
    padding: `${by} ${bx}`,
    margin: `calc(-1 * ${by}) calc(-1 * ${bx})`,
    overflow: 'visible'
  }
})
</script>

<template>
  <div
    class="glow-container"
    :class="{ 'glow-disabled': disabled }"
    :style="containerStyle"
  >
    <slot />
  </div>
</template>

<style scoped>
.glow-container {
  position: relative;
  overflow: visible;
  pointer-events: none; /* prevent negative-margin overflow from intercepting header hover events */
}

.glow-disabled {
  padding: 0 !important;
  margin: 0 !important;
}
</style>
