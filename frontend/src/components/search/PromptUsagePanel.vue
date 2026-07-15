<script setup lang="ts">
import { computed, shallowRef } from "vue";
import { Image, LoaderCircle } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import CopyActionButton from "@/components/ui/CopyActionButton.vue";
import Input from "@/components/ui/Input.vue";
import { useClipboard } from "@/composables/useClipboard";
import { usePromptUsageQuery } from "@/composables/usePromptUsageQuery";
import { getThumbnailUrl } from "@/services/api";
import type { SearchPromptGroupV1, SearchScopeV1 } from "@/types";

const props = defineProps<{ scope: SearchScopeV1 | null; enabled: boolean }>();
const emit = defineEmits<{ showAssets: [group: SearchPromptGroupV1] }>();
const polarity = shallowRef<"positive" | "negative">("positive");
const sort = shallowRef<"usage" | "recent">("usage");
const text = shallowRef("");
const copiedId = shallowRef("");
const polarities = ["positive", "negative"] as const;
const { copyText } = useClipboard();

const request = computed(() =>
  props.scope
    ? {
        polarity: polarity.value,
        scope: props.scope,
        text: text.value.trim() || null,
        prefix: null,
        sort: sort.value,
        limit: 40,
      }
    : null,
);
const usage = usePromptUsageQuery(
  request,
  computed(() => props.enabled),
);

async function copyPrompt(event: MouseEvent, valueId: string, prompt: string) {
  const fallbackRoot = event.currentTarget instanceof Element ? event.currentTarget : null;
  const copied = await copyText(prompt, "prompt", { fallbackRoot });
  if (!copied) {
    copiedId.value = "";
    return;
  }
  copiedId.value = valueId;
  window.setTimeout(() => {
    if (copiedId.value === valueId) copiedId.value = "";
  }, 1_500);
}
</script>

<template>
  <section class="prompt-panel" aria-labelledby="prompt-usage-title">
    <div class="panel-heading">
      <div>
        <p id="prompt-usage-title" class="panel-title">Prompt usage</p>
        <p class="panel-copy">Browse normalized prompts, then narrow the gallery to one exact group.</p>
      </div>
      <select v-model="sort" aria-label="Prompt sort order" class="compact-select">
        <option value="usage">Most used</option>
        <option value="recent">Most recent</option>
      </select>
    </div>

    <div class="prompt-controls">
      <div class="tab-list" role="tablist" aria-label="Prompt polarity">
        <button
          v-for="kind in polarities"
          :key="kind"
          type="button"
          role="tab"
          :aria-selected="polarity === kind"
          :class="{ active: polarity === kind }"
          @click="polarity = kind"
        >
          {{ kind === "positive" ? "Positive" : "Negative" }}
        </button>
      </div>
      <Input v-model="text" aria-label="Filter prompt groups" placeholder="Filter prompt text" maxlength="512" />
    </div>

    <div v-if="usage.isPending.value" class="panel-state"><LoaderCircle class="spin" /> Loading prompt groups…</div>
    <div v-else-if="usage.isError.value" class="panel-state error">
      Prompt groups are unavailable until the index is ready.
    </div>
    <div v-else-if="usage.items.value.length === 0" class="panel-state">No {{ polarity }} prompts in this scope.</div>
    <ul v-else class="prompt-list">
      <li v-for="item in usage.items.value" :key="item.value_id" class="prompt-row">
        <img :src="getThumbnailUrl(item.sample_asset.path, 128)" alt="" loading="lazy" />
        <div class="prompt-text">
          <p>{{ item.text }}</p>
          <span>{{ item.asset_count }} asset{{ item.asset_count === 1 ? "" : "s" }}</span>
        </div>
        <div class="prompt-actions">
          <CopyActionButton
            :copied="copiedId === item.value_id"
            label="Copy"
            success-aria-label="Prompt copied"
            @click="copyPrompt($event, item.value_id, item.text)"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            @click="emit('showAssets', { kind: item.kind, value_id: item.value_id })"
          >
            <Image /> Show assets
          </Button>
        </div>
      </li>
    </ul>
    <Button
      v-if="usage.hasNextPage.value"
      type="button"
      variant="outline"
      size="sm"
      :disabled="usage.isFetchingNextPage.value"
      @click="usage.fetchNextPage()"
    >
      {{ usage.isFetchingNextPage.value ? "Loading…" : "Load more prompts" }}
    </Button>
  </section>
</template>

<style scoped>
.prompt-panel {
  display: grid;
  gap: 12px;
}
.panel-heading,
.prompt-controls,
.prompt-row,
.prompt-actions {
  display: flex;
  align-items: center;
}
.panel-heading {
  justify-content: space-between;
  gap: 12px;
}
.panel-title {
  font-size: 14px;
  font-weight: 650;
}
.panel-copy,
.prompt-text span {
  color: var(--muted-foreground);
  font-size: 12px;
}
.compact-select {
  min-height: 36px;
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 0 28px 0 9px;
  background: var(--background);
  font-size: 12px;
}
.prompt-controls {
  gap: 8px;
}
.tab-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 2px;
}
.tab-list button {
  min-height: 32px;
  border-radius: 6px;
  padding: 0 10px;
  color: var(--muted-foreground);
  font-size: 12px;
}
.tab-list button.active {
  background: var(--foreground);
  color: var(--background);
}
.panel-state {
  display: flex;
  min-height: 64px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px dashed var(--border);
  border-radius: 8px;
  color: var(--muted-foreground);
  font-size: 12px;
}
.panel-state.error {
  color: var(--destructive);
}
.prompt-list {
  display: grid;
  max-height: 360px;
  gap: 7px;
  overflow-y: auto;
}
.prompt-row {
  position: relative;
  gap: 9px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
}
.prompt-row img {
  width: 44px;
  height: 44px;
  flex: none;
  border-radius: 6px;
  background: var(--muted);
  object-fit: cover;
}
.prompt-text {
  min-width: 0;
  flex: 1;
}
.prompt-text p {
  display: -webkit-box;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.prompt-actions {
  gap: 4px;
}
.spin {
  width: 15px;
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (max-width: 640px) {
  .prompt-controls {
    align-items: stretch;
    flex-direction: column;
  }
  .prompt-actions {
    flex-direction: column;
  }
  .prompt-row {
    align-items: flex-start;
  }
}
</style>
