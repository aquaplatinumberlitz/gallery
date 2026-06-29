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
  ready_derivatives: 75,
  expected_derivatives: 100,
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
let scanMutateMock = vi.fn();

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
  useLibraryJobsQuery: () => ({
    data: { value: mockJobsData },
    isFetching: { value: false },
    refetch: vi.fn(),
  }),
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
    warmMutation: { isPending: { value: false }, mutate: vi.fn() },
  }),
}));

vi.mock("@/composables/useClipboard", () => ({
  useClipboard: () => ({ copyText: copyTextMock }),
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
        LibraryEditDialog: { template: "<div class='edit-dialog' />" },
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
    mockStatusData = { status: { ...mockLibrary, ...baseMockStatus }, contract_version: 1 };
    mockContractError = null;
    mockJobsData = [];
    mockGeneratedImagesData = null;
    routerPushMock = vi.fn();
    copyTextMock = vi.fn();
    scanMutateMock = vi.fn();
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
    expect(wrapper.text()).toContain("Use in gallery");
    expect(wrapper.text()).toContain("Edit");
    expect(wrapper.text()).toContain("Update library");
    expect(wrapper.text()).toContain("Unregister");
  });

  it("renders all dashboard sections", () => {
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Status and progress");
    expect(wrapper.text()).toContain("Issues");
    expect(wrapper.text()).toContain("Statistics");
    expect(wrapper.text()).toContain("80");
    expect(wrapper.text()).toContain("20");
    expect(wrapper.text()).toContain("Import paths");
    expect(wrapper.text()).toContain("Exclusion patterns");
    expect(wrapper.text()).toContain("Recent job history");
    expect(wrapper.text()).toContain("Catalog lifecycle");
    expect(wrapper.text()).toContain("Summary");
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

  it("displays latest issue with data", () => {
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
    expect(wrapper.text()).toContain("issue");
    expect(wrapper.text()).toContain("File not found");
    expect(wrapper.text()).toContain("/path/to/file");
  });

  it("copies import path on copy button click", async () => {
    const wrapper = mountSubject();
    const copyBtn = wrapper.get('[aria-label="Copy import path"]');
    await copyBtn.trigger("click");
    expect(copyTextMock).toHaveBeenCalledWith("/photos", "path");
  });

  it("calls scan mutation on Update library button click", async () => {
    const wrapper = mountSubject();
    const scanBtn = wrapper.findAll("button").find((b) => b.text().includes("Update library"));
    expect(scanBtn).not.toBeUndefined();
    await scanBtn!.trigger("click");
    expect(scanMutateMock).toHaveBeenCalledWith({ id: 1 });
  });

  it("renders generated images with full data", () => {
    mockGeneratedImagesData = mockGeneratedImages;
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("Generated images");
    expect(wrapper.text()).toContain("Generate missing");
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
