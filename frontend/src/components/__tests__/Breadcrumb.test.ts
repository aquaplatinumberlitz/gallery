import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { defineComponent, h, inject, nextTick, provide, ref, watch, type Ref } from "vue";
import Breadcrumb from "../Breadcrumb.vue";

const dropdownContextKey = Symbol("dropdown-test-context");

interface DropdownTestContext {
  open: Ref<boolean>;
  toggle: () => void;
}

const DropdownMenuStub = defineComponent({
  props: { open: { type: Boolean, default: false } },
  emits: ["update:open"],
  setup(props, { emit, slots }) {
    const open = ref(props.open);

    watch(
      () => props.open,
      (value) => {
        open.value = value;
      },
    );

    const toggle = () => {
      open.value = !open.value;
      emit("update:open", open.value);
    };

    provide(dropdownContextKey, { open, toggle });
    return () => h("div", slots.default?.());
  },
});

const DropdownMenuTriggerStub = defineComponent({
  setup(_, { slots }) {
    const context = inject<DropdownTestContext>(dropdownContextKey);
    return () => h("span", { onClick: () => context?.toggle() }, slots.default?.());
  },
});

const DropdownMenuContentStub = defineComponent({
  setup(_, { slots, attrs }) {
    const context = inject<DropdownTestContext>(dropdownContextKey);
    return () => (context?.open.value ? h("div", attrs, slots.default?.()) : null);
  },
});

const DropdownMenuItemStub = defineComponent({
  props: { disabled: { type: Boolean, default: false } },
  emits: ["select"],
  setup(props, { emit, slots, attrs }) {
    return () =>
      h(
        "button",
        {
          ...attrs,
          disabled: props.disabled,
          onClick: () => {
            if (!props.disabled) emit("select");
          },
        },
        slots.default?.(),
      );
  },
});

function createWrapper(props: Record<string, unknown> = {}, options: { realDropdown?: boolean } = {}) {
  const dropdownStubs: Record<string, unknown> = options.realDropdown
    ? {}
    : {
        DropdownMenu: DropdownMenuStub,
        DropdownMenuContent: DropdownMenuContentStub,
        DropdownMenuItem: DropdownMenuItemStub,
        DropdownMenuSeparator: { template: "<hr />" },
        DropdownMenuTrigger: DropdownMenuTriggerStub,
      };

  return mount(Breadcrumb, {
    props,
    attachTo: options.realDropdown ? document.body : undefined,
    global: {
      stubs: {
        BreadcrumbRoot: { template: "<div><slot /></div>" },
        BreadcrumbList: { template: "<ol><slot /></ol>" },
        BreadcrumbItem: { template: "<li><slot /></li>" },
        BreadcrumbLink: {
          props: ["disabled"],
          template: "<button :disabled='disabled' @click='$emit(\"click\")'><slot /></button>",
        },
        BreadcrumbPage: { template: "<span><slot /></span>" },
        BreadcrumbSeparator: { template: "<span>/</span>" },
        ...dropdownStubs,
        Tooltip: { template: "<span><slot /></span>" },
        TooltipTrigger: { template: "<span><slot /></span>" },
        TooltipContent: { template: "<span><slot /></span>" },
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

  it("does not allow navigation above the configured root path", async () => {
    const wrapper = createWrapper({
      path: "/home/ubuntu/gallery-repo/frontend",
      rootPath: "/home/ubuntu/gallery-repo",
    });
    const buttonTexts = wrapper.findAll("button").map((button) => button.text());

    expect(buttonTexts).not.toContain("home");
    expect(buttonTexts).not.toContain("ubuntu");
    expect(buttonTexts).toContain("gallery-repo");

    await wrapper
      .findAll("button")
      .find((button) => button.text() === "gallery-repo")!
      .trigger("click");

    expect(wrapper.emitted("navigate")![0]).toEqual(["/home/ubuntu/gallery-repo"]);
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

  it("opens the real portal dropdown from the ellipsis trigger", async () => {
    const wrapper = createWrapper({ path: "/a/b/c/d/e", maxVisible: 3 }, { realDropdown: true });
    const ellipsisBtn = wrapper.find('[aria-label$="more folders"]');

    await ellipsisBtn.trigger("click");
    await nextTick();

    expect(document.body.textContent).toContain("Show full path");

    wrapper.unmount();
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

  it("disables hidden ellipsis ancestors above the root path", async () => {
    const wrapper = createWrapper({ path: "/a/b/c/d/e/f", rootPath: "/a/b/c", maxVisible: 3 });
    await wrapper.find('[aria-label$="more folders"]').trigger("click");

    const hiddenB = wrapper.findAll("button").find((button) => button.text() === "b");
    const hiddenC = wrapper.findAll("button").find((button) => button.text() === "c");

    expect(hiddenB?.attributes("disabled")).toBeDefined();
    expect(hiddenC?.attributes("disabled")).toBeUndefined();
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
