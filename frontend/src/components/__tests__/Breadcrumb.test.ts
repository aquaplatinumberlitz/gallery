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
        "click-outside": {
          mounted(el: HTMLElement, binding: { value: () => void }) {
            el.__clickOutsideHandler = (event: Event) => {
              if (!(el === event.target || el.contains(event.target as Node))) {
                binding.value();
              }
            };
            document.addEventListener("click", el.__clickOutsideHandler);
          },
          unmounted(el: HTMLElement) {
            if (el.__clickOutsideHandler) {
              document.removeEventListener("click", el.__clickOutsideHandler);
            }
          },
        },
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
    expect(wrapper.find('[aria-label$="more folders"]').exists()).toBe(true);
  });

  it("opens ellipsis menu on button click", async () => {
    const wrapper = createWrapper({ path: "/a/b/c/d/e", maxVisible: 3 });
    const ellipsisBtn = wrapper.find('[aria-label$="more folders"]');
    expect(ellipsisBtn.exists()).toBe(true);

    await ellipsisBtn.trigger("click");
    expect(wrapper.text()).toContain("Show full path");

    await ellipsisBtn.trigger("click");
    expect(wrapper.text()).not.toContain("Show full path");
  });

  it("navigates to hidden segment from ellipsis menu", async () => {
    const wrapper = createWrapper({ path: "/a/b/c/d/e", maxVisible: 3 });
    await wrapper.find('[aria-label$="more folders"]').trigger("click");

    const hiddenBtns = wrapper.findAll("button").filter((b) => b.text() === "b");
    expect(hiddenBtns.length).toBeGreaterThan(0);
    await hiddenBtns[0].trigger("click");

    expect(wrapper.emitted("navigate")).toBeTruthy();
    expect(wrapper.emitted("navigate")![0][0]).toBe("/a/b");
  });

  it("expands and collapses full path", async () => {
    const wrapper = createWrapper({ path: "/a/b/c/d/e", maxVisible: 3 });
    await wrapper.find('[aria-label$="more folders"]').trigger("click");

    const showFullPath = wrapper.findAll("button").find((b) => b.text() === "Show full path");
    expect(showFullPath).toBeDefined();
    await showFullPath!.trigger("click");

    const collapseBtn = wrapper.find('[aria-label="Collapse path"]');
    expect(collapseBtn.exists()).toBe(true);

    await collapseBtn.trigger("click");
    expect(wrapper.find('[aria-label="Collapse path"]').exists()).toBe(false);
  });

  it("handles Windows backslash paths", () => {
    const wrapper = createWrapper({ path: "\\folder1\\folder2" });
    expect(wrapper.text()).toContain("folder1");
    expect(wrapper.text()).toContain("folder2");
  });

  it("renders home icon", () => {
    const wrapper = createWrapper({ path: "/test" });
    expect(wrapper.find('[data-testid="home-icon"]').exists()).toBe(true);
  });

  it("does not collapse when path has exactly maxVisible segments", () => {
    const wrapper = createWrapper({ path: "/a/b/c", maxVisible: 3 });
    expect(wrapper.text()).toContain("a");
    expect(wrapper.text()).toContain("b");
    expect(wrapper.text()).toContain("c");
    expect(wrapper.find('[aria-label$="more folders"]').exists()).toBe(false);
  });

  it("renders empty segments path gracefully", () => {
    const wrapper = createWrapper({ path: "///" });
    expect(wrapper.text()).toContain("No path");
  });
});
