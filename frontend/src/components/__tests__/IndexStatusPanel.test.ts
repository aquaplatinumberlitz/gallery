import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import type { StatusResponseEnvelope } from "@/lib/catalog/status";
import { ref } from "vue";

const testState = vi.hoisted(() => ({
  activeLibrary: {
    id: 1,
    name: "Test",
    import_paths: [{ id: 1, library_id: 1, path: "/photos", position: 0 }],
  },
  catalogStatusCalls: [] as Array<{ scopePath: { value: string | null } }>,
}));

const mockStatus = {
  contract_version: 1 as const,
  generated_at: Date.now(),
  summary_state: "ready" as const,
  scope: { kind: "library" as const, library_id: 1, path: null, import_path_count: 1 },
  availability: { state: "available" as const, available_paths: 1, total_paths: 1 },
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
    total_assets: 100,
    ready_assets: 95,
    not_ready_assets: 5,
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
  last_scan_at: null,
  last_index_at: null,
};

const mockDataValue = ref<StatusResponseEnvelope | null>({
  status: mockStatus as StatusResponseEnvelope["status"],
  contract_version: 1 as const,
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
  },
  metadata_lifecycle: null,
});
const mockIsLoadingValue = ref(false);
const mockIsErrorValue = ref(false);
const mockErrorValue = ref<Error | null>(null);
const mockContractErrorValue = ref<Error | null>(null);
const mockRefetch = vi.fn();

vi.mock("@/composables/useCatalogStatusQuery", () => ({
  useCatalogStatusQuery: vi.fn((_libraryId, scopePath: { value: string | null }) => {
    testState.catalogStatusCalls.push({ scopePath });
    return {
      data: mockDataValue,
      isLoading: mockIsLoadingValue,
      isError: mockIsErrorValue,
      error: mockErrorValue,
      refetch: mockRefetch,
      contractError: mockContractErrorValue,
    };
  }),
}));

vi.mock("@/composables/useActiveLibrarySelection", () => ({
  useActiveLibrarySelection: () => ({
    activeLibrary: {
      get value() {
        return testState.activeLibrary;
      },
    },
  }),
}));

vi.mock("@/services/api", () => ({
  scanLibrary: vi.fn(),
}));

vi.mock("@/query", () => ({
  queryClient: { invalidateQueries: vi.fn() },
}));

vi.mock("@/query/keys", () => ({
  normalizeQueryPath: (path: string | null | undefined) => {
    const normalized = (path ?? "").trim().replace(/\\/g, "/").replace(/\/+/g, "/");
    return normalized === "/" ? normalized : normalized.replace(/\/$/, "");
  },
  queryKeys: {
    statusLibrary: vi.fn(() => ["status", "library", 1]),
    statusPathRoot: vi.fn(() => ["status", "path", 1]),
    statusBatch: vi.fn(() => ["status", "batch"]),
    browseRoot: vi.fn(() => ["browse", 1]),
    browseInfiniteRoot: vi.fn(() => ["browse", "infinite", 1]),
    libraries: vi.fn(() => ["libraries"]),
    jobsRoot: vi.fn(() => ["jobs"]),
  },
}));

