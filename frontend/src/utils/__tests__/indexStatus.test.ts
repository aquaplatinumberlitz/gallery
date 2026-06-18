import { describe, it, expect } from "vitest";
import {
  getIndexStatusCounts,
  getGlobalIndexStatusCounts,
  getIndexStatusProgress,
  getIndexStatusProgressInfo,
  getIndexStatusRefetchInterval,
  getIndexStatusState,
  getIndexUiStatus,
  getIndexStatusPresentation,
  hasActiveIndexWork,
  hasFailedIndexWork,
  hasGlobalIndexWork,
  hasGlobalIndexWorkOutsideScope,
  hasKnownIndexUpdates,
  hasQueuedIndexWork,
  type IndexUiStatus,
} from "../indexStatus";
import type { IndexStatusResponse, IndexStatusScope } from "@/types";

function makeBaseStatus(overrides: Partial<IndexStatusResponse> = {}): IndexStatusResponse {
  return {
    path: "/root",
    total: 100,
    indexed_photos: 100,
    metadata_records: 100,
    counts: {},
    queued: 0,
    running: 0,
    done: 100,
    failed: 0,
    stale: 0,
    skipped: 0,
    oldest_queued_age_seconds: null,
    last_error: null,
    updated_at: null,
    enabled: true,
    worker_count: 2,
    active_jobs: 0,
    runtime_queue_depth: 0,
    coalesced_duplicates: 0,
    staged_path_queue_depth: 0,
    staged_path_coalesced: 0,
    staged_path_failed: 0,
    staged_path_flushes_forced: 0,
    staged_path_worker_count: 1,
    active_scan_requests: 0,
    batch_size: 50,
    staged_path_batch_size: 50,
    stage_max_wait_seconds: 5,
    ...overrides,
  };
}

function makeScopedStatus(scope: Partial<IndexStatusScope> = {}): IndexStatusScope {
  return {
    path: "/root",
    total: 100,
    indexed_photos: 100,
    metadata_records: 100,
    counts: {},
    queued: 0,
    running: 0,
    done: 100,
    failed: 0,
    stale: 0,
    skipped: 0,
    oldest_queued_age_seconds: null,
    last_error: null,
    updated_at: null,
    active_jobs: 0,
    runtime_queue_depth: 0,
    staged_path_queue_depth: 0,
    active_scan_requests: 0,
    ...scope,
  };
}

describe("getIndexStatusCounts", () => {
  it("returns zeroed counts for null/undefined status", () => {
    const expected = {
      queued: 0,
      running: 0,
      done: 0,
      failed: 0,
      stale: 0,
      skipped: 0,
      activeJobs: 0,
      runtimeQueueDepth: 0,
      stagedPathQueueDepth: 0,
      stagedPathFailed: 0,
      activeScanRequests: 0,
      activeRebuilds: 0,
      missingMetadataRecords: 0,
    };
    expect(getIndexStatusCounts(null)).toEqual(expected);
    expect(getIndexStatusCounts(undefined)).toEqual(expected);
  });

  it("reads top-level counts when no explicit scope is present", () => {
    const status = makeBaseStatus({
      queued: 1,
      running: 2,
      done: 3,
      failed: 4,
      stale: 5,
      skipped: 6,
    });
    const counts = getIndexStatusCounts(status);
    expect(counts.queued).toBe(1);
    expect(counts.running).toBe(2);
    expect(counts.done).toBe(3);
    expect(counts.failed).toBe(4);
    expect(counts.stale).toBe(5);
    expect(counts.skipped).toBe(6);
    // No explicit scope → runtime-derived counters stay 0
    expect(counts.activeJobs).toBe(0);
    expect(counts.runtimeQueueDepth).toBe(0);
    expect(counts.stagedPathQueueDepth).toBe(0);
    expect(counts.activeScanRequests).toBe(0);
    expect(counts.activeRebuilds).toBe(0);
  });

  it("computes missingMetadataRecords from indexed_photos - metadata_records when missing_metadata_records absent", () => {
    const status = makeBaseStatus({ indexed_photos: 120, metadata_records: 100 });
    expect(getIndexStatusCounts(status).missingMetadataRecords).toBe(20);
  });

  it("clamps missingMetadataRecords to zero when metadata_records exceeds indexed_photos", () => {
    const status = makeBaseStatus({ indexed_photos: 50, metadata_records: 100 });
    expect(getIndexStatusCounts(status).missingMetadataRecords).toBe(0);
  });

  it("prefers explicit missing_metadata_records on the scope when present", () => {
    const status = makeBaseStatus({
      indexed_photos: 120,
      metadata_records: 100,
      missing_metadata_records: 7,
    });
    expect(getIndexStatusCounts(status).missingMetadataRecords).toBe(7);
  });

  it("uses scope-derived runtime counters when status.scope is present", () => {
    const status = makeBaseStatus({
      scope: makeScopedStatus({
        active_jobs: 3,
        runtime_queue_depth: 4,
        staged_path_queue_depth: 5,
        active_scan_requests: 6,
        active_rebuilds: 2,
      }),
    });
    const counts = getIndexStatusCounts(status);
    expect(counts.activeJobs).toBe(3);
    expect(counts.runtimeQueueDepth).toBe(4);
    expect(counts.stagedPathQueueDepth).toBe(5);
    expect(counts.activeScanRequests).toBe(6);
    expect(counts.activeRebuilds).toBe(2);
    // scopedPathFailed is always 0 in the scoped view
    expect(counts.stagedPathFailed).toBe(0);
  });
});

