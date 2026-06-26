import { describe, it, expect } from "vitest";
import { formatLibraryTimestamp, formatAssetCount } from "../libraryStatus";

describe("formatLibraryTimestamp", () => {
  it("returns Never for null", () => expect(formatLibraryTimestamp(null)).toBe("Never"));
  it("returns Never for undefined", () => expect(formatLibraryTimestamp(undefined)).toBe("Never"));
  it("returns Never for empty string", () => expect(formatLibraryTimestamp("")).toBe("Never"));
  it("returns Unknown for invalid date string", () => {
    const result = formatLibraryTimestamp("not-a-date");
    expect(result).toBe("Unknown");
  });
  it("formats a valid timestamp", () => {
    const date = new Date(2024, 0, 15, 10, 30);
    const result = formatLibraryTimestamp(date.getTime());
    expect(result).not.toBe("Never");
    expect(result).not.toBe("Unknown");
  });
  it("formats a valid date string", () => {
    const result = formatLibraryTimestamp("2024-06-15T10:30:00Z");
    expect(result).not.toBe("Never");
    expect(result).not.toBe("Unknown");
  });
  it("formats a number timestamp", () => {
    const ts = 1718461800000;
    const result = formatLibraryTimestamp(ts);
    expect(result).not.toBe("Never");
    expect(result).not.toBe("Unknown");
  });
});

describe("formatAssetCount", () => {
  it("formats zero", () => expect(formatAssetCount(0)).toBe("0"));
  it("formats null as 0", () => expect(formatAssetCount(null)).toBe("0"));
  it("formats undefined as 0", () => expect(formatAssetCount(undefined)).toBe("0"));
  it("formats negative as 0", () => expect(formatAssetCount(-5)).toBe("0"));
  it("formats large numbers", () => expect(formatAssetCount(1500)).toBe("1,500"));
});
