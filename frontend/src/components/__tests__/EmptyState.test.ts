import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import EmptyState from "../EmptyState.vue";

describe("EmptyState", () => {
  it("renders default empty-folder state", () => {
    const wrapper = mount(EmptyState);
    expect(wrapper.text()).toContain("This folder is empty");
    expect(wrapper.text()).toContain("No images or subfolders found here");
  });

  it("renders no-results type", () => {
    const wrapper = mount(EmptyState, { props: { type: "no-results" } });
    expect(wrapper.text()).toContain("No results found");
  });

  it("renders error type", () => {
    const wrapper = mount(EmptyState, { props: { type: "error" } });
    expect(wrapper.text()).toContain("Something went wrong");
  });

  it("renders no-path type (welcome)", () => {
    const wrapper = mount(EmptyState, { props: { type: "no-path" } });
    expect(wrapper.text()).toContain("Welcome to Gallery");
  });

  it("renders loading type", () => {
    const wrapper = mount(EmptyState, { props: { type: "loading" } });
    expect(wrapper.text()).toContain("Loading...");
  });

  it("renders custom title", () => {
    const wrapper = mount(EmptyState, { props: { title: "Custom Title" } });
    expect(wrapper.text()).toContain("Custom Title");
  });

  it("renders action button and emits event on click", async () => {
    const wrapper = mount(EmptyState, { props: { actionLabel: "Retry", actionIcon: "arrow-left" } });
    expect(wrapper.text()).toContain("Retry");
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted("action")).toHaveLength(1);
  });

  it("does not render button when no actionLabel", () => {
    const wrapper = mount(EmptyState);
    expect(wrapper.find("button").exists()).toBe(false);
  });

  it("applies compact class", () => {
    const wrapper = mount(EmptyState, { props: { compact: true } });
    expect(wrapper.classes()).toContain("compact");
  });

  it("spins icon on loading type", () => {
    const wrapper = mount(EmptyState, { props: { type: "loading" } });
    const iconWrap = wrapper.find(".icon-spin");
    expect(iconWrap.exists()).toBe(true);
  });
});
