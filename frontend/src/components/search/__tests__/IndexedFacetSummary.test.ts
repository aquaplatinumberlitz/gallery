import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import IndexedFacetSummary from "../IndexedFacetSummary.vue";

const coreGroups = [
  {
    id: "tools",
    label: "Tools",
    entries: [
      { value: "Unknown", count: 100 },
      { value: "SwarmUI", count: 46 },
    ],
  },
  {
    id: "orientation",
    label: "Orientation",
    entries: [
      { value: "portrait", count: 141 },
      { value: "square", count: 44 },
    ],
  },
  {
    id: "seed",
    label: "Seed",
    entries: [
      { value: "available", count: 107 },
      { value: "missing", count: 102 },
    ],
  },
  {
    id: "metadata",
    label: "Metadata",
    entries: [
      { value: "available", count: 209 },
      { value: "missing", count: 3 },
    ],
  },
];

describe("IndexedFacetSummary", () => {
  it("renders every short facet value and count without collapsing them into truncated text", () => {
    const wrapper = mount(IndexedFacetSummary, { props: { groups: coreGroups } });

    expect(wrapper.get('[aria-label="Tools indexed values"]').text()).toContain("Unknown100");
    expect(wrapper.get('[aria-label="Tools indexed values"]').text()).toContain("SwarmUI46");
    expect(wrapper.get('[aria-label="Orientation indexed values"]').text()).toContain("portrait141");
    expect(wrapper.get('[aria-label="Seed indexed values"]').text()).toContain("missing102");
    expect(wrapper.get('[aria-label="Metadata indexed values"]').text()).toContain("available209");
    expect(wrapper.find(".truncate").exists()).toBe(false);
  });

  it("reveals and collapses long facet groups through an accessible control", async () => {
    const wrapper = mount(IndexedFacetSummary, {
      props: {
        groups: [
          {
            id: "tools",
            label: "Tools",
            entries: [
              { value: "A1111", count: 20 },
              { value: "ComfyUI", count: 18 },
              { value: "SwarmUI", count: 12 },
              { value: "InvokeAI", count: 8 },
              { value: "Fooocus", count: 6 },
              { value: "NovelAI", count: 4 },
            ],
          },
        ],
      },
    });

    expect(wrapper.text()).not.toContain("Fooocus");
    const showMore = wrapper.get('button[aria-controls="indexed-facet-tools"]');
    expect(showMore.text()).toContain("Show 2 more");
    expect(showMore.attributes("aria-expanded")).toBe("false");

    await showMore.trigger("click");
    expect(wrapper.text()).toContain("Fooocus");
    expect(wrapper.text()).toContain("NovelAI");
    expect(showMore.text()).toContain("Show less");
    expect(showMore.attributes("aria-expanded")).toBe("true");

    await showMore.trigger("click");
    expect(wrapper.text()).not.toContain("Fooocus");
    expect(showMore.attributes("aria-expanded")).toBe("false");
  });
});
