<script setup lang="ts">
import { TriangleAlert } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import EmptyState from "@/components/EmptyState.vue";
import SkeletonLoader from "@/components/SkeletonLoader.vue";

type SearchFeedbackState = "pending" | "blocking-error" | "stale-warning" | "pagination-error" | "empty";

interface Props {
  state: SearchFeedbackState;
  message?: string;
  columnCount?: number;
  showAllIndexedHint?: boolean;
}

withDefaults(defineProps<Props>(), {
  message: "Unable to load search results.",
  columnCount: 4,
  showAllIndexedHint: false,
});

const emit = defineEmits<{
  retry: [];
  clear: [];
}>();
</script>

<template>
  <div v-if="state === 'pending'" class="search-feedback-skeleton" role="status" aria-label="Loading search results">
    <div class="search-feedback-grid" :style="{ gridTemplateColumns: `repeat(${columnCount}, 1fr)` }">
      <SkeletonLoader v-for="item in 12" :key="item" type="photo" />
    </div>
  </div>

  <EmptyState
    v-else-if="state === 'blocking-error'"
    type="error"
    title="Search unavailable"
    :description="message"
    action-label="Retry search"
    @action="emit('retry')"
  />

  <div v-else-if="state === 'stale-warning'" class="search-feedback-warning" role="alert">
    <TriangleAlert />
    <span>{{ message }} Showing the last successful results.</span>
    <Button type="button" variant="outline" size="sm" @click="emit('retry')">Retry</Button>
  </div>

  <div v-else-if="state === 'pagination-error'" class="search-feedback-page-error" role="alert">
    <TriangleAlert />
    <span>{{ message }} Earlier results are still available.</span>
    <Button type="button" variant="outline" size="sm" @click="emit('retry')">Retry page</Button>
  </div>

  <div v-else class="search-feedback-empty">
    <EmptyState
      type="no-results"
      title="No results"
      description="Try a filename, album name, prompt, or metadata filter."
      action-label="Clear search"
      action-icon="xmark"
      @action="emit('clear')"
    />
    <p v-if="showAllIndexedHint" class="search-feedback-hint">Try All indexed to search outside this folder.</p>
  </div>
</template>

<style scoped>
.search-feedback-skeleton {
  min-height: 100%;
}

.search-feedback-grid {
  display: grid;
  gap: 20px;
}

.search-feedback-warning,
.search-feedback-page-error {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid color-mix(in srgb, var(--destructive) 35%, var(--border));
  border-radius: 10px;
  background: color-mix(in srgb, var(--destructive) 8%, var(--background));
  padding: 10px 12px;
  color: var(--foreground);
  font-size: 13px;
}

.search-feedback-warning svg,
.search-feedback-page-error svg {
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
  color: var(--destructive);
}

.search-feedback-warning span,
.search-feedback-page-error span {
  min-width: 0;
  flex: 1;
}

.search-feedback-empty {
  display: flex;
  min-height: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.search-feedback-hint {
  margin: 10px 0 0;
  color: var(--muted-foreground);
  font-size: 13px;
}

@media (max-width: 767px) {
  .search-feedback-grid {
    gap: 8px;
  }

  .search-feedback-warning,
  .search-feedback-page-error {
    align-items: flex-start;
    flex-wrap: wrap;
  }
}
</style>
