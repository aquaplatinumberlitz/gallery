import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import IndexProgressBar from "../IndexProgressBar.vue";

describe("IndexProgressBar", () => {
  it("renders with 0%", () => {
    const wrapper = mount(IndexProgressBar, { props: { percent: 0 } });
    expect(wrapper.find(".index-progress-bar__fill").attributes("style")).toContain("width: 0%");
  });

  it("renders with 50%", () => {
    const wrapper = mount(IndexProgressBar, { props: { percent: 50 } });
    expect(wrapper.find(".index-progress-bar__fill").attributes("style")).toContain("width: 50%");
  });

  it("renders with 100%", () => {
    const wrapper = mount(IndexProgressBar, { props: { percent: 100 } });
    expect(wrapper.find(".index-progress-bar__fill").attributes("style")).toContain("width: 100%");
  });
});
