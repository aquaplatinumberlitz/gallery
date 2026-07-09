import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { MaintenanceRuntimeResponse } from "@/services/api";
import { fetchMaintenanceRuntime } from "@/services/api";
import { ACTIVE_POLL_INTERVAL, STABLE_POLL_INTERVAL } from "@/lib/catalog/polling";
import { runtimeHasActiveWork, useMaintenanceRuntimeQuery } from "../useMaintenanceRuntimeQuery";

vi.mock("@/services/api", () => ({ fetchMaintenanceRuntime: vi.fn() }));

let capturedRefetchInterval: ((q: { state: { data: unknown } }) => number | false) | undefined;
vi.mock("@tanstack/vue-query", async () => {
  const actual = await vi.importActual<typeof import("@tanstack/vue-query")>("@tanstack/vue-query");
  return {
    ...actual,
    useQuery: vi.fn((...args: any[]) => {
      capturedRefetchInterval = args[0].refetchInterval;
      return (actual.useQuery as any)(...args);
    }),
  };
});

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
    derivative_configured_worker_count: 3,
    derivative_worker_count: 3,
    derivative_active_jobs: 0,
    derivative_queue_depth: 0,
    derivative_failed_jobs: 0,
    derivative_skipped_jobs: 0,
    derivative_stale_running_jobs: 0,
    derivative_oldest_running_age_seconds: null,
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

const activeRuntime: MaintenanceRuntimeResponse = {
  ...idleRuntime,
  global_runtime: { ...idleRuntime.global_runtime, catalog_active_jobs: 1 },
};

function mountComposable() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { gcTime: 0, retry: false } } });
  let result!: ReturnType<typeof useMaintenanceRuntimeQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useMaintenanceRuntimeQuery();
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, queryClient, wrapper };
}

describe("useMaintenanceRuntimeQuery", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedRefetchInterval = undefined;
  });

  it("calls fetchMaintenanceRuntime on mount and returns data", async () => {
    vi.mocked(fetchMaintenanceRuntime).mockResolvedValue(idleRuntime);
    const { result } = mountComposable();
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(result.data.value).toEqual(idleRuntime);
  });

  it("uses ACTIVE_POLL_INTERVAL in refetchInterval when runtime has active work", async () => {
    vi.mocked(fetchMaintenanceRuntime).mockResolvedValue(activeRuntime);
    mountComposable();
    await vi.waitFor(() => expect(capturedRefetchInterval).toBeDefined());
    expect(capturedRefetchInterval!({ state: { data: activeRuntime } })).toBe(ACTIVE_POLL_INTERVAL);
  });

  it("uses STABLE_POLL_INTERVAL in refetchInterval when runtime is idle", async () => {
    vi.mocked(fetchMaintenanceRuntime).mockResolvedValue(idleRuntime);
    mountComposable();
    await vi.waitFor(() => expect(capturedRefetchInterval).toBeDefined());
    expect(capturedRefetchInterval!({ state: { data: idleRuntime } })).toBe(STABLE_POLL_INTERVAL);
  });
});
