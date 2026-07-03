<script setup lang="ts">
import { computed, type HTMLAttributes } from "vue";
import { Check, Copy } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useClipboard } from "@/composables/useClipboard";

const props = withDefaults(
  defineProps<{
    text?: string | number | null;
    copyId?: string;
    label?: string;
    copiedLabel?: string;
    variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
    size?: "default" | "sm" | "lg" | "icon" | "icon-sm";
    class?: HTMLAttributes["class"];
  }>(),
  {
    text: "",
    copyId: "text",
    label: "Copy",
    copiedLabel: "Copied",
    variant: "ghost",
    size: "icon",
    class: undefined,
  },
);

const { copyStatus, copyText } = useClipboard();
const copied = computed(() => Boolean(copyStatus.value[props.copyId]));
const ariaLabel = computed(() => (copied.value ? props.copiedLabel : props.label));

async function handleCopy() {
  if (props.text == null || props.text === "") return;
  await copyText(String(props.text), props.copyId);
}
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <Button :variant="variant" :size="size" :class="props.class" :aria-label="ariaLabel" @click="handleCopy">
        <span class="relative inline-grid size-4 place-items-center">
          <Check
            aria-hidden="true"
            :class="[
              'col-start-1 row-start-1 text-[var(--gallery-success)] transition-all duration-200',
              copied ? 'scale-100 opacity-100' : 'scale-75 opacity-0',
            ]"
          />
          <Copy
            aria-hidden="true"
            :class="[
              'col-start-1 row-start-1 transition-all duration-200',
              copied ? 'scale-75 opacity-0' : 'scale-100 opacity-100',
            ]"
          />
        </span>
        <slot v-if="$slots.default" :copied="copied">
          {{ copied ? copiedLabel : label }}
        </slot>
      </Button>
    </TooltipTrigger>
    <TooltipContent>{{ ariaLabel }}</TooltipContent>
  </Tooltip>
</template>
