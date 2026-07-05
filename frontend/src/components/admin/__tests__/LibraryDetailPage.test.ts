import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import LibraryDetailPage from "../LibraryDetailPage.vue";

const mockLibrary = {
  id: 1,
  name: "Test Library",
  state: "ready" as const,
  watch_enabled: 1,
  warm_enabled: 1,
  import_paths: [
    { id: 1, library_id: 1, path: "/photos", position: 0, created_at: Date.now(), updated_at: Date.now() },
  ],
  exclusion_patterns: [],
  root_path: "/photos",
  asset_count: 100,
  created_at: Date.now(),
  updated_at: Date.now(),
  last_scan_at: null,
  last_error: null,
};

const baseMockStatus = {
  contract_version: 1,
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

const mockStats = {
  photos: 80,
  videos: 20,
  total_assets: 100,
  active_assets: 95,
  offline_assets: 5,
  usage_bytes: 1048576,
  import_path_count: 1,
};

const mockJobs = [
  {
    id: 1,
    library_id: 1,
    type: "scan",
    state: "completed",
    progress_current: 50,
    progress_total: 100,
    updated_at: Date.now(),
    message: "Scan done",
    error: null,
    created_at: Date.now(),
  },
  {
    id: 2,
    library_id: 1,
    type: "index",
    state: "failed",
    progress_current: 10,
    progress_total: null,
    updated_at: Date.now(),
    message: null,
    error: "Out of memory",
    created_at: Date.now(),
  },
];

const mockGeneratedImages = {
  ready_derivatives: 149,
  expected_derivatives: 200,
  by_kind: {
    thumbnail: {
      ready_derivatives: 75,
      expected_derivatives: 100,
    },
    preview: {
      ready_derivatives: 74,
      expected_derivatives: 100,
    },
  },
  quota_used_bytes: 524288000,
  quota_bytes: 1073741824,
  quota_utilization: 0.488,
};

let mockLibraryData: typeof mockLibrary | null = mockLibrary;
let mockLibraryIsPending = false;
let mockLibraryIsError = false;
let mockStatusData: Record<string, unknown> | null = {
  status: { ...mockLibrary, ...baseMockStatus },
  contract_version: 1,
};
let mockContractError: Error | null = null;
let mockJobsData: unknown[] = [];
let mockGeneratedImagesData: typeof mockGeneratedImages | null = null;
let routerPushMock = vi.fn();
let copyTextMock = vi.fn();
let copyStatusMock: Record<string, boolean> = {};
let scanMutateMock = vi.fn();
let warmMutateMock = vi.fn();
let mockLibraryJobsQueryArgs: unknown[][] = [];

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: routerPushMock }),
  useRoute: () => ({ path: "/admin/libraries/1" }),
}));

vi.mock("@/composables/admin/useLibraryQuery", () => ({
  useLibraryQuery: () => ({
    data: { value: mockLibraryData },
    isPending: { value: mockLibraryIsPending },
    isError: { value: mockLibraryIsError },
  }),
}));

vi.mock("@/composables/useCatalogStatusQuery", () => ({
  useCatalogStatusQuery: () => ({
    data: { value: mockStatusData },
    isPending: { value: false },
    isError: { value: false },
    error: { value: mockContractError },
    isFetching: { value: false },
    refetch: vi.fn(),
    contractError: { value: mockContractError },
  }),
}));

vi.mock("@/composables/admin/useLibraryStatsQuery", () => ({
  useLibraryStatsQuery: () => ({
    data: { value: mockStats },
    isPending: { value: false },
  }),
}));

vi.mock("@/composables/admin/useLibraryJobsQuery", () => ({
  useLibraryJobsQuery: (...args: unknown[]) => {
    mockLibraryJobsQueryArgs.push(args);
    return {
      data: { value: mockJobsData },
      isFetching: { value: false },
      refetch: vi.fn(),
    };
  },
}));

vi.mock("@/composables/admin/useLibrariesQuery", () => ({
  useLibrariesQuery: () => ({
    data: { value: [mockLibrary] },
  }),
}));

vi.mock("@/composables/admin/useLibraryMutations", () => ({
  useLibraryMutations: () => ({
    scanMutation: { isPending: { value: false }, mutate: scanMutateMock, mutateAsync: vi.fn() },
    unregisterMutation: { isPending: { value: false }, mutateAsync: vi.fn() },
  }),
}));

vi.mock("@/composables/admin/useLibraryEvents", () => ({
  useLibraryEvents: vi.fn(),
}));

