import { describe, it, expect } from "vitest";
import { formatBytes, formatPercent, formatFraction } from "../format";

describe("formatBytes", () => {
  it.each([
    [0, "0 B"],
    [undefined, "\u2014"],
    [null as unknown as number, "\u2014"],
    [NaN, "\u2014"],
    [Infinity, "\u2014"],
    [-1, "\u2014"],
    [512, "512 B"],
    [1024, "1.0 KB"],
    [1536, "1.5 KB"],
    [1048576, "1.0 MB"],
    [1073741824, "1.0 GB"],
    [1099511627776, "1.0 TB"],
  ])("formatBytes(%s) => %s", (input, expected) => {
    expect(formatBytes(input)).toBe(expected);
  });
});

describe("formatPercent", () => {
  it.each([
    [undefined, "\u2014"],
    [null, "\u2014"],
    [NaN, "\u2014"],
    [Infinity, "\u2014"],
    [0, "0.0%"],
    [1, "100.0%"],
    [0.5, "50.0%"],
    [0.238, "23.8%"],
  ])("formatPercent(%s) => %s", (input, expected) => {
    expect(formatPercent(input as number | undefined | null)).toBe(expected);
  });
});

describe("formatFraction", () => {
  it.each([
    [3, 10, "3 / 10 (30.0%)"],
    [5, 0, "5 / 0"],
    [null, 10, "0 / 10 (0.0%)"],
    [5, null, "5 / 0"],
  ])("formatFraction(%s, %s) => %s", (num, den, expected) => {
    expect(formatFraction(num as number | null, den as number | null)).toBe(expected);
  });
});
