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

const mockStatus = {
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

vi.mock("@/composables/admin/useLibraryQuery", () => ({
  useLibraryQuery: () => ({
    data: { value: mockLibrary },
    isPending: { value: false },
    isError: { value: false },
  }),
}));

vi.mock("@/composables/useCatalogStatusQuery", () => ({
  useCatalogStatusQuery: () => ({
    data: { value: { status: mockStatus, contract_version: 1 } },
    isPending: { value: false },
    isError: { value: false },
    error: { value: null },
    refetch: vi.fn(),
    contractError: { value: null },
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
    data: { value: [] },
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
    scanMutation: { isPending: { value: false }, mutate: vi.fn(), mutateAsync: vi.fn() },
    unregisterMutation: { isPending: { value: false }, mutateAsync: vi.fn() },
  }),
}));

vi.mock("@/composables/admin/useLibraryEvents", () => ({
  useLibraryEvents: vi.fn(),
}));

vi.mock("@/composables/admin/useGeneratedImagesStatusQuery", () => ({
  useGeneratedImagesStatusQuery: () => ({
    data: { value: null },
    isPending: { value: false },
    refetch: vi.fn(),
  }),
}));

vi.mock("@/composables/admin/useGeneratedImagesMutations", () => ({
  useGeneratedImagesMutations: () => ({
    warmMutation: { isPending: { value: false }, mutate: vi.fn() },
  }),
}));

vi.mock("@/composables/useClipboard", () => ({
  useClipboard: () => ({ copyText: vi.fn() }),
}));

function createWrapper() {
  setActivePinia(createPinia());
  const queryClient = createIsolatedQueryClient();
  return mount(LibraryDetailPage, {
    props: { id: 1 },
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
      stubs: {
        RouterLink: { template: "<a><slot /></a>" },
        Button: { template: "<button :disabled='disabled' @click='$attrs.onClick?.()'><slot /></button>" },
        ButtonLink: { template: "<a :href='to' @click='$attrs.onClick?.()'><slot /></a>" },
        Skeleton: { template: "<div class='skeleton' />" },
        Separator: { template: "<hr />" },
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
  });

  it("renders the library name", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Test Library");
  });

  it("renders the import path", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("/photos");
  });

  it("renders action buttons", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Use in gallery");
    expect(wrapper.text()).toContain("Edit");
    expect(wrapper.text()).toContain("Scan");
    expect(wrapper.text()).toContain("Unregister");
  });

  it("renders Status and progress section", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Status and progress");
  });

  it("renders Issues section", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Issues");
  });

  it("renders Statistics section", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Statistics");
  });

  it("shows photos count in stats", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("80");
  });

  it("shows videos count in stats", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("20");
  });

  it("renders Live status section", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Live status");
  });

  it("renders Problems section", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Problems");
  });

  it("renders Import paths section", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Import paths");
  });

  it("renders Exclusion patterns section", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Exclusion patterns");
  });

  it("renders Recent job history section", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Recent job history");
  });

  it("renders Catalog lifecycle section", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Catalog lifecycle");
  });

  it("renders Summary from status", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Summary");
  });

  it("shows empty jobs state", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("No jobs recorded yet");
  });
});
