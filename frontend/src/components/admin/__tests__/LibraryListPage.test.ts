import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LibraryListPage from "../LibraryListPage.vue";
import type { RegisteredLibrary } from "@/types";

const routerPushMock = vi.fn();
const scanAllMutateMock = vi.fn();
const scanMutateMock = vi.fn();

const mockLibrary: RegisteredLibrary = {
  id: 1,
  name: "Family photos",
  state: "ready",
  watch_enabled: 1,
  warm_enabled: 1,
  import_paths: [{ id: 10, library_id: 1, path: "/photos", position: 0, created_at: 1, updated_at: 1 }],
  exclusion_patterns: [],
  root_path: "/photos",
  asset_count: 12,
  created_at: 1,
  updated_at: 1,
  last_scan_at: null,
  last_error: null,
};

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: routerPushMock }),
}));

vi.mock("@/composables/admin/useLibrariesQuery", () => ({
  useLibrariesQuery: () => ({
    data: { value: [mockLibrary] },
    isPending: { value: false },
    isError: { value: false },
    refetch: vi.fn(),
  }),
}));

vi.mock("@/composables/admin/useGalleryStatsQuery", () => ({
  useGalleryStatsQuery: () => ({
    data: { value: { library_count: 1, photos: 10, videos: 2, usage_bytes: 1024 } },
  }),
}));

vi.mock("@/composables/admin/useJobsQuery", () => ({
  useJobsQuery: () => ({
    data: { value: [] },
  }),
}));

vi.mock("@/composables/admin/useLibraryStatusBatchQuery", () => ({
  useLibraryStatusBatchQuery: () => ({
    statusByLibrary: { value: new Map() },
    contractError: { value: null },
  }),
}));

vi.mock("@/composables/admin/useLibraryMutations", () => ({
  useLibraryMutations: () => ({
    scanMutation: { isPending: { value: false }, mutate: scanMutateMock },
    scanAllMutation: { isPending: { value: false }, mutate: scanAllMutateMock },
    unregisterMutation: { isPending: { value: false }, mutateAsync: vi.fn() },
  }),
}));

vi.mock("@/composables/admin/useLibraryEvents", () => ({
  useLibraryEvents: vi.fn(),
}));

function mountSubject() {
  setActivePinia(createPinia());
  return mount(LibraryListPage, {
    global: {
      stubs: {
        Button: { template: "<button v-bind='$attrs'><slot /></button>" },
        Skeleton: { template: "<div data-testid='skeleton' />" },
        Table: { template: "<table><slot /></table>" },
        TableHeader: { template: "<thead><slot /></thead>" },
        TableBody: { template: "<tbody><slot /></tbody>" },
        TableRow: { template: "<tr><slot /></tr>" },
        TableHead: { template: "<th><slot /></th>" },
        TableCell: { template: "<td><slot /></td>" },
        LibraryActionMenu: {
          template: "<button type='button' @click=\"$emit('scan')\">Update library</button>",
        },
        LibraryStatusBadge: { template: "<span />" },
        LibrarySummaryPanel: { template: "<span>12 photos</span>" },
        LibraryCreateDialog: { template: "<div />" },
        LibraryEditDialog: { template: "<div />" },
        LibraryDeleteConfirmDialog: { template: "<div />" },
      },
    },
  });
}

describe("LibraryListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows Update vocabulary and no user-facing Scan or Rescan actions", () => {
    const wrapper = mountSubject();

    expect(wrapper.get("header").text()).toContain("Update all libraries");
    expect(wrapper.text()).toContain("Update library");
    expect(wrapper.findAll("button").some((button) => button.text().trim() === "Scan")).toBe(false);
    expect(wrapper.findAll("button").some((button) => button.text().trim() === "Scan all")).toBe(false);
    expect(wrapper.findAll("button").some((button) => button.text().trim() === "Rescan")).toBe(false);
  });

  it("keeps Update all libraries wired to the scan-all mutation", async () => {
    const wrapper = mountSubject();

    await wrapper.get("header").find("button").trigger("click");

    expect(scanAllMutateMock).toHaveBeenCalledOnce();
  });

  it("shows the library name as a clickable target", () => {
    const wrapper = mountSubject();

    const libraryButton = wrapper.findAll("button").find((button) => button.text().includes(mockLibrary.name));

    expect(libraryButton?.classes()).toContain("cursor-pointer");
  });

  it("shows total media files with a secondary photo/video breakdown", () => {
    const wrapper = mountSubject();

    expect(wrapper.text()).toContain("12");
    expect(wrapper.get('[aria-label="Media file breakdown"]').text()).toBe("10 photos · 2 videos");
  });
});