describe("IndexStatusPanel", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    testState.activeLibrary = {
      id: 1,
      name: "Test",
      import_paths: [{ id: 1, library_id: 1, path: "/photos", position: 0 }],
    };
    testState.catalogStatusCalls = [];
    mockDataValue.value = {
      status: mockStatus as StatusResponseEnvelope["status"],
      contract_version: 1 as const,
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
      },
      metadata_lifecycle: null,
    };
    mockIsLoadingValue.value = false;
    mockIsErrorValue.value = false;
    mockErrorValue.value = null;
    mockContractErrorValue.value = null;
  });

  it("renders button with catalog status trigger", async () => {
    const IndexStatusPanel = (await import("../IndexStatusPanel.vue")).default;
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(IndexStatusPanel, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Button: { template: "<button><slot /></button>" },
          Badge: { template: "<span><slot /></span>" },
          Popover: { template: "<div><slot /></div>" },
          PopoverTrigger: { template: "<div><slot /></div>" },
          PopoverContent: { template: "<div><slot /></div>" },
          IndexStatusBadge: { template: "<span><slot /></span>" },
          IndexStatusCard: { template: "<div class='status-card'><slot /></div>" },
          Database: { template: "<span>db</span>" },
          Loader: { template: "<span>loader</span>" },
          AlertCircle: { template: "<span>alert</span>" },
        },
      },
    });
    expect(wrapper.find("button").exists()).toBe(true);
  });

  it("renders card variant", async () => {
    const IndexStatusPanel = (await import("../IndexStatusPanel.vue")).default;
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(IndexStatusPanel, {
      props: { variant: "card" },
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          IndexStatusCard: { template: "<div data-testid='status-card'>Card Content</div>" },
          Button: { template: "<button><slot /></button>" },
          Badge: { template: "<span><slot /></span>" },
        },
      },
    });
    expect(wrapper.find('[data-testid="status-card"]').exists()).toBe(true);
  });

  it("shows loading state", async () => {
    mockIsLoadingValue.value = true;
    mockDataValue.value = null;
    const IndexStatusPanel = (await import("../IndexStatusPanel.vue")).default;
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(IndexStatusPanel, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Button: { template: "<button><slot /></button>" },
          Badge: { template: "<span><slot /></span>" },
          Popover: { template: "<div><slot /></div>" },
          PopoverTrigger: { template: "<div><slot /></div>" },
          PopoverContent: { template: "<div class='popover-content'><slot /></div>" },
          IndexStatusBadge: { template: "<span><slot /></span>" },
          IndexStatusCard: { template: "<div class='status-card'><slot /></div>" },
          Database: { template: "<span>db</span>" },
          Loader: { template: "<span>loader</span>" },
          AlertCircle: { template: "<span>alert</span>" },
        },
      },
    });
    expect(wrapper.text()).toBeTruthy();
  });

  it("shows unavailable presentation when status refresh fails with cached ready data", async () => {
    mockIsErrorValue.value = true;
    mockErrorValue.value = new Error("Can't connect to server");

    const IndexStatusPanel = (await import("../IndexStatusPanel.vue")).default;
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(IndexStatusPanel, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Button: { template: "<button><slot /></button>" },
          Badge: { template: "<span><slot /></span>" },
          Popover: { template: "<div><slot /></div>" },
          PopoverTrigger: { template: "<div><slot /></div>" },
          PopoverContent: { template: "<div class='popover-content'><slot /></div>" },
          IndexStatusBadge: {
            props: ["presentation"],
            template: "<span data-testid='status-badge'>{{ presentation.label }} {{ presentation.indicator }}</span>",
          },
          IndexStatusCard: { template: "<div class='status-card'><slot /></div>" },
          PillIndicator: {
            props: ["variant", "pulse"],
            template: "<span data-testid='status-dot'>{{ variant }} {{ pulse }}</span>",
          },
          Database: { template: "<span>db</span>" },
          Loader: { template: "<span>loader</span>" },
          AlertCircle: { template: "<span>alert</span>" },
        },
      },
    });

    expect(wrapper.get('[data-testid="catalog-status-icon-indicator"]').text()).toBe("error false");
    expect(wrapper.get('[data-testid="status-badge"]').text()).toBe("Unavailable error");
    expect(wrapper.text()).toContain("Can't connect to server");
    expect(wrapper.get('[data-testid="status-badge"]').text()).not.toContain("Ready");
  });

  it("shows Update library without a rebuild action and calls scanLibrary", async () => {
    const IndexStatusPanel = (await import("../IndexStatusPanel.vue")).default;
    const { scanLibrary } = await import("@/services/api");
    vi.mocked(scanLibrary).mockResolvedValue({
      library_id: 1,
      job_id: 10,
      scope_path: null,
      operation: "scan",
      trigger: "manual",
      state: "queued",
      coalesced: false,
    });
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(IndexStatusPanel, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Button: { template: "<button v-bind='$attrs'><slot /></button>" },
          Badge: { template: "<span><slot /></span>" },
          Popover: { template: "<div><slot /></div>" },
          PopoverTrigger: { template: "<div><slot /></div>" },
          PopoverContent: { template: "<div class='popover-content'><slot /></div>" },
          IndexStatusBadge: { template: "<span><slot /></span>" },
          IndexStatusCard: { template: "<div class='status-card'><slot /></div>" },
          Database: { template: "<span>db</span>" },
          ChevronRight: { template: "<span />" },
          ChevronDown: { template: "<span />" },
        },
      },
    });

    expect(wrapper.text()).toContain("Update library");
    expect(wrapper.findAll("button").some((button) => button.text() === "Scan")).toBe(false);
    expect(wrapper.findAll("button").some((button) => button.text() === "Rebuild")).toBe(false);

    const updateButton = wrapper.findAll("button").find((button) => button.text() === "Update library");
    expect(updateButton).toBeDefined();
    await updateButton!.trigger("click");

    expect(scanLibrary).toHaveBeenCalledWith(1, undefined);
  });

  it("treats a single import-path root as library scope", async () => {
    const IndexStatusPanel = (await import("../IndexStatusPanel.vue")).default;
    const { scanLibrary } = await import("@/services/api");
    vi.mocked(scanLibrary).mockResolvedValue({
      library_id: 1,
      job_id: 10,
      scope_path: null,
      operation: "scan",
      trigger: "manual",
      state: "queued",
      coalesced: false,
    });
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(IndexStatusPanel, {
      props: { path: "/photos" },
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Button: { template: "<button v-bind='$attrs'><slot /></button>" },
          Badge: { template: "<span><slot /></span>" },
          Popover: { template: "<div><slot /></div>" },
          PopoverTrigger: { template: "<div><slot /></div>" },
          PopoverContent: { template: "<div class='popover-content'><slot /></div>" },
          IndexStatusBadge: { template: "<span><slot /></span>" },
          IndexStatusCard: { template: "<div class='status-card'><slot /></div>" },
          Database: { template: "<span>db</span>" },
          ChevronRight: { template: "<span />" },
          ChevronDown: { template: "<span />" },
        },
      },
    });

    expect(testState.catalogStatusCalls.at(-1)?.scopePath.value).toBeNull();
    const updateButton = wrapper.findAll("button").find((button) => button.text() === "Update library");
    expect(updateButton).toBeDefined();
    await updateButton!.trigger("click");

    expect(scanLibrary).toHaveBeenCalledWith(1, undefined);
  });

  it("keeps nested folders scoped to the current folder", async () => {
    const IndexStatusPanel = (await import("../IndexStatusPanel.vue")).default;
    const { scanLibrary } = await import("@/services/api");
    vi.mocked(scanLibrary).mockResolvedValue({
      library_id: 1,
      job_id: 10,
      scope_path: "/photos/trip",
      operation: "scan",
      trigger: "manual",
      state: "queued",
      coalesced: false,
    });
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(IndexStatusPanel, {
      props: { path: "/photos/trip" },
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Button: { template: "<button v-bind='$attrs'><slot /></button>" },
          Badge: { template: "<span><slot /></span>" },
          Popover: { template: "<div><slot /></div>" },
          PopoverTrigger: { template: "<div><slot /></div>" },
          PopoverContent: { template: "<div class='popover-content'><slot /></div>" },
          IndexStatusBadge: { template: "<span><slot /></span>" },
          IndexStatusCard: { template: "<div class='status-card'><slot /></div>" },
          Database: { template: "<span>db</span>" },
          ChevronRight: { template: "<span />" },
          ChevronDown: { template: "<span />" },
        },
      },
    });

    expect(testState.catalogStatusCalls.at(-1)?.scopePath.value).toBe("/photos/trip");
    const updateButton = wrapper.findAll("button").find((button) => button.text() === "Update current folder");
    expect(updateButton).toBeDefined();
    await updateButton!.trigger("click");

    expect(scanLibrary).toHaveBeenCalledWith(1, "/photos/trip");
  });

  it("does not call one import path the whole library when multiple import paths exist", async () => {
    testState.activeLibrary = {
      id: 1,
      name: "Test",
      import_paths: [
        { id: 1, library_id: 1, path: "/photos", position: 0 },
        { id: 2, library_id: 1, path: "/camera", position: 1 },
      ],
    };
    const IndexStatusPanel = (await import("../IndexStatusPanel.vue")).default;
    const { scanLibrary } = await import("@/services/api");
    vi.mocked(scanLibrary).mockResolvedValue({
      library_id: 1,
      job_id: 10,
      scope_path: "/photos",
      operation: "scan",
      trigger: "manual",
      state: "queued",
      coalesced: false,
    });
    const queryClient = createIsolatedQueryClient();
    const wrapper = mount(IndexStatusPanel, {
      props: { path: "/photos" },
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Button: { template: "<button v-bind='$attrs'><slot /></button>" },
          Badge: { template: "<span><slot /></span>" },
          Popover: { template: "<div><slot /></div>" },
          PopoverTrigger: { template: "<div><slot /></div>" },
          PopoverContent: { template: "<div class='popover-content'><slot /></div>" },
          IndexStatusBadge: { template: "<span><slot /></span>" },
          IndexStatusCard: { template: "<div class='status-card'><slot /></div>" },
          Database: { template: "<span>db</span>" },
          ChevronRight: { template: "<span />" },
          ChevronDown: { template: "<span />" },
        },
      },
    });

    expect(testState.catalogStatusCalls.at(-1)?.scopePath.value).toBe("/photos");
    const updateButton = wrapper.findAll("button").find((button) => button.text() === "Update current folder");
    expect(updateButton).toBeDefined();
    await updateButton!.trigger("click");

    expect(scanLibrary).toHaveBeenCalledWith(1, "/photos");
  });
});
