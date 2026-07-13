/// <reference types="node" />

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseSearchQuery, replaceManagedFilters, serializeManagedFilters } from "../searchQueryGrammar";

describe("searchQueryGrammar", () => {
  it("consumes the shared backend/frontend grammar fixture", () => {
    const fixture = JSON.parse(
      readFileSync(resolve(process.cwd(), "../test-data/search-query-grammar.json"), "utf8"),
    ) as {
      contract_version: number;
      cases: Array<{
        name: string;
        query: string;
        residual_text: string;
        frontend_residual_text?: string;
        frontend_managed_filters: Array<{ field: string; operator?: string; value: string }>;
        frontend_pass_through_tokens: string[];
      }>;
    };
    expect(fixture.contract_version).toBe(1);
    for (const grammarCase of fixture.cases) {
      const parsed = parseSearchQuery(grammarCase.query);
      expect(parsed.residualText, grammarCase.name).toBe(
        grammarCase.frontend_residual_text ?? grammarCase.residual_text,
      );
      expect(parsed.managedFilters, grammarCase.name).toEqual(
        grammarCase.frontend_managed_filters.map((filter) => ({ operator: undefined, ...filter })),
      );
      expect(parsed.passThroughTokens, grammarCase.name).toEqual(grammarCase.frontend_pass_through_tokens);
    }
  });

  it("parses residual text, quotes, escapes, operators, repeated fields, and pass-through tokens", () => {
    const parsed = parseSearchQuery(
      `猫 portrait prompt:'soft light' model:"say \\"hi\\"" seed:>=12 model:pony tool:ComfyUI unknown:"kept value"`,
    );
    expect(parsed.residualText).toBe("猫 portrait");
    expect(parsed.managedFilters).toEqual([
      { field: "prompt", value: "soft light", operator: undefined },
      { field: "model", value: 'say "hi"', operator: undefined },
      { field: "seed", value: "12", operator: ">=" },
      { field: "model", value: "pony", operator: undefined },
    ]);
    expect(parsed.passThroughTokens).toEqual(["tool:ComfyUI", 'unknown:"kept value"']);
  });

  it("replaces only managed filters and preserves search meaning", () => {
    expect(replaceManagedFilters("cat model:pony tool:ComfyUI", [{ field: "seed", value: "7" }])).toBe(
      "cat tool:ComfyUI seed:7",
    );
  });

  it("round-trips Unicode and escaped quoted values", () => {
    const serialized = serializeManagedFilters([
      { field: "prompt", value: '夜の猫 says "hi"' },
      { field: "model", value: "pony\\xl" },
    ]);
    expect(parseSearchQuery(serialized).managedFilters).toEqual([
      { field: "prompt", value: '夜の猫 says "hi"', operator: undefined },
      { field: "model", value: "pony\\xl", operator: undefined },
    ]);
  });
});
