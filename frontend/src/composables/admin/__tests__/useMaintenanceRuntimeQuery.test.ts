import { describe, it, expect } from "vitest";
import type { MaintenanceRuntimeResponse } from "@/services/api";
import { runtimeHasActiveWork } from "../useMaintenanceRuntimeQuery";

const idleRuntime: MaintenanceRuntimeResponse = {
  global_runtime: {
    catalog_worker_count: 1,
    catalog_active_jobs: 0,
    catalog_queue_depth: 0,
    metadata_worker_count: 2,
    metadata_active_jobs: 0,
    metadata_queue_depth: 0,
    metadata_staged_queue_depth: 0,
    watcher_enabled: true,
    watcher_healthy: true,
    watcher_issue: null,
    scheduled_reconciliation_enabled: true,
  },
  metadata_lifecycle: {
    queued_metadata_jobs: 0,
    running_metadata_jobs: 0,
    done_metadata_jobs: 100,
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
  },
};

describe("runtimeHasActiveWork", () => {
  it("returns false for undefined", () => {
    expect(runtimeHasActiveWork(undefined)).toBe(false);
  });

  it("returns false when all counters are zero", () => {
    expect(runtimeHasActiveWork(idleRuntime)).toBe(false);
  });

  it("returns true when catalog_active_jobs > 0", () => {
    const data = { ...idleRuntime, global_runtime: { ...idleRuntime.global_runtime, catalog_active_jobs: 1 } };
    expect(runtimeHasActiveWork(data)).toBe(true);
  });

  it("returns true when catalog_queue_depth > 0", () => {
    const data = { ...idleRuntime, global_runtime: { ...idleRuntime.global_runtime, catalog_queue_depth: 3 } };
    expect(runtimeHasActiveWork(data)).toBe(true);
  });

  it("returns true when metadata_active_jobs > 0", () => {
    const data = { ...idleRuntime, global_runtime: { ...idleRuntime.global_runtime, metadata_active_jobs: 2 } };
    expect(runtimeHasActiveWork(data)).toBe(true);
  });

  it("returns true when metadata_queue_depth > 0", () => {
    const data = { ...idleRuntime, global_runtime: { ...idleRuntime.global_runtime, metadata_queue_depth: 5 } };
    expect(runtimeHasActiveWork(data)).toBe(true);
  });

  it("returns true when lifecycle queued_metadata_jobs > 0", () => {
    const data = {
      ...idleRuntime,
      metadata_lifecycle: { ...idleRuntime.metadata_lifecycle!, queued_metadata_jobs: 4 },
    };
    expect(runtimeHasActiveWork(data)).toBe(true);
  });

  it("returns true when lifecycle running_metadata_jobs > 0", () => {
    const data = {
      ...idleRuntime,
      metadata_lifecycle: { ...idleRuntime.metadata_lifecycle!, running_metadata_jobs: 1 },
    };
    expect(runtimeHasActiveWork(data)).toBe(true);
  });

  it("returns false when lifecycle is null even with active work there", () => {
    const data = { ...idleRuntime, metadata_lifecycle: null };
    expect(runtimeHasActiveWork(data)).toBe(false);
  });
});
