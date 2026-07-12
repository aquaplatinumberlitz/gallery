<script setup lang="ts">
import { computed } from "vue";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { getVideoPosterUrl, getVideoUrl } from "@/services/api";
import type { FileNode } from "@/types";

const props = defineProps<{ open: boolean; video: FileNode | null }>();
const emit = defineEmits<{ "update:open": [value: boolean] }>();
const videoUrl = computed(() => (props.video ? getVideoUrl(props.video.path) : ""));
const posterUrl = computed(() => (props.video ? getVideoPosterUrl(props.video.path) : ""));
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="video-dialog max-w-5xl border-0 bg-black p-0 text-white sm:rounded-xl">
      <DialogHeader class="sr-only">
        <DialogTitle>{{ video?.name || "Video player" }}</DialogTitle>
        <DialogDescription>Native video playback</DialogDescription>
      </DialogHeader>
      <video
        v-if="video"
        data-testid="video-player"
        class="video-player"
        :src="videoUrl"
        :poster="posterUrl"
        :aria-label="video.name"
        controls
        playsinline
        preload="metadata"
      >
        Your browser does not support native video playback.
      </video>
    </DialogContent>
  </Dialog>
</template>

<style scoped>
.video-dialog {
  width: min(94vw, 72rem);
  overflow: hidden;
}

.video-player {
  display: block;
  width: 100%;
  max-height: 86vh;
  background: black;
}

@media (max-width: 639px) {
  .video-dialog {
    width: calc(100vw - 1.5rem);
    max-width: calc(100vw - 1.5rem);
    padding: 0;
    border-radius: 0.75rem;
  }
}
</style>
