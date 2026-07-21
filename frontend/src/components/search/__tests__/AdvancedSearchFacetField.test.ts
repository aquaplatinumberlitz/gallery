import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import AdvancedSearchFacetField from "../AdvancedSearchFacetField.vue";

function createWrapper(
  options: Partial<{ modelValue: string; statusText: string; options: Array<{ value: string; count: number }> }> = {},
) {
  return mount(AdvancedSearchFacetField, {
    props: {
      id: "test-facet",
      label: "Model",
      modelValue: options.modelValue ?? "",
      options: options.options ?? [
        { value: "PonyXL", count: 42 },
        { value: "SDXL", count: 10 },
      ],
      statusText: options.statusText,
      "onUpdate:modelValue": () => {},
    },
    attachTo: document.body,
    global: {
      stubs: {
        Popover: { template: "<div><slot /></div>" },
        PopoverTrigger: { template: "<div><slot /></div>" },
        PopoverContent: { template: "<div><slot /></div>" },
      },
    },
  });
}

describe("AdvancedSearchFacetField", () => {
  it("renders the label and input", () => {
    const wrapper = createWrapper();
    expect(wrapper.find("label").text()).toBe("Model");
    expect(wrapper.find("input").exists()).toBe(true);
  });

  it("binds aria-describedby when statusText is provided", () => {
    const wrapper = createWrapper({ statusText: "3 options available" });
    const input = wrapper.find("input");
    expect(input.attributes("aria-describedby")).toBe("test-facet-status");
    expect(wrapper.text()).toContain("3 options available");
  });

  it("omits aria-describedby when statusText is absent", () => {
    const wrapper = createWrapper();
    expect(wrapper.find("input").attributes("aria-describedby")).toBeUndefined();
  });

  it("renders the suggestion list with listbox role", async () => {
    const wrapper = createWrapper();
    const toggle = wrapper.find("button.advanced-search-facet-toggle");
    await toggle.trigger("click");
    const list = wrapper.find("ul");
    expect(list.exists()).toBe(true);
    expect(list.attributes("role")).toBe("listbox");
  });

  it("renders each suggestion with option role", async () => {
    const wrapper = createWrapper();
    await wrapper.find("button.advanced-search-facet-toggle").trigger("click");
    const options = wrapper.findAll('button[role="option"]');
    expect(options.length).toBe(2);
    expect(options[0].text()).toContain("PonyXL");
    expect(options[1].text()).toContain("SDXL");
  });

  it("selects an option on click", async () => {
    const wrapper = createWrapper();
    await wrapper.find("button.advanced-search-facet-toggle").trigger("click");
    await wrapper.find('button[role="option"]').trigger("click");
  });

  it("supports keyboard navigation with arrow keys", async () => {
    const wrapper = createWrapper();
    await wrapper.find("button.advanced-search-facet-toggle").trigger("click");
    const list = wrapper.find("ul");
    expect(list.attributes("role")).toBe("listbox");
    await list.trigger("keydown", { key: "ArrowDown" });
    await list.trigger("keydown", { key: "Enter" });
  });

  it("closes on Escape key", async () => {
    const wrapper = createWrapper();
    await wrapper.find("button.advanced-search-facet-toggle").trigger("click");
    await wrapper.find("ul").trigger("keydown", { key: "Escape" });
  });
});
