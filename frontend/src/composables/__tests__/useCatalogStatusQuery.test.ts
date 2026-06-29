import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { fetchCatalogStatus } from "@/services/api";
import { useCatalogStatusQuery } from "../useCatalogStatusQuery";
import { assertStatusEnvelope, isStatusContractError } from "@/lib/catalog/contractGuard";
import { statusRefetchInterval } from "@/lib/catalog/polling";
import type { StatusResponseEnvelope } from "@/lib/catalog/status";

vi.mock("@/services/api", () => ({
  fetchCatalogStatus: vi.fn(),
}));

vi.mock("@/lib/catalog/contractGuard", () => ({
  assertStatusEnvelope: vi.fn(),
  isStatusContractError: vi.fn(),
}));

vi.mock("@/lib/catalog/polling", () => ({
  statusRefetchInterval: vi.fn(),
}));

const mockStatusEnvelope = {
  contract_version: 1,
  status: {
    contract_version: 1,
    generated_at: Date.now(),
    summary_state: "ready",
    scope: { kind: "library", library_id: 1, path: null, import_path_count: 1 },
    availability: { state: "available", available_paths: 1, total_paths: 1 },
    scan: {
      state: "complete",
      operation: null,
      trigger: null,
      active_job_id: null,
      completed_units: null,
      total_units: null,
      progress_percent: null,
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
      progress_percent: null,
      global_active_outside_scope: false,
    },
    issue_count: 0,
    issues: { availability: 0, scan: 0, metadata: 0 },
    latest_issue: null,
    last_scan_at: null,
    last_index_at: null,
  },
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
  },
  metadata_lifecycle: null,
};

function setup(libraryId: number | null | undefined, scopePath?: string | null, enabled = true) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { gcTime: 0 } } });
  let result!: ReturnType<typeof useCatalogStatusQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useCatalogStatusQuery(
          () => libraryId,
          () => scopePath ?? null,
          () => enabled,
        );
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, queryClient, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchCatalogStatus).mockResolvedValue(mockStatusEnvelope as StatusResponseEnvelope);
  vi.mocked(assertStatusEnvelope).mockReturnValue(undefined);
  vi.mocked(isStatusContractError).mockReturnValue(false);
  vi.mocked(statusRefetchInterval).mockReturnValue(0);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useCatalogStatusQuery", () => {
  it("fetches status for a library when library id is provided", async () => {
    const { result } = setup(1);
    await vi.waitFor(() => expect(result.data.value).toEqual(mockStatusEnvelope));
    expect(fetchCatalogStatus).toHaveBeenCalledWith(1, null);
  });

  it("does not fetch when library id is null", () => {
    setup(null);
    expect(fetchCatalogStatus).not.toHaveBeenCalled();
  });

  it("does not fetch when enabled is false", () => {
    setup(1, null, false);
    expect(fetchCatalogStatus).not.toHaveBeenCalled();
  });

  it("fetches with scope path when provided", async () => {
    const { result } = setup(1, "/subpath");
    await vi.waitFor(() => expect(result.data.value).toEqual(mockStatusEnvelope));
    expect(fetchCatalogStatus).toHaveBeenCalledWith(1, "/subpath");
  });

  it("has isPending true while loading", () => {
    vi.mocked(fetchCatalogStatus).mockReturnValue(new Promise(() => {}));
    const { result } = setup(1);
    expect(result.isPending.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(fetchCatalogStatus).mockRejectedValue(new Error("network error"));
    vi.mocked(isStatusContractError).mockReturnValue(true);
    const { result } = setup(1);
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.error.value).toBeTruthy();
  });

  it("sets contractError when contract guard fails", async () => {
    const contractErr = new Error("Contract validation failed");
    vi.mocked(isStatusContractError).mockReturnValue(true);
    vi.mocked(fetchCatalogStatus).mockRejectedValue(contractErr);
    const { result } = setup(1);
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    await vi.waitFor(() => expect(result.contractError.value).toBeTruthy());
  });

  it("returns null contractError for non-contract errors", async () => {
    vi.mocked(fetchCatalogStatus).mockRejectedValue(new Error("network error"));
    const { result } = setup(1);
    await vi.waitFor(() => expect(result.isError.value).toBe(true), { timeout: 5000 });
    expect(result.contractError.value).toBeNull();
  });

  it("uses path-specific query key when scope path is provided", async () => {
    const { result } = setup(1, "/subpath");
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(fetchCatalogStatus).toHaveBeenCalledWith(1, "/subpath");
  });
});
