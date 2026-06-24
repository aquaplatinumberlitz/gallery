import { describe, it, expect } from "vitest";
import { formatBytes } from "../format";

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
