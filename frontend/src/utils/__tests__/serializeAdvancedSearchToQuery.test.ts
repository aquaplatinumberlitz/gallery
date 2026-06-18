import { describe, it, expect } from "vitest";
import {
  filterToDisplayString,
  parseFieldedQuery,
  serializeAdvancedSearchToQuery,
} from "../serializeAdvancedSearchToQuery";
import type { FieldFilter } from "@/types";

describe("serializeAdvancedSearchToQuery", () => {
  it("returns an empty string for an empty filter list", () => {
    expect(serializeAdvancedSearchToQuery([])).toBe("");
  });

  it("serializes a single filter without an operator", () => {
    expect(serializeAdvancedSearchToQuery([{ field: "model", value: "gpt" }])).toBe("model:gpt");
  });

  it("serializes filters with explicit operators", () => {
    expect(serializeAdvancedSearchToQuery([{ field: "model", operator: "=", value: "gpt" }])).toBe("model:=gpt");
    expect(serializeAdvancedSearchToQuery([{ field: "seed", operator: ">", value: "100" }])).toBe("seed:>100");
    expect(serializeAdvancedSearchToQuery([{ field: "seed", operator: ">=", value: "100" }])).toBe("seed:>=100");
    expect(serializeAdvancedSearchToQuery([{ field: "seed", operator: "<", value: "100" }])).toBe("seed:<100");
    expect(serializeAdvancedSearchToQuery([{ field: "seed", operator: "<=", value: "100" }])).toBe("seed:<=100");
  });

  it("omits the operator for literal fields (ratio, size, date) regardless of case", () => {
    expect(serializeAdvancedSearchToQuery([{ field: "ratio", operator: ">", value: "1.5" }])).toBe("ratio:1.5");
    expect(serializeAdvancedSearchToQuery([{ field: "size", operator: "=", value: "1024" }])).toBe("size:1024");
    expect(serializeAdvancedSearchToQuery([{ field: "date", operator: ">=", value: "2024-01-01" }])).toBe(
      "date:2024-01-01",
    );
    expect(serializeAdvancedSearchToQuery([{ field: "RATIO", operator: ">", value: "1.5" }])).toBe("RATIO:1.5");
  });

  it("quotes values that contain whitespace", () => {
    expect(serializeAdvancedSearchToQuery([{ field: "prompt", value: "hello world" }])).toBe('prompt:"hello world"');
  });

  it("escapes and quotes values that contain double quotes", () => {
    expect(serializeAdvancedSearchToQuery([{ field: "prompt", value: 'say "hi"' }])).toBe('prompt:"say \\"hi\\""');
  });

  it("quotes values that contain parentheses", () => {
    expect(serializeAdvancedSearchToQuery([{ field: "prompt", value: "(text)" }])).toBe('prompt:"(text)"');
  });

  it("does not quote values without whitespace, quotes, or parens", () => {
    expect(serializeAdvancedSearchToQuery([{ field: "model", value: "gpt-4" }])).toBe("model:gpt-4");
  });

  it("joins multiple filters with a single space", () => {
    const filters: FieldFilter[] = [
      { field: "model", operator: "=", value: "gpt" },
      { field: "seed", operator: ">", value: "100" },
      { field: "prompt", value: "hello world" },
    ];
    expect(serializeAdvancedSearchToQuery(filters)).toBe('model:=gpt seed:>100 prompt:"hello world"');
  });

  it("round-trips through parseFieldedQuery for filters with quoted values and escaped quotes", () => {
    const filters: FieldFilter[] = [
      { field: "prompt", value: 'say "hi" there' },
      { field: "model", operator: "=", value: "gpt" },
    ];
    const serialized = serializeAdvancedSearchToQuery(filters);
    const parsed = parseFieldedQuery(serialized);
    expect(parsed).toEqual(filters);
  });
});

describe("filterToDisplayString", () => {
  it("renders a filter without an operator", () => {
    expect(filterToDisplayString({ field: "model", value: "gpt" })).toBe("model:gpt");
  });

  it("renders a filter with an operator", () => {
    expect(filterToDisplayString({ field: "seed", operator: ">", value: "100" })).toBe("seed:>100");
  });

  it("omits the operator for literal fields", () => {
    expect(filterToDisplayString({ field: "ratio", operator: ">", value: "1.5" })).toBe("ratio:1.5");
  });

  it("quotes values that need quoting (display path does NOT escape inner quotes)", () => {
    expect(filterToDisplayString({ field: "prompt", value: "hello world" })).toBe('prompt:"hello world"');
    // Display variant wraps in quotes but does not escape inner double quotes.
    expect(filterToDisplayString({ field: "prompt", value: 'say "hi"' })).toBe('prompt:"say "hi""');
  });

  it("does not quote plain values", () => {
    expect(filterToDisplayString({ field: "model", value: "gpt-4" })).toBe("model:gpt-4");
  });
});

describe("parseFieldedQuery", () => {
  it("returns an empty array for an empty query", () => {
    expect(parseFieldedQuery("")).toEqual([]);
  });

  it("returns an empty array when no fielded tokens are present", () => {
    expect(parseFieldedQuery("just some free text")).toEqual([]);
  });

  it("parses a single token without an operator", () => {
    expect(parseFieldedQuery("model:gpt")).toEqual([{ field: "model", operator: undefined, value: "gpt" }]);
  });

  it("parses tokens with each operator", () => {
    expect(parseFieldedQuery("seed:=100")).toEqual([{ field: "seed", operator: "=", value: "100" }]);
    expect(parseFieldedQuery("seed:>100")).toEqual([{ field: "seed", operator: ">", value: "100" }]);
    expect(parseFieldedQuery("seed:>=100")).toEqual([{ field: "seed", operator: ">=", value: "100" }]);
    expect(parseFieldedQuery("seed:<100")).toEqual([{ field: "seed", operator: "<", value: "100" }]);
    expect(parseFieldedQuery("seed:<=100")).toEqual([{ field: "seed", operator: "<=", value: "100" }]);
  });

  it("parses multiple tokens separated by whitespace", () => {
    const parsed = parseFieldedQuery("model:=gpt seed:>100");
    expect(parsed).toEqual([
      { field: "model", operator: "=", value: "gpt" },
      { field: "seed", operator: ">", value: "100" },
    ]);
  });

  it("parses quoted values that contain whitespace", () => {
    expect(parseFieldedQuery('prompt:"hello world"')).toEqual([
      { field: "prompt", operator: undefined, value: "hello world" },
    ]);
  });

  it("unescapes double quotes inside quoted values", () => {
    expect(parseFieldedQuery('prompt:"say \\"hi\\""')).toEqual([
      { field: "prompt", operator: undefined, value: 'say "hi"' },
    ]);
  });

  it("lowercases the field name", () => {
    expect(parseFieldedQuery("MODEL:gpt")).toEqual([{ field: "model", operator: undefined, value: "gpt" }]);
  });

  it("stops the value at the next whitespace when unquoted", () => {
    const parsed = parseFieldedQuery("model:gpt seed:100");
    expect(parsed).toHaveLength(2);
    expect(parsed[0].value).toBe("gpt");
    expect(parsed[1].value).toBe("100");
  });

  it("round-trips serialize -> parse for a single filter", () => {
    const original: FieldFilter[] = [{ field: "model", operator: "=", value: "gpt-4" }];
    expect(parseFieldedQuery(serializeAdvancedSearchToQuery(original))).toEqual(original);
  });
});
