<script setup lang="ts">
import { computed } from "vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { RelationReasonCodeV1 } from "@/types";

const props = defineProps<{ reasons: RelationReasonCodeV1[] }>();

const labels: Record<RelationReasonCodeV1, string> = {
  same_exact_signature: "Exact settings",
  same_recipe: "Same recipe",
  same_generation_family: "Same family",
  same_prompt: "Same prompt",
  strong_prompt_overlap: "Strong prompt overlap",
  same_model_hash: "Same model",
  same_model_name: "Same model",
  shared_lora: "Shared LoRA",
  shared_resource: "Shared resource",
  shared_workflow_property: "Shared workflow settings",
  similar_generation_settings: "Similar settings",
  visual_variant: "Visually similar",
};

const descriptions: Record<RelationReasonCodeV1, string> = {
  same_exact_signature:
    "Normalized prompts, model/resources, recipe settings, and recorded seed or exact workflow values match.",
  same_recipe:
    "Normalized prompts, model/resources, sampler, scheduler, dimensions, and recorded generation settings match; seed may differ.",
  same_generation_family: "Normalized prompts and model or resource identities match.",
  same_prompt: "Normalized positive and negative prompts match.",
  strong_prompt_overlap: "The indexed prompts share meaningful uncommon terms after normalization.",
  same_model_hash: "The recorded model hash matches.",
  same_model_name: "The normalized recorded model name matches.",
  shared_lora: "At least one recorded LoRA identity is shared.",
  shared_resource: "At least one recorded generation resource identity is shared.",
  shared_workflow_property: "At least one supported indexed workflow setting matches.",
  similar_generation_settings: "Recorded sampler, scheduler, dimensions, or numeric settings are close.",
  visual_variant:
    "Persisted image fingerprints are within the near-duplicate threshold. This does not prove a shared prompt or lineage.",
};

const visibleReasons = computed(() => {
  const byLabel = new Map<string, { label: string; description: string }>();
  for (const reason of props.reasons) {
    const label = labels[reason];
    if (!byLabel.has(label)) byLabel.set(label, { label, description: descriptions[reason] });
  }
  return [...byLabel.values()];
});
</script>

<template>
  <ul class="reason-list" aria-label="Why this asset is related">
    <li v-for="reason in visibleReasons" :key="reason.label">
      <Tooltip>
        <TooltipTrigger as-child>
          <span class="reason-chip" tabindex="0" :aria-label="`${reason.label}: ${reason.description}`">
            {{ reason.label }}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" class="max-w-[300px] text-pretty">
          {{ reason.description }}
        </TooltipContent>
      </Tooltip>
    </li>
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
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 3px 7px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--muted) 72%, transparent);
  color: var(--muted-foreground);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reason-chip:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}
</style>
