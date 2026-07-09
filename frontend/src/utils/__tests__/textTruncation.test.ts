import { describe, it, expect } from "vitest";
import { fitMiddleTruncate, tableCellFont } from "../textTruncation";

describe("fitMiddleTruncate", () => {
  it("returns the original text when it fits within the budget", () => {
    expect(fitMiddleTruncate("SDXL", 500, "500 13px sans-serif")).toBe("SDXL");
  });

  it("returns the original text when exactly at the budget", () => {
    expect(fitMiddleTruncate("abc", 1000, "500 13px sans-serif")).toBe("abc");
  });

  it("collapses the middle and keeps head + tail when the text overflows", () => {
    const truncated = fitMiddleTruncate("waiNSFWIllustrious_v120", 60, "500 13px sans-serif");
    expect(truncated).toContain("\u2026");
    // Head is preserved from the start.
    expect(truncated.startsWith("wa")).toBe(true);
    // Tail is favored (tailRatio 0.6): the trailing version digits survive.
    expect(/[0-9]+$/.test(truncated)).toBe(true);
    // The middle portion must be collapsed.
    expect(truncated.length).toBeLessThan("waiNSFWIllustrious_v120".length);
  });

  it("favors the tail at the configured tailRatio", () => {
    const long = "dreamshaper_8_inpainting_vae_safetensors_v120";
    const truncated = fitMiddleTruncate(long, 80, "500 13px sans-serif", 0.7);
    expect(truncated.endsWith("v120")).toBe(true);
    expect(truncated.startsWith("dr")).toBe(true);
  });

  it("returns just the ellipsis when the budget is smaller than the ellipsis", () => {
    const truncated = fitMiddleTruncate("waiNSFWIllustrious_v120", 1, "500 13px sans-serif");
    expect(truncated).toBe("\u2026");
  });

  it("returns the original text when head + tail would cover the whole string", () => {
    // Very large budget relative to a short string => no truncation.
    expect(fitMiddleTruncate("abc", 10000, "500 13px sans-serif")).toBe("abc");
  });

  it("is deterministic across calls (cached)", () => {
    const a = fitMiddleTruncate("waiNSFWIllustrious_v120", 60, "500 13px sans-serif");
    const b = fitMiddleTruncate("waiNSFWIllustrious_v120", 60, "500 13px sans-serif");
    expect(a).toBe(b);
  });

  it("handles non-ASCII characters (e.g. unicode filename)", () => {
    const truncated = fitMiddleTruncate("画像生成_waiNSFWIllustrious_v120.png", 50, "500 13px sans-serif");
    expect(truncated).toContain("\u2026");
    // The extension tail survives middle truncation.
    expect(truncated.endsWith("png")).toBe(true);
    // The leading CJK glyphs are preserved.
    expect(truncated.startsWith("画")).toBe(true);
    expect(truncated.length).toBeLessThan("画像生成_waiNSFWIllustrious_v120.png".length);
  });

  it("respects a custom ellipsis", () => {
    const truncated = fitMiddleTruncate("waiNSFWIllustrious_v120", 50, "500 13px sans-serif", 0.6, "...");
    expect(truncated).toContain("...");
  });
});

describe("tableCellFont", () => {
  it("returns a font string containing the weight, size and a family", () => {
    const font = tableCellFont(500, 13);
    expect(font).toContain("500");
    expect(font).toContain("13px");
    expect(font.length).toBeGreaterThan(0);
  });

  it("caches the resolved font across calls", () => {
    const a = tableCellFont();
    const b = tableCellFont();
    expect(a).toBe(b);
  });
});
