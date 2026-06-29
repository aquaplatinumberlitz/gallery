import { describe, expect, it } from "vitest";
import {
  assertLibraryStatusBatch,
  assertStatusEnvelope,
  isStatusContractError,
  StatusContractError,
  STATUS_CONTRACT_ERROR_MESSAGE,
} from "../contractGuard";
import type { GlobalRuntime, StatusResponseEnvelope, UnifiedStatus } from "../status";

const globalRuntime: GlobalRuntime = {
  catalog_worker_count: 1,
  catalog_active_jobs: 0,
  catalog_queue_depth: 0,
  metadata_worker_count: 1,
  metadata_active_jobs: 0,
  metadata_queue_depth: 0,
  metadata_staged_queue_depth: 0,
  watcher_enabled: true,
  watcher_healthy: true,
  watcher_issue: null,
  scheduled_reconciliation_enabled: true,
};

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

function makeEnvelope(status: UnifiedStatus = makeStatus()): StatusResponseEnvelope {
  return { contract_version: 1, status, global_runtime: globalRuntime, metadata_lifecycle: null };
}

describe("assertStatusEnvelope", () => {
  it("accepts a valid contract-v1 envelope", () => {
    expect(() => assertStatusEnvelope(makeEnvelope())).not.toThrow();
  });

  it("rejects an unknown contract_version", () => {
    expect(() =>
      assertStatusEnvelope({ contract_version: 2, status: makeStatus(), global_runtime: globalRuntime }),
    ).toThrow(StatusContractError);
  });

  it("rejects a non-object envelope", () => {
    expect(() => assertStatusEnvelope(null)).toThrow(StatusContractError);
    expect(() => assertStatusEnvelope("not-an-object")).toThrow(StatusContractError);
  });

  it("rejects an envelope missing required status fields", () => {
    const broken = makeEnvelope();
    delete (broken.status as Partial<UnifiedStatus>).summary_state;
    expect(() => assertStatusEnvelope(broken)).toThrow(StatusContractError);
  });

  it("rejects an envelope with non-object global_runtime", () => {
    expect(() =>
      assertStatusEnvelope({
        contract_version: 1,
        status: makeStatus(),
        global_runtime: null as unknown as GlobalRuntime,
      }),
    ).toThrow(StatusContractError);
  });

  it("rejects an envelope with missing metadata.total_assets", () => {
    const broken = makeEnvelope();
    delete (broken.status.metadata as { total_assets?: number | null }).total_assets;
    expect(() => assertStatusEnvelope(broken)).toThrow(StatusContractError);
  });

  it("rejects an envelope with an invalid summary_state string", () => {
    const broken = makeEnvelope();
    (broken.status as { summary_state: string }).summary_state = "invalid_summary";
    expect(() => assertStatusEnvelope(broken)).toThrow(StatusContractError);
  });

  it("rejects an envelope with missing scan.state", () => {
    const broken = makeEnvelope();
    delete (broken.status.scan as { state?: string }).state;
    expect(() => assertStatusEnvelope(broken)).toThrow(StatusContractError);
  });

  it("rejects an envelope with missing scope.library_id", () => {
    const broken = makeEnvelope();
    delete (broken.status.scope as { library_id?: number }).library_id;
    expect(() => assertStatusEnvelope(broken)).toThrow(StatusContractError);
  });
});

describe("assertLibraryStatusBatch", () => {
  it("accepts a valid batch response", () => {
    const batch = {
      contract_version: 1,
      generated_at: 1782036000000,
      items: [{ library_id: 7, status: makeStatus() }],
      global_runtime: globalRuntime,
      metadata_lifecycle: null,
    };
    expect(() => assertLibraryStatusBatch(batch)).not.toThrow();
  });

  it("rejects a batch with unknown contract_version", () => {
    const batch = {
      contract_version: 2,
      generated_at: 1782036000000,
      items: [],
      global_runtime: globalRuntime,
    };
    expect(() => assertLibraryStatusBatch(batch)).toThrow(StatusContractError);
  });

  it("rejects a batch with invalid item status", () => {
    const broken = makeStatus();
    delete (broken as Partial<UnifiedStatus>).scope;
    const batch = {
      contract_version: 1,
      generated_at: 1782036000000,
      items: [{ library_id: 7, status: broken }],
      global_runtime: globalRuntime,
    };
    expect(() => assertLibraryStatusBatch(batch)).toThrow(StatusContractError);
  });
});

describe("metadata_lifecycle guard", () => {
  it("accepts metadata_lifecycle: null", () => {
    expect(() =>
      assertStatusEnvelope({
        contract_version: 1,
        status: makeStatus(),
        global_runtime: globalRuntime,
        metadata_lifecycle: null,
      }),
    ).not.toThrow();
  });

  it("accepts valid metadata_lifecycle object", () => {
    const lifecycle = {
      queued_metadata_jobs: 0,
      running_metadata_jobs: 0,
      done_metadata_jobs: 1,
      stale_metadata_jobs: 0,
      failed_metadata_jobs: 0,
      skipped_metadata_jobs: 0,
      oldest_queued_metadata_job_age: null,
      done_jobs_with_pending_assets: 0,
      current_image_metadata_with_pending_assets: 0,
      metadata_jobs_without_matching_assets: 0,
      assets_done_but_metadata_missing_or_stale: 0,
      repairable_metadata_assets: 0,
      metadata_worker_last_claimed_at: null,
      metadata_worker_last_completed_at: null,
      metadata_worker_alive: true,
    };
    expect(() =>
      assertStatusEnvelope({
        contract_version: 1,
        status: makeStatus(),
        global_runtime: globalRuntime,
        metadata_lifecycle: lifecycle,
      }),
    ).not.toThrow();
  });

  it("rejects metadata_lifecycle with wrong field types", () => {
    const lifecycle = {
      queued_metadata_jobs: 0,
      running_metadata_jobs: 0,
      done_metadata_jobs: "1",
      stale_metadata_jobs: 0,
      failed_metadata_jobs: 0,
      skipped_metadata_jobs: 0,
      oldest_queued_metadata_job_age: null,
      done_jobs_with_pending_assets: 0,
      current_image_metadata_with_pending_assets: 0,
      metadata_jobs_without_matching_assets: 0,
      assets_done_but_metadata_missing_or_stale: 0,
      repairable_metadata_assets: 0,
      metadata_worker_last_claimed_at: null,
      metadata_worker_last_completed_at: null,
      metadata_worker_alive: true,
    };
    expect(() =>
      assertStatusEnvelope({
        contract_version: 1,
        status: makeStatus(),
        global_runtime: globalRuntime,
        metadata_lifecycle: lifecycle,
      }),
    ).toThrow(StatusContractError);
  });
});

describe("StatusContractError", () => {
  it("uses the documented reload message by default", () => {
    const error = new StatusContractError();
    expect(error.message).toBe(STATUS_CONTRACT_ERROR_MESSAGE);
  });

  it("is identified by isStatusContractError", () => {
    const error = new StatusContractError();
    expect(isStatusContractError(error)).toBe(true);
    expect(isStatusContractError(new Error("other"))).toBe(false);
  });
});
