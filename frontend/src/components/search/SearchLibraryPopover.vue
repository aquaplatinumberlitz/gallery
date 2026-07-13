<script setup lang="ts">
import { computed, shallowRef, watch } from "vue";
import { Bookmark, History, Play, Save, Trash2 } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import { useSavedSearches } from "@/composables/useSavedSearches";
import type { PersistableSearchRequestV1, SearchQueryRequestV1 } from "@/types";

const props = defineProps<{ currentRequest: SearchQueryRequestV1 | null }>();
const emit = defineEmits<{ apply: [request: PersistableSearchRequestV1] }>();
const library = useSavedSearches();
const saveName = shallowRef("");
const renameDrafts = shallowRef<Record<string, string>>({});

watch(
  library.saved,
  (saved) => {
    renameDrafts.value = Object.fromEntries(saved.map((item) => [item.id, renameDrafts.value[item.id] ?? item.name]));
  },
  { immediate: true },
);

const canSave = computed(() => Boolean(props.currentRequest && saveName.value.trim()));
const summary = (request: PersistableSearchRequestV1) =>
  request.text ||
  `${request.filters.prompt_groups.length} prompt · ${request.filters.workflow_groups.length} workflow filter`;

function saveCurrent() {
  if (!props.currentRequest) return;
  const saved = library.save(saveName.value, props.currentRequest);
  if (saved) saveName.value = "";
}

function rename(id: string) {
  library.rename(id, renameDrafts.value[id] ?? "");
}
</script>

<template>
  <section class="search-library" aria-labelledby="search-library-title">
    <div class="section-heading">
      <div>
        <p id="search-library-title" class="section-title"><Bookmark /> Search library</p>
        <p class="section-copy">Saved and recent searches stay in this browser.</p>
      </div>
    </div>

    <div class="save-row">
      <Input v-model="saveName" aria-label="Saved search name" placeholder="Name this search" maxlength="120" />
      <Button type="button" size="sm" :disabled="!canSave" @click="saveCurrent"><Save /> Save</Button>
    </div>

    <div v-if="library.saved.value.length" class="library-list" aria-label="Saved searches">
      <div v-for="item in library.saved.value" :key="item.id" class="library-item">
        <Input
          :model-value="renameDrafts[item.id]"
          :aria-label="`Rename ${item.name}`"
          maxlength="120"
          @update:model-value="renameDrafts = { ...renameDrafts, [item.id]: String($event) }"
          @change="rename(item.id)"
        />
        <p>{{ summary(item.request) }}</p>
        <div class="item-actions">
          <Button type="button" variant="outline" size="sm" @click="emit('apply', item.request)"><Play /> Run</Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            :aria-label="`Delete ${item.name}`"
            @click="library.remove(item.id)"
          >
            <Trash2 />
          </Button>
        </div>
      </div>
    </div>

    <div v-if="library.recent.value.length" class="recent-block">
      <div class="recent-heading">
        <span><History /> Recent</span
        ><Button type="button" variant="ghost" size="sm" @click="library.clearRecent">Clear</Button>
      </div>
      <button
        v-for="item in library.recent.value.slice(0, 5)"
        :key="`${item.used_at}-${summary(item.request)}`"
        type="button"
        class="recent-item"
        @click="emit('apply', item.request)"
      >
        <span>{{ summary(item.request) }}</span
        ><Play />
      </button>
    </div>
  </section>
</template>

<style scoped>
.search-library {
  display: grid;
  gap: 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  background: var(--background);
}
.section-title,
.recent-heading span {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
  font-weight: 650;
}
.section-title svg,
.recent-heading svg,
.recent-item svg {
  width: 15px;
  height: 15px;
}
.section-copy,
.library-item p {
  color: var(--muted-foreground);
  font-size: 12px;
}
.save-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}
.library-list,
.recent-block {
  display: grid;
  gap: 8px;
}
.library-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px 8px;
  border-top: 1px solid var(--border);
  padding-top: 9px;
}
.library-item p {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.item-actions {
  grid-column: 2;
  grid-row: 1 / span 2;
  display: flex;
  align-items: center;
  gap: 4px;
}
.recent-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.recent-item {
  display: flex;
  min-height: 40px;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  background: var(--muted);
  text-align: left;
  font-size: 12px;
}
.recent-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@media (max-width: 1023px) {
  .recent-item {
    min-height: 44px;
  }
}
</style>
