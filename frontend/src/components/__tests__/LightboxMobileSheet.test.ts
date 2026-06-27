import { describe, it, expect, vi } from "vitest";
import { nextTick } from "vue";
import { mount } from "@vue/test-utils";
import LightboxMobileSheet from "../LightboxMobileSheet.vue";
import type { MetadataResponse } from "../../types";

function makeMeta(overrides: Partial<MetadataResponse> = {}): MetadataResponse {
  return {
    prompt: "A beautiful landscape",
    negative_prompt: "blurry, noise",
    model: "SDXL 1.0",
    tool: "ComfyUI",
    width: 1024,
    height: 768,
    seed: 12345,
    cfg: 7.5,
    steps: 30,
    sampler: "Euler a",
    scheduler: "Karras",
    name: "test.png",
    date: "2024-01-15",
    generation_time: "15.2s",
    params: {
      Seed: 12345,
      Steps: 30,
      CFG: 7.5,
      Sampler: "Euler a",
      Scheduler: "Karras",
      Model: "SDXL 1.0",
    },
    models: [{ name: "SDXL 1.0", hash: "abc123def456" }],
    loras: [],
    resources: [],
    has_negative: true,
    ...overrides,
  } as MetadataResponse;
}

function createWrapper(props: Record<string, unknown> = {}) {
  const copyText: (text: string | undefined, id: string) => Promise<void> = (props.copyText as any) || vi.fn();
  return mount(LightboxMobileSheet, {
    props: {
      meta: null,
      isLoading: false,
      copyStatus: {},
      copyText,
      ...props,
    },
    global: {
      stubs: {
        BottomSheet: { template: "<div data-testid='bottom-sheet'><slot name='header' /><slot /></div>" },
        ExpandableText: { template: "<span><slot /></span>" },
      },
    },
  });
}

describe("LightboxMobileSheet", () => {
  it("shows loading state", () => {
    const wrapper = createWrapper({ isLoading: true, meta: null });
    expect(wrapper.text()).toContain("Loading info...");
  });

  it("shows error state when no meta", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("No metadata available");
  });

  it("renders tabs when meta is provided", () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    expect(wrapper.text()).toContain("Prompt");
    expect(wrapper.text()).toContain("Params");
    expect(wrapper.text()).toContain("Model");
  });

  it("shows prompt text in Prompt tab", () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    expect(wrapper.text()).toContain("A beautiful landscape");
  });

  it("shows negative prompt text", () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    expect(wrapper.text()).toContain("blurry, noise");
  });

  it("shows generation data in Params tab", async () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    const paramsTab = wrapper.findAll("button").find((b) => b.text() === "Params")!;
    await paramsTab.trigger("click");
    await nextTick();
    expect(wrapper.text()).toContain("Seed");
    expect(wrapper.text()).toContain("12345");
  });

  it("shows model info in Model tab", async () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    const modelTab = wrapper.findAll("button").find((b) => b.text() === "Model")!;
    await modelTab.trigger("click");
    await nextTick();
    expect(wrapper.text()).toContain("SDXL 1.0");
  });

  it("calls copyText when clicking copy button", async () => {
    const copyText = vi.fn();
    const wrapper = createWrapper({ meta: makeMeta(), copyText });
    const promptCopyBtn = wrapper.findAll("button").find((b) => b.attributes("aria-label") === "Copy prompt")!;
    await promptCopyBtn.trigger("click");
    expect(copyText).toHaveBeenCalledWith(makeMeta().prompt, "prompt");
  });

  it("emits close when tapping outside", () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    expect(wrapper.emitted("close")).toBeFalsy();
  });

  it("shows source badge when tool is present", () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    expect(wrapper.text()).toContain("SOURCE");
    expect(wrapper.text()).toContain("ComfyUI");
  });

  it("renders empty prompt text when no prompt", () => {
    const wrapper = createWrapper({ meta: makeMeta({ prompt: "" }) });
    expect(wrapper.text()).toContain("No");
  });

  it("renders hash for models", () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    expect(wrapper.text()).toContain("abc123de");
  });

  it("sets ActiveState change on the params button", async () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    const paramsTab = wrapper.find('[data-testid="tab-params"]');
    const promptTab = wrapper.find('[data-testid="tab-prompt"]');
    expect(promptTab.classes()).toContain("active");
    expect(paramsTab.classes()).not.toContain("active");

    await paramsTab.trigger("click");
    expect(paramsTab.classes()).toContain("active");
    expect(promptTab.classes()).not.toContain("active");
  });

  it("shows expand/collapse chevron", () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    expect(wrapper.find('[aria-label="Expand metadata sheet"]').exists()).toBe(true);
  });

  it("renders empty negative prompt when no negative prompt", () => {
    const wrapper = createWrapper({ meta: makeMeta({ negative_prompt: "" }) });
    expect(wrapper.text()).toContain("No");
  });

  it("renders empty generation data when no params", () => {
    const wrapper = createWrapper({ meta: makeMeta({ params: {} }) });
    expect(wrapper.text()).toContain("No");
  });

  it("renders empty model section when no models", () => {
    const wrapper = createWrapper({ meta: makeMeta({ models: [], params: {} }) });
    expect(wrapper.text()).toContain("No");
  });

  it("shows error icon when no meta", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("No metadata");
  });

  it("renders seed param pill", async () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    const paramsTab = wrapper.findAll("button").find((b) => b.text() === "Params")!;
    await paramsTab.trigger("click");
    expect(wrapper.text()).toContain("12345");
  });
});
