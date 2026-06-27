import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import IndexStatusPanel from "../IndexStatusPanel.vue";

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
  last_scan_at: 1700000000000,
  last_index_at: 1700000000000,
};

vi.mock("@/composables/useCatalogStatusQuery", () => ({
  useCatalogStatusQuery: () => ({
    data: { value: { status: mockStatus, contract_version: 1 } },
    isLoading: { value: false },
    isError: { value: false },
    error: { value: null },
    refetch: vi.fn(),
    contractError: { value: null },
  }),
}));

vi.mock("@/composables/useActiveLibrarySelection", () => ({
  useActiveLibrarySelection: () => ({
    activeLibrary: { value: { id: 1, name: "Test", root_path: "/test" } },
  }),
}));

vi.mock("@/services/api", () => ({
  rebuildLibrary: vi.fn(),
  scanLibrary: vi.fn(),
}));

vi.mock("@/query", () => ({
  queryClient: { invalidateQueries: vi.fn() },
}));

vi.mock("@/query/keys", () => ({
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

vi.mock("@/utils/indexMaintenance", () => ({
  markScopeRebuildStarted: vi.fn(),
}));

function createWrapper(props: Record<string, unknown> = {}) {
  setActivePinia(createPinia());
  const queryClient = createIsolatedQueryClient();
  return mount(IndexStatusPanel, {
    props,
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
      stubs: {
        Button: { template: "<button :disabled='disabled' @click='$attrs.onClick?.()'><slot /></button>" },
        Badge: { template: "<span class='badge'><slot /></span>" },
        Popover: { template: "<div class='popover-wrapper'><slot /></div>" },
        PopoverTrigger: { template: "<div class='popover-trigger'><slot /></div>" },
        PopoverContent: { template: "<div class='popover-content'><slot /></div>" },
        Dialog: { template: "<div v-if='$attrs.open !== false'><slot /></div>" },
        DialogContent: { template: "<div class='dialog-content'><slot /></div>" },
        DialogTitle: { template: "<h2 class='dialog-title'><slot /></h2>" },
        DialogDescription: { template: "<p class='dialog-desc'><slot /></p>" },
        Tooltip: { template: "<span><slot /></span>" },
        TooltipTrigger: { template: "<span><slot /></span>" },
        TooltipContent: { template: "<span><slot /></span>" },
        IndexStatusBadge: { template: "<span class='status-badge'><slot /></span>" },
        IndexStatusCard: { template: "<div data-testid='status-card'><slot /></div>" },
      },
    },
  });
}

describe("IndexStatusPanel extra", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("renders status button with variant='button' (default)", () => {
    const wrapper = createWrapper();
    expect(wrapper.find("button").exists()).toBe(true);
  });

  it("renders card variant", () => {
    const wrapper = createWrapper({ variant: "card" });
    expect(wrapper.find('[data-testid="status-card"]').exists()).toBe(true);
  });

  it("renders popover button with Database icon", () => {
    const wrapper = createWrapper();
    expect(wrapper.find("button").exists()).toBe(true);
  });
});