describe("getGlobalIndexStatusCounts", () => {
  it("returns zeroed counts for null/undefined status", () => {
    const counts = getGlobalIndexStatusCounts(null);
    expect(counts.queued).toBe(0);
    expect(counts.activeJobs).toBe(0);
    expect(counts.activeRebuilds).toBe(0);
  });

  it("reads top-level counts and runtime fields directly", () => {
    const status = makeBaseStatus({
      queued: 1,
      running: 2,
      done: 3,
      failed: 4,
      stale: 5,
      skipped: 6,
      active_jobs: 7,
      runtime_queue_depth: 8,
      staged_path_queue_depth: 9,
      staged_path_failed: 10,
      active_scan_requests: 11,
    });
    const counts = getGlobalIndexStatusCounts(status);
    expect(counts.queued).toBe(1);
    expect(counts.done).toBe(3);
    expect(counts.activeJobs).toBe(7);
    expect(counts.runtimeQueueDepth).toBe(8);
    expect(counts.stagedPathQueueDepth).toBe(9);
    expect(counts.stagedPathFailed).toBe(10);
    expect(counts.activeScanRequests).toBe(11);
    expect(counts.activeRebuilds).toBe(0);
  });

  it("falls back to top-level runtime fields when global_runtime is missing", () => {
    const status = makeBaseStatus({
      active_jobs: 7,
      runtime_queue_depth: 8,
      staged_path_queue_depth: 9,
      staged_path_failed: 10,
      active_scan_requests: 11,
    });
    const counts = getGlobalIndexStatusCounts(status);
    expect(counts.activeJobs).toBe(7);
    expect(counts.stagedPathFailed).toBe(10);
  });

  it("prefers global_runtime when present", () => {
    const status = makeBaseStatus({
      active_jobs: 1,
      global_runtime: {
        enabled: true,
        worker_count: 2,
        active_jobs: 99,
        runtime_queue_depth: 0,
        coalesced_duplicates: 0,
        staged_path_queue_depth: 0,
        staged_path_coalesced: 0,
        staged_path_failed: 0,
        staged_path_flushes_forced: 0,
        staged_path_worker_count: 1,
        active_scan_requests: 0,
        batch_size: 50,
        staged_path_batch_size: 50,
        stage_max_wait_seconds: 5,
      },
    });
    expect(getGlobalIndexStatusCounts(status).activeJobs).toBe(99);
  });

  it("computes missingMetadataRecords from indexed_photos - metadata_records", () => {
    const status = makeBaseStatus({ indexed_photos: 150, metadata_records: 100 });
    expect(getGlobalIndexStatusCounts(status).missingMetadataRecords).toBe(50);
  });
});

describe("hasFailedIndexWork", () => {
  it("returns false for null status", () => {
    expect(hasFailedIndexWork(null)).toBe(false);
  });

  it("returns true when scoped failed > 0", () => {
    expect(hasFailedIndexWork(makeBaseStatus({ failed: 1 }))).toBe(true);
  });

  it("returns true when last_error is set even without failed count", () => {
    expect(
      hasFailedIndexWork(
        makeBaseStatus({
          failed: 0,
          last_error: { path: "/x", message: "boom", updated_at: 1 },
        }),
      ),
    ).toBe(true);
  });

  it("returns false when failed=0 and last_error is null", () => {
    expect(hasFailedIndexWork(makeBaseStatus({ failed: 0, last_error: null }))).toBe(false);
  });
});

