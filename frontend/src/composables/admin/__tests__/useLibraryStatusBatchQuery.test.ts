import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { fetchLibraryStatusBatch } from "@/services/api";
import { useLibraryStatusBatchQuery } from "../useLibraryStatusBatchQuery";
import { assertLibraryStatusBatch, isStatusContractError } from "@/lib/catalog/contractGuard";
import type { LibraryStatusBatchResponse } from "@/lib/catalog/status";

vi.mock("@/services/api", () => ({
  fetchLibraryStatusBatch: vi.fn(),
}));

vi.mock("@/lib/catalog/contractGuard", () => ({
  assertLibraryStatusBatch: vi.fn(),
  isStatusContractError: vi.fn(),
}));

vi.mock("@/lib/catalog/polling", () => ({
  ACTIVE_POLL_INTERVAL: 2000,
  STABLE_POLL_INTERVAL: 10000,
  isUnifiedStatusActive: vi.fn(() => false),
}));

const MOCK_NOW = 1_000_000;
const makeMockBatchResponse = (overrides?: Partial<LibraryStatusBatchResponse>): LibraryStatusBatchResponse => ({
  contract_version: 1 as const,
  generated_at: MOCK_NOW,
  items: [
    {
      library_id: 1,
      status: {
        contract_version: 1 as const,
        generated_at: MOCK_NOW,
        summary_state: "ready" as const,
        scope: { kind: "library" as const, library_id: 1, path: null, import_path_count: 1 },
        availability: { state: "available" as const, available_paths: 0, total_paths: 0 },
        scan: {
          state: "complete" as const,
          operation: null,
          trigger: null,
          active_job_id: null,
          completed_units: null,
          total_units: null,
          progress_percent: null,
        },
        metadata: {
          state: "complete" as const,
          total_assets: null,
          ready_assets: null,
          not_ready_assets: null,
          queued_assets: null,
          running_assets: null,
          stale_assets: null,
          idle_pending_assets: null,
          failed_assets: null,
          progress_percent: null,
          global_active_outside_scope: false,
        },
        issue_count: 0,
        issues: { availability: 0, scan: 0, metadata: 0 },
        latest_issue: null,
        last_scan_at: null,
        last_index_at: null,
      },
    },
  ],
  global_runtime: {
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
    scheduled_reconciliation_enabled: false,
    derivative_configured_worker_count: 3,
    derivative_worker_count: 3,
    derivative_active_jobs: 0,
    derivative_queue_depth: 0,
    derivative_failed_jobs: 0,
    derivative_skipped_jobs: 0,
    derivative_stale_running_jobs: 0,
    derivative_oldest_running_age_seconds: null,
    derivative_reconcile_enabled: true,
    derivative_reconcile_running: false,
    derivative_last_reconcile_started_at: null,
    derivative_last_reconcile_completed_at: null,
    derivative_last_reconcile_status: null,
    derivative_last_reconcile_created_jobs: 0,
  },
  metadata_lifecycle: null,
  ...overrides,
});

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { gcTime: 0 } } });
  let result!: ReturnType<typeof useLibraryStatusBatchQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useLibraryStatusBatchQuery();
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchLibraryStatusBatch).mockResolvedValue(makeMockBatchResponse());
  vi.mocked(assertLibraryStatusBatch).mockReturnValue(undefined);
  vi.mocked(isStatusContractError).mockReturnValue(false);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useLibraryStatusBatchQuery", () => {
  it("fetches batch status on mount", async () => {
    const { result } = setup();
    await vi.waitFor(() => expect(result.data.value).toEqual(makeMockBatchResponse()));
    expect(fetchLibraryStatusBatch).toHaveBeenCalled();
  });

  it("builds statusByLibrary map from response", async () => {
    const { result } = setup();
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(result.statusByLibrary.value.has(1)).toBe(true);
    expect(result.statusByLibrary.value.get(1)?.summary_state).toBe("ready");
  });

  it("has isPending true while loading", () => {
    vi.mocked(fetchLibraryStatusBatch).mockReturnValue(new Promise(() => {}));
    const { result } = setup();
    expect(result.isPending.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(fetchLibraryStatusBatch).mockRejectedValue(new Error("network error"));
    vi.mocked(isStatusContractError).mockReturnValue(true);
    const { result } = setup();
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.error.value).toBeTruthy();
  });

  it("sets contractError on contract failure", async () => {
    const contractErr = new Error("contract error");
    vi.mocked(fetchLibraryStatusBatch).mockRejectedValue(contractErr);
    vi.mocked(isStatusContractError).mockReturnValue(true);
    const { result } = setup();
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.contractError.value).toBeTruthy();
  });

  it("returns null contractError for non-contract errors", async () => {
    vi.mocked(fetchLibraryStatusBatch).mockRejectedValue(new Error("network error"));
    const { result } = setup();
    await vi.waitFor(() => expect(result.isError.value).toBe(true), { timeout: 5000 });
    expect(result.contractError.value).toBeNull();
  });
});
