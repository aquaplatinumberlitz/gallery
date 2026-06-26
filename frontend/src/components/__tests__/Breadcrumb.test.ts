import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import Breadcrumb from "../Breadcrumb.vue";

function createWrapper(props: Record<string, unknown> = {}) {
  return mount(Breadcrumb, {
    props,
    global: {
      stubs: {
        BreadcrumbRoot: { template: "<div><slot /></div>" },
        BreadcrumbList: { template: "<ol><slot /></ol>" },
        BreadcrumbItem: { template: "<li><slot /></li>" },
        BreadcrumbLink: { template: "<button :disabled='disabled' @click='$emit(\"click\")'><slot /></button>" },
        BreadcrumbPage: { template: "<span><slot /></span>" },
        BreadcrumbSeparator: { template: "<span>/</span>" },
        Tooltip: { template: "<span><slot /></span>" },
        TooltipTrigger: { template: "<span><slot /></span>" },
        TooltipContent: { template: "<span><slot /></span>" },
      },
      directives: {
        "click-outside": { mounted() {} },
      },
    },
  });
}

describe("Breadcrumb", () => {
  it("renders 'No path' when no path prop", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("No path");
  });

  it("renders segments for a simple path", () => {
    const wrapper = createWrapper({ path: "/folder1/folder2" });
    expect(wrapper.text()).toContain("folder1");
    expect(wrapper.text()).toContain("folder2");
  });

  it("emits navigate with full path when clicking a non-last segment", async () => {
    const wrapper = createWrapper({ path: "/parent/child" });
    const links = wrapper.findAll("button");
    const parentBtn = links.find((b) => b.text() === "parent");
    expect(parentBtn).toBeDefined();
    await parentBtn!.trigger("click");
    expect(wrapper.emitted("navigate")).toBeTruthy();
    expect(wrapper.emitted("navigate")![0]).toEqual(["/parent"]);
  });

  it("renders last segment as page (not link)", () => {
    const wrapper = createWrapper({ path: "/only" });
    expect(wrapper.text()).toContain("only");
  });

  it("collapses path with more than maxVisible segments", () => {
    const wrapper = createWrapper({ path: "/a/b/c/d/e", maxVisible: 3 });
    expect(wrapper.text()).toContain("a");
    expect(wrapper.text()).toContain("d");
    expect(wrapper.text()).toContain("e");
  });

  it("renders ellipsis button when collapsed", () => {
    const wrapper = createWrapper({ path: "/a/b/c/d/e", maxVisible: 3 });
    expect(wrapper.find(".ellipsis-btn").exists()).toBe(true);
  });

  it("renders collapse button when expanded", async () => {
    const wrapper = createWrapper({ path: "/a/b/c/d/e", maxVisible: 3 });
    expect(wrapper.find(".collapse-btn").exists()).toBe(false);
    wrapper.vm.isExpanded = true;
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".collapse-btn").exists()).toBe(true);
  });

  it("handles Windows backslash paths", () => {
    const wrapper = createWrapper({ path: "\\folder1\\folder2" });
    expect(wrapper.text()).toContain("folder1");
    expect(wrapper.text()).toContain("folder2");
  });

  it("renders home icon", () => {
    const wrapper = createWrapper({ path: "/test" });
    expect(wrapper.find(".size-3\\.5").exists()).toBe(true);
  });
});
