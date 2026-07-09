<script setup lang="ts">
import { computed, type HTMLAttributes } from "vue";
import Button from "@/components/ui/Button.vue";
import CopyStateIcon from "@/components/ui/CopyStateIcon.vue";
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
        <CopyStateIcon :copied="copied" />
        <slot v-if="$slots.default" :copied="copied">
          {{ copied ? copiedLabel : label }}
        </slot>
      </Button>
    </TooltipTrigger>
    <TooltipContent>{{ ariaLabel }}</TooltipContent>
  </Tooltip>
</template>
