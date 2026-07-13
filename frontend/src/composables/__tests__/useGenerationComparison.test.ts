/**
 * Purpose: Protect transparent recorded-setting comparisons for Related Assets.
 * Guarantees: All required generation fields are compared without provenance claims; missing values stay explicit.
 * Run when: Changing metadata parameter aliases or generation-family summary wording.
 */
import { describe, expect, it } from "vitest";
import { useGenerationComparison } from "../useGenerationComparison";
import type { MetadataResponse } from "@/types";

const metadata = (overrides: Partial<MetadataResponse> = {}): MetadataResponse => ({
  tool: "ComfyUI",
  prompt: "fox",
  negative_prompt: "",
  params: {
    Seed: "101",
    Sampler: "Euler",
    Scheduler: "Karras",
    Steps: "28",
    CFG: "7",
    Model: "forest-xl",
    Lora: ["fox-detail"],
    "Denoising strength": "0.4",
    "Hires upscale": "2",
    "Hires steps": "12",
    VAE: "vae.safetensors",
  },
  width: 1024,
  height: 1024,
  name: "reference.png",
  ...overrides,
});

describe("useGenerationComparison", () => {
  it("compares every required recorded setting and identifies changes", () => {
    const candidate = metadata({
      params: { ...metadata().params, Seed: "202", Sampler: "DPM++", CFG: "6.5", Lora: ["other"] },
      width: 768,
    });
    const { comparisons, changed } = useGenerationComparison(metadata(), candidate);
    expect(comparisons.value.map((item) => item.key)).toEqual([
      "seed",
      "sampler",
      "scheduler",
      "steps",
      "cfg",
      "dimensions",
      "model",
      "resources",
      "denoising",
      "hires",
      "vae",
    ]);
    expect(changed.value.map((item) => item.key)).toEqual(["seed", "sampler", "cfg", "dimensions", "resources"]);
  });

  it("keeps one-sided recorded values visible instead of guessing", () => {
    const { comparisons } = useGenerationComparison(metadata(), metadata({ params: {} }));
    expect(comparisons.value.find((item) => item.key === "seed")).toMatchObject({
      reference: "101",
      candidate: "",
      changed: false,
    });
  });
});
