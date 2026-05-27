<script setup lang="ts">
import { computed } from "vue";
import { useGalleryStore } from "../stores/gallery";
import AlbumCard from "./AlbumCard.vue";
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
  }

  .albums-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    padding: 12px 10px;
  }
}

@media (max-width: 480px) {
  .albums-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    padding: 8px 6px;
  }
}
</style>