describe("hasActiveIndexWork", () => {
  it("returns true when running > 0", () => {
    expect(hasActiveIndexWork(makeBaseStatus({ running: 1 }))).toBe(true);
  });

  it("returns true when activeJobs > 0 via explicit scope", () => {
    const status = makeBaseStatus({ scope: makeScopedStatus({ active_jobs: 1 }) });
    expect(hasActiveIndexWork(status)).toBe(true);
  });

  it("returns true when activeScanRequests > 0 via explicit scope", () => {
    const status = makeBaseStatus({ scope: makeScopedStatus({ active_scan_requests: 1 }) });
    expect(hasActiveIndexWork(status)).toBe(true);
  });

  it("returns true when activeRebuilds > 0 via explicit scope", () => {
    const status = makeBaseStatus({ scope: makeScopedStatus({ active_rebuilds: 1 }) });
    expect(hasActiveIndexWork(status)).toBe(true);
  });

  it("returns false for an idle status with no explicit scope", () => {
    expect(hasActiveIndexWork(makeBaseStatus())).toBe(false);
  });
});

describe("hasQueuedIndexWork", () => {
  it("returns true when queued > 0", () => {
    expect(hasQueuedIndexWork(makeBaseStatus({ queued: 1 }))).toBe(true);
  });

  it("returns true when runtimeQueueDepth > 0 via explicit scope", () => {
    const status = makeBaseStatus({ scope: makeScopedStatus({ runtime_queue_depth: 1 }) });
    expect(hasQueuedIndexWork(status)).toBe(true);
  });

  it("returns true when stagedPathQueueDepth > 0 via explicit scope", () => {
    const status = makeBaseStatus({ scope: makeScopedStatus({ staged_path_queue_depth: 1 }) });
    expect(hasQueuedIndexWork(status)).toBe(true);
  });

  it("returns false for an idle status", () => {
    expect(hasQueuedIndexWork(makeBaseStatus())).toBe(false);
  });
});

describe("hasKnownIndexUpdates", () => {
  it("returns true when stale > 0", () => {
    expect(hasKnownIndexUpdates(makeBaseStatus({ stale: 1 }))).toBe(true);
  });

  it("returns true when missingMetadataRecords > 0", () => {
    expect(hasKnownIndexUpdates(makeBaseStatus({ indexed_photos: 120, metadata_records: 100 }))).toBe(true);
  });

  it("returns false when stale=0 and metadata is complete", () => {
    expect(hasKnownIndexUpdates(makeBaseStatus({ stale: 0, indexed_photos: 100, metadata_records: 100 }))).toBe(false);
  });
});

describe("hasGlobalIndexWork", () => {
  it("returns true when global active_jobs > 0", () => {
    expect(hasGlobalIndexWork(makeBaseStatus({ active_jobs: 1 }))).toBe(true);
  });

  it("returns true when global runtime_queue_depth > 0", () => {
    expect(hasGlobalIndexWork(makeBaseStatus({ runtime_queue_depth: 1 }))).toBe(true);
  });

  it("returns true when staged_path_queue_depth > 0", () => {
    expect(hasGlobalIndexWork(makeBaseStatus({ staged_path_queue_depth: 1 }))).toBe(true);
  });

  it("returns true when active_scan_requests > 0", () => {
    expect(hasGlobalIndexWork(makeBaseStatus({ active_scan_requests: 1 }))).toBe(true);
  });

  it("returns false for an idle status", () => {
    expect(hasGlobalIndexWork(makeBaseStatus())).toBe(false);
  });
});

describe("hasGlobalIndexWorkOutsideScope", () => {
  it("returns true when global work exists but scope has no active or queued work", () => {
    const status = makeBaseStatus({
      active_jobs: 1, // global work
      // no scope, no running, no queued
    });
    expect(hasGlobalIndexWorkOutsideScope(status)).toBe(true);
  });

  it("returns false when both global and scoped work exist (scoped work covers it)", () => {
    const status = makeBaseStatus({
      active_jobs: 1,
      running: 1, // scoped running
    });
    expect(hasGlobalIndexWorkOutsideScope(status)).toBe(false);
  });

  it("returns false when no global work is happening", () => {
    expect(hasGlobalIndexWorkOutsideScope(makeBaseStatus())).toBe(false);
  });

  it("returns false when only scoped work exists and no global work", () => {
    const status = makeBaseStatus({ scope: makeScopedStatus({ running: 1 }) });
    expect(hasGlobalIndexWorkOutsideScope(status)).toBe(false);
  });
});

