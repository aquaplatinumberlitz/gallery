import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { UnifiedStatus } from "@/lib/catalog/status";
import LibrarySummaryPanel from "../LibrarySummaryPanel.vue";

function makeStatus(
  metadata: Partial<UnifiedStatus["metadata"]> = {},
  scan: Partial<UnifiedStatus["scan"]> = {},
): UnifiedStatus {
  return {
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
      ...scan,
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
      ...metadata,
    },
    issue_count: 0,
    issues: { availability: 0, scan: 0, metadata: 0 },
    latest_issue: null,
    last_scan_at: null,
    last_index_at: null,
  };
}

describe("LibrarySummaryPanel", () => {
  it("uses a plain complete label when all metadata is ready", () => {
    const wrapper = mount(LibrarySummaryPanel, { props: { status: makeStatus() } });

    expect(wrapper.text()).toContain("209 photos");
    expect(wrapper.text()).toContain("All metadata ready");
    expect(wrapper.text()).not.toContain("Metadata 209 / 209");
  });

  it("shows ready and total counts while metadata is incomplete", () => {
    const wrapper = mount(LibrarySummaryPanel, {
      props: { status: makeStatus({ ready_assets: 187, not_ready_assets: 22, progress_percent: 89.5 }) },
    });

    expect(wrapper.text()).toContain("187 / 209 metadata ready");
  });

  it("uses folder-scan wording during catalog updates", () => {
    const wrapper = mount(LibrarySummaryPanel, {
      props: {
        status: makeStatus(
          { total_assets: 0, ready_assets: 0, not_ready_assets: 0, progress_percent: null },
          { state: "scanning", operation: "scan", trigger: "manual", total_units: 1, completed_units: 0 },
        ),
      },
    });

    expect(wrapper.text()).toContain("Scanning 1 folder");
    expect(wrapper.text()).not.toContain("0 / 1");
    expect(wrapper.text()).not.toContain("No photos");
  });
});
