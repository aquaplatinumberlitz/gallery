<script setup lang="ts">
import type { RelationReasonCodeV1 } from "@/types";

defineProps<{ reasons: RelationReasonCodeV1[] }>();

const labels: Record<RelationReasonCodeV1, string> = {
  same_exact_signature: "Same exact recorded settings",
  same_recipe: "Same recorded recipe",
  same_generation_family: "Same generation family",
  same_prompt: "Same normalized prompt",
  strong_prompt_overlap: "Strong prompt overlap",
  same_model_hash: "Same model hash",
  same_model_name: "Same model name",
  shared_lora: "Shared LoRA",
  shared_resource: "Shared resource",
  shared_workflow_property: "Shared workflow setting",
  similar_generation_settings: "Similar recorded settings",
  visual_variant: "Visual near-duplicate",
};
</script>

<template>
  <ul class="reason-list" aria-label="Why this asset is related">
    <li v-for="reason in reasons" :key="reason" class="reason-chip">{{ labels[reason] }}</li>
  </ul>
</template>

<style scoped>
.reason-list {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  gap: 5px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.reason-chip {
  max-width: 100%;
  padding: 3px 7px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--muted) 72%, transparent);
  color: var(--muted-foreground);
  font-size: 10px;
  font-weight: 650;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
