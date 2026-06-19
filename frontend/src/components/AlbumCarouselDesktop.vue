<script setup lang="ts">
import type { FileNode } from "../types";
import { Carousel, CarouselContent, CarouselItem, CarouselPrevious, CarouselNext } from "./ui/carousel";
import AlbumCard from "./AlbumCard.vue";

defineProps<{
  folders: FileNode[];
}>();

const emit = defineEmits<{
  (e: "open-folder", path: string): void;
}>();

const carouselOpts = {
  align: "start" as const,
  loop: false,
  containScroll: "trimSnaps" as const,
  dragFree: false,
  skipSnaps: false,
};
</script>

<template>
  <div class="album-carousel-frame">
    <Carousel v-slot="{ canScrollPrev, canScrollNext }" :opts="carouselOpts">
      <CarouselContent class="-ml-3 px-6 py-6">
        <CarouselItem v-for="item in folders" :key="item.path" class="basis-auto pl-6">
          <div class="w-[240px]">
            <AlbumCard :node="item" @click="emit('open-folder', item.path)" />
          </div>
        </CarouselItem>
      </CarouselContent>

      <CarouselPrevious
        :class="{ 'opacity-0 pointer-events-none': !canScrollPrev }"
        class="-left-10"
        aria-label="Previous album"
      />
      <CarouselNext
        :class="{ 'opacity-0 pointer-events-none': !canScrollNext }"
        class="-right-10"
        aria-label="Next album"
      />
    </Carousel>
  </div>
</template>

<style scoped lang="scss">
.album-carousel-frame {
  position: relative;
  padding-left: 48px;
  padding-right: 48px;
}
</style>
