<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from "vue";

const props = withDefaults(defineProps<{
  collapsedLines: number;
  text?: string;
}>(), {
  text: undefined,
});

const emit = defineEmits<{
  'expanded-change': [expanded: boolean];
}>();

const isExpanded = ref(false);
const showToggle = ref(false);
const textRef = ref<HTMLElement | null>(null);

watch(isExpanded, (val) => {
  emit('expanded-change', val);
});

let resizeObserver: ResizeObserver | null = null;

function checkOverflow() {
  nextTick(() => {
    requestAnimationFrame(() => {
      if (!textRef.value) return;
      const el = textRef.value;
      showToggle.value = el.scrollHeight > el.clientHeight;
    });
  });
}

function toggle() {
  isExpanded.value = !isExpanded.value;
}

onMounted(() => {
  checkOverflow();
  if (textRef.value) {
    resizeObserver = new ResizeObserver(() => {
      if (!isExpanded.value) {
        checkOverflow();
      }
    });
    resizeObserver.observe(textRef.value);
  }
});

onUnmounted(() => {
  resizeObserver?.disconnect();
});

watch(() => props.text, () => {
  isExpanded.value = false;
  nextTick(() => {
    checkOverflow();
  });
});
</script>

<template>
  <div class="expandable-text">
    <div
      ref="textRef"
      class="expandable-text-content"
      :class="{ 'is-clamped': !isExpanded }"
      :style="{ WebkitLineClamp: isExpanded ? 'unset' : props.collapsedLines }"
    >
      <slot />
    </div>
    <button
      v-if="showToggle"
      type="button"
      class="expandable-text-toggle"
      :aria-expanded="isExpanded"
      @click="toggle"
    >
      {{ isExpanded ? 'Show less' : 'Show more' }}
    </button>
  </div>
</template>

<style scoped>
.expandable-text {
  display: flex;
  flex-direction: column;
}

.expandable-text-content {
  white-space: pre-wrap;
  overflow-wrap: break-word;
  overflow-wrap: anywhere;
  word-break: break-word;
  font-family: 'JetBrains Mono', monospace;
  color: #d1d5db;
  line-height: 1.5;
}

.expandable-text-content.is-clamped {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.expandable-text-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: none;
  color: #86efac;
  cursor: pointer;
  font-size: 11px;
  font-family: 'Inter', sans-serif;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 6px;
  padding: 0;
  align-self: flex-start;
}

.expandable-text-toggle:hover {
  color: #bbf7d0;
}

.expandable-text-toggle:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}
</style>
