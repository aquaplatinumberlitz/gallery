import { describe, it, expect } from "vitest";
import { deriveSummaryState, type PrecedenceFacts } from "../status";

const baseFacts: PrecedenceFacts = {
  resolved: true,
  availability: "available",
  active_catalog_job_state: null,
  active_metadata_state: null,
  latest_covering_scan_failed: false,
  prior_successful_covering_scan: true,
  has_failed_scan_attempt: false,
  metadata_pending_without_active_work: false,
  total_assets: 100,
  ready_assets: 80,
  failed_assets: 0,
  later_scan_failure: false,
  current_metadata_failures: 0,
  metadata_disabled: false,
};

describe("deriveSummaryState", () => {
  it("returns unknown when not resolved", () => {
    expect(deriveSummaryState({ ...baseFacts, resolved: false })).toBe("unknown");
  });

  it("returns offline when unavailable", () => {
    expect(deriveSummaryState({ ...baseFacts, availability: "unavailable" })).toBe("offline");
  });

  it("returns scanning when catalog job is queued", () => {
    expect(deriveSummaryState({ ...baseFacts, active_catalog_job_state: "queued" })).toBe("scanning");
  });

  it("returns scanning when catalog job is running", () => {
    expect(deriveSummaryState({ ...baseFacts, active_catalog_job_state: "running" })).toBe("scanning");
  });

  it("returns indexing when metadata job is queued", () => {
    expect(deriveSummaryState({ ...baseFacts, active_metadata_state: "queued" })).toBe("indexing");
  });

  it("returns indexing when metadata job is running", () => {
    expect(deriveSummaryState({ ...baseFacts, active_metadata_state: "running" })).toBe("indexing");
  });

  it("returns error when latest scan failed and no prior success", () => {
    expect(
      deriveSummaryState({
        ...baseFacts,
        latest_covering_scan_failed: true,
        prior_successful_covering_scan: false,
      }),
    ).toBe("error");
  });

  it("returns needs_scan when no prior scan and no failed attempt", () => {
    expect(
      deriveSummaryState({
        ...baseFacts,
        prior_successful_covering_scan: false,
        has_failed_scan_attempt: false,
      }),
    ).toBe("needs_scan");
  });

  it("returns error when all assets failed and metadata not disabled", () => {
    expect(
      deriveSummaryState({
        ...baseFacts,
        total_assets: 50,
        ready_assets: 0,
        failed_assets: 50,
        metadata_disabled: false,
      }),
    ).toBe("error");
  });

  it("returns needs_update when metadata pending without active work", () => {
    expect(
      deriveSummaryState({
        ...baseFacts,
        metadata_pending_without_active_work: true,
      }),
    ).toBe("needs_update");
  });

  it("returns ready_with_issues when later scan failed", () => {
    expect(
      deriveSummaryState({
        ...baseFacts,
        later_scan_failure: true,
      }),
    ).toBe("ready_with_issues");
  });

  it("returns ready_with_issues when metadata failures exist", () => {
    expect(
      deriveSummaryState({
        ...baseFacts,
        current_metadata_failures: 3,
      }),
    ).toBe("ready_with_issues");
  });

  it("returns ready_with_issues when degraded", () => {
    expect(
      deriveSummaryState({
        ...baseFacts,
        availability: "degraded",
      }),
    ).toBe("ready_with_issues");
  });

  it("returns ready when everything is fine", () => {
    expect(deriveSummaryState(baseFacts)).toBe("ready");
  });
});
