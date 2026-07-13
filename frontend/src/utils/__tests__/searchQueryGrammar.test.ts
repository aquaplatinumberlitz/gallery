import { describe, expect, it } from "vitest";
import { parseSearchQuery, replaceManagedFilters, serializeManagedFilters } from "../searchQueryGrammar";

describe("searchQueryGrammar", () => {
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
