import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import WorkflowFilterBuilder from "../WorkflowFilterBuilder.vue";
import type { WorkflowRegistryPropertyV1 } from "@/types";

const registry: Record<string, Record<string, WorkflowRegistryPropertyV1>> = {
  KSampler: {
    steps: { type: "integer", operators: ["eq", "gte"] },
    sampler_name: { type: "text", operators: ["eq", "contains"] },
  },
};

describe("WorkflowFilterBuilder", () => {
  it("renders only registry controls and emits typed supported predicates", async () => {
    const wrapper = mount(WorkflowFilterBuilder, { props: { registry, initialGroups: [] } });
    await wrapper.get("button").trigger("click");
    expect(wrapper.text()).toContain("KSampler");
    expect(wrapper.text()).toContain("steps");
    expect(wrapper.text()).not.toContain("DROP TABLE");
    const value = wrapper.get('input[aria-label="Value for group 1, row 1"]');
    await value.setValue("20");
    const apply = wrapper.findAll("button").find((button) => button.text().includes("Show matching assets"));
    await apply!.trigger("click");
    expect(wrapper.emitted("apply")?.[0]).toEqual([
      [{ node_type: "KSampler", predicates: [{ property: "steps", op: "eq", value: 20 }] }],
    ]);
  });

  it("does not emit while a predicate row is invalid", async () => {
    const wrapper = mount(WorkflowFilterBuilder, { props: { registry, initialGroups: [] } });
    await wrapper.get("button").trigger("click");
    expect(wrapper.text()).toContain("Enter a value");
    const apply = wrapper.findAll("button").find((button) => button.text().includes("Show matching assets"));
    expect(apply!.attributes("disabled")).toBeDefined();
  });

  it("rejects fractional integer and overflowing uint64 drafts before emit", async () => {
    const integerWrapper = mount(WorkflowFilterBuilder, { props: { registry, initialGroups: [] } });
    await integerWrapper.get("button").trigger("click");
    await integerWrapper.get('input[aria-label="Value for group 1, row 1"]').setValue("1.5");
    expect(integerWrapper.text()).toContain("Enter a whole number");
    expect(integerWrapper.emitted("apply")).toBeUndefined();

    const uintWrapper = mount(WorkflowFilterBuilder, {
      props: {
        registry: { KSampler: { seed: { type: "uint64_token", operators: ["eq"] } } },
        initialGroups: [],
      },
    });
    await uintWrapper.get("button").trigger("click");
    await uintWrapper.get('input[aria-label="Value for group 1, row 1"]').setValue("18446744073709551616");
    expect(uintWrapper.text()).toContain("Value exceeds uint64");
    expect(uintWrapper.emitted("apply")).toBeUndefined();
  });

  it("maps backend 422 paths to the exact predicate row", () => {
    const wrapper = mount(WorkflowFilterBuilder, {
      props: {
        registry,
        initialGroups: [{ node_type: "KSampler", predicates: [{ property: "steps", op: "gte", value: 20 }] }],
        serverFieldErrors: {
          "filters.workflow_groups[0].predicates[0].op": "Unsupported operator from server",
        },
      },
    });
    expect(wrapper.text()).toContain("Unsupported operator from server");
  });
});
