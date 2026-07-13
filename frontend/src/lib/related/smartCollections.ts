import type { PersistableSearchRequestV1, RelatedProfileV1, SearchScopeV1 } from "@/types";
import { emptySearchFilters } from "@/utils/searchRequest";

export type RelatedSmartCollection =
  | {
      id: "same-generation-family" | "same-recipe" | "visual-variants";
      label: string;
      source: "persisted-relation";
      relation: { reference_asset_id: number; profile: RelatedProfileV1; scope: SearchScopeV1; minimum_tier?: number };
    }
  | {
      id: "missing-recorded-metadata";
      label: string;
      source: "persisted-fact";
      fact: "missing-prompt-or-model";
      scope: SearchScopeV1;
    }
  | {
      id: "recent-model" | "recent-lora";
      label: string;
      source: "search-v2";
      request: PersistableSearchRequestV1;
    };

const quoteFieldValue = (value: string) => `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;

export function buildRelatedSmartCollections(options: {
  scope: SearchScopeV1;
  referenceAssetId?: number | null;
  model?: string | null;
  lora?: string | null;
}): RelatedSmartCollection[] {
  const collections: RelatedSmartCollection[] = [
    {
      id: "missing-recorded-metadata",
      label: "Missing prompt or model",
      source: "persisted-fact",
      fact: "missing-prompt-or-model",
      scope: structuredClone(options.scope),
    },
  ];
  if (options.referenceAssetId) {
    collections.unshift(
      {
        id: "same-generation-family",
        label: "Same generation family",
        source: "persisted-relation",
        relation: {
          reference_asset_id: options.referenceAssetId,
          profile: "related",
          scope: structuredClone(options.scope),
          minimum_tier: 80,
        },
      },
      {
        id: "same-recipe",
        label: "Same recorded recipe",
        source: "persisted-relation",
        relation: {
          reference_asset_id: options.referenceAssetId,
          profile: "recipe",
          scope: structuredClone(options.scope),
        },
      },
      {
        id: "visual-variants",
        label: "Visual variants",
        source: "persisted-relation",
        relation: {
          reference_asset_id: options.referenceAssetId,
          profile: "visual",
          scope: structuredClone(options.scope),
        },
      },
    );
  }
  for (const [id, label, field, value] of [
    ["recent-model", "Recently indexed for model", "model", options.model],
    ["recent-lora", "Recently indexed for LoRA", "lora", options.lora],
  ] as const) {
    if (!value?.trim()) continue;
    collections.push({
      id,
      label,
      source: "search-v2",
      request: {
        schema_version: 1,
        mode: "lexical",
        text: `${field}:${quoteFieldValue(value.trim())}`,
        scope: structuredClone(options.scope),
        filters: emptySearchFilters(),
      },
    });
  }
  return collections;
}
