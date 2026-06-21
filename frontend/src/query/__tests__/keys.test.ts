import { describe, expect, it } from "vitest";
import { queryKeys } from "../keys";

describe("library management query keys", () => {
  it("builds library keys", () => {
    expect(queryKeys.librariesRoot()).toEqual(["libraries"]);
    expect(queryKeys.libraries()).toEqual(["libraries", "list"]);
    expect(queryKeys.library(7)).toEqual(["libraries", "detail", 7]);
    expect(queryKeys.libraryProgress(7)).toEqual(["libraries", "progress", 7]);
    expect(queryKeys.libraryStats(7)).toEqual(["libraries", "stats", 7]);
    expect(queryKeys.libraryJobs(7)).toEqual(["libraries", "jobs", 7]);
  });

  it("builds gallery stats and job keys", () => {
    expect(queryKeys.galleryStats()).toEqual(["stats", "gallery"]);
    expect(queryKeys.jobsRoot()).toEqual(["jobs"]);
    expect(queryKeys.jobs()).toEqual(["jobs", "list"]);
    expect(queryKeys.job(11)).toEqual(["jobs", 11]);
  });

  it("builds catalog browse keys", () => {
    expect(queryKeys.browseRoot(7)).toEqual(["browse", 7]);
    expect(queryKeys.browse(7, "/photos/", 100)).toEqual(["browse", 7, "/photos", 100, false]);
    expect(queryKeys.browse(7, null, 100)).toEqual(["browse", 7, null, 100, false]);
    expect(queryKeys.browseInfiniteRoot(7)).toEqual(["browse-infinite", 7]);
    expect(queryKeys.browseInfinite(7, "/photos", 100, true)).toEqual(["browse-infinite", 7, "/photos", 100, true]);
  });
});
