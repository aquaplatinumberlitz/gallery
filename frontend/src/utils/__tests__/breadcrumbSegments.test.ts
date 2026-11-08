import { describe, expect, it } from "vitest";
import { buildBreadcrumbSegments } from "../breadcrumbSegments";

const names = (path: string, rootPath?: string) => buildBreadcrumbSegments(path, rootPath).map((s) => s.name);

describe("buildBreadcrumbSegments", () => {
  it("starts at the filesystem root when there is no import root", () => {
    expect(names("/tmp/data/library/Night City")).toEqual(["tmp", "data", "library", "Night City"]);
  });

  it("starts at the import root, shown with its folder name", () => {
    const segments = buildBreadcrumbSegments("/tmp/data/library/Night City", "/tmp/data/library");
    expect(segments.map((s) => s.name)).toEqual(["library", "Night City"]);
    expect(segments[0]).toEqual({ name: "library", fullPath: "/tmp/data/library", isLast: false, index: 0 });
    expect(segments[1]).toEqual({
      name: "Night City",
      fullPath: "/tmp/data/library/Night City",
      isLast: true,
      index: 1,
    });
  });

  it("shows only the import root when the current path is the root", () => {
    const segments = buildBreadcrumbSegments("/tmp/data/library", "/tmp/data/library");
    expect(segments).toEqual([{ name: "library", fullPath: "/tmp/data/library", isLast: true, index: 0 }]);
  });

  it("falls back to the full path when the root does not contain the current path", () => {
    expect(names("/tmp/data/other/Night City", "/tmp/data/library")).toEqual(["tmp", "data", "other", "Night City"]);
  });

  it("ignores a trailing separator on the import root", () => {
    expect(names("/tmp/data/library/Night City", "/tmp/data/library/")).toEqual(["library", "Night City"]);
  });

  it("does not match a sibling folder that only shares the root name prefix", () => {
    expect(names("/tmp/data/library2/Night City", "/tmp/data/library")).toEqual([
      "tmp",
      "data",
      "library2",
      "Night City",
    ]);
  });

  it("returns no segments for an empty path", () => {
    expect(buildBreadcrumbSegments("", "/tmp/data/library")).toEqual([]);
  });

  it("keeps the import root as a navigable segment that points at the root path", () => {
    const [root] = buildBreadcrumbSegments("/tmp/data/library/Night City", "/tmp/data/library");
    expect(root.fullPath).toBe("/tmp/data/library");
    expect(root.isLast).toBe(false);
  });
});
