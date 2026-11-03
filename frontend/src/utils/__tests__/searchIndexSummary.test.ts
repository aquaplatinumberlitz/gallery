import { describe, expect, it } from "vitest";
import type { SearchIndexStateV1 } from "../../types";
import { summarizeDerivedSearchIndexes } from "../searchIndexSummary";

function row(overrides: Partial<SearchIndexStateV1>): SearchIndexStateV1 {
  return {
    index_name: "prompt_values",
    library_id: 1,
    library_name: "Main",
    state: "ready",
    usable: true,
    enabled: true,
    schema_version: 1,
    extractor_version: 1,
    indexed_count: 10,
    target_count: 10,
    failed_count: 0,
    skipped_count: 0,
    skip_reasons: {},
    active_job_id: null,
    ...overrides,
  };
}

describe("summarizeDerivedSearchIndexes", () => {
  it("returns null when there is no index state to report", () => {
    expect(summarizeDerivedSearchIndexes(null)).toBeNull();
    expect(summarizeDerivedSearchIndexes([])).toBeNull();
    expect(summarizeDerivedSearchIndexes([row({ index_name: "generation_signatures" })])).toBeNull();
  });

  it("reports ready and building percent for the two auto-built indexes", () => {
    const text = summarizeDerivedSearchIndexes([
      row({ index_name: "prompt_values" }),
      row({ index_name: "workflow_properties", state: "building", indexed_count: 40, target_count: 100 }),
    ]);
    expect(text).toBe("Search indexes: prompt groups ready, workflow fields building 40 %");
  });

  it("counts skipped and failed assets as processed and never shows 100 % while building", () => {
    const text = summarizeDerivedSearchIndexes([
      row({
        index_name: "prompt_values",
        state: "building",
        indexed_count: 50,
        skipped_count: 30,
        failed_count: 20,
        target_count: 100,
      }),
    ]);
    expect(text).toBe("Search indexes: prompt groups building 99 %");
  });

  it("aggregates libraries: the least-ready state wins and percent is weighted by target", () => {
    const text = summarizeDerivedSearchIndexes([
      row({ library_id: 1, index_name: "prompt_values" }),
      row({ library_id: 2, index_name: "prompt_values", state: "building", indexed_count: 10, target_count: 30 }),
    ]);
    // Only the building library counts toward the percent: 10 of 30.
    expect(text).toBe("Search indexes: prompt groups building 33 %");
  });

  it("describes pending, degraded and failed states and ignores disabled indexes", () => {
    expect(
      summarizeDerivedSearchIndexes([
        row({ index_name: "prompt_values", state: "pending", usable: false, indexed_count: 0 }),
        row({ index_name: "workflow_properties", state: "degraded" }),
      ]),
    ).toBe("Search indexes: prompt groups waiting to start, workflow fields needs a rebuild");
    expect(summarizeDerivedSearchIndexes([row({ index_name: "workflow_properties", state: "failed" })])).toBe(
      "Search indexes: workflow fields failed",
    );
    expect(
      summarizeDerivedSearchIndexes([
        row({ index_name: "workflow_raw", state: "disabled", enabled: false }),
        row({ index_name: "prompt_values", state: "disabled", enabled: false }),
      ]),
    ).toBeNull();
  });

  it("falls back to a plain building label when the target is unknown", () => {
    expect(
      summarizeDerivedSearchIndexes([
        row({ index_name: "prompt_values", state: "building", indexed_count: 0, target_count: 0 }),
      ]),
    ).toBe("Search indexes: prompt groups building");
  });
});
