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

/**
 * Semantic color tier per reason code.
 * Higher-confidence reasons get warmer/brighter tints.
 * "visual" gets its own distinct hue (rose) to distinguish pixel-similarity from metadata.
 */
const colorTier: Record<RelationReasonCodeV1, string> = {
  // Tier: exact — indigo/violet (highest confidence)
  same_exact_signature: "exact",
  // Tier: recipe — amber (strong, structured match)
  same_recipe: "recipe",
  same_generation_family: "recipe",
  // Tier: prompt — sky/cyan (semantic match)
  same_prompt: "prompt",
  strong_prompt_overlap: "prompt",
  // Tier: model — teal (resource match)
  same_model_hash: "model",
  same_model_name: "model",
  shared_lora: "model",
  shared_resource: "model",
  shared_workflow_property: "model",
  similar_generation_settings: "model",
  // Tier: visual — rose (pixel-based, separate from metadata)
  visual_variant: "visual",
};

const visibleReasons = computed(() => {
  const byLabel = new Map<string, { label: string; description: string; tier: string }>();
  for (const reason of props.reasons) {
    const label = labels[reason];
    if (!byLabel.has(label)) byLabel.set(label, { label, description: descriptions[reason], tier: colorTier[reason] });
  }
  return [...byLabel.values()];
});
</script>

<template>
  <ul class="reason-list" aria-label="Why this asset is related">
    <li v-for="reason in visibleReasons" :key="reason.label">
      <Tooltip>
        <TooltipTrigger as-child>
          <span
            class="reason-chip"
            :data-tier="reason.tier"
            tabindex="0"
            :aria-label="`${reason.label}: ${reason.description}`"
          >
            <span class="reason-dot" aria-hidden="true" />
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

/* ── Base chip ── */
.reason-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  padding: 2px 7px 2px 5px;
  overflow: hidden;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 600;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: default;
  transition: filter 120ms ease;

  /* fallback: neutral */
  border: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
  background: color-mix(in srgb, var(--muted) 60%, transparent);
  color: var(--muted-foreground);
}

.reason-chip:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

/* ── Dot indicator ── */
.reason-dot {
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
  background-color: currentColor;
  opacity: 0.7;
}

/* ── Semantic tiers ── */

/* Exact settings — indigo: highest confidence, structured + seed match */
.reason-chip[data-tier="exact"] {
  background: color-mix(in srgb, #6366f1 10%, var(--background));
  border-color: color-mix(in srgb, #6366f1 35%, transparent);
  color: color-mix(in srgb, #818cf8 90%, var(--foreground));
}
.reason-chip[data-tier="exact"] .reason-dot {
  background-color: #818cf8;
  opacity: 1;
}

/* Same recipe / family — amber: strong generation match */
.reason-chip[data-tier="recipe"] {
  background: color-mix(in srgb, #f59e0b 8%, var(--background));
  border-color: color-mix(in srgb, #f59e0b 30%, transparent);
  color: color-mix(in srgb, #fbbf24 85%, var(--foreground));
}
.reason-chip[data-tier="recipe"] .reason-dot {
  background-color: #f59e0b;
  opacity: 1;
}

/* Same prompt / overlap — sky: semantic/text match */
.reason-chip[data-tier="prompt"] {
  background: color-mix(in srgb, #38bdf8 8%, var(--background));
  border-color: color-mix(in srgb, #38bdf8 30%, transparent);
  color: color-mix(in srgb, #7dd3fc 85%, var(--foreground));
}
.reason-chip[data-tier="prompt"] .reason-dot {
  background-color: #38bdf8;
  opacity: 1;
}

/* Model / LoRA / resource match — teal */
.reason-chip[data-tier="model"] {
  background: color-mix(in srgb, #14b8a6 8%, var(--background));
  border-color: color-mix(in srgb, #14b8a6 28%, transparent);
  color: color-mix(in srgb, #2dd4bf 85%, var(--foreground));
}
.reason-chip[data-tier="model"] .reason-dot {
  background-color: #14b8a6;
  opacity: 1;
}

/* Visually similar — rose: pixel-based, intentionally distinct from metadata */
.reason-chip[data-tier="visual"] {
  background: color-mix(in srgb, #f43f5e 8%, var(--background));
  border-color: color-mix(in srgb, #f43f5e 28%, transparent);
  color: color-mix(in srgb, #fb7185 85%, var(--foreground));
}
.reason-chip[data-tier="visual"] .reason-dot {
  background-color: #f43f5e;
  opacity: 1;
}

/* ── Light mode overrides: darken text for readability ── */
html[data-theme="light"] .reason-chip[data-tier="exact"] {
  color: #4338ca;
}
html[data-theme="light"] .reason-chip[data-tier="recipe"] {
  color: #92400e;
}
html[data-theme="light"] .reason-chip[data-tier="prompt"] {
  color: #0369a1;
}
html[data-theme="light"] .reason-chip[data-tier="model"] {
  color: #0f766e;
}
html[data-theme="light"] .reason-chip[data-tier="visual"] {
  color: #be185d;
}
</style>
