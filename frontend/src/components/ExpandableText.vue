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
  <div
    class="expandable-text"
    :class="{
      'is-clamped': !isExpanded && showToggle,
      'is-expanded': isExpanded
    }"
    :style="{ '--line-clamp': props.collapsedLines }"
  >
    <div
      ref="textRef"
      class="expandable-text__content"
      :class="{ 'is-clamped': !isExpanded }"
    >
      <slot />
    </div>
    <span
      v-if="showToggle && !isExpanded"
      class="expandable-text__fade-toggle"
    >
      <button
        type="button"
        class="expandable-text__toggle"
        :aria-expanded="false"
        @click="toggle"
      >
        Show more
      </button>
    </span>
    <button
      v-if="showToggle && isExpanded"
      type="button"
      class="expandable-text__toggle expandable-text__toggle--inline"
      :aria-expanded="true"
      @click="toggle"
    >
      Show less
    </button>
  </div>
</template>

<style scoped>
.expandable-text {
  position: relative;
}

.expandable-text__content {
  overflow-wrap: break-word;
  overflow-wrap: anywhere;
  word-break: break-word;
  font-family: 'JetBrains Mono', monospace;
  color: #d1d5db;
  line-height: 1.5;
}

.expandable-text__content.is-clamped {
  white-space: normal;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: var(--line-clamp);
  overflow: hidden;
}

/* ------------------------------------------------------------------ */
/* Collapsed: overlay at bottom-right with gradient fade              */
/* ------------------------------------------------------------------ */

.expandable-text__fade-toggle {
  position: absolute;
  right: 0;
  bottom: 0;
  display: inline-flex;
  align-items: flex-end;
  height: 1lh;
  line-height: inherit;
  background: var(--metadata-panel-bg, #000);
}

.expandable-text__fade-toggle::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: -3em;
  width: 3em;
  pointer-events: none;
  background: linear-gradient(90deg, rgba(0, 0, 0, 0), var(--metadata-panel-bg, #000));
}

/* ------------------------------------------------------------------ */
/* Expanded: full text, button inline after                           */
/* ------------------------------------------------------------------ */

.expandable-text.is-expanded .expandable-text__content {
  white-space: pre-wrap;
  display: block;
  overflow: visible;
}

.expandable-text__toggle--inline {
  display: inline-block;
  margin-top: 6px;
}

/* ------------------------------------------------------------------ */
/* Toggle button – CivitAI-style blue link                            */
/* ------------------------------------------------------------------ */

.expandable-text__toggle {
  display: inline;
  height: auto;
  min-height: 0;
  line-height: inherit;
  padding: 0;
  margin: 0;
  border: 0;
  background: none;
  appearance: none;
  font: inherit;
  margin-left: 4px;
  color: rgba(96, 190, 255, 0.96);
  font-weight: 500;
  cursor: pointer;
  text-transform: none;
  white-space: nowrap;
}

.expandable-text__toggle:hover {
  color: rgba(145, 215, 255, 1);
  text-decoration: underline;
}

.expandable-text__toggle:focus-visible {
  outline: 2px solid rgba(96, 190, 255, 0.75);
  outline-offset: 2px;
  border-radius: 4px;
}
</style>