describe("getIndexUiStatus", () => {
  it("returns 'error' when isError is true regardless of other state", () => {
    expect(getIndexUiStatus(null, { hasPath: true, isError: true })).toBe("error");
  });

  it("returns 'unknown' when there is no path", () => {
    expect(getIndexUiStatus(makeBaseStatus(), { hasPath: false })).toBe("unknown");
  });

  it("returns 'unknown' when isLoading is true", () => {
    expect(getIndexUiStatus(makeBaseStatus(), { hasPath: true, isLoading: true })).toBe("unknown");
  });

  it("returns 'unknown' when status is null", () => {
    expect(getIndexUiStatus(null, { hasPath: true })).toBe("unknown");
  });

  it("returns 'warning' when indexer is disabled", () => {
    expect(getIndexUiStatus(makeBaseStatus({ enabled: false }), { hasPath: true })).toBe("warning");
  });

  it("returns 'error' when there is failed index work", () => {
    expect(getIndexUiStatus(makeBaseStatus({ failed: 1 }), { hasPath: true })).toBe("error");
  });

  it("returns 'indexing' when there is active or queued work", () => {
    expect(getIndexUiStatus(makeBaseStatus({ running: 1 }), { hasPath: true })).toBe("indexing");
    expect(getIndexUiStatus(makeBaseStatus({ queued: 1 }), { hasPath: true })).toBe("indexing");
  });

  it("returns 'stale' when there are known updates pending but no active work", () => {
    expect(getIndexUiStatus(makeBaseStatus({ stale: 1 }), { hasPath: true })).toBe("stale");
  });

  it("returns 'ready' when nothing is pending and indexer is enabled", () => {
    expect(getIndexUiStatus(makeBaseStatus(), { hasPath: true })).toBe("ready");
  });
});

describe("getIndexStatusPresentation", () => {
  const cases: Array<{
    status: IndexUiStatus;
    label: string;
    tone: string;
    pulse: boolean;
    buildStatus: () => IndexStatusResponse | null;
    opts: { hasPath: boolean; isLoading?: boolean; isError?: boolean };
  }> = [
    {
      status: "unknown",
      label: "Unknown",
      tone: "gray",
      pulse: false,
      buildStatus: () => null,
      opts: { hasPath: true },
    },
    {
      status: "ready",
      label: "Ready",
      tone: "green",
      pulse: false,
      buildStatus: () => makeBaseStatus(),
      opts: { hasPath: true },
    },
    {
      status: "indexing",
      label: "Updating",
      tone: "yellow",
      pulse: true,
      buildStatus: () => makeBaseStatus({ running: 1 }),
      opts: { hasPath: true },
    },
    {
      status: "stale",
      label: "Needs update",
      tone: "yellow",
      pulse: false,
      buildStatus: () => makeBaseStatus({ stale: 1 }),
      opts: { hasPath: true },
    },
    {
      status: "warning",
      label: "Unavailable",
      tone: "gray",
      pulse: false,
      buildStatus: () => makeBaseStatus({ enabled: false }),
      opts: { hasPath: true },
    },
    {
      status: "error",
      label: "Error",
      tone: "red",
      pulse: false,
      buildStatus: () => makeBaseStatus({ failed: 1 }),
      opts: { hasPath: true, isError: true },
    },
  ];

  for (const c of cases) {
    it(`returns presentation for ${c.status}`, () => {
      const presentation = getIndexStatusPresentation(c.buildStatus(), c.opts);
      expect(presentation.status).toBe(c.status);
      expect(presentation.label).toBe(c.label);
      expect(presentation.tone).toBe(c.tone);
      expect(presentation.showPulse).toBe(c.pulse);
    });
  }
});

describe("getIndexStatusState", () => {
  it("returns 'disabled' when hasPath is false", () => {
    expect(getIndexStatusState(makeBaseStatus(), { hasPath: false })).toBe("disabled");
  });

  it("returns 'unavailable' when isUnavailable is true", () => {
    expect(getIndexStatusState(makeBaseStatus(), { hasPath: true, isUnavailable: true })).toBe("unavailable");
  });

  it("returns 'idle' when status is null", () => {
    expect(getIndexStatusState(null, { hasPath: true })).toBe("idle");
  });

  it("returns 'disabled' when indexer is disabled", () => {
    expect(getIndexStatusState(makeBaseStatus({ enabled: false }), { hasPath: true })).toBe("disabled");
  });

  it("returns 'failed' when there is failed work", () => {
    expect(getIndexStatusState(makeBaseStatus({ failed: 1 }), { hasPath: true })).toBe("failed");
  });

  it("returns 'active' when there is active work", () => {
    expect(getIndexStatusState(makeBaseStatus({ running: 1 }), { hasPath: true })).toBe("active");
  });

  it("returns 'queued' when there is queued work but no active work", () => {
    expect(getIndexStatusState(makeBaseStatus({ queued: 1 }), { hasPath: true })).toBe("queued");
  });

  it("returns 'idle' when nothing is pending", () => {
    expect(getIndexStatusState(makeBaseStatus(), { hasPath: true })).toBe("idle");
  });
});

