/**
 * Purpose: Protect defensive Related Assets response normalization.
 * Guarantees: Duplicate assets union evidence without changing the server's first-seen ordering.
 * Run when: Changing Related Assets response shaping, deduplication, reasons, or ranking display.
 */
import { describe, expect, it } from "vitest";
import type { RelatedSearchResultV1 } from "@/types";
import { normalizeRelatedResults } from "../relatedAssets";

const result = (assetId: number, overrides: Partial<RelatedSearchResultV1> = {}): RelatedSearchResultV1 => ({
  asset_id: assetId,
  library_id: 1,
  library_name: "Library",
  name: `${assetId}.png`,
  path: `/library/${assetId}.png`,
  type: "image",
  parent_path: "/library",
  relative_path: "",
  mtime: assetId,
  width: 512,
  height: 512,
  match_type: "related",
  model: "model",
  sampler: "Euler",
  seed: `${assetId}`,
  prompt_snippet: "prompt",
  relation_tier: 60,
  relation_reasons: ["same_prompt"],
  visual_distance: null,
  metadata_score: 0.6,
  ...overrides,
});

describe("normalizeRelatedResults", () => {
  it("deduplicates by asset ID, unions reasons, and preserves server ordering", () => {
    const normalized = normalizeRelatedResults([
      result(8),
      result(3, { relation_reasons: ["visual_variant"], visual_distance: 2, metadata_score: null }),
      result(8, {
        relation_tier: 80,
        relation_reasons: ["visual_variant", "same_model_hash"],
        visual_distance: 3,
        metadata_score: null,
      }),
      result(5),
    ]);

    expect(normalized.map((item) => item.asset_id)).toEqual([8, 3, 5]);
    expect(normalized[0]).toMatchObject({
      relation_tier: 80,
      relation_reasons: ["same_prompt", "visual_variant", "same_model_hash"],
      metadata_score: 0.6,
      visual_distance: 3,
    });
  });
});
