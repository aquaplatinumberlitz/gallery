import type { RelatedSearchResultV1 } from "@/types";

const TIER_VALUES = [100, 90, 80, 70, 60, 40] as const;

function strongestTier(left: RelatedSearchResultV1["relation_tier"], right: RelatedSearchResultV1["relation_tier"]) {
  const value = Math.max(left, right);
  return TIER_VALUES.find((tier) => tier === value) ?? left;
}

export function normalizeRelatedResults(items: RelatedSearchResultV1[]): RelatedSearchResultV1[] {
  const order: number[] = [];
  const byAssetId = new Map<number, RelatedSearchResultV1>();

  for (const item of items) {
    const existing = byAssetId.get(item.asset_id);
    if (!existing) {
      order.push(item.asset_id);
      byAssetId.set(item.asset_id, {
        ...item,
        relation_reasons: [...new Set(item.relation_reasons)],
      });
      continue;
    }

    byAssetId.set(item.asset_id, {
      ...existing,
      relation_tier: strongestTier(existing.relation_tier, item.relation_tier),
      relation_reasons: [...new Set([...existing.relation_reasons, ...item.relation_reasons])],
      metadata_score:
        existing.metadata_score === null
          ? item.metadata_score
          : item.metadata_score === null
            ? existing.metadata_score
            : Math.max(existing.metadata_score, item.metadata_score),
      visual_distance:
        existing.visual_distance === null
          ? item.visual_distance
          : item.visual_distance === null
            ? existing.visual_distance
            : Math.min(existing.visual_distance, item.visual_distance),
    });
  }

  return order.flatMap((assetId) => {
    const item = byAssetId.get(assetId);
    return item ? [item] : [];
  });
}
