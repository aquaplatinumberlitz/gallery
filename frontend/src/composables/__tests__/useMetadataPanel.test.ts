import { describe, expect, it, vi } from "vitest";
import { reactive } from "vue";
import type { MetadataResponse } from "@/types";
import { useMetadataPanel, type MetadataPanelSource } from "../useMetadataPanel";

function makeMeta(overrides: Partial<MetadataResponse> = {}): MetadataResponse {
  return {
    tool: "ComfyUI",
    prompt: "a castle <lora:detail:0.8> at dawn",
    negative_prompt: "blurry <lora:neg:1>",
    params: {
      Seed: 12345,
      Steps: 30,
      CFG: 7.5,
      Sampler: "Euler a",
      Model: "sdxl",
      Lora: ["detail:0.8", "style:0.5"],
      clip_skip: 2,
      vae: "sdxl_vae",
      Custom: "x",
    },
    models: [{ name: "refiner", hash: "abcdef0123456789" }],
    width: 512,
    height: 512,
    name: "a.png",
    ...overrides,
  } as MetadataResponse;
}

function makeSource(meta: MetadataResponse | null) {
  const copyText = vi.fn(async () => true);
  const source = reactive({ meta, copyText }) as MetadataPanelSource;
  return { source, copyText };
}

describe("useMetadataPanel", () => {
  describe("section flags", () => {
    it("reports which sections have data", () => {
      const { source } = makeSource(makeMeta());
      const panel = useMetadataPanel(source);

      expect(panel.hasGenData.value).toBe(true);
      expect(panel.hasExtraSettings.value).toBe(true);
      expect(panel.hasModels.value).toBe(true);
      expect(panel.hasAdv.value).toBe(true);
      expect(panel.extraEntries.value.map((entry) => entry.key)).toEqual(["clip_skip", "vae"]);
      expect(panel.extraParamKeys.value).toEqual(["Custom"]);
    });

    it("reports empty sections when metadata is missing", () => {
      const { source } = makeSource(null);
      const panel = useMetadataPanel(source);

      expect(panel.hasGenData.value).toBe(false);
      expect(panel.hasExtraSettings.value).toBe(false);
      expect(panel.hasModels.value).toBe(false);
      expect(panel.hasAdv.value).toBe(false);
      expect(panel.extraEntries.value).toEqual([]);
      expect(panel.extraParamKeys.value).toEqual([]);
      expect(panel.genParamsCount.value).toBe(0);
      expect(panel.modelCount.value).toBe(0);
    });

    it("recomputes when the metadata prop changes", () => {
      const { source } = makeSource(makeMeta({ params: {} }));
      const panel = useMetadataPanel(source);
      expect(panel.hasGenData.value).toBe(false);

      (source as { meta: MetadataResponse | null }).meta = makeMeta();

      expect(panel.hasGenData.value).toBe(true);
    });
  });

  describe("counts", () => {
    it("counts populated generation params", () => {
      const { source } = makeSource(makeMeta());
      expect(useMetadataPanel(source).genParamsCount.value).toBe(4);
    });

    it("counts checkpoint, LoRAs, and extra models", () => {
      const { source } = makeSource(makeMeta());
      expect(useMetadataPanel(source).modelCount.value).toBe(4);
    });
  });

  describe("prompt HTML", () => {
    it("wraps LoRA tags in highlight spans", () => {
      const { source } = makeSource(makeMeta());
      const panel = useMetadataPanel(source);

      expect(panel.promptHtml.value).toContain('<span class="lora-pill">detail:0.8</span>');
      expect(panel.negativePromptHtml.value).toContain('<span class="lora-pill">neg:1</span>');
    });

    it("returns an empty string when the prompt is absent", () => {
      const { source } = makeSource(makeMeta({ prompt: "", negative_prompt: undefined }));
      const panel = useMetadataPanel(source);

      expect(panel.promptHtml.value).toBe("");
      expect(panel.negativePromptHtml.value).toBe("");
    });
  });

  describe("copy actions", () => {
    it("copies the prompt, negative prompt, and stringified seed with their status ids", async () => {
      const { source, copyText } = makeSource(makeMeta());
      const panel = useMetadataPanel(source);

      await panel.copyPrompt();
      await panel.copyNegativePrompt();
      await panel.copySeed();

      expect(copyText).toHaveBeenNthCalledWith(1, "a castle <lora:detail:0.8> at dawn", "prompt");
      expect(copyText).toHaveBeenNthCalledWith(2, "blurry <lora:neg:1>", "neg");
      expect(copyText).toHaveBeenNthCalledWith(3, "12345", "seed");
    });

    it("returns the copy result so callers can await it", async () => {
      const { source, copyText } = makeSource(makeMeta());
      copyText.mockResolvedValueOnce(false);

      await expect(useMetadataPanel(source).copyPrompt()).resolves.toBe(false);
    });
  });

  it("starts with the Advanced section collapsed", () => {
    const { source } = makeSource(makeMeta());
    const panel = useMetadataPanel(source);

    expect(panel.showAdvanced.value).toBe(false);
    panel.showAdvanced.value = true;
    expect(panel.showAdvanced.value).toBe(true);
  });
});
