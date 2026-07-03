import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import IndexProgressBar from "../IndexProgressBar.vue";

describe("IndexProgressBar", () => {
  it("renders with 0%", () => {
    const wrapper = mount(IndexProgressBar, { props: { percent: 0 } });
    expect(wrapper.findComponent({ name: "Progress" }).props("modelValue")).toBe(0);
  });

  it("renders with 50%", () => {
    const wrapper = mount(IndexProgressBar, { props: { percent: 50 } });
    expect(wrapper.findComponent({ name: "Progress" }).props("modelValue")).toBe(50);
  });

  it("renders with 100%", () => {
    const wrapper = mount(IndexProgressBar, { props: { percent: 100 } });
    expect(wrapper.findComponent({ name: "Progress" }).props("modelValue")).toBe(100);
  });

  it("uses warning before complete and success when full", async () => {
    const wrapper = mount(IndexProgressBar, { props: { percent: 50 } });
    expect(wrapper.findComponent({ name: "Progress" }).props("indicatorClass")).toBe("bg-warning");

    await wrapper.setProps({ percent: 100 });

    expect(wrapper.findComponent({ name: "Progress" }).props("indicatorClass")).toBe("bg-success");
  });
});
