import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import MaintenancePage from "../MaintenancePage.vue";

let mockFileHealthData: Record<string, unknown> | null = { run: null };
let mockFileHealthIsPending = false;
let mockRuntimeData: Record<string, unknown> | null = null;
let mockRuntimeIsPending = false;
let mockJobsData: unknown[] = [];
let mockGlobalSummaryData: unknown[] | null = null;

vi.mock("@/composables/admin/useFileHealthQuery", () => ({
  useFileHealthQuery: () => ({
    data: { value: mockFileHealthData },
    isPending: { value: mockFileHealthIsPending },
  }),
  useFileHealthMutation: () => ({
    isPending: { value: false },
    mutateAsync: vi.fn(),
  }),
}));

vi.mock("@/composables/admin/useMaintenanceRuntimeQuery", () => ({
  useMaintenanceRuntimeQuery: () => ({
    data: { value: mockRuntimeData },
    isPending: { value: mockRuntimeIsPending },
  }),
}));

vi.mock("@tanstack/vue-query", async () => {
  const actual = await vi.importActual<typeof import("@tanstack/vue-query")>("@tanstack/vue-query");
  return {
    ...actual,
    useQuery: vi.fn((opts: { queryKey: string[] }) => {
      if (opts.queryKey[0] === "jobs") {
        return { data: { value: mockJobsData }, isPending: { value: false }, refetch: vi.fn() };
      }
      if (opts.queryKey[0] === "generated-images") {
        return { data: { value: mockGlobalSummaryData }, isPending: { value: false }, refetch: vi.fn() };
      }
      return { data: { value: null }, isPending: { value: false }, refetch: vi.fn() };
    }),
  };
});

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return {
    ...actual,
    fetchJobs: vi.fn(),
    fetchLibraries: vi.fn().mockResolvedValue([]),
    fetchGeneratedImagesStatus: vi.fn(),
  };
});

vi.mock("@/composables/useToast", () => ({
  useToast: () => ({ error: vi.fn() }),
}));

vi.mock("../dialogs/GeneratedImagesClearDialog.vue", () => ({
  default: { template: "<div class='clear-dialog' />" },
}));

vi.mock("../dialogs/GeneratedImagesRebuildDialog.vue", () => ({
  default: { template: "<div class='rebuild-dialog' />" },
}));

function mountSubject() {
  setActivePinia(createPinia());
  const queryClient = createIsolatedQueryClient();
  return mount(MaintenancePage, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
      stubs: {
        Button: { template: "<button v-bind='$attrs'><slot /></button>" },
        Skeleton: { template: "<div data-testid='skeleton' />" },
        Separator: { template: "<hr />" },
        Tooltip: { template: "<span><slot /></span>" },
        TooltipContent: { template: "<span><slot /></span>" },
        TooltipTrigger: { template: "<span><slot /></span>" },
      },
    },
  });
}

describe("MaintenancePage", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    mockFileHealthData = { run: null };
    mockFileHealthIsPending = false;
    mockRuntimeData = null;
    mockRuntimeIsPending = false;
    mockJobsData = [];
    mockGlobalSummaryData = null;
  });

  it("renders System services", () => {
    mockRuntimeData = {
      global_runtime: {
        catalog_worker_count: 1,
        catalog_active_jobs: 0,
        catalog_queue_depth: 0,
        metadata_worker_count: 2,
        metadata_active_jobs: 1,
        metadata_queue_depth: 3,
        metadata_staged_queue_depth: 0,
        watcher_enabled: true,
        watcher_healthy: true,
        watcher_issue: null,
        scheduled_reconciliation_enabled: true,
      },
      metadata_lifecycle: null,
    };
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("System services");
  });

  it("renders watcher healthy and latest issue", () => {
    mockRuntimeData = {
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
      metadata_lifecycle: null,
    };
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Watching for changes");
    expect(wrapper.text()).toContain("Healthy");
  });

  it("renders watcher unhealthy with issue", () => {
    mockRuntimeData = {
      global_runtime: {
        catalog_worker_count: 1,
        catalog_active_jobs: 0,
        catalog_queue_depth: 0,
        metadata_worker_count: 2,
        metadata_active_jobs: 0,
        metadata_queue_depth: 0,
        metadata_staged_queue_depth: 0,
        watcher_enabled: true,
        watcher_healthy: false,
        watcher_issue: "Something broke",
        scheduled_reconciliation_enabled: true,
      },
      metadata_lifecycle: null,
    };
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Unhealthy");
    expect(wrapper.text()).toContain("Something broke");
  });

  it("renders scheduled refresh", () => {
    mockRuntimeData = {
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
        scheduled_reconciliation_enabled: false,
      },
      metadata_lifecycle: null,
    };
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Scheduled refresh");
    expect(wrapper.text()).toContain("Off");
  });

  it("renders catalog and metadata worker/job counts", () => {
    mockRuntimeData = {
      global_runtime: {
        catalog_worker_count: 3,
        catalog_active_jobs: 1,
        catalog_queue_depth: 5,
        metadata_worker_count: 4,
        metadata_active_jobs: 2,
        metadata_queue_depth: 10,
        metadata_staged_queue_depth: 7,
        watcher_enabled: true,
        watcher_healthy: true,
        watcher_issue: null,
        scheduled_reconciliation_enabled: true,
      },
      metadata_lifecycle: null,
    };
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Catalog workers");
    expect(wrapper.text()).toContain("3");
    expect(wrapper.text()).toContain("Catalog active jobs");
    expect(wrapper.text()).toContain("1");
    expect(wrapper.text()).toContain("Catalog queue depth");
    expect(wrapper.text()).toContain("5");
    expect(wrapper.text()).toContain("Metadata workers");
    expect(wrapper.text()).toContain("4");
    expect(wrapper.text()).toContain("Metadata active jobs");
    expect(wrapper.text()).toContain("2");
    expect(wrapper.text()).toContain("Metadata queue depth");
    expect(wrapper.text()).toContain("10");
    expect(wrapper.text()).toContain("Metadata staged queue depth");
    expect(wrapper.text()).toContain("7");
  });

  it("renders Metadata jobs", () => {
    mockRuntimeData = {
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
        queued_metadata_jobs: 2,
        running_metadata_jobs: 1,
        failed_metadata_jobs: 3,
        stale_metadata_jobs: 5,
        skipped_metadata_jobs: 1,
        done_metadata_jobs: 100,
        done_jobs_with_pending_assets: 0,
        metadata_jobs_without_matching_assets: 1,
        assets_done_but_metadata_missing_or_stale: 4,
        repairable_metadata_assets: 2,
        metadata_worker_alive: true,
        metadata_worker_last_claimed_at: null,
        metadata_worker_last_completed_at: null,
        current_image_metadata_with_pending_assets: 0,
        oldest_queued_metadata_job_age: 300,
      },
    };
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Metadata jobs");
    expect(wrapper.text()).toContain("Queued");
    expect(wrapper.text()).toContain("2");
    expect(wrapper.text()).toContain("Running");
    expect(wrapper.text()).toContain("1");
    expect(wrapper.text()).toContain("Failed jobs");
    expect(wrapper.text()).toContain("3");
    expect(wrapper.text()).toContain("Old or missing metadata");
    expect(wrapper.text()).toContain("9");
    expect(wrapper.text()).toContain("Repairable");
    expect(wrapper.text()).toContain("2");
    expect(wrapper.text()).toContain("Jobs for missing files");
    expect(wrapper.text()).toContain("1");
  });
});
