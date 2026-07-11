import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { VueQueryPlugin } from "@tanstack/vue-query";
import { createIsolatedQueryClient } from "@/test/queryClient";
import type { FieldFilter } from "@/types";
import AdvancedSearchDrawer from "../AdvancedSearchDrawer.vue";

const facetState = vi.hoisted(() => ({
  data: { value: { model: [], sampler: [], scheduler: [] } as Record<string, Array<{ value: string; count: number }>> },
  isLoading: { value: false },
  isError: { value: false },
}));

vi.mock("@/composables/useFacetsQuery", () => ({
  useFacetsQuery: () => facetState,
}));

vi.mock("@/composables/useActiveLibrarySelection", () => ({
  useActiveLibrarySelection: () => ({
    activeImportRootPath: { value: "/photos" },
  }),
}));

function createWrapper(initialFilters: FieldFilter[] = []) {
  setActivePinia(createPinia());
  const queryClient = createIsolatedQueryClient();
  return mount(AdvancedSearchDrawer, {
    props: { isOpen: true, initialFilters },
    attachTo: document.body,
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
      stubs: {
        Teleport: { template: "<div><slot /></div>" },
        Tooltip: { template: "<div><slot /></div>" },
        TooltipTrigger: { template: "<div><slot /></div>" },
        TooltipContent: { template: "<div><slot /></div>" },
      },
    },
  });
}

function button(wrapper: ReturnType<typeof createWrapper>, name: string | RegExp) {
  return wrapper
    .findAll("button")
    .find((item) => (typeof name === "string" ? item.text().trim() === name : name.test(item.text().trim())));
}

async function openGroup(wrapper: ReturnType<typeof createWrapper>, name: string) {
  const trigger = button(wrapper, new RegExp(`^${name}`));
  expect(trigger).toBeDefined();
  if (trigger!.attributes("aria-expanded") !== "true") await trigger!.trigger("click");
  await flushPromises();
}