vi.mock("@/composables/admin/useGeneratedImagesStatusQuery", () => ({
  useGeneratedImagesStatusQuery: () => ({
    data: { value: mockGeneratedImagesData },
    isPending: { value: false },
    isFetching: { value: false },
    refetch: vi.fn(),
  }),
}));

vi.mock("@/composables/admin/useGeneratedImagesMutations", () => ({
  useGeneratedImagesMutations: () => ({
    warmMutation: { isPending: { value: false }, mutate: warmMutateMock },
  }),
}));

vi.mock("@/composables/useClipboard", () => ({
  useClipboard: () => ({ copyStatus: { value: copyStatusMock }, copyText: copyTextMock }),
}));

function mountSubject(propsId = 1) {
  setActivePinia(createPinia());
  const queryClient = createIsolatedQueryClient();
  return mount(LibraryDetailPage, {
    props: { id: propsId },
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
      stubs: {
        RouterLink: { template: "<a><slot /></a>" },
        Button: { template: "<button v-bind='$attrs'><slot /></button>" },
        ButtonLink: { template: "<a :href='to' @click='$attrs.onClick?.()'><slot /></a>" },
        Skeleton: { template: "<div data-testid='skeleton' />" },
        Separator: { template: "<hr />" },
        Tooltip: { template: "<span><slot /></span>" },
        TooltipContent: { template: "<span><slot /></span>" },
        TooltipTrigger: { template: "<span><slot /></span>" },
        LibraryProgressBar: { template: "<div class='library-progress' />" },
        LibraryStatusBadge: { template: "<span class='status-badge'><slot /></span>" },
        LibraryEditDialog: { props: ["open"], template: "<div class='edit-dialog' :data-open='open' />" },
        LibraryDeleteConfirmDialog: { template: "<div class='delete-dialog' />" },
      },
    },
  });
}

