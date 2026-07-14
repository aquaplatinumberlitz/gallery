<script setup lang="ts">
import { computed } from "vue";
import Badge from "@/components/ui/Badge.vue";
import type { UnifiedSearchResult } from "@/types";

const props = defineProps<{ result: UnifiedSearchResult }>();

const matchLabel = computed(() => {
  const labels: Record<string, string> = {
    filename_exact: "Exact name",
    filename_prefix: "Name prefix",
    filename: "File name",
    prompt: "Prompt",
    negative_prompt: "Negative prompt",
    metadata: "Metadata",
  };
  return labels[props.result.match_type] ?? props.result.match_type.replaceAll("_", " ");
});

const generationDetails = computed(() =>
  [
    props.result.model ? `Model ${props.result.model}` : "",
    props.result.sampler ? `Sampler ${props.result.sampler}` : "",
    props.result.seed ? `Seed ${props.result.seed}` : "",
  ].filter(Boolean),
);
</script>

<template>
  <div class="search-result-metadata">
    <div class="search-result-metadata-heading">
      <Badge variant="secondary" class="search-result-match">{{ matchLabel }}</Badge>
      <span v-if="result.library_name" class="search-result-library">{{ result.library_name }}</span>
    </div>
    <p v-if="result.prompt_snippet" class="search-result-snippet">{{ result.prompt_snippet }}</p>
    <p v-if="generationDetails.length" class="search-result-generation">{{ generationDetails.join(" · ") }}</p>
  </div>
</template>

<style scoped>
.search-result-metadata {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.search-result-metadata-heading {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 6px;
}

.search-result-match {
  min-width: 0;
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
  text-transform: capitalize;
}

.search-result-library,
.search-result-generation,
.search-result-snippet {
  min-width: 0;
  overflow: hidden;
  color: var(--muted-foreground);
  font-size: 11px;
  line-height: 1.35;
  text-overflow: ellipsis;
}

.search-result-library,
.search-result-generation {
  white-space: nowrap;
}

.search-result-library {
  flex: 1;
  text-align: right;
}

.search-result-snippet {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
</style>
