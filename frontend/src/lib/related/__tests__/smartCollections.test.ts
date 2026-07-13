/**
 * Purpose: Protect canonical smart-collection descriptors without stored membership.
 * Guarantees: Collections use Search V2 requests or persisted facts/relations and never contain asset lists.
 * Run when: Changing Related Assets smart collection definitions.
 */
import { describe, expect, it } from "vitest";
import { buildRelatedSmartCollections } from "../smartCollections";

describe("buildRelatedSmartCollections", () => {
  it("builds bounded relation facts and canonical model/LoRA queries", () => {
    const collections = buildRelatedSmartCollections({
      scope: { kind: "library", library_id: 4 },
      referenceAssetId: 9,
      model: 'Forest "XL"',
      lora: "fox-detail",
    });
    expect(collections.map((item) => item.id)).toEqual([
      "same-generation-family",
      "same-recipe",
      "visual-variants",
      "missing-recorded-metadata",
      "recent-model",
      "recent-lora",
    ]);
    const model = collections.find((item) => item.id === "recent-model");
    expect(model?.source).toBe("search-v2");
    if (model?.source === "search-v2") expect(model.request.text).toBe('model:"Forest \\"XL\\""');
    expect(collections.every((item) => !("items" in item))).toBe(true);
  });
});
