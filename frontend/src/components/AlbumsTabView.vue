<script setup lang="ts">
import { computed } from "vue";
import { useGalleryStore } from "../stores/gallery";
import AlbumCard from "./AlbumCard.vue";
import AlbumCardMobile from "./AlbumCardMobile.vue";
import GlowContainer from "./GlowContainer.vue";
import EmptyState from "./EmptyState.vue";

const galleryStore = useGalleryStore();

const props = defineProps<{
  isMobile: boolean
}>()

const searchQuery = computed(() => galleryStore.searchQuery);

const filteredAlbums = computed(() =>
  galleryStore.galleryFolders.filter((item) =>
    !searchQuery.value ||
    item.name.toLowerCase().includes(searchQuery.value.toLowerCase())
  )
);

const handleOpenFolder = (path: string) => {
  galleryStore.selectFolder(path);
};

const hasAlbums = computed(() => filteredAlbums.value.length > 0);
</script>

<template>
  <div class="albums-tab-view">
    <div v-if="!hasAlbums && searchQuery" class="empty-search">
      <EmptyState
        type="no-results"
        :title="`No albums matching '${searchQuery}'`"
        description="Try a different search term"
        compact
      />
    </div>

    <div v-else-if="!hasAlbums" class="empty-albums">
      <EmptyState
        type="empty-folder"
        title="No albums found"
        description="Browse a folder to see its subfolders as albums"
        compact
      />
    </div>

    <GlowContainer v-else :disabled="props.isMobile">
      <div class="albums-grid">
        <AlbumCard
          v-for="item in filteredAlbums"
          :key="item.path"
          class="album-card-desktop"
          :node="item"
          @click="handleOpenFolder(item.path)"
        />
        <AlbumCardMobile
          v-for="item in filteredAlbums"
          :key="`mobile-${item.path}`"
          class="album-card-mobile-item"
          :node="item"
          @click="handleOpenFolder(item.path)"
        />
      </div>
    </GlowContainer>
  </div>
</template>

<style scoped>
.albums-tab-view {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px;
}

.albums-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 20px;
  padding: 16px;
}

.albums-grid > * {
  min-width: 0;
}

.album-card-mobile-item {
  display: none;
}

.empty-search,
.empty-albums {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  padding: 32px;
}

@media (max-width: 767px) {
  .albums-tab-view {
    padding: 0;
    overflow-y: hidden;
    overflow-x: hidden;
  }

  .albums-grid {
    display: flex;
    flex-wrap: nowrap;
    gap: 8px;
    overflow-x: auto;
    overflow-y: hidden;
    padding: 8px;
    scroll-snap-type: x mandatory;
    touch-action: pan-x;
    overscroll-behavior-x: contain;
    scrollbar-width: none;
    -ms-overflow-style: none;
  }

  .albums-grid::-webkit-scrollbar {
    display: none;
  }

  .album-card-desktop {
    display: none;
  }

  .album-card-mobile-item {
    display: block;
    flex: 0 0 calc((100vw - 32px) / 3);
    min-width: calc((100vw - 32px) / 3);
    max-width: calc((100vw - 32px) / 3);
    scroll-snap-align: start;
  }
}

@media (max-width: 480px) {
  .albums-grid {
    gap: 8px;
    padding: 8px;
  }
}

@media (max-width: 360px) {
  .album-card-mobile-item {
    flex: 0 0 calc((100vw - 24px) / 2);
    min-width: calc((100vw - 24px) / 2);
    max-width: calc((100vw - 24px) / 2);
  }
}
</style>
