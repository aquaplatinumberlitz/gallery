<script setup lang="ts">
import type { HTMLAttributes } from "vue";
import { computed, ref } from "vue";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const inputVariants = cva(
  "flex w-full rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-xs transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
  {
    variants: {
      variant: {
        default: "h-9",
        ghost:
          "h-full border-none bg-transparent px-2 py-0 outline-none min-w-0 text-sm text-foreground placeholder:text-muted-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

type InputVariants = VariantProps<typeof inputVariants>;

interface Props {
  class?: HTMLAttributes["class"];
  type?: string;
  variant?: InputVariants["variant"];
  modelValue?: string;
}

const props = withDefaults(defineProps<Props>(), {
  class: undefined,
  type: "text",
  variant: "default",
  modelValue: undefined,
});

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const inputClasses = computed(() => cn(inputVariants({ variant: props.variant }), props.class));
const inputRef = ref<HTMLInputElement | null>(null);

// CJ-01: while an IME is composing, the uncommitted text must not reach the model. The value is emitted once on
// compositionend with the committed text. While composing, the bound value follows the live DOM value, so a re-render
// does not overwrite the composition.
const composing = ref(false);

function onInput(event: Event) {
  if (composing.value || (event as InputEvent).isComposing) return;
  emit("update:modelValue", (event.target as HTMLInputElement).value);
}

function onCompositionStart() {
  composing.value = true;
}

function onCompositionEnd(event: CompositionEvent) {
  composing.value = false;
  emit("update:modelValue", (event.target as HTMLInputElement).value);
}

defineExpose({
  blur: () => inputRef.value?.blur(),
  focus: () => inputRef.value?.focus(),
});
</script>

<template>
  <input
    ref="inputRef"
    :type="type"
    :value="composing && inputRef ? inputRef.value : modelValue"
    :class="inputClasses"
    @input="onInput"
    @compositionstart="onCompositionStart"
    @compositionend="onCompositionEnd"
  />
</template>
