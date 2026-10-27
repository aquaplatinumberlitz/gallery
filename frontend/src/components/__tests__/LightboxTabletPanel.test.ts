import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import LightboxTabletPanel from "../LightboxTabletPanel.vue";
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
  const wrapper = mount(LightboxTabletPanel, {
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
    attachTo: document.body,
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

describe("LightboxTabletPanel", () => {
  it("shows the loading state until metadata arrives", () => {
    const { wrapper } = mountPanel({ meta: null, isLoading: true });
    expect(wrapper.find(".meta-loading").text()).toContain("Loading info...");
  });

  it("shows the error state when there is no metadata", () => {
    const { wrapper } = mountPanel({ meta: null });
    expect(wrapper.find('[data-testid="meta-error"]').text()).toContain("No metadata available");
  });

  it("focuses the sheet handle on mount and toggles expansion from it", async () => {
    const { wrapper } = mountPanel();
    await wrapper.vm.$nextTick();
    const handle = wrapper.find(".tablet-handle-wrapper");

    expect(document.activeElement).toBe(handle.element);
    expect(wrapper.find(".tablet-panel").classes()).not.toContain("tablet-expanded");
    expect(handle.attributes("aria-label")).toBe("Expand image information");

    await handle.trigger("click");

    expect(wrapper.find(".tablet-panel").classes()).toContain("tablet-expanded");
    expect(handle.attributes("aria-label")).toBe("Collapse image information");
  });

  it("emits close from the close button, backdrop, and Escape", async () => {
    const { wrapper } = mountPanel();

    await wrapper.find(".tablet-close-btn").trigger("click");
    await wrapper.find(".tablet-backdrop").trigger("click");
    await wrapper.find(".tablet-panel").trigger("keydown.esc");

    expect(wrapper.emitted("close")).toHaveLength(3);
  });

  it("highlights LoRA tags inside the prompt", () => {
    const { wrapper } = mountPanel();
    expect(wrapper.find(".tablet-text .lora-pill").text()).toBe("detail:0.8");
  });

  it("copies prompt, negative prompt, and seed on click", async () => {
    const { wrapper, copyText } = mountPanel();
    const copyables = wrapper.findAll(".metadata-copyable");

    await copyables.find((el) => el.text().includes("Negative Prompt"))!.trigger("click");
    await copyables.find((el) => el.text().trim() === "Prompt")!.trigger("click");
    await copyables.find((el) => el.text().includes("12345"))!.trigger("click");

    expect(copyText).toHaveBeenNthCalledWith(1, "blurry, noise", "neg");
    expect(copyText).toHaveBeenNthCalledWith(2, "a castle <lora:detail:0.8> at dawn", "prompt");
    expect(copyText).toHaveBeenNthCalledWith(3, "12345", "seed");
  });

  it("copies from the keyboard with Enter and Space", async () => {
    const { wrapper, copyText } = mountPanel();
    const seed = wrapper.findAll(".metadata-copyable").find((el) => el.text().includes("12345"))!;

    await seed.trigger("keydown.enter");
    await seed.trigger("keydown.space");

    expect(copyText).toHaveBeenCalledTimes(2);
    expect(copyText).toHaveBeenCalledWith("12345", "seed");
  });

  it("lists extra settings, resources, and hashes", () => {
    const { wrapper } = mountPanel();
    expect(wrapper.text()).toContain("Extra Settings");
    expect(wrapper.text()).toContain("Clip Skip");
    expect(wrapper.text()).toContain("Checkpoint");
    expect(wrapper.text()).toContain("Refiner");
    expect(wrapper.text()).toContain("#abcdef01");
  });

  it("expands the Advanced section on demand", async () => {
    const { wrapper } = mountPanel();
    const toggle = wrapper.find(".accordion-header");

    expect(toggle.attributes("aria-expanded")).toBe("false");
    expect(wrapper.find("#tablet-advanced-content").exists()).toBe(false);
    expect(toggle.find(".count-pill").text()).toBe("1");

    await toggle.trigger("click");

    expect(toggle.attributes("aria-expanded")).toBe("true");
    expect(wrapper.find("#tablet-advanced-content").text()).toContain("Custom");
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
  });
});
