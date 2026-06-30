<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type ComponentPublicInstance } from "vue";
import type { HTMLAttributes } from "vue";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

defineOptions({
  inheritAttrs: false,
});

const props = withDefaults(
  defineProps<{
    text?: string | number | null;
    as?: string;
    class?: HTMLAttributes["class"];
    contentClass?: HTMLAttributes["class"];
    side?: "top" | "right" | "bottom" | "left";
    align?: "start" | "center" | "end";
  }>(),
  {
    text: "",
    as: "span",
    class: undefined,
    contentClass: undefined,
    side: "top",
    align: "center",
  },
);

const triggerRef = ref<HTMLElement | null>(null);
const isOverflowing = ref(false);
let resizeObserver: ResizeObserver | null = null;

const tooltipText = computed(() => (props.text == null ? "" : String(props.text)));
const tooltipEnabled = computed(() => Boolean(tooltipText.value) && isOverflowing.value);
const triggerClass = computed(() => cn("truncate", props.class));
const contentClass = computed(() => cn("max-w-[320px] break-words", props.contentClass));

function resolveElement(el: Element | ComponentPublicInstance | null): HTMLElement | null {
  if (el instanceof HTMLElement) return el;
  const element = (el as ComponentPublicInstance | null)?.$el;
  return element instanceof HTMLElement ? element : null;
}

function setTriggerRef(el: Element | ComponentPublicInstance | null) {
  const nextElement = resolveElement(el);
  if (triggerRef.value === nextElement) return;

  triggerRef.value = nextElement;
  void nextTick(() => {
    measureOverflow();
    observeTrigger();
  });
}

function measureOverflow() {
  const element = triggerRef.value;
  if (!element) {
    isOverflowing.value = false;
    return;
  }

  isOverflowing.value = element.scrollWidth > element.clientWidth || element.scrollHeight > element.clientHeight;
}

function observeTrigger() {
  resizeObserver?.disconnect();
  resizeObserver = null;

  if (typeof ResizeObserver === "undefined" || !triggerRef.value) return;

  resizeObserver = new ResizeObserver(() => measureOverflow());
  resizeObserver.observe(triggerRef.value);
}

onMounted(async () => {
  await nextTick();
  measureOverflow();
  observeTrigger();
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
});

watch(tooltipText, async () => {
  await nextTick();
  measureOverflow();
  observeTrigger();
});
</script>

<template>
  <Tooltip v-if="tooltipEnabled">
    <TooltipTrigger as-child>
      <component :is="as" :ref="setTriggerRef" :class="triggerClass" v-bind="$attrs">
        <slot>{{ tooltipText }}</slot>
      </component>
    </TooltipTrigger>
    <TooltipContent :side="side" :align="align" :class="contentClass">
      {{ tooltipText }}
    </TooltipContent>
  </Tooltip>

  <component v-else :is="as" :ref="setTriggerRef" :class="triggerClass" v-bind="$attrs">
    <slot>{{ tooltipText }}</slot>
  </component>
</template>
