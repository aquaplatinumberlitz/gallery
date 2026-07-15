/**
 * Purpose: Protect stable accessible copy for backend relation reason codes.
 * Guarantees: Every reason maps to transparent non-probabilistic language.
 * Run when: Changing Related Assets reason codes or localized labels.
 */
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import RelationReasonList from "../RelationReasonList.vue";

describe("RelationReasonList", () => {
  it("maps typed reasons to stable accessible evidence chips", () => {
    const wrapper = mount(RelationReasonList, {
      props: { reasons: ["same_recipe", "shared_lora", "visual_variant"] },
    });
    expect(wrapper.get("ul").attributes("aria-label")).toBe("Why this asset is related");
    expect(wrapper.text()).toContain("Same recipe");
    expect(wrapper.text()).toContain("Shared LoRA");
    expect(wrapper.text()).toContain("Visually similar");
    expect(wrapper.text()).not.toMatch(/\d+%/);
    expect(wrapper.find('[aria-label^="Same recipe:"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label^="Visually similar:"]').attributes("aria-label")).toContain(
      "does not prove a shared prompt or lineage",
    );
  });

  it("collapses multiple backend model reason codes into one honest badge", () => {
    const wrapper = mount(RelationReasonList, {
      props: { reasons: ["same_model_hash", "same_model_name"] },
    });
    expect(wrapper.findAll("li")).toHaveLength(1);
    expect(wrapper.get(".reason-chip").text()).toBe("Same model");
  });
});
