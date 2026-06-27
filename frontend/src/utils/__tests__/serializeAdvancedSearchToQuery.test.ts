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

  it.each([
    ["=", "seed:=100"],
    [">", "seed:>100"],
    [">=", "seed:>=100"],
    ["<", "seed:<100"],
    ["<=", "seed:<=100"],
  ])("serializes filter with operator %s", (operator, expected) => {
    expect(serializeAdvancedSearchToQuery([{ field: "seed", operator: operator as FieldFilter["operator"], value: "100" }])).toBe(expected);
  });

  it.each([
    ["ratio", ">", "1.5", "ratio:1.5"],
    ["size", "=", "1024", "size:1024"],
    ["date", ">=", "2024-01-01", "date:2024-01-01"],
    ["RATIO", ">", "1.5", "RATIO:1.5"],
  ])("omits operator for literal field %s", (field, operator, value, expected) => {
    expect(serializeAdvancedSearchToQuery([{ field, operator: operator as FieldFilter["operator"], value }])).toBe(expected);
  });

  it('quotes values that contain whitespace', () => {
    expect(serializeAdvancedSearchToQuery([{ field: "prompt", value: "hello world" }])).toBe('prompt:"hello world"');
  });

  it('escapes and quotes values that contain double quotes', () => {
    expect(serializeAdvancedSearchToQuery([{ field: "prompt", value: 'say "hi"' }])).toBe('prompt:"say \\"hi\\""');
  });

  it('quotes values that contain parentheses', () => {
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

  it('quotes values that need quoting', () => {
    expect(filterToDisplayString({ field: "prompt", value: "hello world" })).toBe('prompt:"hello world"');
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

  it.each([
    ["seed:=100", "="],
    ["seed:>100", ">"],
    ["seed:>=100", ">="],
    ["seed:<100", "<"],
    ["seed:<=100", "<="],
  ])("parses token with operator from %s", (query) => {
    const result = parseFieldedQuery(query);
    expect(result).toHaveLength(1);
    expect(result[0].field).toBe("seed");
    expect(result[0].value).toBe("100");
  });

  it("parses multiple tokens separated by whitespace", () => {
    const parsed = parseFieldedQuery("model:=gpt seed:>100");
    expect(parsed).toEqual([
      { field: "model", operator: "=", value: "gpt" },
      { field: "seed", operator: ">", value: "100" },
    ]);
  });

  it('parses quoted values that contain whitespace', () => {
    expect(parseFieldedQuery('prompt:"hello world"')).toEqual([
      { field: "prompt", operator: undefined, value: "hello world" },
    ]);
  });

  it('unescapes double quotes inside quoted values', () => {
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
