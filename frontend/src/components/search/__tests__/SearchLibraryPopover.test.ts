import { beforeEach, describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import SearchLibraryPopover from "../SearchLibraryPopover.vue";

const request = {
  schema_version: 1 as const,
  mode: "lexical" as const,
  text: "portrait",
  scope: { kind: "all" as const },
  filters: { prompt_groups: [], workflow_groups: [] },
  cursor: null,
  limit: 60,
};

describe("SearchLibraryPopover", () => {
  beforeEach(() => localStorage.clear());

  it("saves and reruns the current canonical request", async () => {
    const wrapper = mount(SearchLibraryPopover, { props: { currentRequest: request } });
    await wrapper.get('input[aria-label="Saved search name"]').setValue("Portraits");
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Save"))!
      .trigger("click");
    expect(wrapper.findAll("input").some((input) => input.element.value === "Portraits")).toBe(true);
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Run"))!
      .trigger("click");
    expect(wrapper.emitted("apply")?.[0]?.[0]).toEqual(expect.objectContaining({ text: "portrait" }));
  });
});
