import { describe, it, expect, vi } from "vitest";
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
    params: { Seed: 12345, Steps: 30, CFG: 7.5, Sampler: "Euler a", Scheduler: "Karras", Model: "SDXL 1.0" },
    models: [{ name: "SDXL 1.0", hash: "abc123def456" }],
    loras: [{ name: "lora_v1", resource_hash: "def789", weight: 0.8 }],
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

describe("LightboxMobileSheet extra", () => {
  it("renders empty prompt section when no prompt", () => {
    const wrapper = createWrapper({ meta: makeMeta({ prompt: "" }) });
    expect(wrapper.text()).toContain("No");
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

  it("shows loading spinner when loading", () => {
    const wrapper = createWrapper({ isLoading: true, meta: null });
    expect(wrapper.text()).toContain("Loading info...");
  });

  it("shows error icon when no meta", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("No metadata");
  });

  it("renders Params tab with generation data", async () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    const paramsTab = wrapper.findAll("button").find((b) => b.text() === "Params");
    await paramsTab?.trigger("click");
    expect(wrapper.text()).toContain("Generation Data");
  });

  it("renders seed param pill", async () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    const paramsTab = wrapper.findAll("button").find((b) => b.text() === "Params");
    await paramsTab?.trigger("click");
    expect(wrapper.element.innerHTML).toContain("12345");
  });

  it("renders Model tab with model info", async () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    const modelTab = wrapper.findAll("button").find((b) => b.text() === "Model");
    await modelTab?.trigger("click");
    expect(wrapper.text()).toContain("Checkpoint");
    expect(wrapper.text()).toContain("SDXL 1.0");
  });

  it("renders expand toggle button", () => {
    const wrapper = createWrapper({ meta: makeMeta() });
    expect(wrapper.find('[aria-label="Expand metadata sheet"]').exists()).toBe(true);
  });
});