describe("AdvancedSearchDrawer", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    facetState.data.value = { model: [], sampler: [], scheduler: [] };
    facetState.isLoading.value = false;
    facetState.isError.value = false;
  });

  it("opens Content and files by default and collapses advanced groups", () => {
    const wrapper = createWrapper();
    expect(button(wrapper, /^Content and files/)?.attributes("aria-expanded")).toBe("true");
    expect(button(wrapper, /^Generation settings/)?.attributes("aria-expanded")).toBe("false");
    expect(button(wrapper, /^Dimensions/)?.attributes("aria-expanded")).toBe("false");
    expect(button(wrapper, /^Query syntax/)?.attributes("aria-expanded")).toBe("false");
    expect(wrapper.get("#advanced-search-prompt").isVisible()).toBe(true);
  });

  it("keeps the action footer outside the scrollable filter body", () => {
    const wrapper = createWrapper();
    const footer = wrapper.get('[data-testid="advanced-search-footer"]');
    const body = wrapper.get('[data-testid="advanced-search-scroll-body"]');
    expect(body.element.contains(footer.element)).toBe(false);
    expect(footer.classes()).toContain("shrink-0");
  });

  it("shows the meaningful active-filter count in the summary and apply label", () => {
    const wrapper = createWrapper([
      { field: "prompt", value: "cat" },
      { field: "steps", operator: ">=", value: "30" },
      { field: "unknown_key", value: "kept" },
    ]);
    expect(wrapper.text()).toContain("3 filters selected");
    expect(button(wrapper, "Apply 3 filters")).toBeDefined();
  });

  it("clears staged values, stays open, and does not emit apply", async () => {
    const wrapper = createWrapper([{ field: "prompt", value: "cat" }]);
    await button(wrapper, "Clear all")!.trigger("click");
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true);
    expect((wrapper.get("#advanced-search-prompt").element as HTMLInputElement).value).toBe("");
    expect(wrapper.text()).toContain("No filters selected");
    expect(wrapper.emitted("apply")).toBeUndefined();
    expect(wrapper.emitted("close")).toBeUndefined();
  });

  it("cancel restores the opening values and closes without applying", async () => {
    const wrapper = createWrapper([{ field: "prompt", value: "cat" }]);
    await wrapper.get("#advanced-search-prompt").setValue("dog");
    await button(wrapper, "Cancel")!.trigger("click");
    expect((wrapper.get("#advanced-search-prompt").element as HTMLInputElement).value).toBe("cat");
    expect(wrapper.emitted("close")).toHaveLength(1);
    expect(wrapper.emitted("apply")).toBeUndefined();
  });

  it("applies staged filters and closes", async () => {
    const wrapper = createWrapper();
    await wrapper.get("#advanced-search-prompt").setValue("blue archive");
    await button(wrapper, "Apply 1 filter")!.trigger("click");
    await flushPromises();
    expect(wrapper.emitted("apply")?.[0]).toEqual([[{ field: "prompt", value: "blue archive" }]]);
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("preserves repeated filters when opened and applied unchanged", async () => {
    const filters: FieldFilter[] = [
      { field: "model", value: "PonyXL" },
      { field: "model", value: "SDXL" },
    ];
    const wrapper = createWrapper(filters);
    await button(wrapper, "Apply 2 filters")!.trigger("click");
    await flushPromises();
    expect(wrapper.emitted("apply")?.[0]).toEqual([filters]);
  });

  it("preserves unknown pass-through filters", async () => {
    const filters: FieldFilter[] = [
      { field: "prompt", value: "portrait" },
      { field: "future_filter", operator: ">=", value: "7" },
    ];
    const wrapper = createWrapper(filters);
    await button(wrapper, "Apply 2 filters")!.trigger("click");
    await flushPromises();
    expect(wrapper.emitted("apply")?.[0]).toEqual([filters]);
  });

  it("keeps repeated pass-through filters when the primary value is edited", async () => {
    const wrapper = createWrapper([
      { field: "model", value: "PonyXL" },
      { field: "model", value: "SDXL" },
    ]);
    await wrapper.get("#advanced-search-model").setValue("Flux");
    await button(wrapper, "Apply 2 filters")!.trigger("click");
    await flushPromises();
    expect(wrapper.emitted("apply")?.[0]).toEqual([
      [
        { field: "model", value: "Flux" },
        { field: "model", value: "SDXL" },
      ],
    ]);
  });

  it("connects invalid controls to stable announced errors", async () => {
    const wrapper = createWrapper();
    await openGroup(wrapper, "Generation settings");
    await wrapper.get("#advanced-search-steps").setValue("0");
    await flushPromises();
    const input = wrapper.get("#advanced-search-steps");
    expect(input.attributes("aria-invalid")).toBe("true");
    expect(input.attributes("aria-describedby")).toBe("advanced-search-steps-error");
    expect(wrapper.get("#advanced-search-steps-error").attributes("role")).toBe("alert");
    expect((input.element as HTMLInputElement).value).toBe("0");
    expect(button(wrapper, /^Apply/)?.attributes()).toHaveProperty("disabled");
  });

  it("marks the selected aspect-ratio preset as pressed", async () => {
    const wrapper = createWrapper();
    await openGroup(wrapper, "Dimensions");
    const preset = wrapper.findAll("button").find((item) => item.attributes("aria-label") === "16:9");
    expect(preset).toBeDefined();
    await preset!.trigger("click");
    expect(preset!.attributes("aria-pressed")).toBe("true");
    expect(preset!.attributes("data-state")).toBe("on");
  });

  it.each([
    [true, false, "Loading suggestions"],
    [false, false, "No suggestions available"],
    [false, true, "Suggestions unavailable"],
  ])("shows distinct facet state loading=%s failed=%s", async (loading, failed, expected) => {
    facetState.isLoading.value = loading;
    facetState.isError.value = failed;
    const wrapper = createWrapper();
    await openGroup(wrapper, "Generation settings");
    expect(wrapper.text().match(new RegExp(expected, "g"))).toHaveLength(3);
    expect(wrapper.get("#advanced-search-model").attributes("disabled")).toBeUndefined();
    expect(wrapper.get("#advanced-search-sampler").attributes("disabled")).toBeUndefined();
    expect(wrapper.get("#advanced-search-scheduler").attributes("disabled")).toBeUndefined();
  });

  it("applies a valid form with Ctrl+Enter", async () => {
    const wrapper = createWrapper();
    await wrapper.get("#advanced-search-prompt").setValue("shortcut");
    await wrapper.get("form").trigger("keydown", { key: "Enter", ctrlKey: true });
    await flushPromises();
    expect(wrapper.emitted("apply")?.[0]).toEqual([[{ field: "prompt", value: "shortcut" }]]);
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("does not apply on an unmodified Enter in raw metadata text", async () => {
    const wrapper = createWrapper();
    await openGroup(wrapper, "Query syntax");
    await wrapper.get("#advanced-search-raw").trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("apply")).toBeUndefined();
  });
});
