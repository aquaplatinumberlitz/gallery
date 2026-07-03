import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { UnifiedStatus } from "@/lib/catalog/status";
import LibraryProgressBar from "../LibraryProgressBar.vue";

type StatusOverrides = Omit<Partial<UnifiedStatus>, "scan" | "metadata"> & {
  scan?: Partial<UnifiedStatus["scan"]>;
  metadata?: Partial<UnifiedStatus["metadata"]>;
};

function makeStatus(overrides: StatusOverrides = {}): UnifiedStatus {
  const base: UnifiedStatus = {
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
      total_assets: 209,
      ready_assets: 209,
      not_ready_assets: 0,
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

  return {
    ...base,
    ...overrides,
    scan: { ...base.scan, ...overrides.scan },
    metadata: { ...base.metadata, ...overrides.metadata },
  };
}

describe("LibraryProgressBar", () => {
  it("uses folder-scan wording during catalog updates", () => {
    const wrapper = mount(LibraryProgressBar, {
      props: {
        status: makeStatus({
          scan: { state: "scanning", operation: "scan", trigger: "manual", total_units: 1, completed_units: 0 },
          metadata: { state: "queued", total_assets: 0, ready_assets: 0, progress_percent: null },
        }),
      },
    });

    expect(wrapper.text()).toContain("Scanning 1 folder");
    expect(wrapper.text()).not.toContain("0 / 1");
  });

  it("uses asset-count wording during metadata updates", () => {
    const wrapper = mount(LibraryProgressBar, {
      props: {
        status: makeStatus({
          metadata: {
            state: "indexing",
            total_assets: 209,
            ready_assets: 51,
            not_ready_assets: 158,
            progress_percent: 24.4,
          },
        }),
      },
    });

    expect(wrapper.text()).toContain("51 / 209 metadata ready");
    expect(wrapper.text()).toContain("24%");
  });

  it("uses the gallery success color for progress fill", () => {
    const wrapper = mount(LibraryProgressBar, {
      props: { status: makeStatus() },
    });

    expect(wrapper.findComponent({ name: "Progress" }).props("indicatorClass")).toContain("bg-success");
    expect(wrapper.findComponent({ name: "Progress" }).props("indicatorClass")).not.toContain("bg-primary");
  });

  it("uses the gallery warning color while progress is incomplete", () => {
    const wrapper = mount(LibraryProgressBar, {
      props: {
        status: makeStatus({
          metadata: {
            state: "indexing",
            total_assets: 209,
            ready_assets: 51,
            not_ready_assets: 158,
            progress_percent: 24.4,
          },
        }),
      },
    });

    expect(wrapper.findComponent({ name: "Progress" }).props("indicatorClass")).toContain("bg-warning");
    expect(wrapper.findComponent({ name: "Progress" }).props("indicatorClass")).not.toContain("bg-success");
  });

  it("uses the muted color for progress track", () => {
    const wrapper = mount(LibraryProgressBar, {
      props: { status: makeStatus() },
    });

    expect(wrapper.findComponent({ name: "Progress" }).props("class")).toContain("bg-muted");
  });
});
