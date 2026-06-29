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
let mockRuntimeRefetch = vi.fn();
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

vi.mock("@/composables/admin/useMaintenanceRuntimeQuery", async () => {
  const actual = await vi.importActual<typeof import("@/composables/admin/useMaintenanceRuntimeQuery")>(
    "@/composables/admin/useMaintenanceRuntimeQuery",
  );
  return {
    ...actual,
    useMaintenanceRuntimeQuery: () => ({
      data: { value: mockRuntimeData },
      isPending: { value: mockRuntimeIsPending },
      refetch: mockRuntimeRefetch,
    }),
  };
});

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
    clearImportedData: vi.fn(),
    rebuildImportedData: vi.fn(),
  };
});

vi.mock("@/composables/useToast", () => ({
  useToast: () => ({ error: vi.fn() }),
}));

vi.mock("../dialogs/GeneratedImagesClearDialog.vue", () => ({
  default: {
    props: ["open", "pending", "blocked", "blockMessage"],
    emits: ["update:open", "confirm"],
    template: `
      <div class="clear-dialog" :data-blocked="String(Boolean(blocked))" :data-message="blockMessage || ''">
        <button class="clear-dialog-confirm" :disabled="pending || blocked" @click="$emit('confirm')">Confirm clear</button>
      </div>
    `,
  },
}));

