/**
 * Purpose: Protect evidence-based generation-family summary counts.
 * Guarantees: Visual similarity tiers never inflate exact, recipe, or family counts.
 * Run when: Changing relation reasons, tier presentation, or generation comparison summaries.
 */
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { RelatedSearchResultV1 } from "@/types";
import GenerationFamilySummary from "../GenerationFamilySummary.vue";

const result = (overrides: Partial<RelatedSearchResultV1>): RelatedSearchResultV1 => ({
  asset_id: 2,
  library_id: 1,
  library_name: "Library",
  name: "candidate.png",
  path: "/library/candidate.png",
  type: "image",
  parent_path: "/library",
  relative_path: "",
  mtime: 2,
  width: 512,
  height: 512,
  match_type: "related",
  model: "Example XL",
  sampler: "Euler",
  seed: "42",
  prompt_snippet: "portrait",
  relation_tier: 80,
  relation_reasons: ["visual_variant"],
  visual_distance: 2,
  metadata_score: null,
  ...overrides,
});

describe("GenerationFamilySummary", () => {
  it("counts generation evidence from reasons instead of numeric tiers", () => {
    const wrapper = mount(GenerationFamilySummary, {
      props: {
        results: [
          result({}),
          result({
            asset_id: 3,
            relation_tier: 90,
            relation_reasons: ["same_recipe", "same_generation_family"],
          }),
        ],
        referenceMetadata: null,
        candidateMetadata: null,
      },
    });
    const counts = wrapper.findAll(".summary-counts dd").map((item) => item.text());

    expect(counts).toEqual(["0", "1", "1"]);
  });
});
