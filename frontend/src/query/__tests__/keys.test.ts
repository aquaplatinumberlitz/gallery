import { describe, it, expect } from "vitest";
import { normalizeQueryPath, normalizeBrowsePath, queryKeys } from "../keys";

describe("normalizeQueryPath", () => {
  it("trims whitespace", () => expect(normalizeQueryPath(" /p ")).toBe("/p"));
  it("normalizes backslashes", () => expect(normalizeQueryPath("\\p\\q")).toBe("/p/q"));
  it("collapses duplicate slashes", () => expect(normalizeQueryPath("//p//q")).toBe("/p/q"));
  it("preserves root slash", () => expect(normalizeQueryPath("/")).toBe("/"));
  it("strips trailing slash", () => expect(normalizeQueryPath("/p/")).toBe("/p"));
  it("handles null", () => expect(normalizeQueryPath(null)).toBe(""));
  it("handles undefined", () => expect(normalizeQueryPath(undefined)).toBe(""));
});

describe("normalizeBrowsePath", () => {
  it("returns null for empty", () => expect(normalizeBrowsePath("")).toBeNull());
  it("returns path for valid", () => expect(normalizeBrowsePath("/p")).toBe("/p"));
  it("handles null", () => expect(normalizeBrowsePath(null)).toBeNull());
});

describe("queryKeys", () => {
  it("generatedImagesRoot", () => expect(queryKeys.generatedImagesRoot()).toEqual(["generated-images"]));
  it("landingPages", () => expect(queryKeys.landingPages()).toEqual(["landing-pages"]));
  it("librariesRoot", () => expect(queryKeys.librariesRoot()).toEqual(["libraries"]));
  it("libraries", () => expect(queryKeys.libraries()).toEqual(["libraries", "list"]));
  it("library", () => expect(queryKeys.library(5)).toEqual(["libraries", "detail", 5]));
  it("libraryStats", () => expect(queryKeys.libraryStats(5)).toEqual(["libraries", "stats", 5]));
  it("libraryJobs", () => expect(queryKeys.libraryJobs(5)).toEqual(["libraries", "jobs", 5]));
  it("galleryStats", () => expect(queryKeys.galleryStats()).toEqual(["stats", "gallery"]));
  it("jobsRoot", () => expect(queryKeys.jobsRoot()).toEqual(["jobs"]));
  it("jobs", () => expect(queryKeys.jobs()).toEqual(["jobs", "list"]));
  it("job", () => expect(queryKeys.job(9)).toEqual(["jobs", 9]));
  it("browseAllRoot", () => expect(queryKeys.browseAllRoot()).toEqual(["browse"]));
  it("browseRoot", () => expect(queryKeys.browseRoot(4)).toEqual(["browse", 4]));
  it("folderChildren", () => expect(queryKeys.folderChildren("/p")).toEqual(["folder-children", "/p"]));
  it("browseInfiniteAllRoot", () => expect(queryKeys.browseInfiniteAllRoot()).toEqual(["browse-infinite"]));
  it("browseInfiniteRoot", () => expect(queryKeys.browseInfiniteRoot(4)).toEqual(["browse-infinite", 4]));
  it("search", () => expect(queryKeys.search("cat", "all", "/p")).toEqual(["search", "cat", "all", "/p"]));
  it("metadata", () => expect(queryKeys.metadata("/a.png")).toEqual(["metadata", "/a.png"]));
  it("statusRoot", () => expect(queryKeys.statusRoot()).toEqual(["status"]));
  it("statusBatch", () => expect(queryKeys.statusBatch()).toEqual(["status", "libraries", "batch"]));
  it("statusLibrary", () => expect(queryKeys.statusLibrary(4)).toEqual(["status", "library", 4]));
  it("statusPathRoot", () => expect(queryKeys.statusPathRoot(4)).toEqual(["status", "path", 4]));
  it("libraryInspectorRoot", () => expect(queryKeys.libraryInspectorRoot()).toEqual(["library-inspector"]));
  it("facets", () => expect(queryKeys.facets("/p")).toEqual(["facets", "/p"]));
  it("maintenanceRoot", () => expect(queryKeys.maintenanceRoot()).toEqual(["maintenance"]));
  it("maintenanceFileHealth", () => expect(queryKeys.maintenanceFileHealth()).toEqual(["maintenance", "file-health"]));
  it("browse with includeOffline", () => {
    expect(queryKeys.browse(4, "/p", 50, true)).toEqual(["browse", 4, "/p", 50, true]);
  });
  it("browseInfinite with includeOffline", () => {
    expect(queryKeys.browseInfinite(4, "/p", 50, true)).toEqual(["browse-infinite", 4, "/p", 50, true]);
  });
  it("statusPath", () => {
    expect(queryKeys.statusPath(4, "/p")).toEqual(["status", "path", 4, "/p"]);
    expect(queryKeys.statusPath(4, "")).toEqual(["status", "path", 4, null]);
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
