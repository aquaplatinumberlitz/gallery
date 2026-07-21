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
    useQuery: vi.fn((opts: { queryKey: string[] | { value: string[] } }) => {
      const queryKey = "value" in opts.queryKey ? opts.queryKey.value : opts.queryKey;
      if (queryKey[0] === "jobs") {
        return {
          data: { value: mockJobsData },
          isPending: { value: false },
          isFetching: { value: false },
          refetch: vi.fn(),
        };
      }
      if (queryKey[0] === "generated-images") {
        return {
          data: { value: mockGlobalSummaryData },
          isPending: { value: false },
          isFetching: { value: false },
          refetch: vi.fn(),
        };
      }
      return {
        data: { value: null },
        isPending: { value: false },
        isFetching: { value: false },
        refetch: vi.fn(),
      };
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
        ButtonLink: { template: "<a><slot /></a>" },
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

  it("renders File catalog diagnostics", () => {
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
    expect(wrapper.text()).toContain("File catalog");
    expect(wrapper.text()).toContain("Tracks which source files exist in registered libraries.");
  });

  it("combines image cache coverage and queue diagnostics", () => {
    mockRuntimeData = {
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
        scheduled_reconciliation_enabled: true,
        derivative_configured_worker_count: 3,
        derivative_worker_count: 2,
        derivative_active_jobs: 1,
        derivative_queue_depth: 4,
        derivative_failed_jobs: 2,
        derivative_skipped_jobs: 1,
        derivative_stale_running_jobs: 1,
        derivative_oldest_running_age_seconds: 30,
      },
      metadata_lifecycle: null,
    };

    const wrapper = mountSubject();
    const imageCache = wrapper
      .findAll('[data-slot="card"]')
      .find((card) => card.text().includes("Coverage and queue health for cached thumbnails and previews."));
    expect(imageCache?.text()).toContain("Coverage");
    expect(imageCache?.text()).toContain("Queue health");
    expect(imageCache?.text()).toContain("2/3");
    expect(imageCache?.text()).toContain("Queue depth");
    expect(imageCache?.text()).toContain("Stale running jobs");
  });

  it("shows only Rebuild and explicit Clear imported data action buttons", () => {
    const wrapper = mountSubject();
    const actionLabels = wrapper
      .get("header")
      .findAll("button")
      .map((button) => button.text().trim());
    expect(actionLabels).toEqual(["Rebuild", "Clear imported data"]);
    expect(wrapper.text()).toContain("search indexes");
    expect(wrapper.text()).not.toContain("Rebuild outdated previews");
    expect(wrapper.text()).not.toContain("Clear thumbnails");
  });

  it("renders recent job history with compact rows", () => {
    mockJobsData = [
      {
        id: 12,
        library_id: 4,
        parent_job_id: null,
        type: "scan",
        state: "running",
        progress_current: 5,
        progress_total: 10,
        message: "Scanning",
        error: null,
        created_at: Date.now(),
        updated_at: Date.now(),
        started_at: null,
        finished_at: null,
      },
    ];
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Recent jobs");
    expect(wrapper.text()).toContain("Latest 8 file catalog, metadata, and image cache jobs.");
    expect(wrapper.text()).toContain("View all jobs");
    expect(wrapper.text()).toContain("scan #12");
    expect(wrapper.text()).toContain("Library #4");
    expect(wrapper.text()).toContain("5 / 10");
    expect(wrapper.text()).not.toContain("Active jobs");
  });

  it("explains the imported data flow", () => {
    const wrapper = mountSubject();

    expect(wrapper.text()).toContain("Imported data flow");
    expect(wrapper.text()).toContain("Processing pipeline");
    expect(wrapper.text()).toContain("File catalog");
    expect(wrapper.text()).toContain("Discovers source files");
    expect(wrapper.text()).toContain("Metadata extraction");
    expect(wrapper.text()).toContain("Reads file details");
    expect(wrapper.text()).toContain("Image cache");
    expect(wrapper.text()).toContain("Builds thumbnails and previews");
  });

  it("presents file checks, issues, and repair results as one workflow", () => {
    mockFileHealthData = {
      run: {
        id: 1,
        trigger: "manual",
        started_at: 1,
        finished_at: 2,
        status: "completed",
        error: null,
        issues: {
          missing_source_files: 2,
          generated_image_missing: 1,
          generated_image_abandoned: 0,
          metadata_mismatch: 3,
          file_index_ownership_mismatch: 1,
          orphaned_work_item: 0,
          generated_image_job_mismatch: 0,
        },
        repairs: { repaired: 1, requeued: 2, failed: 0, skipped: 0, recovered: 0, unchanged: 3 },
      },
    };

    const wrapper = mountSubject();
    const fileHealth = wrapper
      .findAll('[data-slot="card"]')
      .find((card) => card.text().includes("Check catalog, metadata, and image cache consistency"));

    expect(fileHealth?.text()).toContain("Run checks");
    expect(fileHealth?.text()).toContain("Issues found");
    expect(fileHealth?.text()).toContain("Missing source files");
    expect(fileHealth?.text()).toContain("Actions taken");
    expect(fileHealth?.text()).toContain("Requeued");
    expect(wrapper.text()).not.toContain("File issues");
    expect(wrapper.text()).not.toContain("Repair results");
  });

  it("keeps catalog, metadata, and preview diagnostics read-only", () => {
    mockRuntimeData = {
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
        scheduled_reconciliation_enabled: true,
      },
      metadata_lifecycle: {
        queued_metadata_jobs: 0,
        running_metadata_jobs: 0,
        failed_metadata_jobs: 0,
        stale_metadata_jobs: 0,
        assets_done_but_metadata_missing_or_stale: 0,
        repairable_metadata_assets: 0,
        metadata_jobs_without_matching_assets: 0,
      },
    };
    mockGlobalSummaryData = [{ ready_derivatives: 2, expected_derivatives: 2 }];
    const wrapper = mountSubject();

    const runtimeSection = wrapper.get('section[aria-labelledby="runtime-heading"]');
    const runtimeCards = runtimeSection.findAll('.rounded-xl');
    const catalogSection = runtimeCards[0];
    const metadataSection = runtimeCards[1];
    const cards = wrapper.findAll('[data-slot="card"]');
    const thumbnailsSection = cards.find((section) => section.text().includes("Image cache"));

    expect(catalogSection?.findAll("button").map((button) => button.attributes("aria-label"))).toEqual([
      "About File catalog queue depth",
    ]);
    expect(metadataSection?.findAll("button").map((button) => button.attributes("aria-label"))).toEqual([
      "About Metadata queue depth",
      "About Metadata staged queue depth",
      "About Failed jobs",
      "About Old or missing metadata",
      "About Jobs without catalog item",
    ]);
    expect(thumbnailsSection?.text()).not.toContain("Rebuild");
    expect(thumbnailsSection?.text()).not.toContain("Clear");
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
    expect(wrapper.text()).toContain("File catalog workers");
    expect(wrapper.text()).toContain("3");
    expect(wrapper.text()).toContain("Active jobs");
    expect(wrapper.text()).toContain("1");
    expect(wrapper.text()).toContain("Queue depth");
    expect(wrapper.text()).toContain("5");
    expect(wrapper.text()).toContain("Workers");
    expect(wrapper.text()).toContain("4");
    expect(wrapper.text()).toContain("Active jobs");
    expect(wrapper.text()).toContain("2");
    expect(wrapper.text()).toContain("Queue depth");
    expect(wrapper.text()).toContain("10");
    expect(wrapper.text()).toContain("Staged queue depth");
    expect(wrapper.text()).toContain("7");
  });

  it("renders Metadata extraction", () => {
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
    expect(wrapper.text()).toContain("Metadata extraction");
    expect(wrapper.text()).toContain("Reads file details after files are cataloged.");
    expect(wrapper.text()).toContain("Workers");
    expect(wrapper.text()).toContain("Active jobs");
    expect(wrapper.text()).toContain("Queue depth");
    expect(wrapper.text()).toContain("Staged queue depth");
    expect(wrapper.text()).toContain("Queued");
    expect(wrapper.text()).toContain("2");
    expect(wrapper.text()).toContain("Running");
    expect(wrapper.text()).toContain("1");
    expect(wrapper.text()).toContain("Failed jobs");
    expect(wrapper.text()).toContain("3");
    expect(wrapper.text()).toContain("Old or missing metadata");
    expect(wrapper.text()).toContain("9");
    expect(wrapper.text()).toContain("Can be repaired");
    expect(wrapper.text()).toContain("2");
    expect(wrapper.text()).toContain("Jobs without catalog item");
    expect(wrapper.text()).toContain("1");
  });
});
