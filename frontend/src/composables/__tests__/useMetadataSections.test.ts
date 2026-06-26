import { describe, expect, it } from "vitest";
import type { MetadataResponse } from "@/types";
import {
  hasCoreParams,
  hasSecondaryParams,
  hasModelData,
  getExtraParamKeys,
  hasAdvancedData,
  getSecondaryEntries,
  CORE_PARAMS,
  SECONDARY_PARAMS_MAP,
} from "../useMetadataSections";

describe("useMetadataSections", () => {
  describe("CORE_PARAMS", () => {
    it("contains expected generation parameters", () => {
      expect(CORE_PARAMS.has("Seed")).toBe(true);
      expect(CORE_PARAMS.has("Steps")).toBe(true);
      expect(CORE_PARAMS.has("CFG")).toBe(true);
      expect(CORE_PARAMS.has("Sampler")).toBe(true);
      expect(CORE_PARAMS.has("Scheduler")).toBe(true);
      expect(CORE_PARAMS.has("AspectRatio")).toBe(true);
    });
  });

  describe("SECONDARY_PARAMS_MAP", () => {
    it("contains expected secondary parameter labels", () => {
      expect(SECONDARY_PARAMS_MAP.clip_skip).toBe("Clip Skip");
      expect(SECONDARY_PARAMS_MAP.vae).toBe("VAE");
      expect(SECONDARY_PARAMS_MAP.model_hash).toBe("Model Hash");
    });
  });

  describe("hasCoreParams", () => {
    it("returns false for null or undefined params", () => {
      expect(hasCoreParams(null)).toBe(false);
      expect(hasCoreParams(undefined)).toBe(false);
    });

    it("returns false when no core params have truthy values", () => {
      expect(hasCoreParams({ Seed: null, Steps: "", CFG: undefined })).toBe(false);
    });

    it("returns true when a core param has a truthy value", () => {
      expect(hasCoreParams({ Seed: 42 })).toBe(true);
      expect(hasCoreParams({ Steps: "30" })).toBe(true);
      expect(hasCoreParams({ CFG: 7.5 })).toBe(true);
    });
  });

  describe("hasSecondaryParams", () => {
    it("returns false for null or undefined params", () => {
      expect(hasSecondaryParams(null)).toBe(false);
      expect(hasSecondaryParams(undefined)).toBe(false);
    });

    it("returns false when no secondary params have truthy values", () => {
      expect(hasSecondaryParams({ clip_skip: null, vae: "", ensd: undefined })).toBe(false);
    });

    it("returns false when secondary param is an empty array", () => {
      expect(hasSecondaryParams({ loras: [] })).toBe(false);
    });

    it("returns true when a secondary param has a truthy value", () => {
      expect(hasSecondaryParams({ clip_skip: 1 })).toBe(true);
      expect(hasSecondaryParams({ vae: "sd-vae-ft-mse" })).toBe(true);
    });
  });

  describe("hasModelData", () => {
    const baseMeta = { path: "/test.png", width: 512, height: 512, mtime: 1000 };

    it("returns false for null or undefined metadata", () => {
      expect(hasModelData(null)).toBe(false);
      expect(hasModelData(undefined)).toBe(false);
    });

    it("returns false when no model data exists", () => {
      expect(hasModelData(baseMeta as unknown as MetadataResponse)).toBe(false);
    });

    it("returns true when params.Model is set", () => {
      const meta = { ...baseMeta, params: { Model: "sd-xl" } };
      expect(hasModelData(meta as unknown as MetadataResponse)).toBe(true);
    });

    it("returns true when params.Lora is non-empty", () => {
      const meta = { ...baseMeta, params: { Lora: ["lora1", "lora2"] } };
      expect(hasModelData(meta as unknown as MetadataResponse)).toBe(true);
    });

    it("returns true when models array is non-empty", () => {
      const meta = { ...baseMeta, models: [{ name: "sd-xl", type: "model" }] };
      expect(hasModelData(meta as unknown as MetadataResponse)).toBe(true);
    });
  });

  describe("getExtraParamKeys", () => {
    it("returns empty array for null or undefined params", () => {
      expect(getExtraParamKeys(null)).toEqual([]);
      expect(getExtraParamKeys(undefined)).toEqual([]);
    });

    it("returns empty array when all keys are known", () => {
      const params = { Seed: 42, Steps: "30", Model: "sd-xl", Lora: [] };
      expect(getExtraParamKeys(params)).toEqual([]);
    });

    it("returns keys not in known sets", () => {
      const params = { Seed: 42, custom_param: "value", another_unknown: true };
      const extra = getExtraParamKeys(params);
      expect(extra).toContain("custom_param");
      expect(extra).toContain("another_unknown");
      expect(extra).not.toContain("Seed");
    });
  });

  describe("hasAdvancedData", () => {
    it("returns false for null or undefined metadata", () => {
      expect(hasAdvancedData(null)).toBe(false);
      expect(hasAdvancedData(undefined)).toBe(false);
    });

    it("returns false when no extra params exist", () => {
      const meta = { path: "/test.png", width: 512, height: 512, mtime: 1000, params: { Seed: 42 } };
      expect(hasAdvancedData(meta as unknown as MetadataResponse)).toBe(false);
    });

    it("returns true when extra params exist", () => {
      const meta = {
        path: "/test.png",
        width: 512,
        height: 512,
        mtime: 1000,
        params: { Seed: 42, custom_metric: 0.95 },
      };
      expect(hasAdvancedData(meta as unknown as MetadataResponse)).toBe(true);
    });
  });

  describe("getSecondaryEntries", () => {
    it("returns empty array for null or undefined params", () => {
      expect(getSecondaryEntries(null)).toEqual([]);
      expect(getSecondaryEntries(undefined)).toEqual([]);
    });

    it("returns entries for secondary params with truthy values", () => {
      const params = { clip_skip: 1, vae: "sd-vae-ft-mse", ensd: null };
      const entries = getSecondaryEntries(params);
      expect(entries).toHaveLength(2);
      expect(entries[0]).toEqual({ key: "clip_skip", label: "Clip Skip", value: 1 });
      expect(entries[1]).toEqual({ key: "vae", label: "VAE", value: "sd-vae-ft-mse" });
    });

    it("skips params with empty array values", () => {
      const params = { loras: [] };
      expect(getSecondaryEntries(params)).toEqual([]);
    });
  });
});
