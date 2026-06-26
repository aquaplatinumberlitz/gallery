import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { setActivePinia, createPinia } from "pinia";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import AdvancedSearchDrawer from "../search/AdvancedSearchDrawer.vue";

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
        Input: { template: "<input :value='$attrs.modelValue ?? modelValue' @input='$emit(\"update:modelValue\", $event.target.value)' />" },
      },
    },
  });
}

describe("AdvancedSearchDrawer extra", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("renders all textual field labels", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Prompt");
    expect(wrapper.text()).toContain("Negative Prompt");
    expect(wrapper.text()).toContain("Model");
    expect(wrapper.text()).toContain("Sampler");
    expect(wrapper.text()).toContain("Scheduler");
    expect(wrapper.text()).toContain("LoRA");
    expect(wrapper.text()).toContain("VAE");
    expect(wrapper.text()).toContain("Folder");
    expect(wrapper.text()).toContain("Name");
  });

  it("renders numeric field labels", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Seed");
    expect(wrapper.text()).toContain("Steps");
    expect(wrapper.text()).toContain("CFG Scale");
    expect(wrapper.text()).toContain("Clip Skip");
  });

  it("renders aspect ratio preset buttons", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("1:1");
    expect(wrapper.text()).toContain("4:3");
    expect(wrapper.text()).toContain("16:9");
    expect(wrapper.text()).toContain("3:2");
    expect(wrapper.text()).toContain("2:3");
    expect(wrapper.text()).toContain("9:16");
  });

  it("renders dimension and ratio input fields", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Size");
  });

  it("renders date field", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Date");
  });

  it("renders operator select for seed field", () => {
    const wrapper = createWrapper();
    const seedOps = wrapper.findAll("select").filter(s => s.attributes("aria-label") === "Seed operator");
    expect(seedOps.length).toBe(1);
  });

  it("renders operator select for steps field", () => {
    const wrapper = createWrapper();
    const stepsOps = wrapper.findAll("select").filter(s => s.attributes("aria-label") === "Steps operator");
    expect(stepsOps.length).toBe(1);
  });
});
