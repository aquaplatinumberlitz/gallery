<script setup lang="ts">
import type { FileNode } from "../types";
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselPrevious,
  CarouselNext,
} from "./ui/carousel";
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
    <Carousel
      v-slot="{ canScrollPrev, canScrollNext }"
      :opts="carouselOpts"
    >
      <CarouselContent class="-ml-6">
        <CarouselItem
          v-for="item in folders"
          :key="item.path"
          class="box-content w-[240px] max-w-[240px] flex-[0_0_auto] px-3"
        >
          <AlbumCard
            :node="item"
            @click="emit('open-folder', item.path)"
          />
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
