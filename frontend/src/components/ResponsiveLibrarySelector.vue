<script setup lang="ts">
import { computed } from "vue";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useDevice } from "@/composables/useDevice";
import LibrarySelectorContent from "./LibrarySelectorContent.vue";

const open = defineModel<boolean>({ required: true });
const { isMobile, isTablet } = useDevice();
const useSheet = computed(() => isMobile.value || isTablet.value);

function close() {
  open.value = false;
}
</script>

<template>
  <Sheet v-if="useSheet" v-model:open="open">
    <SheetContent
      side="bottom"
      class="flex max-h-[min(75dvh,40rem)] flex-col overflow-hidden rounded-t-xl p-0 md:max-h-[min(62dvh,40rem)]"
    >
      <SheetHeader class="border-b px-5 py-4 text-left">
        <SheetTitle>Choose library</SheetTitle>
        <SheetDescription>Select a registered import path to browse.</SheetDescription>
      </SheetHeader>
      <div class="overflow-y-auto px-4 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))] md:px-5">
        <LibrarySelectorContent @close="close" />
      </div>
    </SheetContent>
  </Sheet>

  <Dialog v-else v-model:open="open">
    <DialogContent class="max-h-[min(640px,calc(100vh-2rem))] max-w-[34rem] overflow-hidden p-0">
      <DialogHeader class="border-b px-5 py-4 text-left">
        <DialogTitle>Choose library</DialogTitle>
        <DialogDescription>Select a registered import path to browse.</DialogDescription>
      </DialogHeader>
      <div class="max-h-[min(520px,calc(100vh-10rem))] overflow-y-auto px-5 py-4">
        <LibrarySelectorContent @close="close" />
      </div>
    </DialogContent>
  </Dialog>
</template>
