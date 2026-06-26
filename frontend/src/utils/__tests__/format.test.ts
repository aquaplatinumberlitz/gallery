import { describe, it, expect } from "vitest";
import { formatBytes, formatPercent } from "../format";

describe("formatBytes", () => {
  it('returns "0 B" for zero', () => {
    expect(formatBytes(0)).toBe("0 B");
  });

  it('returns "—" for undefined', () => {
    expect(formatBytes(undefined)).toBe("\u2014");
  });

  it('returns "—" for null', () => {
    expect(formatBytes(null as unknown as number)).toBe("\u2014");
  });

  it('returns "—" for NaN', () => {
    expect(formatBytes(NaN)).toBe("\u2014");
  });

  it('returns "—" for Infinity', () => {
    expect(formatBytes(Infinity)).toBe("\u2014");
  });

  it('returns "—" for negative numbers', () => {
    expect(formatBytes(-1)).toBe("\u2014");
  });

  it("formats 512 B", () => {
    expect(formatBytes(512)).toBe("512 B");
  });

  it("formats 1 KB", () => {
    expect(formatBytes(1024)).toBe("1.0 KB");
  });

  it("formats 1.5 KB", () => {
    expect(formatBytes(1536)).toBe("1.5 KB");
  });

  it("formats 1 MB", () => {
    expect(formatBytes(1048576)).toBe("1.0 MB");
  });

  it("formats 1 GB", () => {
    expect(formatBytes(1073741824)).toBe("1.0 GB");
  });

  it("formats 1 TB", () => {
    expect(formatBytes(1099511627776)).toBe("1.0 TB");
  });
});

describe("formatPercent", () => {
  it('returns "—" for undefined', () => {
    expect(formatPercent(undefined)).toBe("\u2014");
  });

  it('returns "—" for null', () => {
    expect(formatPercent(null)).toBe("\u2014");
  });

  it('returns "—" for NaN', () => {
    expect(formatPercent(NaN)).toBe("\u2014");
  });

  it('returns "—" for Infinity', () => {
    expect(formatPercent(Infinity)).toBe("\u2014");
  });

  it('returns "0.0%" for 0', () => {
    expect(formatPercent(0)).toBe("0.0%");
  });

  it('returns "100.0%" for 1', () => {
    expect(formatPercent(1)).toBe("100.0%");
  });

  it('returns "50.0%" for 0.5', () => {
    expect(formatPercent(0.5)).toBe("50.0%");
  });

  it('returns "23.8%" for 0.238', () => {
    expect(formatPercent(0.238)).toBe("23.8%");
  });

  it('returns "0.0%" when expected=0 (division guard)', () => {
    expect(formatPercent(0)).toBe("0.0%");
  });
});

import { formatFraction } from "../format";

describe("formatFraction", () => {
  it("formats numerator and denominator", () => {
    expect(formatFraction(3, 10)).toBe("3 / 10 (30.0%)");
  });
  it("handles zero denominator", () => {
    expect(formatFraction(5, 0)).toBe("5 / 0");
  });
  it("handles null numerator", () => {
    expect(formatFraction(null, 10)).toBe("0 / 10 (0.0%)");
  });
  it("handles null denominator", () => {
    expect(formatFraction(5, null)).toBe("5 / 0");
  });
});
