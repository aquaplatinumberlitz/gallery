<script setup lang="ts">
import { computed } from "vue";
import { GitCompareArrows, Layers3 } from "lucide-vue-next";
import { useGenerationComparison } from "@/composables/useGenerationComparison";
import type { MetadataResponse, RelatedSearchResultV1 } from "@/types";

const props = defineProps<{
  results: RelatedSearchResultV1[];
  referenceMetadata: MetadataResponse | null;
  candidateMetadata: MetadataResponse | null;
  candidateName?: string;
}>();

const exactCount = computed(
  () => props.results.filter((item) => item.relation_reasons.includes("same_exact_signature")).length,
);
const recipeCount = computed(
  () => props.results.filter((item) => item.relation_reasons.includes("same_recipe")).length,
);
const familyCount = computed(
  () => props.results.filter((item) => item.relation_reasons.includes("same_generation_family")).length,
);
const { comparisons, changed } = useGenerationComparison(
  () => props.referenceMetadata,
  () => props.candidateMetadata,
);
</script>

<template>
  <section class="family-summary" aria-labelledby="family-summary-title">
    <div class="summary-heading">
      <Layers3 class="size-4" />
      <div>
        <h3 id="family-summary-title">Recorded-generation summary</h3>
        <p>Same recorded settings are grouped as evidence; this does not claim lineage.</p>
      </div>
    </div>
    <dl class="summary-counts">
      <div>
        <dt>Exact settings</dt>
        <dd>{{ exactCount }}</dd>
      </div>
      <div>
        <dt>Same recipe</dt>
        <dd>{{ recipeCount }}</dd>
      </div>
      <div>
        <dt>Same family</dt>
        <dd>{{ familyCount }}</dd>
      </div>
    </dl>

    <div v-if="candidateMetadata && comparisons.length" class="comparison-block">
      <div class="comparison-title">
        <GitCompareArrows class="size-4" />
        <span>Compared with {{ candidateName || "selected asset" }}</span>
        <span class="changed-count">{{ changed.length }} changed</span>
      </div>
      <dl class="comparison-grid">
        <div v-for="item in comparisons" :key="item.key" :class="{ changed: item.changed }">
          <dt>{{ item.label }}</dt>
          <dd>
            <span>{{ item.reference || "Not recorded" }}</span>
            <span aria-hidden="true">→</span>
            <span>{{ item.candidate || "Not recorded" }}</span>
          </dd>
        </div>
      </dl>
    </div>
  </section>
</template>

<style scoped>
.family-summary {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: color-mix(in srgb, var(--card) 90%, var(--muted));
}

.summary-heading,
.comparison-title {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.summary-heading h3,
.summary-heading p {
  margin: 0;
}

.summary-heading h3 {
  font-size: 13px;
}

.summary-heading p {
  margin-top: 2px;
  color: var(--muted-foreground);
  font-size: 11px;
}

.summary-counts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  border-radius: 10px;
  background: var(--border);
}

.summary-counts div {
  padding: 9px;
  background: var(--background);
}

.summary-counts dt {
  color: var(--muted-foreground);
  font-size: 10px;
}

.summary-counts dd {
  margin: 3px 0 0;
  font-size: 17px;
  font-weight: 750;
}

.comparison-block {
  display: grid;
  gap: 8px;
}

.comparison-title {
  align-items: center;
  font-size: 11px;
  font-weight: 650;
}

.changed-count {
  margin-left: auto;
  color: var(--muted-foreground);
}

.comparison-grid {
  display: grid;
  gap: 5px;
  margin: 0;
}

.comparison-grid > div {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  gap: 8px;
  padding: 7px 8px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--muted) 62%, transparent);
}

.comparison-grid > div.changed {
  background: color-mix(in srgb, var(--warning, #d98b1d) 13%, var(--muted));
}

.comparison-grid dt {
  color: var(--muted-foreground);
  font-size: 10px;
}

.comparison-grid dd {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 6px;
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 10px;
}
</style>
