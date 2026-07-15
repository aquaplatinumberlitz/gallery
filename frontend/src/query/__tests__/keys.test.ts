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
  it("provides a root key that invalidates every library search-index query", () => {
    expect(queryKeys.searchIndexesRoot()).toEqual(["search-indexes"]);
    expect(queryKeys.searchIndexes(7)).toEqual(["search-indexes", 7]);
  });

  it.each([
    ["generatedImagesRoot", [], ["generated-images"]],
    ["landingPages", [], ["landing-pages"]],
    ["librariesRoot", [], ["libraries"]],
    ["libraries", [], ["libraries", "list"]],
    ["library", [5], ["libraries", "detail", 5]],
    ["libraryStats", [5], ["libraries", "stats", 5]],
    ["offlineLibraryAssets", [5], ["libraries", "offline-assets", 5]],
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
    ["metadata", ["/a.png"], ["metadata", "/a.png"]],
    ["statusRoot", [], ["status"]],
    ["statusBatch", [], ["status", "libraries", "batch"]],
    ["statusLibrary", [4], ["status", "library", 4]],
    ["statusPathRoot", [4], ["status", "path", 4]],
    ["libraryInspectorRoot", [], ["library-inspector"]],
    ["facets", ["folder", 4, "/p"], ["facets", "folder", 4, "/p"]],
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

  it("libraryJobs includes limit when provided", () => {
    expect(queryKeys.libraryJobs(5, 8)).toEqual(["libraries", "jobs", 5, 8]);
  });

  it("jobs includes limit when provided", () => {
    expect(queryKeys.jobs(8)).toEqual(["jobs", "list", 8]);
  });

  it("search contains the complete persistable canonical request and limit but not cursor", () => {
    expect(
      queryKeys.search({
        schema_version: 1,
        mode: "lexical",
        text: "CaseSensitive",
        scope: { kind: "folder", library_id: 4, import_path_id: 9, relative_path: "Portraits/A" },
        filters: { prompt_groups: [], workflow_groups: [] },
        cursor: "opaque",
        limit: 60,
      }),
    ).toEqual([
      "search-v2",
      {
        schema_version: 1,
        mode: "lexical",
        text: "CaseSensitive",
        scope: { kind: "folder", library_id: 4, import_path_id: 9, relative_path: "Portraits/A" },
        filters: { prompt_groups: [], workflow_groups: [] },
      },
      60,
    ]);
  });

  it("prompt usage keys contain polarity, scope, text, sort, and limit but no cursor", () => {
    const request = {
      polarity: "negative" as const,
      scope: { kind: "library" as const, library_id: 4 },
      prefix: null,
      text: "watermark",
      sort: "recent" as const,
      limit: 40,
    };
    expect(queryKeys.promptUsage(request)).toEqual(["prompt-usage", request]);
  });

  it("related assets keys partition reference, scope, profile, and limit", () => {
    const request = {
      schema_version: 1 as const,
      reference_asset_id: 9,
      profile: "visual" as const,
      scope: { kind: "library" as const, library_id: 4 },
      limit: 60,
    };
    expect(queryKeys.relatedAssets(request)).toEqual(["related-assets", request]);
  });

  it.each([
    [4, "/p", ["status", "path", 4, "/p"]],
    [4, "", ["status", "path", 4, null]],
  ] as const)("statusPath(%i, %j) => %j", (libraryId, path, expected) => {
    expect(queryKeys.statusPath(libraryId, path)).toEqual(expected);
  });

  it("libraryInspector", () => {
    expect(queryKeys.libraryInspector("q", "all", "/p", 50, "date_desc", "SDXL", "has_prompt")).toEqual([
      "library-inspector",
      "q",
      "all",
      "/p",
      50,
      "date_desc",
      "SDXL",
      "has_prompt",
    ]);
  });
});
