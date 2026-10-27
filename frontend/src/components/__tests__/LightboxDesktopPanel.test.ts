import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import LightboxDesktopPanel from "../LightboxDesktopPanel.vue";
import type { MetadataResponse } from "../../types";

function makeMeta(overrides: Partial<MetadataResponse> = {}): MetadataResponse {
  return {
    tool: "ComfyUI",
    prompt: "a castle <lora:detail:0.8> at dawn",
    negative_prompt: "blurry, noise",
    params: {
      Seed: 12345,
      Steps: 30,
      CFG: 7.5,
      Sampler: "Euler a",
      Model: "sdxl",
      Lora: ["detail:0.8"],
      clip_skip: 2,
      Custom: "value",
    },
    models: [{ name: "refiner", param: "Refiner", hash: "abcdef0123456789" }],
    width: 1024,
    height: 768,
    name: "a.png",
    ...overrides,
  } as MetadataResponse;
}

function mountPanel(props: Record<string, unknown> = {}) {
  const copyText = vi.fn(async () => true);
  const wrapper = mount(LightboxDesktopPanel, {
    props: {
      meta: makeMeta(),
      isLoading: false,
      imageName: "a.png",
      sizeText: "1024 x 768",
      dateText: "Jan 15, 2024",
      genTimeText: "15.2s",
      copyStatus: {},
      copyText,
      ...props,
    },
    global: {
      stubs: {
        ExpandableText: { template: "<span class='expandable-stub'><slot /></span>" },
        OverflowTooltip: { props: ["text"], template: "<h3><slot /></h3>" },
        Tooltip: { template: "<span><slot /></span>" },
        TooltipTrigger: { template: "<span><slot /></span>" },
        TooltipContent: { template: "<span class='tooltip-content-stub'><slot /></span>" },
      },
    },
  });
  return { wrapper, copyText };
}

describe("LightboxDesktopPanel", () => {
  it("shows the loading state until metadata arrives", () => {
    const { wrapper } = mountPanel({ meta: null, isLoading: true });
    expect(wrapper.find(".meta-loading").text()).toContain("Loading info...");
  });

  it("shows the error state when there is no metadata", () => {
    const { wrapper } = mountPanel({ meta: null });
    expect(wrapper.find('[data-testid="meta-error"]').text()).toContain("No metadata available");
  });

  it("renders the header facts and source badge", () => {
    const { wrapper } = mountPanel();
    const header = wrapper.find(".meta-header");
    expect(header.text()).toContain("a.png");
    expect(header.text()).toContain("1024 x 768");
    expect(header.text()).toContain("Jan 15, 2024");
    expect(header.text()).toContain("15.2s");
    expect(header.find(".source-chip").text()).toBe("ComfyUI");
  });

  it("highlights LoRA tags inside the prompt", () => {
    const { wrapper } = mountPanel();
    expect(wrapper.find(".prompt-box .lora-pill").text()).toBe("detail:0.8");
  });

  it("copies the prompt, negative prompt, and seed with their status ids", async () => {
    const { wrapper, copyText } = mountPanel();

    await wrapper.find('button[aria-label="Copy prompt"]').trigger("click");
    await wrapper.find('button[aria-label="Copy negative prompt"]').trigger("click");
    await wrapper.find('button[aria-label="Copy seed"]').trigger("click");

    expect(copyText).toHaveBeenNthCalledWith(1, "a castle <lora:detail:0.8> at dawn", "prompt");
    expect(copyText).toHaveBeenNthCalledWith(2, "blurry, noise", "neg");
    expect(copyText).toHaveBeenNthCalledWith(3, "12345", "seed");
  });

  it("shows accordion counts for generation data and model resources", () => {
    const { wrapper } = mountPanel();
    const pills = wrapper.findAll(".accordion-header .count-pill").map((pill) => pill.text());
    // Generation Data: Seed, Steps, CFG, Sampler; Model & Resources: checkpoint + 1 LoRA + 1 model; Advanced: Custom
    expect(pills).toEqual(["4", "3", "1"]);
  });

  it("toggles the Model & Resources and Advanced accordions", async () => {
    const { wrapper } = mountPanel();
    const headers = wrapper.findAll(".accordion-header");
    const resources = headers.find((header) => header.text().includes("Model & Resources"))!;
    const advanced = headers.find((header) => header.text().includes("Advanced"))!;

    expect(resources.attributes("aria-expanded")).toBe("false");
    expect(advanced.attributes("aria-expanded")).toBe("false");

    await resources.trigger("click");
    await advanced.trigger("click");

    expect(resources.attributes("aria-expanded")).toBe("true");
    expect(advanced.attributes("aria-expanded")).toBe("true");
  });

  it("lists extra settings, resources, hashes, and advanced keys", () => {
    const { wrapper } = mountPanel();
    expect(wrapper.text()).toContain("Extra Settings");
    expect(wrapper.text()).toContain("Clip Skip");
    expect(wrapper.text()).toContain("Checkpoint");
    expect(wrapper.text()).toContain("sdxl");
    expect(wrapper.text()).toContain("LoRA");
    expect(wrapper.text()).toContain("Refiner");
    expect(wrapper.text()).toContain("#abcdef01");
    expect(wrapper.text()).toContain("Custom");
  });

  it("renders muted empty states when metadata has no content", () => {
    const { wrapper } = mountPanel({
      meta: makeMeta({ prompt: "", negative_prompt: "", params: {}, models: [], tool: undefined }),
    });
    expect(wrapper.text()).toContain("No prompt metadata");
    expect(wrapper.text()).toContain("No negative prompt");
    expect(wrapper.text()).toContain("No generation parameters");
    expect(wrapper.text()).toContain("No model/resource metadata found");
    expect(wrapper.findAll(".is-empty")).toHaveLength(4);
    expect(wrapper.find(".source-badge").exists()).toBe(false);
    expect(wrapper.find(".extra-settings, .advanced").exists()).toBe(false);
  });
});
