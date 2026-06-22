import { describe, expect, it } from "vitest";
import {
  ACTIVE_POLL_INTERVAL,
  STABLE_POLL_INTERVAL,
  isUnifiedStatusActive,
  statusRefetchInterval,
} from "../polling";
import type { UnifiedStatus } from "../status";

function makeStatus(overrides: Partial<UnifiedStatus> = {}): UnifiedStatus {
  return {
    contract_version: 1,
    generated_at: 1782036000000,
    summary_state: "ready",
    scope: { kind: "library", library_id: 7, path: null, import_path_count: 1 },
    availability: { state: "available", available_paths: 1, total_paths: 1 },
    scan: {
      state: "complete",
      operation: "scan",
      trigger: "manual",
      active_job_id: null,
      completed_units: 10,
      total_units: 10,
      progress_percent: 100,
    },
    metadata: {
      state: "complete",
      total_assets: 10,
      ready_assets: 10,
      not_ready_assets: 0,
      queued_assets: 0,
      running_assets: 0,
      stale_assets: 0,
      idle_pending_assets: 0,
      failed_assets: 0,
      progress_percent: 100,
      global_active_outside_scope: false,
    },
    issue_count: 0,
    issues: { availability: 0, scan: 0, metadata: 0 },
    latest_issue: null,
    last_scan_at: 1782036040000,
    last_index_at: 1782036050000,
    ...overrides,
  } as UnifiedStatus;
}

describe("isUnifiedStatusActive", () => {
  it("returns false for undefined/null status", () => {
    expect(isUnifiedStatusActive(undefined)).toBe(false);
    expect(isUnifiedStatusActive(null)).toBe(false);
  });

  it("returns false when scan and metadata are settled", () => {
    expect(isUnifiedStatusActive(makeStatus())).toBe(false);
  });

  it("returns true when scan.state is queued", () => {
    expect(
      isUnifiedStatusActive(
        makeStatus({ scan: { ...makeStatus().scan, state: "queued" } }),
      ),
    ).toBe(true);
  });

  it("returns true when scan.state is scanning", () => {
    expect(
      isUnifiedStatusActive(
        makeStatus({ scan: { ...makeStatus().scan, state: "scanning" } }),
      ),
    ).toBe(true);
  });

  it("returns true when metadata.state is queued", () => {
    expect(
      isUnifiedStatusActive(
        makeStatus({ metadata: { ...makeStatus().metadata, state: "queued" } }),
      ),
    ).toBe(true);
  });

  it("returns true when metadata.state is indexing", () => {
    expect(
      isUnifiedStatusActive(
        makeStatus({ metadata: { ...makeStatus().metadata, state: "indexing" } }),
      ),
    ).toBe(true);
  });

  it("returns false when scan failed and metadata is complete", () => {
    expect(
      isUnifiedStatusActive(
        makeStatus({ scan: { ...makeStatus().scan, state: "failed" } }),
      ),
    ).toBe(false);
  });
});

describe("statusRefetchInterval", () => {
  it("returns false when not enabled", () => {
    expect(statusRefetchInterval(makeStatus(), false)).toBe(false);
  });

  it("returns false when status is undefined or null", () => {
    expect(statusRefetchInterval(undefined, true)).toBe(false);
    expect(statusRefetchInterval(null, true)).toBe(false);
  });

  it("returns the stable interval when the scope is settled", () => {
    expect(statusRefetchInterval(makeStatus(), true)).toBe(STABLE_POLL_INTERVAL);
  });

  it("returns the active interval when scan is queued", () => {
    const status = makeStatus({ scan: { ...makeStatus().scan, state: "queued" } });
    expect(statusRefetchInterval(status, true)).toBe(ACTIVE_POLL_INTERVAL);
  });

  it("returns the active interval when metadata is indexing", () => {
    const status = makeStatus({ metadata: { ...makeStatus().metadata, state: "indexing" } });
    expect(statusRefetchInterval(status, true)).toBe(ACTIVE_POLL_INTERVAL);
  });
});
