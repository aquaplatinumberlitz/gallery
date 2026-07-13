import { describe, expect, it } from "vitest";
import type { LocationQuery } from "vue-router";
import type { SearchQueryRequestV1 } from "@/types";
import { decodeSearchUrlQuery, encodeSearchUrlQuery } from "../searchUrlCodec";

const request: SearchQueryRequestV1 = {
  schema_version: 1,
  mode: "workflow",
  text: "猫 model:Flux",
  scope: {
    kind: "folder",
    library_id: 2,
    import_path_id: 7,
    relative_path: "CaseSensitive/Portraits",
  },
  filters: {
    prompt_groups: [{ kind: "positive", value_id: "abcdefghijklmnopqrstuvwxyz0123456789_-ABCDE" }],
    workflow_groups: [
      {
        node_type: "KSampler",
        predicates: [{ property: "steps", op: "gte", value: 20 }],
      },
    ],
  },
  cursor: "opaque-not-shareable",
  limit: 25,
};

describe("search URL codec", () => {
  it("round-trips canonical state while omitting cursor, limit, and absolute paths", () => {
    const encoded = encodeSearchUrlQuery(request);
    expect(encoded).toMatchObject({
      search_v: "1",
      q: "猫 model:Flux",
      scope: "folder",
      library: "2",
      import: "7",
      path: "CaseSensitive/Portraits",
      mode: "workflow",
    });
    expect(encoded).not.toHaveProperty("cursor");
    expect(encoded).not.toHaveProperty("limit");
    expect(JSON.stringify(encoded)).not.toContain("/home/");

    const decoded = decodeSearchUrlQuery(encoded as LocationQuery);
    expect(decoded.invalid).toBe(false);
    expect(decoded.request).toEqual({ ...request, cursor: null, limit: 60 });
  });

  it.each([
    [{ search_v: "2", q: "cat", scope: "all" }],
    [{ search_v: "1", q: "cat", scope: "folder", library: "2", import: "7", path: "../escape" }],
    [{ search_v: "1", q: "cat", scope: "folder", library: "2", import: "7", path: "/absolute" }],
    [{ search_v: "1", q: "cat", scope: "library", library: "bad" }],
    [{ search_v: "1", q: "cat", scope: "all", pg: "***" }],
  ])("rejects malformed URL state", (query) => {
    expect(decodeSearchUrlQuery(query as LocationQuery)).toEqual({ request: null, invalid: true });
  });

  it("treats a normal gallery URL as having no search state", () => {
    expect(decodeSearchUrlQuery({ eruda: "1" })).toEqual({ request: null, invalid: false });
  });
});
