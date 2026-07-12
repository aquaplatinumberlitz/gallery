<script setup lang="ts">
import type { DialogContentEmits, DialogContentProps } from "reka-ui";
import type { HTMLAttributes } from "vue";
import type { SheetVariants } from ".";
import { reactiveOmit } from "@vueuse/core";
import { X } from "lucide-vue-next";
import { DialogClose, DialogContent, DialogOverlay, DialogPortal, useForwardPropsEmits } from "reka-ui";
import { cn } from "@/lib/utils";
import { sheetVariants } from ".";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface SheetContentProps extends DialogContentProps {
  class?: HTMLAttributes["class"];
  side?: SheetVariants["side"];
}

defineOptions({
  inheritAttrs: false,
});

const props = defineProps<SheetContentProps>();

const emits = defineEmits<DialogContentEmits>();

const delegatedProps = reactiveOmit(props, "class", "side");

const forwarded = useForwardPropsEmits(delegatedProps, emits);
</script>

<template>
  <DialogPortal>
    <DialogOverlay
      class="fixed inset-0 z-[var(--gallery-z-modal)] bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
    />
    <DialogContent :class="cn(sheetVariants({ side }), props.class)" v-bind="{ ...forwarded, ...$attrs }">
      <slot />

      <Tooltip>
        <TooltipTrigger as-child>
          <span class="absolute right-2 top-2 inline-flex sm:right-3 sm:top-3">
            <DialogClose
              class="inline-flex size-11 cursor-pointer items-center justify-center rounded-md opacity-70 transition-opacity hover:bg-accent hover:opacity-100 focus-visible:outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none data-[state=open]:bg-secondary"
              aria-label="Close"
            >
              <X class="size-4 text-muted-foreground" />
              <span class="sr-only">Close</span>
            </DialogClose>
          </span>
        </TooltipTrigger>
        <TooltipContent>Close</TooltipContent>
      </Tooltip>
    </DialogContent>
  </DialogPortal>
</template>
