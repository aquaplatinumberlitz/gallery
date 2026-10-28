import { QueryClient, QueryObserver } from "@tanstack/vue-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ACTIVE_POLL_INTERVAL,
  POLL_BACKOFF_FACTOR,
  STABLE_POLL_INTERVAL,
  activePollInterval,
  backoffInterval,
  isUnifiedStatusActive,
  observeFetchDuration,
  statusRefetchInterval,
  type PolledQuery,
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
    expect(isUnifiedStatusActive(makeStatus({ scan: { ...makeStatus().scan, state: "queued" } }))).toBe(true);
  });

  it("returns true when scan.state is scanning", () => {
    expect(isUnifiedStatusActive(makeStatus({ scan: { ...makeStatus().scan, state: "scanning" } }))).toBe(true);
  });

  it("returns true when metadata.state is queued", () => {
    expect(isUnifiedStatusActive(makeStatus({ metadata: { ...makeStatus().metadata, state: "queued" } }))).toBe(true);
  });

  it("returns true when metadata.state is indexing", () => {
    expect(isUnifiedStatusActive(makeStatus({ metadata: { ...makeStatus().metadata, state: "indexing" } }))).toBe(true);
  });

  it("returns false when scan failed and metadata is complete", () => {
    expect(isUnifiedStatusActive(makeStatus({ scan: { ...makeStatus().scan, state: "failed" } }))).toBe(false);
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

function fakeQuery(fetchStatus?: "fetching" | "paused" | "idle"): PolledQuery & { state: { fetchStatus?: string } } {
  return { state: { fetchStatus } };
}

describe("backoffInterval", () => {
  it("keeps the active interval when no fetch was observed or the duration is unusable", () => {
    expect(backoffInterval(null)).toBe(ACTIVE_POLL_INTERVAL);
    expect(backoffInterval(undefined)).toBe(ACTIVE_POLL_INTERVAL);
    expect(backoffInterval(0)).toBe(ACTIVE_POLL_INTERVAL);
    expect(backoffInterval(-50)).toBe(ACTIVE_POLL_INTERVAL);
    expect(backoffInterval(Number.NaN)).toBe(ACTIVE_POLL_INTERVAL);
    expect(backoffInterval(Number.POSITIVE_INFINITY)).toBe(ACTIVE_POLL_INTERVAL);
  });

  it("does not slow down fast endpoints", () => {
    expect(backoffInterval(40)).toBe(ACTIVE_POLL_INTERVAL);
    expect(backoffInterval(ACTIVE_POLL_INTERVAL / POLL_BACKOFF_FACTOR)).toBe(ACTIVE_POLL_INTERVAL);
  });

  it("never drops below twice the last fetch duration", () => {
    expect(backoffInterval(3_000)).toBe(6_000);
    expect(backoffInterval(12_500)).toBe(25_000);
    for (const duration of [1_251, 2_000, 5_000, 20_000, 29_999]) {
      expect(backoffInterval(duration)).toBeGreaterThanOrEqual(POLL_BACKOFF_FACTOR * duration);
    }
  });

  it("caps at the stable interval", () => {
    expect(backoffInterval(STABLE_POLL_INTERVAL / 2)).toBe(STABLE_POLL_INTERVAL);
    expect(backoffInterval(STABLE_POLL_INTERVAL)).toBe(STABLE_POLL_INTERVAL);
    expect(backoffInterval(10 * STABLE_POLL_INTERVAL)).toBe(STABLE_POLL_INTERVAL);
  });
});

describe("observeFetchDuration", () => {
  it("measures the time between the fetching and idle invocations", () => {
    const query = fakeQuery();
    expect(observeFetchDuration(query, 100)).toBeNull();

    query.state.fetchStatus = "fetching";
    expect(observeFetchDuration(query, 1_000)).toBeNull();
    expect(observeFetchDuration(query, 2_500)).toBeNull();

    query.state.fetchStatus = "idle";
    expect(observeFetchDuration(query, 4_200)).toBe(3_200);
    expect(observeFetchDuration(query, 9_000)).toBe(3_200);
  });

  it("keeps the previous duration until the next fetch completes", () => {
    const query = fakeQuery("fetching");
    observeFetchDuration(query, 0);
    query.state.fetchStatus = "idle";
    expect(observeFetchDuration(query, 800)).toBe(800);

    query.state.fetchStatus = "fetching";
    expect(observeFetchDuration(query, 5_000)).toBe(800);
    query.state.fetchStatus = "idle";
    expect(observeFetchDuration(query, 5_100)).toBe(100);
  });

  it("tracks each query separately", () => {
    const slow = fakeQuery("fetching");
    const fast = fakeQuery("fetching");
    observeFetchDuration(slow, 0);
    observeFetchDuration(fast, 0);
    slow.state.fetchStatus = "idle";
    fast.state.fetchStatus = "idle";
    expect(observeFetchDuration(slow, 9_000)).toBe(9_000);
    expect(observeFetchDuration(fast, 50)).toBe(50);
  });

  it("ignores a paused fetch and queries without a fetch status", () => {
    const paused = fakeQuery("fetching");
    observeFetchDuration(paused, 0);
    paused.state.fetchStatus = "paused";
    expect(observeFetchDuration(paused, 10_000)).toBeNull();
    expect(observeFetchDuration(undefined, 1)).toBeNull();
    expect(observeFetchDuration(null, 1)).toBeNull();
    expect(observeFetchDuration({}, 1)).toBeNull();
  });
});

describe("activePollInterval", () => {
  it("is the plain active interval without a query or before any fetch finished", () => {
    expect(activePollInterval()).toBe(ACTIVE_POLL_INTERVAL);
    expect(activePollInterval(fakeQuery("fetching"), 0)).toBe(ACTIVE_POLL_INTERVAL);
  });

  it("backs off after a slow fetch and recovers after a fast one", () => {
    const query = fakeQuery("fetching");
    activePollInterval(query, 0);
    query.state.fetchStatus = "idle";
    expect(activePollInterval(query, 4_000)).toBe(8_000);

    query.state.fetchStatus = "fetching";
    activePollInterval(query, 12_000);
    query.state.fetchStatus = "idle";
    expect(activePollInterval(query, 12_050)).toBe(ACTIVE_POLL_INTERVAL);
  });
});

describe("statusRefetchInterval backoff", () => {
  it("uses the backed-off interval while work is active and keeps the stable interval when settled", () => {
    const slow = fakeQuery("fetching");
    activePollInterval(slow, 0);
    slow.state.fetchStatus = "idle";
    activePollInterval(slow, 6_000);
    const queued = makeStatus({ scan: { ...makeStatus().scan, state: "queued" } });
    expect(statusRefetchInterval(queued, true, slow)).toBe(12_000);
    expect(statusRefetchInterval(makeStatus(), true, slow)).toBe(STABLE_POLL_INTERVAL);
    expect(statusRefetchInterval(queued, false, slow)).toBe(false);
    expect(statusRefetchInterval(undefined, true, slow)).toBe(false);
  });
});

describe("refetchInterval wired to a real TanStack query", () => {
  let clock = 0;

  beforeEach(() => {
    vi.useFakeTimers();
    clock = 0;
    vi.spyOn(performance, "now").mockImplementation(() => clock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("never schedules the next active poll sooner than twice the previous fetch took", async () => {
    const client = new QueryClient();
    const fetchDurations = [4_000, 6_000, 100];
    let call = 0;
    const intervals: Array<number | false> = [];
    const observer = new QueryObserver(client, {
      queryKey: ["polling-backoff"],
      queryFn: async () => {
        const duration = fetchDurations[Math.min(call, fetchDurations.length - 1)];
        call += 1;
        await new Promise<void>((resolve) =>
          setTimeout(() => {
            clock += duration;
            resolve();
          }, duration),
        );
        return { call };
      },
      refetchInterval: (query) => {
        const interval = statusRefetchInterval(
          makeStatus({ scan: { ...makeStatus().scan, state: "scanning" } }),
          true,
          query,
        );
        intervals.push(interval);
        return interval;
      },
    });
    const unsubscribe = observer.subscribe(() => undefined);

    await vi.advanceTimersByTimeAsync(4_000);
    expect(call).toBe(1);
    expect(intervals.at(-1)).toBe(8_000);

    await vi.advanceTimersByTimeAsync(8_000 - 1);
    expect(call).toBe(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(call).toBe(2);

    await vi.advanceTimersByTimeAsync(6_000);
    expect(intervals.at(-1)).toBe(12_000);

    await vi.advanceTimersByTimeAsync(12_000);
    expect(call).toBe(3);
    await vi.advanceTimersByTimeAsync(100);
    expect(intervals.at(-1)).toBe(ACTIVE_POLL_INTERVAL);

    unsubscribe();
    client.clear();
  });
});
