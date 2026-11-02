/**
 * Purpose: Protect the versioned image URL builders (docs/archived/IMAGE_PIPELINE_PLAN.md, IP-2 / IP-5).
 * Guarantees: `getThumbnailUrl` / `getPreviewUrl` append `v=<content_version>` only when a version is given
 * (so unversioned items keep today's URL), keep the existing `path` / `max_long_edge` parameters in front,
 * encode the version, and `getThumbnailSrcset` offers the 256 and 512 px derivatives with the same version.
 * Run when: Changing image URL builders, the backend `v` contract, or thumbnail sizes.
 */
import { describe, expect, it } from "vitest";
import { getPreviewUrl, getThumbnailSrcset, getThumbnailUrl } from "../api";

describe("getThumbnailUrl", () => {
  it("keeps today's URL when no version is given", () => {
    expect(getThumbnailUrl("/a b.png")).toBe("/api/thumbnail?path=%2Fa+b.png&max_long_edge=512");
    expect(getThumbnailUrl("/a.png", 256)).toBe("/api/thumbnail?path=%2Fa.png&max_long_edge=256");
  });

  it("appends &v=<version> after max_long_edge", () => {
    expect(getThumbnailUrl("/a.png", 512, "1700000000123456789-48213")).toBe(
      "/api/thumbnail?path=%2Fa.png&max_long_edge=512&v=1700000000123456789-48213",
    );
  });

  it.each([undefined, null, ""])(
    "treats %j as unversioned (covers without an identity report an empty string)",
    (version) => {
      expect(getThumbnailUrl("/a.png", 512, version)).toBe("/api/thumbnail?path=%2Fa.png&max_long_edge=512");
    },
  );

  it("URL-encodes the version", () => {
    expect(getThumbnailUrl("/a.png", 512, "1 2&3")).toContain("&v=1+2%263");
  });
});

describe("getPreviewUrl", () => {
  it("keeps today's URL when no version is given", () => {
    expect(getPreviewUrl("/a.png")).toBe("/api/preview?path=%2Fa.png&max_long_edge=1440");
  });

  it("appends &v=<version> after max_long_edge", () => {
    expect(getPreviewUrl("/a.png", 1440, "9-8")).toBe("/api/preview?path=%2Fa.png&max_long_edge=1440&v=9-8");
  });

  it("treats an empty version as unversioned", () => {
    expect(getPreviewUrl("/a.png", 1440, "")).toBe("/api/preview?path=%2Fa.png&max_long_edge=1440");
  });
});

describe("getThumbnailSrcset", () => {
  it("lists the 256 and 512 px derivatives with width descriptors", () => {
    expect(getThumbnailSrcset("/a.png")).toBe(
      "/api/thumbnail?path=%2Fa.png&max_long_edge=256 256w, /api/thumbnail?path=%2Fa.png&max_long_edge=512 512w",
    );
  });

  it("carries the version on every candidate", () => {
    expect(getThumbnailSrcset("/a.png", "7-3")).toBe(
      "/api/thumbnail?path=%2Fa.png&max_long_edge=256&v=7-3 256w, /api/thumbnail?path=%2Fa.png&max_long_edge=512&v=7-3 512w",
    );
  });

  it("never puts whitespace or commas inside a candidate URL (they would split the srcset)", () => {
    const srcset = getThumbnailSrcset("/my photos/a, b.png", "1-2");
    const candidates = srcset.split(", ");
    expect(candidates).toHaveLength(2);
    for (const candidate of candidates) expect(candidate.trim().split(/\s+/)).toHaveLength(2);
  });
});

describe("retry cache-buster", () => {
  it("appends r=<n> after v only for a retry", () => {
    expect(getThumbnailUrl("/a.png", 512, "7-3", 2)).toBe("/api/thumbnail?path=%2Fa.png&max_long_edge=512&v=7-3&r=2");
    expect(getThumbnailUrl("/a.png", 512, undefined, 1)).toBe("/api/thumbnail?path=%2Fa.png&max_long_edge=512&r=1");
  });

  it.each([undefined, 0])("adds no r for retry %j", (retry) => {
    expect(getThumbnailUrl("/a.png", 512, "7-3", retry)).toBe("/api/thumbnail?path=%2Fa.png&max_long_edge=512&v=7-3");
  });

  it("puts r on every srcset candidate", () => {
    expect(getThumbnailSrcset("/a.png", "7-3", 1)).toBe(
      "/api/thumbnail?path=%2Fa.png&max_long_edge=256&v=7-3&r=1 256w, /api/thumbnail?path=%2Fa.png&max_long_edge=512&v=7-3&r=1 512w",
    );
  });
});