vi.mock("../dialogs/GeneratedImagesRebuildDialog.vue", () => ({
  default: {
    props: ["open", "pending", "blocked", "blockMessage"],
    emits: ["update:open", "confirm"],
    template: `
      <div class="rebuild-dialog" :data-blocked="String(Boolean(blocked))" :data-message="blockMessage || ''">
        <button class="rebuild-dialog-confirm" :disabled="pending || blocked" @click="$emit('confirm')">Confirm rebuild</button>
      </div>
    `,
  },
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

function findSectionByHeading(wrapper: ReturnType<typeof mountSubject>, heading: string) {
  return wrapper.findAll("section").find((section) => section.find("h3").text() === heading);
}

describe("MaintenancePage", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    mockFileHealthData = { run: null };
    mockFileHealthIsPending = false;
    mockRuntimeData = null;
    mockRuntimeIsPending = false;
    mockRuntimeRefetch = vi.fn(async () => ({ data: mockRuntimeData }));
    mockJobsData = [];
    mockGlobalSummaryData = null;
  });

  it("renders file catalog diagnostics with imported data flow context", () => {
    mockRuntimeData = {
      global_runtime: {
        catalog_worker_count: 1,
        catalog_active_jobs: 0,
        catalog_queue_depth: 0,
        metadata_worker_count: 2,
        metadata_active_jobs: 1,
        metadata_queue_depth: 3,
        metadata_staged_queue_depth: 0,
        derivative_active_jobs: 0,
        derivative_queue_depth: 0,
        watcher_enabled: true,
        watcher_healthy: true,
        watcher_issue: null,
        scheduled_reconciliation_enabled: true,
      },
      metadata_lifecycle: null,
    };
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Imported data flow");
    expect(wrapper.text()).toContain("File catalog");
    expect(wrapper.text()).toContain("Metadata extraction");
    expect(wrapper.text()).toContain("Preview cache");
    expect(wrapper.text()).toContain("Tracks which source files exist in registered libraries.");
  });

  it("shows only Rebuild and Clear imported-data action buttons", () => {
    const wrapper = mountSubject();
    const actionLabels = wrapper
      .get("header")
      .findAll("button")
      .map((button) => button.text().trim());
    expect(actionLabels).toEqual(["Rebuild", "Clear"]);
    expect(wrapper.text()).not.toContain("Rebuild outdated previews");
    expect(wrapper.text()).not.toContain("Clear thumbnails");
  });

  it("disables destructive imported-data actions while preview jobs are active", () => {
    mockRuntimeData = {
      global_runtime: {
        catalog_worker_count: 1,
        catalog_active_jobs: 0,
        catalog_queue_depth: 0,
        metadata_worker_count: 1,
        metadata_active_jobs: 0,
        metadata_queue_depth: 0,
        metadata_staged_queue_depth: 0,
        derivative_active_jobs: 1,
        derivative_queue_depth: 2,
        watcher_enabled: true,
        watcher_healthy: true,
        watcher_issue: null,
        scheduled_reconciliation_enabled: true,
      },
      metadata_lifecycle: null,
    };
    const wrapper = mountSubject();
    const buttons = wrapper.get("header").findAll("button");

    expect(buttons.map((button) => button.attributes("disabled"))).toEqual(["", ""]);
    expect(wrapper.text()).toContain(
      "Maintenance actions are locked while catalog, metadata, or preview cache jobs are running.",
    );
    expect(wrapper.text()).toContain("Preview active jobs");
    expect(wrapper.text()).toContain("Preview queue depth");
  });

  it("also disables the clear confirmation while maintenance is locked", () => {
    mockRuntimeData = {
      global_runtime: {
        catalog_worker_count: 1,
        catalog_active_jobs: 0,
        catalog_queue_depth: 0,
        metadata_worker_count: 1,
        metadata_active_jobs: 0,
        metadata_queue_depth: 0,
        metadata_staged_queue_depth: 0,
        derivative_active_jobs: 1,
        derivative_queue_depth: 0,
        watcher_enabled: true,
        watcher_healthy: true,
        watcher_issue: null,
        scheduled_reconciliation_enabled: true,
      },
      metadata_lifecycle: null,
    };
    const wrapper = mountSubject();

    expect(wrapper.get(".clear-dialog").attributes("data-blocked")).toBe("true");
    expect(wrapper.get(".clear-dialog-confirm").attributes("disabled")).toBe("");
  });

  it("refetches runtime before clear and skips the mutation if work became active", async () => {
    const idleRuntime = {
      global_runtime: {
        catalog_worker_count: 1,
        catalog_active_jobs: 0,
        catalog_queue_depth: 0,
        metadata_worker_count: 1,
        metadata_active_jobs: 0,
        metadata_queue_depth: 0,
        metadata_staged_queue_depth: 0,
        derivative_active_jobs: 0,
        derivative_queue_depth: 0,
        watcher_enabled: true,
        watcher_healthy: true,
        watcher_issue: null,
        scheduled_reconciliation_enabled: true,
      },
      metadata_lifecycle: null,
    };
    mockRuntimeData = idleRuntime;
    const activeRuntime = {
      global_runtime: {
        ...idleRuntime.global_runtime,
        derivative_active_jobs: 1,
      },
      metadata_lifecycle: null,
    };
    mockRuntimeRefetch = vi.fn(async () => ({ data: activeRuntime }));
    const { clearImportedData } = await import("@/services/api");
    const wrapper = mountSubject();

    await wrapper.get(".clear-dialog-confirm").trigger("click");

    expect(mockRuntimeRefetch).toHaveBeenCalled();
    expect(clearImportedData).not.toHaveBeenCalled();
  });

  it("keeps catalog, metadata, and thumbnail diagnostics read-only", () => {
    mockRuntimeData = {
      global_runtime: {
        catalog_worker_count: 1,
        catalog_active_jobs: 0,
        catalog_queue_depth: 0,
        metadata_worker_count: 1,
        metadata_active_jobs: 0,
        metadata_queue_depth: 0,
        metadata_staged_queue_depth: 0,
        derivative_active_jobs: 0,
        derivative_queue_depth: 0,
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

    const catalogSection = findSectionByHeading(wrapper, "File catalog");
    const metadataSection = findSectionByHeading(wrapper, "Metadata extraction");
    const thumbnailsSection = findSectionByHeading(wrapper, "Preview cache");

    expect(catalogSection?.findAll("button").map((button) => button.attributes("aria-label"))).toEqual([
      "About Catalog queue depth",
    ]);
    expect(metadataSection?.findAll("button").map((button) => button.attributes("aria-label"))).toEqual([
      "About Metadata queue depth",
      "About Metadata staged queue depth",
      "About Old or missing metadata",
      "About Jobs without catalog item",
    ]);
    expect(thumbnailsSection?.findAll("button").map((button) => button.attributes("aria-label"))).toEqual([
      "Refresh summary",
      "About Expected files",
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
        derivative_active_jobs: 0,
        derivative_queue_depth: 0,
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
        derivative_active_jobs: 0,
        derivative_queue_depth: 0,
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
        derivative_active_jobs: 0,
        derivative_queue_depth: 0,
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
        derivative_active_jobs: 0,
        derivative_queue_depth: 0,
        watcher_enabled: true,
        watcher_healthy: true,
        watcher_issue: null,
        scheduled_reconciliation_enabled: true,
      },
      metadata_lifecycle: null,
    };
    const wrapper = mountSubject();
    const catalogSection = findSectionByHeading(wrapper, "File catalog");
    const metadataSection = findSectionByHeading(wrapper, "Metadata extraction");

    expect(wrapper.text()).toContain("Catalog workers");
    expect(wrapper.text()).toContain("3");
    expect(wrapper.text()).toContain("Catalog active jobs");
    expect(wrapper.text()).toContain("1");
    expect(wrapper.text()).toContain("Catalog queue depth");
    expect(wrapper.text()).toContain("5");
    expect(catalogSection?.text()).not.toContain("Metadata workers");
    expect(metadataSection?.text()).toContain("Metadata workers");
    expect(metadataSection?.text()).toContain("4");
    expect(metadataSection?.text()).toContain("Metadata active jobs");
    expect(metadataSection?.text()).toContain("2");
    expect(metadataSection?.text()).toContain("Metadata queue depth");
    expect(metadataSection?.text()).toContain("10");
    expect(metadataSection?.text()).toContain("Metadata staged queue depth");
    expect(metadataSection?.text()).toContain("7");
  });

  it("renders Metadata extraction lifecycle diagnostics", () => {
    mockRuntimeData = {
      global_runtime: {
        catalog_worker_count: 1,
        catalog_active_jobs: 0,
        catalog_queue_depth: 0,
        metadata_worker_count: 2,
        metadata_active_jobs: 0,
        metadata_queue_depth: 0,
        metadata_staged_queue_depth: 0,
        derivative_active_jobs: 0,
        derivative_queue_depth: 0,
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