describe("LibraryDetailPage", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    mockLibraryData = mockLibrary;
    mockLibraryIsPending = false;
    mockLibraryIsError = false;
    mockStats.active_assets = 95;
    mockStats.offline_assets = 5;
    mockStatusData = { status: { ...mockLibrary, ...baseMockStatus }, contract_version: 1 };
    mockContractError = null;
    mockJobsData = [];
    mockGeneratedImagesData = null;
    routerPushMock = vi.fn();
    copyTextMock = vi.fn();
    copyStatusMock = {};
    scanMutateMock = vi.fn();
    warmMutateMock = vi.fn();
    mockLibraryJobsQueryArgs = [];
  });

  it("renders the library name", () => {
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Test Library");
  });

  it("renders the import path", () => {
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("/photos");
  });

  it("renders action buttons", () => {
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Open gallery");
    expect(wrapper.text()).toContain("Edit");
    expect(wrapper.text()).toContain("Update library");
    expect(wrapper.text()).toContain("Unregister library");
  });

  it("renders all dashboard sections", () => {
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Overview");
    expect(wrapper.text()).toContain("Status");
    expect(wrapper.text()).toContain("Thumbnails");
    expect(wrapper.text()).toContain("All systems available");
    expect(wrapper.text()).toContain("File catalog is current");
    expect(wrapper.text()).toContain("80");
    expect(wrapper.text()).toContain("20");
    expect(wrapper.text()).toContain("95 available");
    expect(wrapper.text()).toContain("5 unavailable");
    expect(wrapper.text()).toContain("95/100 assets");
    expect(wrapper.text()).toContain("Available: indexed images/videos currently available on disk.");
    expect(wrapper.text()).toContain(
      "Unavailable: cataloged files not available in the latest scan or under unavailable import paths.",
    );
    expect(wrapper.text()).toContain("Configuration");
    expect(wrapper.text()).toContain("Library folder");
    expect(wrapper.text()).toContain("Excluded paths");
    expect(wrapper.text()).toContain("None configured");
    expect(wrapper.text()).toContain("Add pattern");
    expect(wrapper.text()).toContain("Danger zone");
    expect(wrapper.text()).toContain("Recent job history");
    expect(wrapper.text()).toContain("Latest 8 jobs");
    expect(wrapper.text()).toContain("View all jobs");
    expect(wrapper.text()).toContain("File catalog lifecycle");
    expect(wrapper.find(".library-progress").exists()).toBe(false);
  });

  it("places danger zone after history and lifecycle details", () => {
    const text = mountSubject().text();
    expect(text.indexOf("Recent job history")).toBeLessThan(text.indexOf("File catalog lifecycle"));
    expect(text.indexOf("File catalog lifecycle")).toBeLessThan(text.indexOf("Danger zone"));
  });

  it("limits the embedded job history", () => {
    mountSubject();
    expect(mockLibraryJobsQueryArgs[0]?.[1]).toBe(8);
  });

  it("hides unavailable file count when there are no unavailable files", () => {
    mockStats.offline_assets = 0;
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("95 available");
    expect(wrapper.text()).not.toContain("0 unavailable");
  });

  it("shows empty jobs state", () => {
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("No jobs recorded yet");
  });

  it("shows library not found when id is invalid", () => {
    mockLibraryData = null;
    const wrapper = mountSubject(0);
    expect(wrapper.text()).toContain("Library not found");
  });

  it("shows library not found when library query errors", () => {
    mockLibraryData = null;
    mockLibraryIsError = true;
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Library not found");
  });

  it("shows loading skeleton when library is pending", () => {
    mockLibraryData = null;
    mockLibraryIsPending = true;
    const wrapper = mountSubject();
    expect(wrapper.find('[data-testid="skeleton"]').exists()).toBe(true);
  });

  it("shows status contract error message", () => {
    mockContractError = new Error("App updated, please reload");
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("App updated, please reload");
  });

  it("displays latest issue details after review", async () => {
    mockStatusData = {
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
        issue_count: 5,
        issues: { availability: 1, scan: 2, metadata: 2 },
        latest_issue: { source: "File update", message: "File not found", path: "/path/to/file" },
        last_scan_at: null,
        last_index_at: null,
      },
      contract_version: 1,
    };
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("5 issues need attention");
    expect(wrapper.text()).not.toContain("File not found");
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Review"))!
      .trigger("click");
    expect(wrapper.text()).toContain("Hide details");
    expect(wrapper.text()).toContain("File not found");
    expect(wrapper.text()).toContain("/path/to/file");
  });

  it("shows fix action when the library is unavailable", async () => {
    mockStatusData = {
      status: {
        ...baseMockStatus,
        availability: { state: "unavailable", available_paths: 0, total_paths: 1 },
        issue_count: 1,
        issues: { availability: 1, scan: 0, metadata: 0 },
        latest_issue: { source: "Availability", message: "Library path unavailable", path: "/photos" },
      },
      contract_version: 1,
    };
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Unavailable");
    expect(wrapper.text()).toContain("Library unavailable");
    const fixButton = wrapper.findAll("button").find((button) => button.text().includes("Fix now"));
    expect(fixButton).not.toBeUndefined();
    await fixButton!.trigger("click");
    expect(scanMutateMock).toHaveBeenCalledWith({ id: 1 });
  });

  it("copies import path on copy button click", async () => {
    const wrapper = mountSubject();
    const copyBtn = wrapper.get('[aria-label="Copy path"]');
    await copyBtn.trigger("click");
    expect(copyTextMock).toHaveBeenCalledWith("/photos", "path");
  });

  it("shows copied state on the folder path copy button", () => {
    copyStatusMock = { path: true };
    const wrapper = mountSubject();
    expect(wrapper.find('[aria-label="Path copied"]').exists()).toBe(true);
  });

  it("opens edit dialog from configuration actions", async () => {
    const wrapper = mountSubject();
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Add pattern"))!
      .trigger("click");
    expect(wrapper.find(".edit-dialog").attributes("data-open")).toBe("true");
  });

  it("calls scan mutation on Update library button click", async () => {
    const wrapper = mountSubject();
    const scanBtn = wrapper.findAll("button").find((b) => b.text().includes("Update library"));
    expect(scanBtn).not.toBeUndefined();
    await scanBtn!.trigger("click");
    expect(scanMutateMock).toHaveBeenCalledWith({ id: 1 });
  });

  it("renders derivative cache with full data", () => {
    mockGeneratedImagesData = mockGeneratedImages;
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Thumbnails");
    expect(wrapper.text()).toContain("74/100 cached");
    expect(wrapper.text()).toContain("26 thumbnails missing");
    expect(wrapper.text()).toContain("Build missing thumbnails");
    expect(wrapper.find(".bg-warning").exists()).toBe(true);
    expect(wrapper.find(".bg-primary").exists()).toBe(false);
  });

  it("queues all missing thumbnails from the thumbnail action", async () => {
    mockGeneratedImagesData = mockGeneratedImages;
    const wrapper = mountSubject();
    const buildButton = wrapper.findAll("button").find((button) => button.text().includes("Build missing thumbnails"));
    expect(buildButton).not.toBeUndefined();

    await buildButton!.trigger("click");

    expect(warmMutateMock).toHaveBeenCalledWith();
  });

  it("renders jobs with actual data", () => {
    mockJobsData = mockJobs;
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("scan");
    expect(wrapper.text()).toContain("index");
    expect(wrapper.text()).toContain("Scan done");
    expect(wrapper.text()).toContain("Out of memory");
  });
});