describe("getIndexStatusRefetchInterval", () => {
  it("returns 60s when unavailable", () => {
    expect(getIndexStatusRefetchInterval(makeBaseStatus(), true)).toBe(60_000);
  });

  it("returns 60s when status is null", () => {
    expect(getIndexStatusRefetchInterval(null)).toBe(60_000);
  });

  it("returns 2.5s when there is active scoped work", () => {
    expect(getIndexStatusRefetchInterval(makeBaseStatus({ running: 1 }))).toBe(2_500);
  });

  it("returns 2.5s when there is queued scoped work", () => {
    expect(getIndexStatusRefetchInterval(makeBaseStatus({ queued: 1 }))).toBe(2_500);
  });

  it("returns 2.5s when there is only global work outside scope", () => {
    expect(getIndexStatusRefetchInterval(makeBaseStatus({ active_jobs: 1 }))).toBe(2_500);
  });

  it("returns 60s when idle", () => {
    expect(getIndexStatusRefetchInterval(makeBaseStatus())).toBe(60_000);
  });
});

describe("getIndexStatusProgress", () => {
  it("returns null when total is zero", () => {
    expect(getIndexStatusProgress(makeBaseStatus({ queued: 0, running: 0, done: 0, failed: 0, stale: 0, skipped: 0 }))).toBeNull();
  });

  it("returns null for null status", () => {
    expect(getIndexStatusProgress(null)).toBeNull();
  });

  it("returns percentage of done vs total", () => {
    const status = makeBaseStatus({ queued: 0, running: 0, done: 75, failed: 0, stale: 0, skipped: 25 });
    expect(getIndexStatusProgress(status)).toBe(75);
  });

  it("clamps the percentage to 0-100", () => {
    const status = makeBaseStatus({ queued: 0, running: 0, done: 200, failed: 0, stale: 0, skipped: 0 });
    expect(getIndexStatusProgress(status)).toBe(100);
  });
});

describe("getIndexStatusProgressInfo", () => {
  it("returns zeroed info for null status with null total and percent", () => {
    const info = getIndexStatusProgressInfo(null);
    expect(info.indexed).toBe(0);
    expect(info.pending).toBe(0);
    expect(info.total).toBeNull();
    expect(info.percent).toBeNull();
  });

  it("uses status.total when it is greater than zero", () => {
    const status = makeBaseStatus({ total: 200, done: 50 });
    const info = getIndexStatusProgressInfo(status);
    expect(info.total).toBe(200);
    expect(info.percent).toBe(25);
  });

  it("falls back to sum of counts when status.total is 0", () => {
    const status = makeBaseStatus({ total: 0, queued: 10, running: 5, done: 50, failed: 5, stale: 5, skipped: 25 });
    const info = getIndexStatusProgressInfo(status);
    expect(info.total).toBe(100);
    expect(info.percent).toBe(50);
  });

  it("returns null total when both status.total and fallback sum are 0", () => {
    const status = makeBaseStatus({ total: 0, queued: 0, running: 0, done: 0, failed: 0, stale: 0, skipped: 0 });
    const info = getIndexStatusProgressInfo(status);
    expect(info.total).toBeNull();
    expect(info.percent).toBeNull();
  });

  it("computes pending as the sum of pending counters", () => {
    const status = makeBaseStatus({
      queued: 1,
      running: 2,
      stale: 3,
      active_jobs: 4,
      active_scan_requests: 5,
      // scope-derived counters stay 0 without explicit scope
    });
    const info = getIndexStatusProgressInfo(status);
    // pending = queued + running + stale + runtimeQueueDepth + stagedPathQueueDepth + activeJobs + activeScanRequests
    // For top-level status without scope, runtime/staged counters stay 0
    expect(info.pending).toBe(1 + 2 + 3 + 0 + 0 + 0 + 0);
  });

  it("includes scope-derived counters in pending when scope is present", () => {
    const status = makeBaseStatus({
      scope: makeScopedStatus({
        queued: 1,
        running: 2,
        stale: 3,
        runtime_queue_depth: 4,
        staged_path_queue_depth: 5,
        active_jobs: 6,
        active_scan_requests: 7,
      }),
    });
    const info = getIndexStatusProgressInfo(status);
    expect(info.pending).toBe(1 + 2 + 3 + 4 + 5 + 6 + 7);
  });

  it("clamps percentage to 0-100 when done exceeds total", () => {
    const status = makeBaseStatus({ total: 100, done: 150 });
    expect(getIndexStatusProgressInfo(status).percent).toBe(100);
  });
});
