import { describe, expect, it } from "vitest";
import type { FieldFilter } from "@/types";
import {
  buildDefaultValues,
  buildStagedState,
  collectStagedChips,
  collectStagedFilters,
  defaultSlotValue,
  fieldValueForFacet,
} from "../advancedSearchModel";

function stagedFrom(filters: FieldFilter[]) {
  const { values, tokens } = buildStagedState(filters);
  return { values, tokens, openingValues: structuredClone(values) };
}

function chipShape(chip: ReturnType<typeof collectStagedChips>[number]) {
  return {
    id: chip.id,
    kind: chip.kind,
    slot: chip.slot,
    tokenId: chip.tokenId,
    filter: chip.filter,
  };
}

describe("collectStagedChips", () => {
  it("marks unknown filters as removable passthrough chips", () => {
    const { values, tokens, openingValues } = stagedFrom([{ field: "future_filter", operator: ">=", value: "7" }]);
    const chips = collectStagedChips(values, tokens, openingValues);
    expect(chips.map(chipShape)).toEqual([
      {
        id: "chip-passthru-filter-0",
        kind: "passthrough",
        slot: null,
        tokenId: "filter-0",
        filter: { field: "future_filter", operator: ">=", value: "7" },
      },
    ]);
  });

  it("keeps an unchanged primary filter as a primary chip pointing at its slot", () => {
    const { values, tokens, openingValues } = stagedFrom([{ field: "model", value: "PonyXL" }]);
    const chips = collectStagedChips(values, tokens, openingValues);
    expect(chips.map(chipShape)).toEqual([
      {
        id: "chip-primary-filter-0-=",
        kind: "primary",
        slot: "model",
        tokenId: "filter-0",
        filter: { field: "model", value: "PonyXL" },
      },
    ]);
  });

  it("reflects the edited value on a primary chip while keeping slot and tokenId", () => {
    const { values, tokens, openingValues } = stagedFrom([{ field: "model", value: "PonyXL" }]);
    values.model = "Flux";
    const chips = collectStagedChips(values, tokens, openingValues);
    expect(chips.map(chipShape)).toEqual([
      {
        id: "chip-primary-filter-0-=",
        kind: "primary",
        slot: "model",
        tokenId: "filter-0",
        filter: { field: "model", value: "Flux" },
      },
    ]);
  });

  it("emits a new primary chip without a tokenId for freshly typed text filters", () => {
    const values = buildDefaultValues();
    values.prompt = "cat";
    const chips = collectStagedChips(values, [], buildDefaultValues());
    expect(chips.map(chipShape)).toEqual([
      {
        id: "chip-new-prompt-=",
        kind: "primary",
        slot: "prompt",
        tokenId: null,
        filter: { field: "prompt", value: "cat" },
      },
    ]);
  });

  it("emits a new primary chip with operator for freshly typed numeric filters", () => {
    const values = buildDefaultValues();
    values.steps = { value: "30", op: ">=" };
    const chips = collectStagedChips(values, [], buildDefaultValues());
    expect(chips.map(chipShape)).toEqual([
      {
        id: "chip-new-steps->=",
        kind: "primary",
        slot: "steps",
        tokenId: null,
        filter: { field: "steps", operator: ">=", value: "30" },
      },
    ]);
  });

  it("expands a between op into two chips sharing the same slot and tokenId", () => {
    const { values, tokens, openingValues } = stagedFrom([{ field: "width", operator: ">=", value: "512" }]);
    values.width = { value: "512;1024", op: "between" };
    const chips = collectStagedChips(values, tokens, openingValues);
    expect(chips.map(chipShape)).toEqual([
      {
        id: "chip-primary-filter-0->=",
        kind: "primary",
        slot: "width",
        tokenId: "filter-0",
        filter: { field: "width", operator: ">=", value: "512" },
      },
      {
        id: "chip-primary-filter-0-<=",
        kind: "primary",
        slot: "width",
        tokenId: "filter-0",
        filter: { field: "width", operator: "<=", value: "1024" },
      },
    ]);
  });

  it("emits two new chips from a freshly typed between numeric filter", () => {
    const values = buildDefaultValues();
    values.steps = { value: "20;40", op: "between" };
    const chips = collectStagedChips(values, [], buildDefaultValues());
    expect(chips.map(chipShape)).toEqual([
      {
        id: "chip-new-steps->=",
        kind: "primary",
        slot: "steps",
        tokenId: null,
        filter: { field: "steps", operator: ">=", value: "20" },
      },
      {
        id: "chip-new-steps-<=",
        kind: "primary",
        slot: "steps",
        tokenId: null,
        filter: { field: "steps", operator: "<=", value: "40" },
      },
    ]);
  });

  it("splits a repeated field into one primary chip and one passthrough chip", () => {
    const { values, tokens, openingValues } = stagedFrom([
      { field: "model", value: "PonyXL" },
      { field: "model", value: "SDXL" },
    ]);
    values.model = "Flux";
    const chips = collectStagedChips(values, tokens, openingValues);
    expect(chips.map(chipShape)).toEqual([
      {
        id: "chip-primary-filter-0-=",
        kind: "primary",
        slot: "model",
        tokenId: "filter-0",
        filter: { field: "model", value: "Flux" },
      },
      {
        id: "chip-passthru-filter-1",
        kind: "passthrough",
        slot: null,
        tokenId: "filter-1",
        filter: { field: "model", value: "SDXL" },
      },
    ]);
  });

  it("stays consistent with collectStagedFilters filter order", () => {
    const { values, tokens, openingValues } = stagedFrom([
      { field: "prompt", value: "portrait" },
      { field: "future_filter", operator: ">=", value: "7" },
    ]);
    values.prompt = "landscape";
    const filters = collectStagedFilters(values, tokens, openingValues);
    const chipFilters = collectStagedChips(values, tokens, openingValues).map((chip) => chip.filter);
    expect(filters).toEqual(chipFilters);
  });
});

describe("defaultSlotValue", () => {
  it("returns an empty string for text slots", () => {
    expect(defaultSlotValue("model")).toBe("");
    expect(defaultSlotValue("prompt")).toBe("");
  });

  it("returns a neutral numeric value for numeric slots", () => {
    expect(defaultSlotValue("steps")).toEqual({ value: "", op: "=" });
    expect(defaultSlotValue("seed")).toEqual({ value: "", op: "=" });
  });
});

describe("fieldValueForFacet", () => {
  it("returns the raw string for text fields", () => {
    expect(fieldValueForFacet("model", "PonyXL")).toBe("PonyXL");
  });

  it("wraps the value with the equals operator for numeric fields", () => {
    expect(fieldValueForFacet("steps", "30")).toEqual({ value: "30", op: "=" });
  });
});
