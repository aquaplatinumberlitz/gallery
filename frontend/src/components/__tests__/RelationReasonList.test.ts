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
    expect(wrapper.text()).toContain("Same recorded recipe");
    expect(wrapper.text()).toContain("Shared LoRA");
    expect(wrapper.text()).toContain("Visual near-duplicate");
    expect(wrapper.text()).not.toMatch(/\d+%/);
  });
});
