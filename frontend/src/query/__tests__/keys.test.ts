import { describe, it, expect } from "vitest";
import { normalizeQueryPath, normalizeBrowsePath, queryKeys } from "../keys";

describe("normalizeQueryPath", () => {
  it.each([
    [" /p ", "/p"],
    ["\\p\\q", "/p/q"],
    ["//p//q", "/p/q"],
    ["/", "/"],
    ["/p/", "/p"],
    [null, ""],
    [undefined, ""],
  ])("normalizeQueryPath(%j) => %j", (input, expected) => {
    expect(normalizeQueryPath(input as string | null | undefined)).toBe(expected);
  });
});

describe("normalizeBrowsePath", () => {
  it.each([
    ["", null],
    ["/p", "/p"],
    [null, null],
  ])("normalizeBrowsePath(%j) => %j", (input, expected) => {
    expect(normalizeBrowsePath(input as string | null)).toBe(expected);
  });
});

describe("queryKeys", () => {
  it.each([
    ["generatedImagesRoot", [], ["generated-images"]],
    ["landingPages", [], ["landing-pages"]],
    ["librariesRoot", [], ["libraries"]],
    ["libraries", [], ["libraries", "list"]],
    ["library", [5], ["libraries", "detail", 5]],
    ["libraryStats", [5], ["libraries", "stats", 5]],
    ["libraryJobs", [5], ["libraries", "jobs", 5]],
    ["galleryStats", [], ["stats", "gallery"]],
    ["jobsRoot", [], ["jobs"]],
    ["jobs", [], ["jobs", "list"]],
    ["job", [9], ["jobs", 9]],
    ["browseAllRoot", [], ["browse"]],
    ["browseRoot", [4], ["browse", 4]],
    ["folderChildren", ["/p"], ["folder-children", "/p"]],
    ["browseInfiniteAllRoot", [], ["browse-infinite"]],
    ["browseInfiniteRoot", [4], ["browse-infinite", 4]],
    ["search", ["cat", "all", "/p"], ["search", "cat", "all", "/p"]],
    ["metadata", ["/a.png"], ["metadata", "/a.png"]],
    ["statusRoot", [], ["status"]],
    ["statusBatch", [], ["status", "libraries", "batch"]],
    ["statusLibrary", [4], ["status", "library", 4]],
    ["statusPathRoot", [4], ["status", "path", 4]],
    ["libraryInspectorRoot", [], ["library-inspector"]],
    ["facets", ["/p"], ["facets", "/p"]],
    ["maintenanceRoot", [], ["maintenance"]],
    ["maintenanceFileHealth", [], ["maintenance", "file-health"]],
    ["maintenanceRuntime", [], ["maintenance", "runtime"]],
  ] as const)("queryKeys.%s(%j) => %j", (method, args, expected) => {
    expect((queryKeys as any)[method](...args)).toEqual(expected);
  });

  it("browse with includeOffline", () => {
    expect(queryKeys.browse(4, "/p", 50, true)).toEqual(["browse", 4, "/p", 50, true]);
  });

  it("browseInfinite with includeOffline", () => {
    expect(queryKeys.browseInfinite(4, "/p", 50, true)).toEqual(["browse-infinite", 4, "/p", 50, true]);
  });

  it.each([
    [4, "/p", ["status", "path", 4, "/p"]],
    [4, "", ["status", "path", 4, null]],
  ] as const)("statusPath(%i, %j) => %j", (libraryId, path, expected) => {
    expect(queryKeys.statusPath(libraryId, path)).toEqual(expected);
  });

  it("libraryInspector", () => {
    expect(queryKeys.libraryInspector("q", "all", "/p", 50, "date_desc")).toEqual([
      "library-inspector",
      "q",
      "all",
      "/p",
      50,
      "date_desc",
    ]);
  });
});
