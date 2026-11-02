/**
 * Purpose: Protect the `sizes` rule for the grid thumbnail `srcset` (256w / 512w).
 * Guarantees: `sizes` is the card's rendered width scaled by the cover-crop aspect ratio, so a derivative
 * is only chosen when its short edge still covers the square card; unknown dimensions are treated as wide.
 * Run when: Changing thumbnail `srcset`/`sizes`, card geometry, or the available thumbnail derivatives.
 */
import { describe, expect, it } from "vitest";
import { coverAspectRatio, thumbnailSizes, UNKNOWN_ASPECT_RATIO } from "../thumbnailSizes";

describe("coverAspectRatio", () => {
  it("is long edge over short edge regardless of orientation", () => {
    expect(coverAspectRatio(1024, 1024)).toBe(1);
    expect(coverAspectRatio(1536, 1024)).toBeCloseTo(1.5);
    expect(coverAspectRatio(1024, 1536)).toBeCloseTo(1.5);
  });

  it.each([
    [undefined, undefined],
    [null, 100],
    [100, null],
    [0, 100],
    [100, -1],
    [Number.NaN, 100],
  ])("falls back to the wide default for unknown dimensions (%j, %j)", (width, height) => {
    expect(coverAspectRatio(width, height)).toBe(UNKNOWN_ASPECT_RATIO);
  });
});

describe("thumbnailSizes", () => {
  it("is the card width for a square image", () => {
    expect(thumbnailSizes(230, 1)).toBe("230px");
  });

  it("scales the slot by the aspect ratio so a 3:2 photo in a 230 px card keeps the 512 px derivative", () => {
    expect(thumbnailSizes(230, 1.5)).toBe("345px");
  });

  it("rounds up to whole pixels", () => {
    expect(thumbnailSizes(184.5, 1)).toBe("185px");
  });

  it("is undefined until the card has a measured width", () => {
    expect(thumbnailSizes(0, 1)).toBeUndefined();
    expect(thumbnailSizes(Number.NaN, 1)).toBeUndefined();
  });

  it("never goes below the card width", () => {
    expect(thumbnailSizes(200, 0.5)).toBe("200px");
  });
});
