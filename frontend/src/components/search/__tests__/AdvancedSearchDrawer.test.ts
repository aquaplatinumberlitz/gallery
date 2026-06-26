import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { setActivePinia, createPinia } from "pinia";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import AdvancedSearchDrawer from "../AdvancedSearchDrawer.vue";

vi.mock("@/composables/useFacetsQuery", () => ({
  useFacetsQuery: () => ({
    data: { value: { model: [], sampler: [], scheduler: [] } },
    isLoading: { value: false },
  }),
}));

vi.mock("@/composables/useActiveLibrarySelection", () => ({
  useActiveLibrarySelection: () => ({
    activeImportRootPath: { value: "/photos" },
  }),
}));

function createWrapper(props: Record<string, unknown> = {}) {
  setActivePinia(createPinia());
  const queryClient = createIsolatedQueryClient();
  return mount(AdvancedSearchDrawer, {
    props: {
      isOpen: true,
      initialFilters: [],
      ...props,
    },
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
      stubs: {
        Teleport: { template: "<div><slot /></div>" },
        Button: { template: "<button :disabled='disabled' @click='$attrs.onClick?.()'><slot /></button>" },
        Input: {
          template:
            "<input :value='$attrs.modelValue ?? modelValue' @input='$emit(\"update:modelValue\", $event.target.value)' />",
        },
      },
    },
  });
}

describe("AdvancedSearchDrawer", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("renders the drawer when isOpen is true", () => {
    const wrapper = createWrapper();
    expect(wrapper.find(".advanced-search-drawer").exists()).toBe(true);
  });

  it("renders the advanced search title", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Advanced Search");
  });

  it("renders text fields section", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Text Fields");
  });

  it("renders numeric fields section", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Numeric Fields");
  });

  it("renders prompt input field", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Prompt");
  });

  it("renders negative prompt input field", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Negative Prompt");
  });

  it("renders model input field", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Model");
  });

  it("renders seed numeric field", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Seed");
  });

  it("renders aspect ratio presets", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("1:1");
    expect(wrapper.text()).toContain("16:9");
    expect(wrapper.text()).toContain("4:3");
  });

  it("renders Apply button", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Apply");
  });

  it("renders Reset button", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Reset");
  });

  it("renders Cancel button", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Cancel");
  });

  it("emits close when cancel is clicked through overlay", async () => {
    const wrapper = createWrapper();
    const overlay = wrapper.find(".advanced-search-overlay");
    if (overlay.exists()) {
      await overlay.trigger("click");
      expect(wrapper.emitted("close")).toBeTruthy();
    }
  });

  it("does not render when isOpen is false", () => {
    const wrapper = createWrapper({ isOpen: false });
    expect(wrapper.find(".advanced-search-drawer").exists()).toBe(false);
  });

  it("renders sampler and scheduler fields", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Sampler");
    expect(wrapper.text()).toContain("Scheduler");
  });

  it("renders LoRA and VAE fields", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("LoRA");
    expect(wrapper.text()).toContain("VAE");
  });

  it("renders Folder and Name fields", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Folder");
    expect(wrapper.text()).toContain("Name");
  });
});
